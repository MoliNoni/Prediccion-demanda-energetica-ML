import hashlib
import json
import os
from pathlib import Path
from typing import Any

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
import sklearn

from features.contracts import FEATURE_CONTRACT_V2
from features.pipeline import FeaturePreparationError, build_online_features_v2
from models.training_v2 import INPUT_DATASET_V2, train_v2_model

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_NAME_V2 = "HistGradientBoostingRegressor"
MODEL_VERSION_V2 = "1.1.0"
MODEL_HORIZON_V2 = 1
DEFAULT_TRACKING_DIRECTORY = PROJECT_ROOT / "mlruns"
SERVING_METADATA_PATH_V2 = PROJECT_ROOT / "data/processed/serving_model_v2_metadata.json"
SERVING_ARTIFACT_PATH_V2 = "model"


class CandidateServingArtifactUnavailableError(RuntimeError):
    """Raised when the non-active v2 candidate artifact cannot be loaded."""


def _pipeline_hash() -> str:
    path = Path(__file__).resolve().parents[1] / "features" / "pipeline.py"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contract_hash() -> str:
    path = Path(__file__).resolve().parents[1] / "features" / "contracts.py"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_candidate_serving_artifact_v2(
    input_path: Path = INPUT_DATASET_V2,
    metadata_path: Path = SERVING_METADATA_PATH_V2,
    tracking_directory: Path = DEFAULT_TRACKING_DIRECTORY,
    experiment_name: str = "energy-demand-forecast",
    evaluation_path: Path = Path("data/processed/evaluation_results_h1_v2.json"),
) -> dict[str, Any]:
    """Log the v2 candidate without registering or activating it for serving."""
    if not input_path.is_file() or not evaluation_path.is_file():
        raise FileNotFoundError("V2 dataset and evaluation results are required")
    dataset = pd.read_parquet(input_path)
    model, training = train_v2_model(dataset)
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    tracking_uri = tracking_directory.resolve().as_uri()
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name="phase-10-candidate-hgb-v2") as run:
        mlflow.sklearn.log_model(
            model,
            artifact_path=SERVING_ARTIFACT_PATH_V2,
            input_example=dataset.loc[:, list(FEATURE_CONTRACT_V2.predictor_columns)].head(1),
        )
        metadata = {
            "model_name": MODEL_NAME_V2,
            "model_version": MODEL_VERSION_V2,
            "horizon": MODEL_HORIZON_V2,
            "candidate": True,
            "promotion_status": "not_promoted",
            "feature_set_name": FEATURE_CONTRACT_V2.name,
            "feature_set_version": FEATURE_CONTRACT_V2.version,
            "predictor_columns": list(FEATURE_CONTRACT_V2.predictor_columns),
            "python_version": ".".join(str(part) for part in __import__("sys").version_info[:3]),
            "scikit_learn_version": sklearn.__version__,
            "mlflow_version": mlflow.__version__,
            "joblib_version": joblib.__version__,
            "hyperparameters": training["model"],
            "dataset": str(input_path),
            "periods": {
                "train": "2000-2019",
                "validation": "2020-2021",
                "test": "2022-2023",
            },
            "evaluation": evaluation,
            "feature_pipeline_sha256": _pipeline_hash(),
            "feature_contract_sha256": _contract_hash(),
            "run_id": run.info.run_id,
            "tracking_uri": tracking_uri,
            "model_uri": f"runs:/{run.info.run_id}/{SERVING_ARTIFACT_PATH_V2}",
        }
        mlflow.set_tags(
            {
                "model_name": MODEL_NAME_V2,
                "model_version": MODEL_VERSION_V2,
                "horizon": str(MODEL_HORIZON_V2),
                "feature_set_version": FEATURE_CONTRACT_V2.version,
                "candidate": "true",
                "promotion_status": "not_promoted",
            }
        )
        mlflow.log_params(
            {"features": json.dumps(metadata["predictor_columns"]), **training["model"]}
        )
        for result in evaluation["results"]:
            for version in ("v1_hgb", "v2_hgb"):
                for metric, value in result[version].items():
                    mlflow.log_metric(f"{result['split']}.{version}.{metric}", value)
        mlflow.log_dict(metadata, "serving_model_v2_metadata.json")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def _tracking_uri_candidates(metadata: dict[str, Any] | None = None) -> list[str]:
    candidates: list[str] = []
    runtime_values = []
    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if mlflow_tracking_uri:
        runtime_values.append(mlflow_tracking_uri.strip())

    local_tracking_uri = DEFAULT_TRACKING_DIRECTORY.resolve().as_uri()
    if local_tracking_uri not in runtime_values:
        runtime_values.append(local_tracking_uri)

    metadata_tracking_uri = metadata.get("tracking_uri") if metadata else None
    if metadata_tracking_uri and not (
        mlflow_tracking_uri or str(DEFAULT_TRACKING_DIRECTORY.resolve())
    ):
        runtime_values.append(metadata_tracking_uri.strip())
    elif metadata_tracking_uri and not (
        metadata_tracking_uri.startswith("file:///C:/")
        or metadata_tracking_uri.startswith("file:///c:/")
    ):
        runtime_values.append(metadata_tracking_uri.strip())

    for value in runtime_values:
        if value and value not in candidates:
            candidates.append(value)
    return candidates


class CandidateMlflowModelLoaderV2:
    """Loads only the candidate v2 artifact; it does not query active models."""

    def __init__(self, metadata_path: Path = SERVING_METADATA_PATH_V2) -> None:
        self.metadata_path = metadata_path

    def load(self) -> tuple[Any, dict[str, Any]]:
        try:
            metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            if (
                metadata["model_name"] != MODEL_NAME_V2
                or metadata["model_version"] != MODEL_VERSION_V2
                or metadata["feature_set_version"] != FEATURE_CONTRACT_V2.version
                or metadata["predictor_columns"] != list(FEATURE_CONTRACT_V2.predictor_columns)
                or not metadata["candidate"]
                or metadata["promotion_status"] != "not_promoted"
            ):
                raise CandidateServingArtifactUnavailableError("V2 serving metadata is invalid")

            last_error: Exception | None = None
            for tracking_uri in _tracking_uri_candidates(metadata):
                try:
                    mlflow.set_tracking_uri(tracking_uri)
                    model = mlflow.sklearn.load_model(metadata["model_uri"])
                    metadata["tracking_uri"] = tracking_uri
                    return model, metadata
                except (
                    OSError,
                    TypeError,
                    ValueError,
                    mlflow.exceptions.MlflowException,
                ) as error:
                    last_error = error
            raise CandidateServingArtifactUnavailableError(
                "V2 serving artifact is unavailable"
            ) from last_error
        except CandidateServingArtifactUnavailableError:
            raise
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            mlflow.exceptions.MlflowException,
        ) as error:
            raise CandidateServingArtifactUnavailableError(
                "V2 serving artifact is unavailable"
            ) from error


def predict_candidate_v2(
    historical_demand: pd.DataFrame,
    target_date: pd.Timestamp | str,
    loader: CandidateMlflowModelLoaderV2 | None = None,
) -> float:
    """Predict with v2 only when explicitly invoked outside the active API path."""
    model, metadata = (loader or CandidateMlflowModelLoaderV2()).load()
    try:
        features = build_online_features_v2(historical_demand, target_date)
    except FeaturePreparationError as error:
        raise CandidateServingArtifactUnavailableError(
            "V2 historical demand is insufficient for online features"
        ) from error
    return float(model.predict(features.loc[:, metadata["predictor_columns"]])[0])
