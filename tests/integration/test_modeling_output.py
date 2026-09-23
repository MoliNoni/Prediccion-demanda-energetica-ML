from pathlib import Path

import pandas as pd

from models.training import PREDICTIONS_OUTPUT, run_modeling


def test_modeling_output_contains_validation_and_test(tmp_path: Path) -> None:
    dates = pd.date_range("2000-01-29", "2023-12-30", freq="D")
    frame = pd.DataFrame(
        {
            "reference_date": dates,
            "target_date": dates + pd.Timedelta(days=1),
            "lag_1": 1.0,
            "lag_7": 2.0,
            "lag_14": 3.0,
            "lag_28": 4.0,
            "rolling_mean_7": 5.0,
            "rolling_std_7": 1.0,
            "rolling_mean_14": 6.0,
            "rolling_std_14": 1.0,
            "rolling_mean_28": 7.0,
            "rolling_std_28": 1.0,
            "weekday": dates.weekday,
            "day_of_month": dates.day,
            "month": dates.month,
            "iso_week": dates.isocalendar().week.astype("int64"),
            "day_of_year": dates.dayofyear,
            "weekend": (dates.weekday >= 5).astype(int),
            "weekday_sin": 0.0,
            "weekday_cos": 1.0,
            "month_sin": 0.0,
            "month_cos": 1.0,
            "day_of_year_sin": 0.0,
            "day_of_year_cos": 1.0,
            "target_h1": range(len(dates)),
        }
    )
    source = tmp_path / "features.parquet"
    output = tmp_path / "predictions.parquet"
    metadata = tmp_path / "metadata.json"
    frame.to_parquet(source, index=False)

    result, _ = run_modeling(source, output, metadata)

    assert output.exists()
    assert metadata.exists()
    assert len(pd.read_parquet(output)) == len(result)
    assert set(result["split"]) == {"validation", "test"}
    assert PREDICTIONS_OUTPUT.name == "model_predictions_h1.parquet"
