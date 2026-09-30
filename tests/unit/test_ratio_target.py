import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import HistGradientBoostingRegressor

from evaluation.metrics import wape
from features.contracts import FEATURE_CONTRACT_V2
from features.pipeline import create_features_v2
from ingestion.constants import EXPECTED_COLUMNS
from ingestion.constants import TARGET_COLUMN as DEMAND_COLUMN
from models.ratio_target import (
    BASE_COLUMN,
    DATE_COLUMN,
    MATCH_ABS_TOLERANCE_KWH,
    MATCH_REL_TOLERANCE,
    RatioConfig,
    RatioTargetModel,
    base_demand,
    bias_pct,
    build_matrix,
    daily_series,
    decode_prediction,
    default_grid,
    encode_target,
    matches_within_tolerance,
    prepare_frame,
    select_on_validation,
)

FAST_HYPERPARAMETERS = "v1_1_0"


def demand_frame(dates: pd.DatetimeIndex, values: np.ndarray) -> pd.DataFrame:
    frame = pd.DataFrame(0.0, index=range(len(dates)), columns=list(EXPECTED_COLUMNS))
    frame["Fecha"] = dates
    frame[DEMAND_COLUMN] = values
    return frame


def growing_series(start: str, end: str, growth_per_year: float = 6.0) -> pd.Series:
    """Weekly pattern on top of a linear trend; levels keep rising through the period."""
    dates = pd.date_range(start, end, freq="D")
    years = np.arange(len(dates)) / 365.0
    weekly = np.array([0.0, 4.0, 5.0, 5.5, 5.0, -3.0, -8.0])[dates.weekday]
    return pd.Series(100.0 + growth_per_year * years + weekly, index=dates)


def v2_features(series: pd.Series) -> pd.DataFrame:
    return create_features_v2(demand_frame(series.index, series.to_numpy()))


@pytest.mark.parametrize("transform", ["ratio", "log_ratio"])
def test_encode_then_decode_reconstructs_demand(transform: str) -> None:
    demand = np.array([120.0, 95.5, 210.0])
    base = np.array([100.0, 100.0, 200.0])

    encoded = encode_target(demand, base, transform)

    assert decode_prediction(encoded, base, transform) == pytest.approx(demand)


def test_ratio_encoding_is_scale_free() -> None:
    small = encode_target([110.0], [100.0], "ratio")
    large = encode_target([1_100.0], [1_000.0], "ratio")

    assert small == pytest.approx(large)


def test_unknown_transform_is_rejected() -> None:
    with pytest.raises(ValueError):
        encode_target([1.0], [1.0], "difference")
    with pytest.raises(ValueError):
        RatioConfig(3, "ratio", "relative_only", "v1_1_0")


@pytest.mark.parametrize("base_lag", [1, 7])
def test_base_demand_uses_only_days_before_the_target(base_lag: int) -> None:
    series = growing_series("2020-01-01", "2020-03-31")
    target_dates = pd.DatetimeIndex(["2020-02-10", "2020-03-01"])

    base = base_demand(series, target_dates, base_lag)

    expected = [series[day - pd.Timedelta(days=base_lag)] for day in target_dates]
    assert base == pytest.approx(expected)
    with pytest.raises(ValueError):
        base_demand(series, target_dates, 0)


@pytest.mark.parametrize("base_lag", [1, 7])
def test_features_for_a_day_do_not_depend_on_that_day_or_later(base_lag: int) -> None:
    series = growing_series("2019-01-01", "2020-06-30")
    target = pd.Timestamp("2020-05-15")
    daily = series
    baseline = prepare_frame(v2_features(series), daily, base_lag)[0]
    row = baseline.loc[baseline[DATE_COLUMN] == target]

    tampered_series = series.copy()
    tampered_series[tampered_series.index >= target] *= 5.0
    tampered = prepare_frame(v2_features(tampered_series), tampered_series, base_lag)[0]
    tampered_row = tampered.loc[tampered[DATE_COLUMN] == target]

    predictors = list(FEATURE_CONTRACT_V2.predictor_columns)
    assert row[predictors].to_numpy() == pytest.approx(tampered_row[predictors].to_numpy())
    assert row[BASE_COLUMN].item() == pytest.approx(tampered_row[BASE_COLUMN].item())
    for mode in ("relative_only", "relative_plus_levels"):
        assert build_matrix(row, mode).to_numpy() == pytest.approx(
            build_matrix(tampered_row, mode).to_numpy()
        )


def test_rows_without_a_base_are_dropped_and_counted() -> None:
    series = growing_series("2020-01-01", "2020-03-31")
    features = v2_features(series)
    daily = series.copy()
    gap_day = pd.Timestamp("2020-03-08")
    daily[gap_day] = np.nan
    target_of_gap = gap_day + pd.Timedelta(days=7)

    prepared, dropped = prepare_frame(features, daily, 7)

    assert dropped == 1
    assert target_of_gap not in set(prepared[DATE_COLUMN])
    assert len(prepared) == len(features) - 1
    assert prepared[BASE_COLUMN].notna().all()


@pytest.mark.parametrize("bad_base", [0.0, -5.0])
def test_rows_with_a_non_positive_base_are_dropped_and_counted(bad_base: float) -> None:
    series = growing_series("2020-01-01", "2020-03-31")
    features = v2_features(series)
    daily = series.copy()
    daily[pd.Timestamp("2020-03-08")] = bad_base

    prepared, dropped = prepare_frame(features, daily, 7)

    assert dropped == 1
    assert (prepared[BASE_COLUMN] > 0).all()


def test_daily_series_rejects_duplicate_dates() -> None:
    dates = pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-02"])
    frame = demand_frame(dates, np.array([1.0, 2.0, 3.0]))

    with pytest.raises(ValueError, match="duplicate"):
        daily_series(frame, "Fecha", DEMAND_COLUMN)


def test_daily_series_rejects_null_dates() -> None:
    dates = pd.DatetimeIndex(["2020-01-01", pd.NaT, "2020-01-03"])
    frame = demand_frame(dates, np.array([1.0, 2.0, 3.0]))

    with pytest.raises(ValueError, match="null dates"):
        daily_series(frame, "Fecha", DEMAND_COLUMN)


def test_daily_series_keeps_missing_days_as_nan() -> None:
    dates = pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-04"])
    frame = demand_frame(dates, np.array([1.0, 2.0, 4.0]))

    series = daily_series(frame, "Fecha", DEMAND_COLUMN)

    assert len(series) == 4
    assert np.isnan(series[pd.Timestamp("2020-01-03")])


def test_relative_target_model_predicts_above_the_training_ceiling() -> None:
    series = growing_series("2000-01-01", "2013-12-31", growth_per_year=8.0)
    features = v2_features(series)
    train_end, test_start = pd.Timestamp("2009-12-31"), pd.Timestamp("2012-01-01")
    training_max = series[:train_end].max()
    assert series[test_start:].min() > training_max  # the toy test levels exceed train levels

    prepared, _ = prepare_frame(features, series, 7)
    train = prepared.loc[prepared[DATE_COLUMN] <= train_end]
    test = prepared.loc[prepared[DATE_COLUMN] >= test_start]
    candidate = RatioTargetModel(RatioConfig(7, "ratio", "relative_only", FAST_HYPERPARAMETERS))
    candidate.fit(train)
    absolute = HistGradientBoostingRegressor(random_state=42).fit(
        train[list(FEATURE_CONTRACT_V2.predictor_columns)], train["target_h1"]
    )

    candidate_prediction = candidate.predict(test)
    absolute_prediction = absolute.predict(test[list(FEATURE_CONTRACT_V2.predictor_columns)])

    assert absolute_prediction.max() <= training_max + 1e-6
    assert candidate_prediction.max() > training_max
    candidate_error = np.abs(candidate_prediction - test["target_h1"]).mean()
    absolute_error = np.abs(absolute_prediction - test["target_h1"]).mean()
    assert candidate_error < absolute_error / 2


@pytest.mark.parametrize("transform", ["ratio", "log_ratio"])
@pytest.mark.parametrize("feature_mode", ["relative_only", "relative_plus_levels"])
def test_every_transform_and_feature_mode_fits_and_predicts_demand(
    transform: str, feature_mode: str
) -> None:
    series = growing_series("2018-01-01", "2020-12-31")
    prepared, _ = prepare_frame(v2_features(series), series, 7)
    train = prepared.loc[prepared[DATE_COLUMN] < "2020-06-01"]
    test = prepared.loc[prepared[DATE_COLUMN] >= "2020-06-01"]

    model = RatioTargetModel(RatioConfig(7, transform, feature_mode, FAST_HYPERPARAMETERS))
    prediction = model.fit(train).predict(test)

    assert prediction.shape == (len(test),)
    assert np.isfinite(prediction).all()
    assert np.abs(prediction / test["target_h1"] - 1).mean() < 0.05


@pytest.mark.parametrize("transform", ["ratio", "log_ratio"])
def test_fit_drops_and_counts_rows_whose_target_cannot_be_encoded(transform: str) -> None:
    series = growing_series("2018-01-01", "2019-12-31")
    prepared, _ = prepare_frame(v2_features(series), series, 7)
    broken = prepared.copy()
    broken.loc[10, "target_h1"] = np.nan
    broken.loc[20, "target_h1"] = 0.0
    broken.loc[30, "target_h1"] = -4.0
    model = RatioTargetModel(RatioConfig(7, transform, "relative_only", FAST_HYPERPARAMETERS))

    model.fit(broken)

    assert model.dropped_training_rows == (3 if transform == "log_ratio" else 1)
    with pytest.raises(ValueError, match="usable target"):
        model.fit(broken.assign(target_h1=np.nan))


def test_selection_rejects_non_finite_scores_and_fails_when_all_are_invalid(monkeypatch) -> None:
    series = growing_series("2000-01-01", "2013-12-31")
    prepared, _ = prepare_frame(v2_features(series), series, 7)
    grid = [
        RatioConfig(7, transform, "relative_only", "v1_1_0") for transform in ("ratio", "log_ratio")
    ]
    years = (2000, 2009), (2010, 2011)
    real_wape = wape

    values = iter([float("nan")])
    monkeypatch.setattr(
        "models.ratio_target.wape",
        lambda a, p: next(values, None) or real_wape(a, p),
    )
    best, scores = select_on_validation({7: prepared}, grid, *years)

    assert best == grid[1]
    assert scores[0]["validation_wape"] is None
    assert scores[1]["validation_wape"] is not None

    monkeypatch.setattr("models.ratio_target.wape", lambda a, p: float("inf"))
    with pytest.raises(ValueError, match="non-finite"):
        select_on_validation({7: prepared}, grid, *years)


def test_selection_rejects_empty_train_or_validation_slices() -> None:
    series = growing_series("2000-01-01", "2013-12-31")
    prepared, _ = prepare_frame(v2_features(series), series, 7)
    grid = [RatioConfig(7, "ratio", "relative_only", "v1_1_0")]

    with pytest.raises(ValueError, match="Empty train or validation"):
        select_on_validation({7: prepared}, grid, (2000, 2009), (2030, 2031))
    with pytest.raises(ValueError, match="Empty train or validation"):
        select_on_validation({7: prepared}, grid, (1990, 1991), (2010, 2011))
    with pytest.raises(ValueError, match="must not be empty"):
        select_on_validation({7: prepared}, [], (2000, 2009), (2010, 2011))


def test_grid_selection_ignores_rows_outside_train_and_validation_years() -> None:
    series = growing_series("2000-01-01", "2013-12-31")
    features = v2_features(series)
    prepared, _ = prepare_frame(features, series, 7)
    years = prepared[DATE_COLUMN].dt.year
    grid = [
        RatioConfig(7, transform, "relative_only", "v1_1_0") for transform in ("ratio", "log_ratio")
    ]

    train_years, validation_years = (2000, 2009), (2010, 2011)
    reference = select_on_validation({7: prepared}, grid, train_years, validation_years)
    corrupted = prepared.copy()
    later = years > 2011
    corrupted.loc[later, "target_h1"] = corrupted.loc[later, "target_h1"] * 3 + 1e6
    repeated = select_on_validation({7: corrupted}, grid, train_years, validation_years)

    assert repeated[0] == reference[0]
    assert [s["validation_wape"] for s in repeated[1]] == pytest.approx(
        [s["validation_wape"] for s in reference[1]]
    )
    assert {s["validation_rows"] for s in reference[1]} == {int((years.between(2010, 2011)).sum())}


def test_default_grid_is_the_declared_small_grid() -> None:
    grid = default_grid()

    assert len(grid) == len(set(grid)) == 24
    assert {config.base_lag for config in grid} == {1, 7}
    assert {config.hyperparameters for config in grid} == {"v1_1_0", "regularized", "larger"}


def test_bias_is_negative_for_under_forecasts() -> None:
    assert bias_pct([100.0, 100.0], [90.0, 90.0]) == pytest.approx(-10.0)


DEMAND_SCALE = 2e8  # kWh, the order of magnitude of the daily demand
LIMIT = MATCH_ABS_TOLERANCE_KWH + MATCH_REL_TOLERANCE * DEMAND_SCALE


def test_match_tolerance_accepts_a_difference_just_inside_the_limit() -> None:
    assert matches_within_tolerance([DEMAND_SCALE + LIMIT * 0.99], [DEMAND_SCALE])
    assert matches_within_tolerance([DEMAND_SCALE - LIMIT * 0.99], [DEMAND_SCALE])


def test_match_tolerance_rejects_a_difference_just_outside_the_limit() -> None:
    assert not matches_within_tolerance([DEMAND_SCALE + LIMIT * 1.01], [DEMAND_SCALE])
    assert not matches_within_tolerance([DEMAND_SCALE - LIMIT * 1.01], [DEMAND_SCALE])


def test_match_tolerance_rejects_non_finite_empty_and_mismatched_inputs() -> None:
    assert not matches_within_tolerance([np.nan], [1.0])
    assert not matches_within_tolerance([1.0], [np.inf])
    assert not matches_within_tolerance([], [])
    assert not matches_within_tolerance([1.0, 2.0], [1.0])
