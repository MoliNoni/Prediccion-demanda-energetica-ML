import numpy as np
import pandas as pd
import pytest

from evaluation.temporal_sensitivity import compare_alternative_temporal_split
from features.contracts import FEATURE_CONTRACT_V2
from models.training import PREDICTOR_COLUMNS


def feature_frame(columns: tuple[str, ...]) -> pd.DataFrame:
    dates = pd.date_range("2015-01-01", "2023-12-31", freq="D")
    frame = pd.DataFrame({"target_date": dates, "target_h1": np.arange(len(dates), dtype=float)})
    for position, column in enumerate(columns, start=1):
        frame[column] = position + np.arange(len(dates), dtype=float) / 100
    return frame


def test_alternative_split_excludes_pandemic_years_from_training_and_selection() -> None:
    result = compare_alternative_temporal_split(
        feature_frame(PREDICTOR_COLUMNS),
        feature_frame(FEATURE_CONTRACT_V2.predictor_columns),
    )

    assert result["alternative_split"]["train"] == "2015-2019"
    assert result["alternative_split"]["excluded_extraordinary_period"] == "2020-2021"
    assert [item["year"] for item in result["results"]] == [2022, 2023]
    assert result["results"][0]["split"] == "validation"
    assert result["test_used_for_selection"] is False


def test_alternative_split_rejects_unaligned_v1_and_v2_dates() -> None:
    v1 = feature_frame(PREDICTOR_COLUMNS)
    v2 = feature_frame(FEATURE_CONTRACT_V2.predictor_columns)
    v2 = v2.loc[v2["target_date"] != pd.Timestamp("2022-01-01")].copy()

    with pytest.raises(ValueError, match="not aligned"):
        compare_alternative_temporal_split(v1, v2)
