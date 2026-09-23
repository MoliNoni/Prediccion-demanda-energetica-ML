"""Run the pre-test Phase 11 feature experiments for the approved HGB model."""

import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.metrics import mae, rmse, smape, wape
from ingestion.constants import TARGET_COLUMN as DEMAND_COLUMN
from models.training import (
    DATE_COLUMN,
    INPUT_DATASET,
    PREDICTOR_COLUMNS,
    TARGET_COLUMN,
    build_selected_model,
)

HISTORICAL_DEMAND_PATH = Path("data/interim/energy_demand_daily.parquet")
OUTPUT_PATH = Path("data/processed/phase11_feature_experiments.json")


def metric_values(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    return {
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "smape": smape(actual, predicted),
        "wape": wape(actual, predicted),
    }


def experimental_features(
    feature_frame: pd.DataFrame,
    historical_demand: pd.DataFrame,
) -> pd.DataFrame:
    source = historical_demand.loc[:, ["Fecha", DEMAND_COLUMN]].copy()
    source["Fecha"] = pd.to_datetime(source["Fecha"], errors="raise")
    demand = source.set_index("Fecha")[DEMAND_COLUMN].sort_index()
    result = feature_frame.copy()
    reference_dates = pd.to_datetime(result["reference_date"], errors="raise")
    result["demand_at_reference_date"] = reference_dates.map(demand)
    result["lag_2"] = (reference_dates - pd.Timedelta(2, unit="D")).map(demand)
    result["lag_3"] = (reference_dates - pd.Timedelta(3, unit="D")).map(demand)
    result["rolling_mean_3_including_reference"] = reference_dates.map(
        demand.rolling(3).mean()
    )
    result["rolling_std_3_including_reference"] = reference_dates.map(
        demand.rolling(3).std()
    )
    return result


def evaluate_candidate(
    frame: pd.DataFrame,
    candidate: str,
    added_features: tuple[str, ...],
    train_end_year: int = 2019,
    validation_years: tuple[int, ...] = (2020, 2021),
) -> dict[str, Any]:
    usable = frame.dropna(subset=list(added_features))
    usable_dates = pd.to_datetime(usable[DATE_COLUMN], errors="raise")
    train = usable.loc[usable_dates.dt.year.between(2000, train_end_year)]
    validation = usable.loc[usable_dates.dt.year.isin(validation_years)]
    if train.empty or validation.empty:
        raise ValueError("Feature candidate must have train and validation records")

    columns = (*PREDICTOR_COLUMNS, *added_features)
    model = build_selected_model()
    model.fit(train.loc[:, columns], train[TARGET_COLUMN])
    prediction = model.predict(validation.loc[:, columns])
    return {
        "candidate": candidate,
        "added_features": list(added_features),
        "train_years": f"2000-{train_end_year}",
        "validation_years": ", ".join(str(year) for year in validation_years),
        "test_years_used": [],
        "train_records": len(train),
        "validation_records": len(validation),
        "metrics": metric_values(validation[TARGET_COLUMN], pd.Series(prediction)),
    }


def run(
    input_path: Path = INPUT_DATASET,
    historical_demand_path: Path = HISTORICAL_DEMAND_PATH,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    base = pd.read_parquet(input_path).sort_values(DATE_COLUMN).reset_index(drop=True)
    historical = pd.read_parquet(historical_demand_path)
    frame = experimental_features(base, historical)
    candidates = (
        ("approved_features", ()),
        ("add_demand_at_reference_date", ("demand_at_reference_date",)),
        (
            "add_short_memory",
            (
                "demand_at_reference_date",
                "lag_2",
                "lag_3",
                "rolling_mean_3_including_reference",
                "rolling_std_3_including_reference",
            ),
        ),
    )
    results = [evaluate_candidate(frame, name, features) for name, features in candidates]
    stability_windows = []
    for year in range(2016, 2022):
        for name, features in (candidates[0], candidates[-1]):
            stability_windows.append(
                evaluate_candidate(
                    frame,
                    name,
                    features,
                    train_end_year=year - 1,
                    validation_years=(year,),
                )
            )
    output = {
        "purpose": "Pre-test, hypothesis-driven feature comparison for H+1",
        "input_dataset": str(input_path),
        "historical_demand_input": str(historical_demand_path),
        "leakage_control": (
            "Every added feature uses demand on or before reference_date; "
            "Test 2022-2023 is excluded."
        ),
        "results": results,
        "expanding_yearly_stability": stability_windows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    run()
    print(f"Output: {OUTPUT_PATH}")
