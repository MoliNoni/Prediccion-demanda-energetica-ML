import pandas as pd
import pytest

from evaluation.run_evaluation_v2 import compare_v1_v2


def prediction_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.to_datetime(["2020-01-01", "2022-01-01"])
    common = {"target_date": dates, "target_h1": [100.0, 200.0], "split": ["validation", "test"]}
    return (
        pd.DataFrame({**common, "HistGradientBoostingRegressor_prediction": [110.0, 220.0]}),
        pd.DataFrame(
            {**common, "HistGradientBoostingRegressor_v2_prediction": [105.0, 210.0]}
        ),
    )


def test_comparison_reports_absolute_and_relative_differences() -> None:
    comparison = compare_v1_v2(*prediction_frames())
    validation = comparison["results"][0]

    assert validation["v2_hgb"]["mae"] < validation["v1_hgb"]["mae"]
    assert validation["difference"]["wape"]["absolute_v2_minus_v1"] < 0
    assert comparison["test_used_for_selection"] is False


def test_comparison_rejects_unaligned_prediction_dates() -> None:
    v1, v2 = prediction_frames()
    v2.loc[0, "target_date"] = pd.Timestamp("2020-01-02")

    with pytest.raises(ValueError, match="not aligned"):
        compare_v1_v2(v1, v2)
