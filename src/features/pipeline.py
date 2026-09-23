from pathlib import Path

import numpy as np
import pandas as pd

from features.contracts import (
    FEATURE_CONTRACT_V1,
    FEATURE_CONTRACT_V2,
    FeatureContract,
)
from ingestion.constants import EXPECTED_COLUMNS, TARGET_COLUMN

FEATURE_OUTPUT = Path("data/processed/energy_demand_features_h1.parquet")
FEATURE_OUTPUT_V2 = Path("data/processed/energy_demand_features_h1_v2.parquet")
FEATURE_COLUMNS = FEATURE_CONTRACT_V1.feature_columns
FEATURE_COLUMNS_V2 = FEATURE_CONTRACT_V2.feature_columns


class FeaturePreparationError(ValueError):
    """Raised when the Phase 2 input does not meet its required contract."""


def _validate_input(frame: pd.DataFrame) -> None:
    missing = [column for column in EXPECTED_COLUMNS if column not in frame.columns]
    if missing:
        raise FeaturePreparationError(f"Missing input columns: {missing}")
    if frame["Fecha"].isna().any():
        raise FeaturePreparationError("Input contains null dates")
    if frame["Fecha"].duplicated().any():
        raise FeaturePreparationError("Input contains duplicate dates")
    if pd.to_numeric(frame[TARGET_COLUMN], errors="coerce").isna().any():
        raise FeaturePreparationError("Input target contains null or non-numeric values")


def _calendar_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    calendar = pd.DataFrame(index=index)
    calendar["weekday"] = index.weekday
    calendar["day_of_month"] = index.day
    calendar["month"] = index.month
    calendar["iso_week"] = index.isocalendar().week.astype("int64").to_numpy()
    calendar["day_of_year"] = index.dayofyear
    calendar["weekend"] = (index.weekday >= 5).astype("int8")
    calendar["weekday_sin"] = np.sin(2 * np.pi * calendar["weekday"] / 7)
    calendar["weekday_cos"] = np.cos(2 * np.pi * calendar["weekday"] / 7)
    calendar["month_sin"] = np.sin(2 * np.pi * (calendar["month"] - 1) / 12)
    calendar["month_cos"] = np.cos(2 * np.pi * (calendar["month"] - 1) / 12)
    year_length = np.where(index.is_leap_year, 366, 365)
    calendar["day_of_year_sin"] = np.sin(
        2 * np.pi * (calendar["day_of_year"] - 1) / year_length
    )
    calendar["day_of_year_cos"] = np.cos(
        2 * np.pi * (calendar["day_of_year"] - 1) / year_length
    )
    return calendar


def _prepare_source(frame: pd.DataFrame) -> pd.DataFrame:
    _validate_input(frame)
    source = frame.loc[:, list(EXPECTED_COLUMNS)].copy()
    source["Fecha"] = pd.to_datetime(source["Fecha"], errors="raise").dt.normalize()
    source[TARGET_COLUMN] = pd.to_numeric(source[TARGET_COLUMN], errors="raise")
    return source.sort_values("Fecha").set_index("Fecha")


def _build_feature_frame(
    target_by_day: pd.Series,
    daily_index: pd.DatetimeIndex,
    contract: FeatureContract,
) -> pd.DataFrame:
    result = pd.DataFrame(index=daily_index)
    for lag in (1, 7, 14, 28):
        result[f"lag_{lag}"] = target_by_day.shift(lag)
    shifted = target_by_day.shift(1)
    for window in (7, 14, 28):
        rolling = shifted.rolling(window=window, min_periods=window)
        result[f"rolling_mean_{window}"] = rolling.mean()
        result[f"rolling_std_{window}"] = rolling.std()
    if contract.version == FEATURE_CONTRACT_V2.version:
        result["demand_at_reference_date"] = target_by_day
        result["lag_2"] = target_by_day.shift(2)
        result["lag_3"] = target_by_day.shift(3)
        short_rolling = target_by_day.rolling(window=3, min_periods=3)
        result["rolling_mean_3_including_reference"] = short_rolling.mean()
        result["rolling_std_3_including_reference"] = short_rolling.std()
    return result.join(_calendar_features(daily_index))


def _create_features(frame: pd.DataFrame, contract: FeatureContract) -> pd.DataFrame:
    source = _prepare_source(frame)
    daily_index = pd.date_range(source.index.min(), source.index.max(), freq="D")
    target_by_day = source[TARGET_COLUMN].reindex(daily_index)
    result = _build_feature_frame(target_by_day, daily_index, contract)
    result["target_date"] = result.index + pd.Timedelta(days=1)
    result["target_h1"] = target_by_day.shift(-1)
    result["reference_date"] = result.index

    required = [*contract.predictor_columns, "target_h1"]
    result = result.dropna(subset=required)
    result = result[result["reference_date"].isin(source.index)]
    result = result[result["target_date"].isin(source.index)]
    result = result.loc[:, list(contract.feature_columns)]
    return result.reset_index(drop=True)


def create_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Build the unchanged, approved v1 feature dataset."""
    return _create_features(frame, FEATURE_CONTRACT_V1)


def create_features_v2(frame: pd.DataFrame) -> pd.DataFrame:
    """Build the candidate v2 feature dataset using calendar-aligned history."""
    return _create_features(frame, FEATURE_CONTRACT_V2)


def _build_online_features(
    frame: pd.DataFrame,
    target_date: pd.Timestamp | str,
    contract: FeatureContract,
) -> pd.DataFrame:
    """Build one H+1 row from history available on or before its reference date."""
    source = _prepare_source(frame)
    requested_target = pd.Timestamp(target_date).normalize()
    reference_date = requested_target - pd.Timedelta(days=1)
    if reference_date not in source.index:
        raise FeaturePreparationError("Reference date is not available in historical demand")

    daily_index = pd.date_range(source.index.min(), reference_date, freq="D")
    target_by_day = source[TARGET_COLUMN].reindex(daily_index)
    result = _build_feature_frame(target_by_day, daily_index, contract)
    result["target_date"] = requested_target
    result["reference_date"] = result.index
    row = result.loc[[reference_date]]
    predictor_columns = contract.predictor_columns
    if row.loc[:, list(predictor_columns)].isna().any().any():
        raise FeaturePreparationError("Insufficient or incomplete historical demand")
    return row.loc[:, ["reference_date", "target_date", *predictor_columns]].reset_index(
        drop=True
    )


def build_online_features(frame: pd.DataFrame, target_date: pd.Timestamp | str) -> pd.DataFrame:
    """Build one H+1 feature row for the approved v1 contract."""
    return _build_online_features(frame, target_date, FEATURE_CONTRACT_V1)


def build_online_features_v2(frame: pd.DataFrame, target_date: pd.Timestamp | str) -> pd.DataFrame:
    """Build one H+1 feature row for the candidate v2 contract."""
    return _build_online_features(frame, target_date, FEATURE_CONTRACT_V2)


def build_feature_dataset(
    input_path: Path = Path("data/interim/energy_demand_daily.parquet"),
    output_path: Path = FEATURE_OUTPUT,
) -> pd.DataFrame:
    if not input_path.is_file():
        raise FileNotFoundError(f"Feature input not found: {input_path}")
    frame = pd.read_parquet(input_path)
    result = create_features(frame)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output_path, index=False)
    return result


def build_feature_dataset_v2(
    input_path: Path = Path("data/interim/energy_demand_daily.parquet"),
    output_path: Path = FEATURE_OUTPUT_V2,
) -> pd.DataFrame:
    if not input_path.is_file():
        raise FileNotFoundError(f"Feature input not found: {input_path}")
    frame = pd.read_parquet(input_path)
    result = create_features_v2(frame)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output_path, index=False)
    return result
