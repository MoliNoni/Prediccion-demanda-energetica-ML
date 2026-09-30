"""Serving integration for model v1.2.0: the ratio-target candidate refit on 2000-2021.

The fitted artifact is the plain scikit-learn estimator, so loading never depends on pickled
project classes. The serving wrapper (``RatioTargetModel``) rebuilds the scale-free features
with the same functions used offline and returns demand in kWh (``ratio * demand_{t-7}``).
"""

import json
from pathlib import Path
from typing import Any

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import sklearn

from features.contracts import FEATURE_CONTRACT_V2
from features.pipeline import FeaturePreparationError, build_online_features_v2
from ingestion.constants import INTERIM_OUTPUT
from ingestion.constants import TARGET_COLUMN as DEMAND_COLUMN
from models.ratio_target import (
    BASE_COLUMN,
    HYPERPARAMETER_SETS,
    RANDOM_STATE,
    TRAIN_YEARS,
    VALIDATION_YEARS,
    RatioConfig,
    RatioTargetModel,
    base_demand,
    build_matrix,
    daily_series,
    feature_columns,
    prepare_frame,
    refit_on_train_and_validation,
    rows_in_years,
)
from models.serving_v2 import (
    DEFAULT_TRACKING_DIRECTORY,
    MODEL_NAME_V2,
    CandidateServingArtifactUnavailableError,
    _contract_hash,
    _pipeline_hash,
    _tracking_uri_candidates,
)
from models.training_v2 import INPUT_DATASET_V2

# Same name as v1.0.0 and v1.1.0 (the family of the estimator); the version tells them apart.
MODEL_NAME_RATIO = MODEL_NAME_V2
MODEL_VERSION_RATIO = "1.2.0"
MODEL_HORIZON_RATIO = 1
FEATURE_SET_VERSION_RATIO = "v2-ratio7"
SERVING_CONFIG = RatioConfig(7, "ratio", "relative_plus_levels", "v1_1_0")
PREDICTOR_COLUMNS_RATIO = [*FEATURE_CONTRACT_V2.predictor_columns, BASE_COLUMN]
SERVING_METADATA_PATH_RATIO = (
    Path(__file__).resolve().parents[2] / "data/processed/serving_model_v1_2_metadata.json"
)
SERVING_ARTIFACT_PATH_RATIO = "model"
SERVING_TRAIN_YEARS = (TRAIN_YEARS[0], VALIDATION_YEARS[1])
RESULTS_PATH = Path("data/processed/phase12_ratio_target_results.json")
PREDICTIONS_PATH = Path("data/processed/phase12_ratio_target_predictions.parquet")
REFIT_PREDICTION_COLUMN = "ratio_candidate_refit_2000_2021"
REFIT_MATCH_ABS_TOLERANCE_KWH = 1.0  # kWh; demand is ~2e8, so this is ~5e-9 relative
TEST_YEARS = (2022, 2023)


def build_online_features_ratio(
    frame: pd.DataFrame, target_date: pd.Timestamp | str
) -> pd.DataFrame:
    """Build the v2 online row for ``target_date`` plus ``demand_{t-7}`` as ``base_demand``."""
    row = build_online_features_v2(frame, target_date)
    try:
        daily = daily_series(frame, "Fecha", DEMAND_COLUMN)
    except ValueError as error:
        raise FeaturePreparationError(str(error)) from error
    base = float(base_demand(daily, [row["target_date"].iloc[0]], SERVING_CONFIG.base_lag)[0])
    if not np.isfinite(base) or base <= 0:
        raise FeaturePreparationError("Base demand (t-7) is missing or not positive")
    row[BASE_COLUMN] = base
    return row.loc[:, ["reference_date", "target_date", *PREDICTOR_COLUMNS_RATIO]]


def fit_serving_model(features: pd.DataFrame, daily: pd.Series) -> tuple[RatioTargetModel, Any]:
    """Refit the selected config on 2000-2021 with the Phase 12 code path."""
    prepared, _ = prepare_frame(features, daily, SERVING_CONFIG.base_lag)
    return refit_on_train_and_validation(prepared, SERVING_CONFIG), prepared


def verify_against_phase12(
    model: RatioTargetModel, prepared: pd.DataFrame, predictions_path: Path
) -> float:
    """Return the max abs diff vs the Phase 12 refit Test predictions; raise if it is large."""
    test_frame = rows_in_years(prepared, TEST_YEARS)
    stored = pd.read_parquet(predictions_path).set_index("date")[REFIT_PREDICTION_COLUMN]
    dates = pd.DatetimeIndex(test_frame["target_date"])
    expected = stored.reindex(dates).to_numpy(dtype=float)
    difference = np.abs(model.predict(test_frame) - expected)
    max_difference = float(difference.max()) if len(difference) else float("nan")
    if not np.isfinite(max_difference) or max_difference > REFIT_MATCH_ABS_TOLERANCE_KWH:
        raise ValueError(
            "Refit does not reproduce the Phase 12 refit predictions "
            f"(max abs diff {max_difference})"
        )
    return max_difference


def create_serving_artifact_v1_2(
    features_path: Path = INPUT_DATASET_V2,
    daily_path: Path = INTERIM_OUTPUT,
    results_path: Path = RESULTS_PATH,
    predictions_path: Path = PREDICTIONS_PATH,
    metadata_path: Path = SERVING_METADATA_PATH_RATIO,
    tracking_directory: Path = DEFAULT_TRACKING_DIRECTORY,
    experiment_name: str = "energy-demand-forecast",
) -> dict[str, Any]:
    """Refit, log and describe v1.2.0 without registering or activating it."""
    for path in (features_path, daily_path, results_path, predictions_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required input not found: {path}")
    results = json.loads(results_path.read_text(encoding="utf-8"))
    if results["selected_config"] != SERVING_CONFIG.as_dict():
        raise ValueError("Phase 12 selected a different config than the serving config")

    features = pd.read_parquet(features_path)
    daily = daily_series(pd.read_parquet(daily_path), "Fecha", DEMAND_COLUMN)
    model, prepared = fit_serving_model(features, daily)
    max_difference = verify_against_phase12(model, prepared, predictions_path)
    training = rows_in_years(prepared, SERVING_TRAIN_YEARS)
    matrix = build_matrix(training, SERVING_CONFIG.feature_mode)

    tracking_uri = tracking_directory.resolve().as_uri()
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name="phase-12-ratio-target-v1-2-0") as run:
        mlflow.sklearn.log_model(
            model.estimator,
            artifact_path=SERVING_ARTIFACT_PATH_RATIO,
            input_example=matrix.head(1),
        )
        metadata = {
            "model_name": MODEL_NAME_RATIO,
            "model_version": MODEL_VERSION_RATIO,
            "horizon": MODEL_HORIZON_RATIO,
            "feature_set_name": FEATURE_CONTRACT_V2.name,
            "feature_set_version": FEATURE_SET_VERSION_RATIO,
            "target": "ratio demand_t / demand_{t-7}; served value is ratio * demand_{t-7} (kWh)",
            "ratio_config": SERVING_CONFIG.as_dict(),
            "predictor_columns": PREDICTOR_COLUMNS_RATIO,
            "estimator_columns": list(feature_columns(SERVING_CONFIG.feature_mode)),
            "python_version": ".".join(str(part) for part in __import__("sys").version_info[:3]),
            "scikit_learn_version": sklearn.__version__,
            "mlflow_version": mlflow.__version__,
            "joblib_version": joblib.__version__,
            "hyperparameters": {
                **HYPERPARAMETER_SETS[SERVING_CONFIG.hyperparameters],
                "random_state": RANDOM_STATE,
            },
            "dataset": str(features_path),
            "periods": {
                "train": "2000-2021",
                "evaluation_train": "2000-2019",
                "evaluation_validation": "2020-2021",
                "evaluation_test": "2022-2023",
            },
            "training_records": len(training),
            "training_max_actual": float(training["target_h1"].max()),
            "phase12_test_metrics": {
                "fit_2000_2019": results["test"]["ratio_candidate"]["test_overall"],
                "refit_2000_2021": results["test"][REFIT_PREDICTION_COLUMN]["test_overall"],
                "v1_1_0_absolute": results["test"]["v1_1_0_absolute"]["test_overall"],
            },
            "refit_vs_phase12_max_abs_diff_kwh": max_difference,
            "phase12_results": str(results_path),
            "feature_pipeline_sha256": _pipeline_hash(),
            "feature_contract_sha256": _contract_hash(),
            "run_id": run.info.run_id,
            "tracking_uri": tracking_uri,
            "model_uri": f"runs:/{run.info.run_id}/{SERVING_ARTIFACT_PATH_RATIO}",
        }
        mlflow.set_tags(
            {
                "model_name": MODEL_NAME_RATIO,
                "model_version": MODEL_VERSION_RATIO,
                "horizon": str(MODEL_HORIZON_RATIO),
                "feature_set_version": FEATURE_SET_VERSION_RATIO,
            }
        )
        mlflow.log_params(
            {**SERVING_CONFIG.as_dict(), **HYPERPARAMETER_SETS[SERVING_CONFIG.hyperparameters]}
        )
        for name, metrics in metadata["phase12_test_metrics"].items():
            for metric, value in metrics.items():
                mlflow.log_metric(f"test.{name}.{metric}", value)
        mlflow.log_dict(metadata, "serving_model_v1_2_metadata.json")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8")
    return metadata


class RatioMlflowModelLoader:
    """Loads the v1.2.0 estimator and wraps it so ``predict`` returns demand in kWh."""

    def __init__(self, metadata_path: Path = SERVING_METADATA_PATH_RATIO) -> None:
        self.metadata_path = metadata_path

    def load(self) -> tuple[RatioTargetModel, dict[str, Any]]:
        try:
            metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            if (
                metadata["model_name"] != MODEL_NAME_RATIO
                or metadata["model_version"] != MODEL_VERSION_RATIO
                or metadata["horizon"] != MODEL_HORIZON_RATIO
                or metadata["feature_set_version"] != FEATURE_SET_VERSION_RATIO
                or metadata["predictor_columns"] != PREDICTOR_COLUMNS_RATIO
                or metadata["ratio_config"] != SERVING_CONFIG.as_dict()
            ):
                raise CandidateServingArtifactUnavailableError("V1.2 serving metadata is invalid")

            last_error: Exception | None = None
            for tracking_uri in _tracking_uri_candidates(metadata):
                try:
                    mlflow.set_tracking_uri(tracking_uri)
                    estimator = mlflow.sklearn.load_model(metadata["model_uri"])
                    metadata["tracking_uri"] = tracking_uri
                    return RatioTargetModel.from_estimator(SERVING_CONFIG, estimator), metadata
                except (TypeError, ValueError, mlflow.exceptions.MlflowException) as error:
                    last_error = error
            raise CandidateServingArtifactUnavailableError(
                "V1.2 serving artifact is unavailable"
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
                "V1.2 serving artifact is unavailable"
            ) from error
