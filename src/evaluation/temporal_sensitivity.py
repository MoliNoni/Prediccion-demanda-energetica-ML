"""Alternative temporal-sensitivity comparison that preserves official evaluation outputs."""

from typing import Any

import pandas as pd

from evaluation.metrics import mae, rmse, smape, wape
from features.contracts import FEATURE_CONTRACT_V2
from models.training import DATE_COLUMN, PREDICTOR_COLUMNS, TARGET_COLUMN, build_selected_model

V1_PREDICTION_COLUMN = "HistGradientBoostingRegressor_prediction"
V2_PREDICTION_COLUMN = "HistGradientBoostingRegressor_v2_prediction"
ALTERNATIVE_TRAIN_YEARS = (2015, 2019)
ALTERNATIVE_VALIDATION_YEAR = 2022
ALTERNATIVE_TEST_YEAR = 2023


def _metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    return {
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "smape": smape(actual, predicted),
        "wape": wape(actual, predicted),
    }


def _difference(v1: dict[str, float], v2: dict[str, float]) -> dict[str, dict[str, float]]:
    return {
        metric: {
            "absolute_v2_minus_v1": v2[metric] - v1[metric],
            "relative_percent": (v2[metric] - v1[metric]) / v1[metric] * 100,
        }
        for metric in v1
    }


def _partition(frame: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    dates = pd.to_datetime(frame[DATE_COLUMN], errors="raise")
    partition = frame.loc[dates.dt.year.between(start_year, end_year)].copy()
    if partition.empty:
        raise ValueError("Alternative temporal partition is empty")
    return partition


def _predict(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    predictor_columns: tuple[str, ...],
    prediction_column: str,
) -> pd.DataFrame:
    model = build_selected_model()
    model.fit(train.loc[:, predictor_columns], train[TARGET_COLUMN])
    prediction = evaluation.loc[:, [DATE_COLUMN, TARGET_COLUMN]].copy()
    prediction[prediction_column] = model.predict(evaluation.loc[:, predictor_columns])
    return prediction


def _compare_partition(
    v1: pd.DataFrame,
    v2: pd.DataFrame,
    year: int,
) -> dict[str, Any]:
    joined = v1.merge(v2, on=[DATE_COLUMN, TARGET_COLUMN], how="inner", validate="one_to_one")
    if len(joined) != len(v1) or len(joined) != len(v2):
        raise ValueError(f"V1 and v2 predictions are not aligned for {year}")
    v1_metrics = _metrics(joined[TARGET_COLUMN], joined[V1_PREDICTION_COLUMN])
    v2_metrics = _metrics(joined[TARGET_COLUMN], joined[V2_PREDICTION_COLUMN])
    return {
        "split": "validation" if year == ALTERNATIVE_VALIDATION_YEAR else "test",
        "year": year,
        "records": len(joined),
        "v1_hgb": v1_metrics,
        "v2_hgb": v2_metrics,
        "difference": _difference(v1_metrics, v2_metrics),
    }


def compare_alternative_temporal_split(
    v1_features: pd.DataFrame,
    v2_features: pd.DataFrame,
) -> dict[str, Any]:
    """Compare fixed v1/v2 HGB definitions on the approved sensitivity split."""
    required_v1 = {DATE_COLUMN, TARGET_COLUMN, *PREDICTOR_COLUMNS}
    required_v2 = {DATE_COLUMN, TARGET_COLUMN, *FEATURE_CONTRACT_V2.predictor_columns}
    if missing := required_v1.difference(v1_features.columns):
        raise ValueError(f"Missing v1 feature columns: {sorted(missing)}")
    if missing := required_v2.difference(v2_features.columns):
        raise ValueError(f"Missing v2 feature columns: {sorted(missing)}")

    v1_train = _partition(v1_features, *ALTERNATIVE_TRAIN_YEARS)
    v2_train = _partition(v2_features, *ALTERNATIVE_TRAIN_YEARS)
    v1_predictions = {
        year: _predict(
            v1_train,
            _partition(v1_features, year, year),
            PREDICTOR_COLUMNS,
            V1_PREDICTION_COLUMN,
        )
        for year in (ALTERNATIVE_VALIDATION_YEAR, ALTERNATIVE_TEST_YEAR)
    }
    v2_predictions = {
        year: _predict(
            v2_train,
            _partition(v2_features, year, year),
            FEATURE_CONTRACT_V2.predictor_columns,
            V2_PREDICTION_COLUMN,
        )
        for year in (ALTERNATIVE_VALIDATION_YEAR, ALTERNATIVE_TEST_YEAR)
    }
    return {
        "purpose": "Phase 11 temporal sensitivity of fixed HGB v1 versus v2",
        "official_split_preserved": {
            "train": "2000-2019",
            "validation": "2020-2021",
            "test": "2022-2023",
        },
        "alternative_split": {
            "train": "2015-2019",
            "validation": "2022",
            "test": "2023",
            "excluded_extraordinary_period": "2020-2021",
        },
        "test_used_for_selection": False,
        "results": [
            _compare_partition(v1_predictions[year], v2_predictions[year], year)
            for year in (ALTERNATIVE_VALIDATION_YEAR, ALTERNATIVE_TEST_YEAR)
        ],
    }
