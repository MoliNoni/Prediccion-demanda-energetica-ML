import numpy as np
import pandas as pd

from features.pipeline import FEATURE_COLUMNS
from models.training import (
    PREDICTOR_COLUMNS,
    build_baseline,
    split_temporally,
    train_and_predict,
)


def modeling_frame() -> pd.DataFrame:
    dates = pd.date_range("2000-01-29", "2023-12-30", freq="D")
    frame = pd.DataFrame(index=dates)
    for position, column in enumerate(PREDICTOR_COLUMNS, start=1):
        frame[column] = position + np.arange(len(dates)) / 1000
    frame["reference_date"] = dates
    frame["target_date"] = dates + pd.Timedelta(days=1)
    frame["target_h1"] = np.arange(len(dates), dtype=float)
    return frame.loc[:, FEATURE_COLUMNS]


def test_temporal_split_is_disjoint_and_ordered() -> None:
    split = split_temporally(modeling_frame())

    assert split.train["target_date"].dt.year.max() == 2019
    assert set(split.validation["target_date"].dt.year.unique()) == {2020, 2021}
    assert set(split.test["target_date"].dt.year.unique()) == {2022, 2023}
    assert split.train["target_date"].max() < split.validation["target_date"].min()
    assert split.validation["target_date"].max() < split.test["target_date"].min()


def test_baseline_uses_weekly_lag() -> None:
    frame = pd.DataFrame({"lag_7": [10.0, 20.0]})

    assert build_baseline(frame).tolist() == [10.0, 20.0]


def test_training_generates_validation_and_test_predictions() -> None:
    predictions, metadata = train_and_predict(modeling_frame())

    assert set(predictions["split"]) == {"validation", "test"}
    assert len(predictions) == metadata["validation_records"] + metadata["test_records"]
    assert predictions["baseline_prediction"].notna().all()
    assert predictions["RandomForestRegressor_prediction"].notna().all()
    assert predictions["HistGradientBoostingRegressor_prediction"].notna().all()
    assert set(PREDICTOR_COLUMNS).isdisjoint({"target_h1", "reference_date", "target_date"})
