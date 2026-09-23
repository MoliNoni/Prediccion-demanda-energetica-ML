import json

import mlflow

from tracking.mlflow_tracking import track_existing_results

Metrics = tuple[float, float, float, float]


def modeling_metadata() -> dict[str, object]:
    return {
        "input_dataset": "data/processed/energy_demand_features_h1.parquet",
        "horizon": "H+1",
        "target": "target_h1",
        "train_years": "2000-2019",
        "validation_years": "2020-2021",
        "test_years": "2022-2023",
        "train_records": 7246,
        "validation_records": 731,
        "test_records": 730,
        "predictor_columns": ["lag_1", "lag_7"],
        "models": {
            "RandomForestRegressor": {"n_estimators": 200, "random_state": 42},
            "HistGradientBoostingRegressor": {"max_iter": 200, "random_state": 42},
        },
    }


def metric_result(model: str, split: str, values: Metrics) -> dict[str, object]:
    mae, rmse, smape, wape = values
    return {"model": model, "split": split, "mae": mae, "rmse": rmse, "smape": smape, "wape": wape}


def evaluation_results() -> dict[str, object]:
    return {
        "input_predictions": "data/processed/model_predictions_h1.parquet",
        "selection_metric": "MAE",
        "tie_break_metric": "RMSE",
        "selected_model_by_validation": "HistGradientBoostingRegressor",
        "test_used_for_selection": False,
        "results": [
            metric_result("baseline", "validation", (3.0, 4.0, 5.0, 6.0)),
            metric_result("RandomForestRegressor", "validation", (2.0, 3.0, 4.0, 5.0)),
            metric_result("HistGradientBoostingRegressor", "validation", (1.0, 2.0, 3.0, 4.0)),
            metric_result("HistGradientBoostingRegressor", "test", (7.0, 8.0, 9.0, 10.0)),
        ],
    }


def write_tracking_inputs(tmp_path):
    modeling_path = tmp_path / "modeling.json"
    evaluation_path = tmp_path / "evaluation.json"
    modeling_path.write_text(json.dumps(modeling_metadata()), encoding="utf-8")
    evaluation_path.write_text(json.dumps(evaluation_results()), encoding="utf-8")
    return modeling_path, evaluation_path


def test_tracks_existing_results_and_artifacts(tmp_path) -> None:
    modeling_path, evaluation_path = write_tracking_inputs(tmp_path)
    tracking_directory = tmp_path / "mlruns"

    run_id = track_existing_results(modeling_path, evaluation_path, tracking_directory)

    client = mlflow.tracking.MlflowClient(tracking_directory.resolve().as_uri())
    run = client.get_run(run_id)
    assert run.data.tags["selected_model"] == "HistGradientBoostingRegressor"
    assert run.data.tags["selection.primary_metric"] == "MAE"
    assert run.data.tags["selection.split"] == "validation"
    assert run.data.tags["selection.test_used"] == "false"
    assert run.data.params["seed"] == "42"
    assert run.data.metrics["validation.baseline.mae"] == 3.0
    assert run.data.metrics["validation.RandomForestRegressor.rmse"] == 3.0
    assert run.data.metrics["test.HistGradientBoostingRegressor.wape"] == 10.0
    artifact_paths = {item.path for item in client.list_artifacts(run_id)}
    assert artifact_paths == {"evaluation.json", "modeling.json"}


def test_tracking_is_reproducible_with_same_inputs(tmp_path) -> None:
    modeling_path, evaluation_path = write_tracking_inputs(tmp_path)
    tracking_directory = tmp_path / "mlruns"

    first_run_id = track_existing_results(modeling_path, evaluation_path, tracking_directory)
    second_run_id = track_existing_results(modeling_path, evaluation_path, tracking_directory)

    client = mlflow.tracking.MlflowClient(tracking_directory.resolve().as_uri())
    assert client.get_run(first_run_id).data.params == client.get_run(second_run_id).data.params
    assert client.get_run(first_run_id).data.metrics == client.get_run(second_run_id).data.metrics


