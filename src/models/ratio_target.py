"""Relative-target (ratio) candidate for the H+1 daily demand model.

Why: tree ensembles cannot predict outside the range of their training target, so a model
trained on absolute demand is capped near the training maximum while demand keeps growing.
This module predicts the growth-free ratio ``demand_t / demand_{t-k}`` (or its logarithm) and
reconstructs ``demand_hat_t = ratio_hat * demand_{t-k}``.

Leakage reasoning. A v2 row has ``reference_date = t - 1`` and ``target_date = t``. Demand of
the reference day is known when forecasting ``t`` (it is the v2 feature
``demand_at_reference_date``). Hence the only legitimate bases are ``demand_{t-k}`` with
``k >= 1``. The supported bases are ``k = 1`` (the reference day) and ``k = 7`` (same weekday
last week, i.e. ``reference_date - 6``). ``demand_t`` and later values never enter a feature.

Feature choice. The v2 predictors are kept, with two changes for scale invariance:
level features (lags, rolling means and standard deviations, demand at the reference date)
are divided by the base demand, and the calendar features are kept unchanged (holiday
information reaches the model only through them, as in v2). The ``relative_plus_levels`` mode
also keeps the raw level features so validation can show whether they help; trees cannot
extrapolate on them, which is the reason ``relative_only`` exists.

Rows whose base demand is missing or non-positive are dropped and counted, never imputed.
"""

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from evaluation.metrics import wape
from features.contracts import FEATURE_CONTRACT_V2

DATE_COLUMN = "target_date"
TARGET_COLUMN = "target_h1"
BASE_COLUMN = "base_demand"
BASE_LAGS = (1, 7)
TRANSFORMS = ("ratio", "log_ratio")
FEATURE_MODES = ("relative_only", "relative_plus_levels")
TRAIN_YEARS = (2000, 2019)
VALIDATION_YEARS = (2020, 2021)

LEVEL_COLUMNS = (
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_7",
    "lag_14",
    "lag_28",
    "rolling_mean_3_including_reference",
    "rolling_std_3_including_reference",
    "rolling_mean_7",
    "rolling_std_7",
    "rolling_mean_14",
    "rolling_std_14",
    "rolling_mean_28",
    "rolling_std_28",
    "demand_at_reference_date",
)
CALENDAR_COLUMNS = tuple(
    column for column in FEATURE_CONTRACT_V2.predictor_columns if column not in LEVEL_COLUMNS
)
RELATIVE_COLUMNS = tuple(f"{column}_rel" for column in LEVEL_COLUMNS)

# Hyperparameters of the served model v1.1.0 (serving_model_v2_metadata.json) plus two
# pre-declared alternatives. All other settings keep the scikit-learn defaults.
HYPERPARAMETER_SETS: dict[str, dict[str, Any]] = {
    "v1_1_0": {
        "max_iter": 200,
        "learning_rate": 0.05,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 20,
        "l2_regularization": 0.0,
    },
    "regularized": {
        "max_iter": 300,
        "learning_rate": 0.03,
        "max_leaf_nodes": 15,
        "min_samples_leaf": 40,
        "l2_regularization": 1.0,
    },
    "larger": {
        "max_iter": 400,
        "learning_rate": 0.03,
        "max_leaf_nodes": 63,
        "min_samples_leaf": 20,
        "l2_regularization": 0.0,
    },
}
RANDOM_STATE = 42


@dataclass(frozen=True)
class RatioConfig:
    base_lag: int
    transform: str
    feature_mode: str
    hyperparameters: str

    def __post_init__(self) -> None:
        if self.base_lag not in BASE_LAGS:
            raise ValueError(f"base_lag must be one of {BASE_LAGS}")
        if self.transform not in TRANSFORMS:
            raise ValueError(f"transform must be one of {TRANSFORMS}")
        if self.feature_mode not in FEATURE_MODES:
            raise ValueError(f"feature_mode must be one of {FEATURE_MODES}")
        if self.hyperparameters not in HYPERPARAMETER_SETS:
            raise ValueError(f"hyperparameters must be one of {tuple(HYPERPARAMETER_SETS)}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_grid() -> list[RatioConfig]:
    return [
        RatioConfig(base_lag, transform, mode, hyper)
        for base_lag in BASE_LAGS
        for transform in TRANSFORMS
        for mode in FEATURE_MODES
        for hyper in HYPERPARAMETER_SETS
    ]


def encode_target(demand: Sequence[float], base: Sequence[float], transform: str) -> np.ndarray:
    ratio = np.asarray(demand, dtype=float) / np.asarray(base, dtype=float)
    if transform == "ratio":
        return ratio
    if transform == "log_ratio":
        return np.log(ratio)
    raise ValueError(f"Unknown transform: {transform}")


def decode_prediction(
    predicted: Sequence[float], base: Sequence[float], transform: str
) -> np.ndarray:
    predicted_array = np.asarray(predicted, dtype=float)
    if transform == "ratio":
        ratio = predicted_array
    elif transform == "log_ratio":
        ratio = np.exp(predicted_array)
    else:
        raise ValueError(f"Unknown transform: {transform}")
    return ratio * np.asarray(base, dtype=float)


def daily_series(demand: pd.DataFrame, date_column: str, value_column: str) -> pd.Series:
    """Return demand on a complete daily index; missing days stay NaN (never imputed)."""
    dates = pd.to_datetime(demand[date_column]).dt.normalize()
    series = pd.Series(demand[value_column].to_numpy(dtype=float), index=dates).sort_index()
    return series.reindex(pd.date_range(series.index.min(), series.index.max(), freq="D"))


def base_demand(
    daily: pd.Series, target_dates: Iterable[pd.Timestamp], base_lag: int
) -> np.ndarray:
    """Return ``demand_{t-base_lag}`` for each target date ``t`` (NaN when unavailable)."""
    if base_lag < 1:
        raise ValueError("base_lag must be at least 1 to avoid using the target day")
    lookup = pd.DatetimeIndex(pd.to_datetime(list(target_dates))) - pd.Timedelta(days=base_lag)
    return daily.reindex(lookup).to_numpy(dtype=float)


def prepare_frame(
    features: pd.DataFrame, daily: pd.Series, base_lag: int
) -> tuple[pd.DataFrame, int]:
    """Attach the base demand and drop rows without a usable base.

    Returns the prepared frame and the number of dropped rows.
    """
    frame = features.sort_values(DATE_COLUMN).reset_index(drop=True).copy()
    frame[DATE_COLUMN] = pd.to_datetime(frame[DATE_COLUMN])
    frame[BASE_COLUMN] = base_demand(daily, frame[DATE_COLUMN], base_lag)
    usable = frame[BASE_COLUMN].notna() & (frame[BASE_COLUMN] > 0)
    return frame.loc[usable].reset_index(drop=True), int((~usable).sum())


def feature_columns(feature_mode: str) -> tuple[str, ...]:
    if feature_mode == "relative_only":
        return (*CALENDAR_COLUMNS, *RELATIVE_COLUMNS)
    if feature_mode == "relative_plus_levels":
        return (*CALENDAR_COLUMNS, *RELATIVE_COLUMNS, *LEVEL_COLUMNS)
    raise ValueError(f"Unknown feature mode: {feature_mode}")


def build_matrix(frame: pd.DataFrame, feature_mode: str) -> pd.DataFrame:
    """Build the model matrix from a prepared frame (level features made scale-free)."""
    base = frame[BASE_COLUMN].to_numpy(dtype=float)
    matrix = frame.loc[:, list(CALENDAR_COLUMNS)].copy()
    for column in LEVEL_COLUMNS:
        matrix[f"{column}_rel"] = frame[column].to_numpy(dtype=float) / base
    if feature_mode == "relative_plus_levels":
        for column in LEVEL_COLUMNS:
            matrix[column] = frame[column].to_numpy(dtype=float)
    return matrix.loc[:, list(feature_columns(feature_mode))]


class RatioTargetModel:
    """HistGradientBoosting on the relative target; ``predict`` returns demand."""

    def __init__(self, config: RatioConfig) -> None:
        self.config = config
        self.estimator = HistGradientBoostingRegressor(
            random_state=RANDOM_STATE, **HYPERPARAMETER_SETS[config.hyperparameters]
        )

    def fit(self, frame: pd.DataFrame) -> "RatioTargetModel":
        target = encode_target(frame[TARGET_COLUMN], frame[BASE_COLUMN], self.config.transform)
        self.estimator.fit(build_matrix(frame, self.config.feature_mode), target)
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        raw = self.estimator.predict(build_matrix(frame, self.config.feature_mode))
        return decode_prediction(raw, frame[BASE_COLUMN], self.config.transform)


def rows_in_years(frame: pd.DataFrame, years: tuple[int, int]) -> pd.DataFrame:
    year = pd.to_datetime(frame[DATE_COLUMN]).dt.year
    return frame.loc[year.between(*years)]


def select_on_validation(
    prepared: dict[int, pd.DataFrame],
    configs: Sequence[RatioConfig],
    train_years: tuple[int, int] = TRAIN_YEARS,
    validation_years: tuple[int, int] = VALIDATION_YEARS,
) -> tuple[RatioConfig, list[dict[str, Any]]]:
    """Fit every config on the train years and score it on the validation years only.

    ``prepared`` maps each base lag to its prepared frame. Rows outside the train and
    validation years (including the Test period) are never read for fitting or scoring.
    Ties are broken by grid order.
    """
    if not configs:
        raise ValueError("configs must not be empty")
    scores: list[dict[str, Any]] = []
    for config in configs:
        frame = prepared[config.base_lag]
        train = rows_in_years(frame, train_years)
        validation = rows_in_years(frame, validation_years)
        model = RatioTargetModel(config).fit(train)
        prediction = model.predict(validation)
        scores.append(
            {
                **config.as_dict(),
                "validation_rows": len(validation),
                "validation_wape": wape(validation[TARGET_COLUMN], prediction),
            }
        )
    best_index = int(np.argmin([score["validation_wape"] for score in scores]))
    return configs[best_index], scores


def bias_pct(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Signed bias as a percentage of total actual demand (negative = under-forecast)."""
    actual_array = np.asarray(actual, dtype=float)
    return float(
        (np.sum(np.asarray(predicted, dtype=float) - actual_array)) / actual_array.sum() * 100
    )
