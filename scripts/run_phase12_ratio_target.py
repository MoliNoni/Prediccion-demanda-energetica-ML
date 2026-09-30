"""Phase 12: relative-target candidate, selected on Validation and evaluated once on Test."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from evaluation.metrics import mae, rmse, smape, wape
from ingestion.constants import INTERIM_OUTPUT
from ingestion.constants import TARGET_COLUMN as DEMAND_COLUMN
from models.ratio_target import (
    DATE_COLUMN,
    TARGET_COLUMN,
    TRAIN_YEARS,
    RatioConfig,
    RatioTargetModel,
    base_demand,
    bias_pct,
    daily_series,
    default_grid,
    prepare_frame,
    refit_on_train_and_validation,
    rows_in_years,
    select_on_validation,
)
from models.training_v2 import INPUT_DATASET_V2, PREDICTOR_COLUMNS_V2, train_v2_model
from powerbi.transform import colombian_holidays

PREDICTIONS_V2_PATH = Path("data/processed/model_predictions_h1_v2.parquet")
OUTPUT_PATH = Path("data/processed/phase12_ratio_target_results.json")
PREDICTIONS_OUTPUT = Path("data/processed/phase12_ratio_target_predictions.parquet")
CANDIDATE_DIRECTORY = Path("data/processed/candidates")
TEST_YEARS = (2022, 2023)
TEST_CALENDAR = (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31"))
REPRODUCTION_TOLERANCE_KWH = 1e-6
ACTUAL = "actual"
V1_METHOD = "v1_1_0_absolute"
CANDIDATE = "ratio_candidate"
CANDIDATE_REFIT = "ratio_candidate_refit_2000_2021"
NAIVE_WEEK = "naive_same_weekday_last_week"
NAIVE_DAY = "naive_previous_day"
METHODS = (V1_METHOD, CANDIDATE, CANDIDATE_REFIT, NAIVE_WEEK, NAIVE_DAY)


def metric_values(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    return {
        "records": int(len(actual)),
        "wape": wape(actual, predicted),
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "smape": smape(actual, predicted),
        "bias_pct": bias_pct(actual, predicted),
    }


def holiday_flags(dates: pd.Series) -> pd.Series:
    years = sorted(set(dates.dt.year))
    holidays = {day for year in years for day in colombian_holidays(year)}
    return dates.dt.date.isin(holidays)


def method_report(test: pd.DataFrame, method: str, training_max: float) -> dict[str, Any]:
    dates = test["date"]
    actual, predicted = test[ACTUAL], test[method]
    is_holiday = holiday_flags(dates)
    in_2023 = dates.dt.year == 2023
    monthly = {
        f"{month:02d}": wape(
            actual[in_2023 & (dates.dt.month == month)],
            predicted[in_2023 & (dates.dt.month == month)],
        )
        for month in range(1, 13)
    }
    return {
        "test_overall": metric_values(actual, predicted),
        "test_2022": metric_values(actual[dates.dt.year == 2022], predicted[dates.dt.year == 2022]),
        "test_2023": metric_values(actual[in_2023], predicted[in_2023]),
        "holiday": metric_values(actual[is_holiday], predicted[is_holiday]),
        "non_holiday": metric_values(actual[~is_holiday], predicted[~is_holiday]),
        "monthly_wape_2023": monthly,
        "max_predicted_2023": float(predicted[in_2023].max()),
        "max_actual_2023": float(actual[in_2023].max()),
        "days_predicted_above_training_max_2023": int((predicted[in_2023] > training_max).sum()),
    }


def check_test_calendar(
    daily: pd.Series, features: pd.DataFrame, evaluated: pd.DatetimeIndex
) -> dict[str, int]:
    """Check that every Test date with source demand was evaluated; return the counts.

    Dates genuinely absent from the source (missing or NaN demand) are the only ones that may
    be missing. Anything else means a feature or base-demand step silently removed a date.
    """
    calendar = pd.date_range(*TEST_CALENDAR, freq="D")
    present = daily.reindex(calendar).notna().to_numpy()
    expected = calendar[present]
    feature_dates = pd.DatetimeIndex(
        rows_in_years(
            features.assign(**{DATE_COLUMN: pd.to_datetime(features[DATE_COLUMN])}), TEST_YEARS
        )[DATE_COLUMN]
    )
    missing = expected.difference(evaluated)
    unexpected = evaluated.difference(expected)
    if len(missing) or len(unexpected):
        raise ValueError(
            f"Evaluated Test dates differ from the expected calendar: "
            f"{len(missing)} missing (first: {list(missing[:3])}), "
            f"{len(unexpected)} unexpected"
        )
    return {
        "calendar_days": len(calendar),
        "absent_from_source": int((~present).sum()),
        "expected_dates": len(expected),
        "feature_rows_in_test_years": len(feature_dates),
        "removed_by_prepare_frame": len(feature_dates.difference(evaluated)),
        "evaluated_dates": len(evaluated),
    }


def run(
    features_path: Path = INPUT_DATASET_V2,
    daily_path: Path = INTERIM_OUTPUT,
    v1_predictions_path: Path = PREDICTIONS_V2_PATH,
    output_path: Path = OUTPUT_PATH,
    predictions_path: Path = PREDICTIONS_OUTPUT,
    candidate_directory: Path = CANDIDATE_DIRECTORY,
    grid: Sequence[RatioConfig] | None = None,
) -> dict[str, Any]:
    features = pd.read_parquet(features_path)
    daily = daily_series(pd.read_parquet(daily_path), "Fecha", DEMAND_COLUMN)
    grid = list(grid) if grid is not None else default_grid()

    prepared: dict[int, pd.DataFrame] = {}
    dropped: dict[str, int] = {}
    for base_lag in sorted({config.base_lag for config in grid}):
        prepared[base_lag], count = prepare_frame(features, daily, base_lag)
        dropped[f"base_lag_{base_lag}"] = count

    # 1. Model selection on Validation only (fit on 2000-2019, score on 2020-2021).
    selected, scores = select_on_validation(prepared, grid)

    # 2. Locked Test evaluation. Primary: same training window as Phase 11 and v1.1.0.
    frame = prepared[selected.base_lag]
    train = rows_in_years(frame, TRAIN_YEARS)
    test_frame = rows_in_years(frame, TEST_YEARS)
    final_model = RatioTargetModel(selected).fit(train)
    # Secondary, pre-declared: refit on train + validation (no further selection).
    refit_model = refit_on_train_and_validation(frame, selected)

    # 3. Baselines on identical dates.
    v1 = pd.read_parquet(v1_predictions_path)
    v1 = v1.loc[v1["split"] == "test"].copy()
    v1["date"] = pd.to_datetime(v1[DATE_COLUMN])
    v1_official = v1.set_index("date")["HistGradientBoostingRegressor_v2_prediction"]

    dates = pd.DatetimeIndex(test_frame[DATE_COLUMN])
    test = pd.DataFrame(
        {
            "date": dates,
            ACTUAL: test_frame[TARGET_COLUMN].to_numpy(),
            V1_METHOD: v1_official.reindex(dates).to_numpy(),
            CANDIDATE: final_model.predict(test_frame),
            CANDIDATE_REFIT: refit_model.predict(test_frame),
            NAIVE_WEEK: base_demand(daily, dates, 7),
            NAIVE_DAY: base_demand(daily, dates, 1),
        }
    )
    dropped_test = int(test[[*METHODS]].isna().any(axis=1).sum())
    if dropped_test:
        raise ValueError(f"{dropped_test} Test dates lack a baseline or prediction")
    calendar_report = check_test_calendar(daily, features, dates)
    training_max = float(train[TARGET_COLUMN].max())

    # Reproduce v1.1.0 with the project's own pipeline as a cross-check of the stored file.
    v2_model, _ = train_v2_model(features)
    v2_test = rows_in_years(
        features.assign(**{DATE_COLUMN: pd.to_datetime(features[DATE_COLUMN])}), TEST_YEARS
    )
    reproduced = pd.Series(
        v2_model.predict(v2_test.loc[:, list(PREDICTOR_COLUMNS_V2)]),
        index=pd.DatetimeIndex(v2_test[DATE_COLUMN]),
    )
    reproduced_on_test = reproduced.reindex(dates).to_numpy()
    if np.isnan(reproduced_on_test).any():
        raise ValueError("The v1.1.0 reproduction lacks predictions for some Test dates")
    reproduction_max_abs_diff = float(np.abs(reproduced_on_test - test[V1_METHOD].to_numpy()).max())
    if not np.isfinite(reproduction_max_abs_diff) or (
        reproduction_max_abs_diff > REPRODUCTION_TOLERANCE_KWH
    ):
        raise ValueError(
            "v1.1.0 reproduction does not match the stored predictions: max abs diff "
            f"{reproduction_max_abs_diff} kWh (tolerance {REPRODUCTION_TOLERANCE_KWH})"
        )

    output = {
        "purpose": "Relative-target candidate versus v1.1.0 and naive baselines",
        "protocol": (
            "Grid selected on Validation 2020-2021 with models fitted on 2000-2019. The selected "
            "config was fitted on 2000-2019 (same window as the Phase 11 final test and v1.1.0, "
            "primary result) and, pre-declared and without further selection, on 2000-2021 "
            "(secondary result). Test 2022-2023 was evaluated once per fitted model. "
            "Demand is reconstructed as ratio_hat * demand_{t-k} with k known at forecast time."
        ),
        "test_used_for_selection": False,
        "units": "kWh",
        "periods": {
            "train": "2000-2019",
            "validation": "2020-2021",
            "test": "2022-2023",
        },
        "grid_size": len(grid),
        "grid_validation_scores": scores,
        "selected_config": selected.as_dict(),
        "rows_dropped_for_missing_base": {
            **dropped,
            "test_dates_without_baseline_or_prediction": dropped_test,
        },
        "test_calendar": calendar_report,
        "training_max_actual": training_max,
        "v1_1_0_reproduction_max_abs_diff_vs_stored": reproduction_max_abs_diff,
        "baseline_notes": {
            V1_METHOD: "stored test predictions of v1.1.0 (trained 2000-2019)",
            NAIVE_WEEK: "demand at t-7",
            NAIVE_DAY: "demand at t-1",
        },
        "test": {method: method_report(test, method, training_max) for method in METHODS},
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, allow_nan=False), encoding="utf-8")
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    test.to_parquet(predictions_path, index=False)
    candidate_directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, candidate_directory / "ratio_target_candidate.joblib")
    joblib.dump(refit_model, candidate_directory / "ratio_target_candidate_refit.joblib")
    return output


if __name__ == "__main__":
    result = run()
    print(f"Selected: {RatioConfig(**result['selected_config'])}")
    print(f"Output: {OUTPUT_PATH}")
