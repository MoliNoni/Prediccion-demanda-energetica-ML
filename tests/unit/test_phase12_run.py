import importlib.util
import json
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import pytest

from features.pipeline import create_features_v2
from ingestion.constants import EXPECTED_COLUMNS
from ingestion.constants import TARGET_COLUMN as DEMAND_COLUMN
from models.ratio_target import RatioConfig
from models.serving_ratio import (
    SERVING_CONFIG,
    RatioMlflowModelLoader,
    build_online_features_ratio,
    create_serving_artifact_v1_2,
)
from models.training_v2 import train_and_predict_v2

SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "run_phase12_ratio_target.py"
GRID = [
    RatioConfig(7, "ratio", "relative_only", "v1_1_0"),
    RatioConfig(7, "ratio", "relative_plus_levels", "v1_1_0"),
]


def load_script():
    spec = importlib.util.spec_from_file_location("run_phase12_ratio_target_cli", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_demand() -> pd.DataFrame:
    dates = pd.date_range("2000-01-01", "2023-12-31", freq="D")
    weekly = np.array([0.0, 4.0, 5.0, 5.5, 5.0, -3.0, -8.0])[dates.weekday]
    frame = pd.DataFrame(0.0, index=range(len(dates)), columns=list(EXPECTED_COLUMNS))
    frame["Fecha"] = dates
    frame[DEMAND_COLUMN] = 100.0 + 0.02 * np.arange(len(dates)) + weekly
    return frame


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("phase12")
    demand = synthetic_demand()
    features = create_features_v2(demand)
    predictions, _ = train_and_predict_v2(features)
    paths = {
        "features_path": directory / "features.parquet",
        "daily_path": directory / "daily.parquet",
        "v1_predictions_path": directory / "v1.parquet",
    }
    features.to_parquet(paths["features_path"], index=False)
    demand.to_parquet(paths["daily_path"], index=False)
    predictions.to_parquet(paths["v1_predictions_path"], index=False)
    return paths, demand, predictions


def outputs(directory: Path) -> dict[str, Path]:
    return {
        "output_path": directory / "results.json",
        "predictions_path": directory / "predictions.parquet",
        "candidate_directory": directory / "candidates",
    }


def test_run_writes_a_finite_report_and_the_expected_calendar(inputs, tmp_path) -> None:
    paths, _, _ = inputs
    script = load_script()

    result = script.run(**paths, **outputs(tmp_path), grid=GRID)

    written = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert written["selected_config"] in [config.as_dict() for config in GRID]
    assert written["test_calendar"] == {
        "calendar_days": 730,
        "absent_from_source": 0,
        "expected_dates": 730,
        "feature_rows_in_test_years": 730,
        "removed_by_prepare_frame": 0,
        "evaluated_dates": 730,
    }
    assert written["v1_1_0_reproduction_max_abs_diff_vs_stored"] == 0.0
    assert result["test"]["ratio_candidate"]["test_overall"]["records"] == 730
    assert (tmp_path / "predictions.parquet").is_file()
    assert (tmp_path / "candidates" / "ratio_target_candidate_refit.joblib").is_file()


def test_run_fails_when_the_v1_reproduction_differs_from_the_stored_file(inputs, tmp_path) -> None:
    paths, _, predictions = inputs
    tampered = predictions.copy()
    column = "HistGradientBoostingRegressor_v2_prediction"
    tampered[column] = tampered[column] + 1.0
    tampered_path = tmp_path / "tampered.parquet"
    tampered.to_parquet(tampered_path, index=False)

    with pytest.raises(ValueError, match="reproduction does not match"):
        load_script().run(
            **{**paths, "v1_predictions_path": tampered_path}, **outputs(tmp_path), grid=GRID
        )
    assert not (tmp_path / "results.json").exists()


def test_run_fails_when_test_dates_are_removed_without_being_absent_from_the_source(
    inputs, tmp_path
) -> None:
    paths, _, _ = inputs
    features = pd.read_parquet(paths["features_path"])
    dropped = pd.to_datetime(features["target_date"]).between("2023-03-01", "2023-03-05")
    features_path = tmp_path / "features_missing.parquet"
    features.loc[~dropped].to_parquet(features_path, index=False)

    with pytest.raises(ValueError, match="differ from the expected calendar"):
        load_script().run(
            **{**paths, "features_path": features_path}, **outputs(tmp_path), grid=GRID
        )


@pytest.fixture
def isolated_mlflow():
    previous = mlflow.get_tracking_uri()
    yield
    mlflow.set_tracking_uri(previous)


def test_artifact_creation_roundtrips_through_a_local_mlflow_store(
    inputs, tmp_path, monkeypatch, isolated_mlflow
) -> None:
    paths, demand, _ = inputs
    script = load_script()
    script.run(**paths, **outputs(tmp_path), grid=[SERVING_CONFIG])
    tracking_directory = tmp_path / "mlruns"
    metadata_path = tmp_path / "serving_model_v1_2_metadata.json"

    metadata = create_serving_artifact_v1_2(
        features_path=paths["features_path"],
        daily_path=paths["daily_path"],
        results_path=tmp_path / "results.json",
        predictions_path=tmp_path / "predictions.parquet",
        metadata_path=metadata_path,
        tracking_directory=tracking_directory,
    )

    written = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert written["model_version"] == "1.2.0"
    assert written["feature_set_version"] == "v2-ratio7"
    assert written["periods"]["train"] == "2000-2021"
    assert written["refit_vs_phase12_max_abs_diff_kwh"] == 0.0
    assert set(written["phase12_test_metrics"]) == {
        "fit_2000_2019",
        "refit_2000_2021",
        "v1_1_0_absolute",
    }
    assert metadata["model_uri"].startswith("runs:/")

    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking_directory.resolve().as_uri())
    model, loaded = RatioMlflowModelLoader(metadata_path).load()
    target = pd.Timestamp("2023-06-15")
    available = demand.loc[demand["Fecha"] < target]
    row = build_online_features_ratio(available, target)
    online = model.predict(row.loc[:, loaded["predictor_columns"]])[0]
    stored = pd.read_parquet(tmp_path / "predictions.parquet").set_index("date")
    assert online == pytest.approx(stored.loc[target, "ratio_candidate_refit_2000_2021"])


def test_artifact_creation_rejects_a_phase12_run_that_selected_another_config(
    inputs, tmp_path, isolated_mlflow
) -> None:
    paths, _, _ = inputs
    load_script().run(
        **paths, **outputs(tmp_path), grid=[RatioConfig(7, "ratio", "relative_only", "v1_1_0")]
    )

    with pytest.raises(ValueError, match="different config"):
        create_serving_artifact_v1_2(
            features_path=paths["features_path"],
            daily_path=paths["daily_path"],
            results_path=tmp_path / "results.json",
            predictions_path=tmp_path / "predictions.parquet",
            metadata_path=tmp_path / "metadata.json",
            tracking_directory=tmp_path / "mlruns",
        )
    assert not (tmp_path / "metadata.json").exists()
