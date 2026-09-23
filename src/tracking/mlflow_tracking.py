import json
from pathlib import Path
from typing import Any

import mlflow

DEFAULT_EXPERIMENT_NAME = "energy-demand-forecast"
DEFAULT_RUN_NAME = "phase-5-existing-results"
DEFAULT_TRACKING_DIRECTORY = Path("mlruns")
MODELING_METADATA_PATH = Path("data/processed/modeling_run_metadata.json")
EVALUATION_RESULTS_PATH = Path("data/processed/evaluation_results_h1.json")
PROJECT_VERSION = "0.1.0"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"MLflow input not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _validation_results(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    results = [result for result in evaluation["results"] if result["split"] == "validation"]
    expected_models = {
        "baseline",
        "RandomForestRegressor",
        "HistGradientBoostingRegressor",
    }
    if {result["model"] for result in results} != expected_models:
        raise ValueError("Evaluation results must contain Validation metrics for all candidates")
    return results


def _test_result(evaluation: dict[str, Any], selected_model: str) -> dict[str, Any]:
    results = [
        result
        for result in evaluation["results"]
        if result["split"] == "test" and result["model"] == selected_model
    ]
    if len(results) != 1:
        raise ValueError("Evaluation results must contain one Test result for the selected model")
    return results[0]


def _string_value(value: object) -> str:
    return json.dumps(value, sort_keys=True) if value is None else str(value)


def _log_candidate_params(modeling: dict[str, Any]) -> None:
    mlflow.log_param("candidate.baseline.strategy", "weekly_persistence_lag_7")
    for model_name, params in modeling["models"].items():
        for parameter, value in params.items():
            mlflow.log_param(f"candidate.{model_name}.{parameter}", _string_value(value))


def _log_metrics(results: list[dict[str, Any]], prefix: str) -> None:
    for result in results:
        model = result["model"]
        for metric in ("mae", "rmse", "smape", "wape"):
            mlflow.log_metric(f"{prefix}.{model}.{metric}", result[metric])


def track_existing_results(
    modeling_metadata_path: Path = MODELING_METADATA_PATH,
    evaluation_results_path: Path = EVALUATION_RESULTS_PATH,
    tracking_directory: Path = DEFAULT_TRACKING_DIRECTORY,
    experiment_name: str = DEFAULT_EXPERIMENT_NAME,
    run_name: str = DEFAULT_RUN_NAME,
) -> str:
    """Track approved modeling and evaluation outputs without retraining models."""
    modeling = _load_json(modeling_metadata_path)
    evaluation = _load_json(evaluation_results_path)
    selected_model = evaluation["selected_model_by_validation"]
    validation_results = _validation_results(evaluation)
    test_result = _test_result(evaluation, selected_model)

    tracking_uri = tracking_directory.resolve().as_uri()
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags(
            {
                "project.version": PROJECT_VERSION,
                "horizon": modeling["horizon"],
                "selection.primary_metric": evaluation["selection_metric"],
                "selection.criterion": "lowest_mae",
                "selection.tie_break_metric": evaluation["tie_break_metric"],
                "selection.split": "validation",
                "selection.test_used": str(evaluation["test_used_for_selection"]).lower(),
                "selected_model": selected_model,
                "model_artifacts_available": "false",
            }
        )
        mlflow.log_params(
            {
                "dataset.features_path": modeling["input_dataset"],
                "dataset.predictions_path": evaluation["input_predictions"],
                "dataset.target": modeling["target"],
                "dataset.train_period": modeling["train_years"],
                "dataset.validation_period": modeling["validation_years"],
                "dataset.test_period": modeling["test_years"],
                "dataset.train_records": modeling["train_records"],
                "dataset.validation_records": modeling["validation_records"],
                "dataset.test_records": modeling["test_records"],
                "seed": 42,
                "features": json.dumps(modeling["predictor_columns"]),
            }
        )
        _log_candidate_params(modeling)
        _log_metrics(validation_results, "validation")
        _log_metrics([test_result], "test")
        mlflow.log_artifact(evaluation_results_path)
        mlflow.log_artifact(modeling_metadata_path)
        return run.info.run_id
