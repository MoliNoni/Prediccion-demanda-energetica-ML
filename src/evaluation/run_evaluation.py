import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.metrics import mae, rmse, smape, wape

PREDICTIONS_INPUT = Path("data/processed/model_predictions_h1.parquet")
EVALUATION_OUTPUT = Path("data/processed/evaluation_results_h1.json")
TARGET_COLUMN = "target_h1"
PREDICTION_COLUMNS = {
    "baseline": "baseline_prediction",
    "RandomForestRegressor": "RandomForestRegressor_prediction",
    "HistGradientBoostingRegressor": "HistGradientBoostingRegressor_prediction",
}


def _metric_row(frame: pd.DataFrame, model: str, split: str) -> dict[str, Any]:
    actual = frame[TARGET_COLUMN].to_numpy()
    predicted = frame[PREDICTION_COLUMNS[model]].to_numpy()
    return {
        "model": model,
        "split": split,
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "smape": smape(actual, predicted),
        "wape": wape(actual, predicted),
        "records": len(frame),
    }


def select_by_validation(results: list[dict[str, Any]]) -> str:
    candidates = [result for result in results if result["split"] == "validation"]
    ordered = sorted(candidates, key=lambda result: (result["mae"], result["rmse"]))
    best = ordered[0]
    tied = [
        result
        for result in ordered
        if result["mae"] == best["mae"] and result["rmse"] == best["rmse"]
    ]
    if len(tied) > 1:
        raise ValueError("Validation selection remains tied after MAE and RMSE")
    return best["model"]


def evaluate_predictions(
    frame: pd.DataFrame,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    required = {"target_date", TARGET_COLUMN, "split", *PREDICTION_COLUMNS.values()}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Missing evaluation columns: {missing}")
    if set(frame["split"]) != {"validation", "test"}:
        raise ValueError("Predictions must contain exactly validation and test splits")

    validation = frame.loc[frame["split"] == "validation"]
    test = frame.loc[frame["split"] == "test"]
    validation_results = [
        _metric_row(validation, model, "validation") for model in PREDICTION_COLUMNS
    ]
    selected_model = select_by_validation(validation_results)
    test_result = _metric_row(test, selected_model, "test")
    metadata = {
        "input_predictions": str(PREDICTIONS_INPUT),
        "target": TARGET_COLUMN,
        "selection_metric": "MAE",
        "tie_break_metric": "RMSE",
        "complementary_metrics": ["sMAPE", "WAPE"],
        "selected_model_by_validation": selected_model,
        "test_used_for_selection": False,
        "results": validation_results + [test_result],
    }
    return metadata, validation_results + [test_result]


def run_evaluation(
    input_path: Path = PREDICTIONS_INPUT,
    output_path: Path = EVALUATION_OUTPUT,
) -> dict[str, Any]:
    if not input_path.is_file():
        raise FileNotFoundError(f"Evaluation input not found: {input_path}")
    frame = pd.read_parquet(input_path)
    metadata, _ = evaluate_predictions(frame)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata
