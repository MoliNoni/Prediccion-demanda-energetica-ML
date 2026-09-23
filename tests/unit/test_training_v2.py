import numpy as np
import pandas as pd

from features.contracts import FEATURE_CONTRACT_V2
from models.training_v2 import PREDICTOR_COLUMNS_V2, train_and_predict_v2


def v2_frame() -> pd.DataFrame:
    dates = pd.date_range("2000-01-29", "2023-12-30", freq="D")
    frame = pd.DataFrame(index=dates)
    for position, column in enumerate(PREDICTOR_COLUMNS_V2, start=1):
        frame[column] = position + np.arange(len(dates)) / 1000
    frame["reference_date"] = dates
    frame["target_date"] = dates + pd.Timedelta(days=1)
    frame["target_h1"] = np.arange(len(dates), dtype=float)
    return frame.loc[:, FEATURE_CONTRACT_V2.feature_columns]


def test_v2_training_uses_only_v2_contract_and_generates_both_evaluations() -> None:
    predictions, metadata = train_and_predict_v2(v2_frame())

    assert metadata["feature_set_version"] == "v2"
    assert metadata["predictor_columns"] == list(PREDICTOR_COLUMNS_V2)
    assert set(predictions["split"]) == {"validation", "test"}
    assert predictions["HistGradientBoostingRegressor_v2_prediction"].notna().all()
