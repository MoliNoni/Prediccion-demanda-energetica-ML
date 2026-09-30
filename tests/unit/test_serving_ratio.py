import json

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import HistGradientBoostingRegressor

from features.pipeline import FeaturePreparationError, create_features_v2
from ingestion.constants import EXPECTED_COLUMNS
from ingestion.constants import TARGET_COLUMN as DEMAND_COLUMN
from models.ratio_target import DATE_COLUMN, RatioTargetModel, daily_series, prepare_frame
from models.serving_ratio import (
    FEATURE_SET_VERSION_RATIO,
    MODEL_HORIZON_RATIO,
    MODEL_NAME_RATIO,
    MODEL_VERSION_RATIO,
    PREDICTOR_COLUMNS_RATIO,
    SERVING_CONFIG,
    RatioMlflowModelLoader,
    build_online_features_ratio,
    fit_serving_model,
)
from models.serving_v2 import CandidateServingArtifactUnavailableError


def history(start: str, end: str) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    weekly = np.array([0.0, 4.0, 5.0, 5.5, 5.0, -3.0, -8.0])[dates.weekday]
    frame = pd.DataFrame(0.0, index=range(len(dates)), columns=list(EXPECTED_COLUMNS))
    frame["Fecha"] = dates
    frame[DEMAND_COLUMN] = 100.0 + 0.03 * np.arange(len(dates)) + weekly
    return frame


@pytest.fixture(scope="module")
def fitted():
    demand = history("2017-01-01", "2021-12-31")
    features = create_features_v2(demand)
    daily = daily_series(demand, "Fecha", DEMAND_COLUMN)
    model, prepared = fit_serving_model(features, daily)
    return model, prepared, demand


def test_online_prediction_equals_the_offline_prediction_for_the_same_date(fitted) -> None:
    model, prepared, demand = fitted
    target = pd.Timestamp("2021-09-15")
    offline_row = prepared.loc[prepared[DATE_COLUMN] == target]
    # Only history up to the reference day is available at forecast time.
    available = demand.loc[demand["Fecha"] < target]

    online_row = build_online_features_ratio(available, target)

    assert list(online_row.columns) == ["reference_date", "target_date", *PREDICTOR_COLUMNS_RATIO]
    online = model.predict(online_row.loc[:, PREDICTOR_COLUMNS_RATIO])
    assert online == pytest.approx(model.predict(offline_row))
    assert online[0] == pytest.approx(
        float(demand.loc[demand["Fecha"] == target, DEMAND_COLUMN].iloc[0]), rel=0.05
    )


def test_online_base_demand_is_the_demand_seven_days_before_the_target(fitted) -> None:
    _, _, demand = fitted
    target = pd.Timestamp("2021-09-15")

    row = build_online_features_ratio(demand.loc[demand["Fecha"] < target], target)

    expected = demand.loc[demand["Fecha"] == target - pd.Timedelta(days=7), DEMAND_COLUMN]
    assert row["base_demand"].iloc[0] == pytest.approx(expected.iloc[0])


@pytest.mark.parametrize("bad_base", [0.0, -1.0, np.nan])
def test_online_features_reject_an_unusable_base_demand(fitted, bad_base: float) -> None:
    _, _, demand = fitted
    target = pd.Timestamp("2021-09-15")
    available = demand.loc[demand["Fecha"] < target].copy()
    is_base_day = available["Fecha"] == target - pd.Timedelta(days=7)
    available.loc[is_base_day, DEMAND_COLUMN] = bad_base

    with pytest.raises(FeaturePreparationError):
        build_online_features_ratio(available, target)


def test_online_features_reject_duplicate_history_dates(fitted) -> None:
    _, _, demand = fitted
    target = pd.Timestamp("2021-09-15")
    available = demand.loc[demand["Fecha"] < target]

    with pytest.raises(FeaturePreparationError):
        build_online_features_ratio(pd.concat([available, available.tail(1)]), target)


def metadata() -> dict[str, object]:
    return {
        "model_name": MODEL_NAME_RATIO,
        "model_version": MODEL_VERSION_RATIO,
        "horizon": MODEL_HORIZON_RATIO,
        "feature_set_version": FEATURE_SET_VERSION_RATIO,
        "predictor_columns": PREDICTOR_COLUMNS_RATIO,
        "ratio_config": SERVING_CONFIG.as_dict(),
        "tracking_uri": "file:///unused-for-test",
        "model_uri": "runs:/ratio/model",
    }


def test_loader_wraps_the_estimator_so_predict_returns_demand(
    fitted, tmp_path, monkeypatch
) -> None:
    model, prepared, _ = fitted
    path = tmp_path / "ratio.json"
    path.write_text(json.dumps(metadata()), encoding="utf-8")
    monkeypatch.setattr("models.serving_ratio.mlflow.sklearn.load_model", lambda _: model.estimator)

    loaded, loaded_metadata = RatioMlflowModelLoader(path).load()

    assert isinstance(loaded, RatioTargetModel)
    assert loaded_metadata["model_version"] == "1.2.0"
    sample = prepared.tail(5)
    assert loaded.predict(sample) == pytest.approx(model.predict(sample))
    assert isinstance(loaded.estimator, HistGradientBoostingRegressor)


def test_loader_prefers_the_runtime_tracking_uri_over_a_stale_windows_path(
    tmp_path, monkeypatch
) -> None:
    stale = {**metadata(), "tracking_uri": "file:///C:/Users/User/Desktop/project/mlruns"}
    path = tmp_path / "ratio.json"
    path.write_text(json.dumps(stale), encoding="utf-8")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "file:///app/mlruns")
    captured: list[str] = []
    monkeypatch.setattr("models.serving_ratio.mlflow.set_tracking_uri", captured.append)

    def fake_load_model(model_uri: str):
        assert captured[-1] == "file:///app/mlruns"
        assert model_uri == "runs:/ratio/model"
        return HistGradientBoostingRegressor()

    monkeypatch.setattr("models.serving_ratio.mlflow.sklearn.load_model", fake_load_model)

    _, loaded_metadata = RatioMlflowModelLoader(path).load()

    assert loaded_metadata["tracking_uri"] == "file:///app/mlruns"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_version", "1.1.0"),
        ("predictor_columns", ["lag_1"]),
        ("feature_set_version", "v2"),
        ("ratio_config", {**SERVING_CONFIG.as_dict(), "base_lag": 1}),
    ],
)
def test_loader_rejects_metadata_that_does_not_match_the_serving_contract(
    tmp_path, field: str, value: object
) -> None:
    path = tmp_path / "ratio.json"
    path.write_text(json.dumps({**metadata(), field: value}), encoding="utf-8")

    with pytest.raises(CandidateServingArtifactUnavailableError, match="metadata is invalid"):
        RatioMlflowModelLoader(path).load()


def test_loader_reports_a_missing_metadata_file(tmp_path) -> None:
    with pytest.raises(CandidateServingArtifactUnavailableError, match="unavailable"):
        RatioMlflowModelLoader(tmp_path / "missing.json").load()


def test_serving_fit_uses_the_phase12_prepared_frame(fitted) -> None:
    _, prepared, demand = fitted
    daily = daily_series(demand, "Fecha", DEMAND_COLUMN)

    expected, _ = prepare_frame(create_features_v2(demand), daily, SERVING_CONFIG.base_lag)

    assert prepared[DATE_COLUMN].tolist() == expected[DATE_COLUMN].tolist()
