"""Evaluate the approved HGB configuration on pre-test temporal windows."""

import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.metrics import mae, rmse, smape, wape
from models.training import (
    DATE_COLUMN,
    INPUT_DATASET,
    PREDICTOR_COLUMNS,
    TARGET_COLUMN,
    build_baseline,
    build_selected_model,
)

OUTPUT_PATH = Path("data/processed/phase11_validation_sensitivity.json")
EARLIEST_VALIDATION_YEAR = 2016
LATEST_VALIDATION_YEAR = 2021


def metric_values(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    return {
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "smape": smape(actual, predicted),
        "wape": wape(actual, predicted),
    }


def evaluate_window(
    frame: pd.DataFrame,
    train_end_year: int,
    validation_year: int,
) -> dict[str, Any]:
    if validation_year > LATEST_VALIDATION_YEAR:
        raise ValueError("Phase 11 validation sensitivity must not use Test years")

    dates = pd.to_datetime(frame[DATE_COLUMN], errors="raise")
    train = frame.loc[dates.dt.year.between(2000, train_end_year)]
    validation = frame.loc[dates.dt.year.eq(validation_year)]
    if train.empty or validation.empty:
        raise ValueError("Temporal window must contain train and validation records")
    if train[DATE_COLUMN].max() >= validation[DATE_COLUMN].min():
        raise ValueError("Training records must precede validation records")

    model = build_selected_model()
    model.fit(train.loc[:, PREDICTOR_COLUMNS], train[TARGET_COLUMN])
    model_prediction = pd.Series(
        model.predict(validation.loc[:, PREDICTOR_COLUMNS]), index=validation.index
    )
    actual = validation[TARGET_COLUMN]
    return {
        "train_years": f"2000-{train_end_year}",
        "validation_year": validation_year,
        "train_records": len(train),
        "validation_records": len(validation),
        "HistGradientBoostingRegressor": metric_values(actual, model_prediction),
        "weekly_persistence_baseline": metric_values(actual, build_baseline(validation)),
    }


def run(
    input_path: Path = INPUT_DATASET,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    frame = pd.read_parquet(input_path).sort_values(DATE_COLUMN).reset_index(drop=True)
    current_validation = [
        evaluate_window(frame, train_end_year=2019, validation_year=year)
        for year in (2020, 2021)
    ]
    expanding = [
        evaluate_window(frame, train_end_year=year - 1, validation_year=year)
        for year in range(EARLIEST_VALIDATION_YEAR, LATEST_VALIDATION_YEAR + 1)
    ]
    result = {
        "purpose": "Pre-test validation sensitivity of the approved HGB configuration",
        "input_dataset": str(input_path),
        "test_years_used": [],
        "current_validation_window": current_validation,
        "expanding_yearly_windows": expanding,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    run()
    print(f"Output: {OUTPUT_PATH}")
