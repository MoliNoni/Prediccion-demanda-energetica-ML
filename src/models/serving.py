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

from models.training import INPUT_DATASET, PREDICTOR_COLUMNS, train_selected_model

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_NAME = "HistGradientBoostingRegressor"
MODEL_VERSION = "1.0.0"
MODEL_HORIZON = 1
DEFAULT_TRACKING_DIRECTORY = PROJECT_ROOT / "mlruns"
SERVING_METADATA_PATH = PROJECT_ROOT / "data/processed/serving_model_metadata.json"
SERVING_ARTIFACT_PATH = "model"


class ServingArtifactUnavailableError(RuntimeError):
    """Raised when the approved serving artifact cannot be loaded."""


def _feature_pipeline_hash() -> str:
    path = Path(__file__).resolve().parents[1] / "features" / "pipeline.py"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_serving_artifact(
    input_path: Path = INPUT_DATASET,
    metadata_path: Path = SERVING_METADATA_PATH,
    tracking_directory: Path = DEFAULT_TRACKING_DIRECTORY,
    experiment_name: str = "energy-demand-forecast",
) -> dict[str, Any]:
    """Train only the selected HGB model and log it using MLflow's sklearn flavor."""
    if not input_path.is_file():
        raise FileNotFoundError(f"Serving input not found: {input_path}")

    frame = pd.read_parquet(input_path)
    model, training_metadata = train_selected_model(frame)
    tracking_uri = tracking_directory.resolve().as_uri()
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name="phase-9-serving-hgb") as run:
        mlflow.sklearn.log_model(model, artifact_path=SERVING_ARTIFACT_PATH)
        metadata = {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "horizon": MODEL_HORIZON,
            "python_version": ".".join(str(part) for part in __import__("sys").version_info[:3]),
            "scikit_learn_version": sklearn.__version__,
            "mlflow_version": mlflow.__version__,
            "joblib_version": joblib.__version__,
            "predictor_columns": list(PREDICTOR_COLUMNS),
            "hyperparameters": training_metadata["model"],
            "run_id": run.info.run_id,
            "tracking_uri": tracking_uri,
            "model_uri": f"runs:/{run.info.run_id}/{SERVING_ARTIFACT_PATH}",
            "dataset": str(input_path),
            "feature_pipeline_sha256": _feature_pipeline_hash(),
        }
        mlflow.set_tags(
            {
                "model_name": MODEL_NAME,
                "model_version": MODEL_VERSION,
                "horizon": str(MODEL_HORIZON),
                "model_artifacts_available": "true",
                "predictor_columns": json.dumps(list(PREDICTOR_COLUMNS)),
            }
        )
        mlflow.log_dict(metadata, "serving_model_metadata.json")

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


class MlflowModelLoader:
    def __init__(self, metadata_path: Path = SERVING_METADATA_PATH) -> None:
        self.metadata_path = metadata_path
        self._model: Any | None = None
        self._metadata: dict[str, Any] | None = None

    def load(self) -> tuple[Any, dict[str, Any]]:
        if self._model is not None and self._metadata is not None:
            return self._model, self._metadata
        if not self.metadata_path.is_file():
            raise ServingArtifactUnavailableError("Serving model metadata is unavailable")
        try:
            metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            if metadata["model_name"] != MODEL_NAME or metadata["model_version"] != MODEL_VERSION:
                raise ServingArtifactUnavailableError(
                    "Serving model metadata does not match the approved model"
                )
            if metadata["predictor_columns"] != list(PREDICTOR_COLUMNS):
                raise ServingArtifactUnavailableError(
                    "Serving model predictor columns do not match the approved contract"
                )

            last_error: Exception | None = None
            for tracking_uri in _tracking_uri_candidates(metadata):
                try:
                    mlflow.set_tracking_uri(tracking_uri)
                    model = mlflow.sklearn.load_model(metadata["model_uri"])
                    metadata["tracking_uri"] = tracking_uri
                    break
                except (TypeError, ValueError, mlflow.exceptions.MlflowException) as error:
                    last_error = error
            else:
                raise ServingArtifactUnavailableError(
                    "Serving model artifact is unavailable"
                ) from last_error
        except ServingArtifactUnavailableError:
            raise
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            mlflow.exceptions.MlflowException,
        ) as error:
            raise ServingArtifactUnavailableError(
                "Serving model artifact is unavailable"
            ) from error
        self._model = model
        self._metadata = metadata
        return model, metadata
