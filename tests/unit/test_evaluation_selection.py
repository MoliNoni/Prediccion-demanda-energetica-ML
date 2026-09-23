import pandas as pd

from evaluation.run_evaluation import evaluate_predictions, select_by_validation


def result(model: str, mae: float, rmse: float, split: str = "validation") -> dict[str, object]:
    return {"model": model, "mae": mae, "rmse": rmse, "split": split}


def test_selection_uses_validation_mae_then_rmse() -> None:
    assert (
        select_by_validation(
            [
                result("baseline", 2, 3),
                result("RandomForestRegressor", 1, 4),
                result("HistGradientBoostingRegressor", 1, 2),
            ]
        )
        == "HistGradientBoostingRegressor"
    )


def test_test_results_do_not_change_selection() -> None:
    frame = pd.DataFrame(
        {
            "target_date": pd.to_datetime(["2020-01-01", "2022-01-01"]),
            "target_h1": [10.0, 10.0],
            "split": ["validation", "test"],
            "baseline_prediction": [9.0, 0.0],
            "RandomForestRegressor_prediction": [8.0, 100.0],
            "HistGradientBoostingRegressor_prediction": [7.0, 100.0],
        }
    )
    metadata, results = evaluate_predictions(frame)

    assert metadata["selected_model_by_validation"] == "baseline"
    assert metadata["test_used_for_selection"] is False
    assert [item["split"] for item in results] == ["validation", "validation", "validation", "test"]
