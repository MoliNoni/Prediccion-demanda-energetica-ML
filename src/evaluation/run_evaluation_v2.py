import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.metrics import mae, rmse, smape, wape

V1_PREDICTIONS_PATH = Path("data/processed/model_predictions_h1.parquet")
V2_PREDICTIONS_PATH = Path("data/processed/model_predictions_h1_v2.parquet")
EVALUATION_OUTPUT_V2 = Path("data/processed/evaluation_results_h1_v2.json")
TARGET_COLUMN = "target_h1"
V1_PREDICTION_COLUMN = "HistGradientBoostingRegressor_prediction"
V2_PREDICTION_COLUMN = "HistGradientBoostingRegressor_v2_prediction"


def _metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    return {
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "smape": smape(actual, predicted),
        "wape": wape(actual, predicted),
    }


def _difference(v1: dict[str, float], v2: dict[str, float]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for metric, v1_value in v1.items():
        absolute = v2[metric] - v1_value
        relative = absolute / v1_value * 100 if v1_value else 0.0
        result[metric] = {"absolute_v2_minus_v1": absolute, "relative_percent": relative}
    return result


def compare_v1_v2(
    v1_predictions: pd.DataFrame,
    v2_predictions: pd.DataFrame,
) -> dict[str, Any]:
    required_v1 = {"target_date", TARGET_COLUMN, "split", V1_PREDICTION_COLUMN}
    required_v2 = {"target_date", TARGET_COLUMN, "split", V2_PREDICTION_COLUMN}
    if missing := required_v1.difference(v1_predictions.columns):
        raise ValueError(f"Missing v1 prediction columns: {sorted(missing)}")
    if missing := required_v2.difference(v2_predictions.columns):
        raise ValueError(f"Missing v2 prediction columns: {sorted(missing)}")
    results = []
    for split_name in ("validation", "test"):
        v1 = v1_predictions.loc[v1_predictions["split"] == split_name]
        v2 = v2_predictions.loc[v2_predictions["split"] == split_name]
        joined = v1.loc[:, ["target_date", TARGET_COLUMN, V1_PREDICTION_COLUMN]].merge(
            v2.loc[:, ["target_date", TARGET_COLUMN, V2_PREDICTION_COLUMN]],
            on=["target_date", TARGET_COLUMN],
            how="inner",
            validate="one_to_one",
        )
        if len(joined) != len(v1) or len(joined) != len(v2):
            raise ValueError(f"V1 and v2 predictions are not aligned for {split_name}")
        v1_metrics = _metrics(joined[TARGET_COLUMN], joined[V1_PREDICTION_COLUMN])
        v2_metrics = _metrics(joined[TARGET_COLUMN], joined[V2_PREDICTION_COLUMN])
        results.append(
            {
                "split": split_name,
                "records": len(joined),
                "v1_hgb": v1_metrics,
                "v2_hgb": v2_metrics,
                "difference": _difference(v1_metrics, v2_metrics),
            }
        )
    return {
        "purpose": "Controlled v1 versus v2 HGB comparison",
        "selection_rule": "v2 features were fixed before the single Phase 11 Test comparison",
        "test_used_for_selection": False,
        "results": results,
    }


def run_evaluation_v2(
    v1_predictions_path: Path = V1_PREDICTIONS_PATH,
    v2_predictions_path: Path = V2_PREDICTIONS_PATH,
    output_path: Path = EVALUATION_OUTPUT_V2,
) -> dict[str, Any]:
    if not v1_predictions_path.is_file() or not v2_predictions_path.is_file():
        raise FileNotFoundError("V1 and v2 prediction inputs are required")
    output = compare_v1_v2(
        pd.read_parquet(v1_predictions_path), pd.read_parquet(v2_predictions_path)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output
