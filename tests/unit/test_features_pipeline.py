import numpy as np
import pandas as pd
import pytest

from features.pipeline import FEATURE_COLUMNS, create_features
from ingestion.constants import EXPECTED_COLUMNS, TARGET_COLUMN


def source_frame(dates: list[str], values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Fecha": dates,
            TARGET_COLUMN: values,
            "Generación kWh": values,
            "Demanda No Atendida kWh": [None] * len(dates),
            "Exportaciones kWh": [None] * len(dates),
            "Importaciones kWh": [None] * len(dates),
        },
        columns=EXPECTED_COLUMNS,
    )


def test_lags_use_exact_calendar_dates() -> None:
    dates = pd.date_range("2023-01-01", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
    result = create_features(source_frame(dates, list(range(40))))
    row = result.loc[result["reference_date"] == pd.Timestamp("2023-01-29")].iloc[0]

    assert row["lag_1"] == 27
    assert row["lag_7"] == 21
    assert row["lag_14"] == 14
    assert row["lag_28"] == 0


def test_rolling_uses_shifted_past_only() -> None:
    dates = pd.date_range("2023-01-01", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
    result = create_features(source_frame(dates, list(range(40))))
    row = result.loc[result["reference_date"] == pd.Timestamp("2023-01-29")].iloc[0]

    assert row["rolling_mean_7"] == pytest.approx(sum(range(21, 28)) / 7)
    assert row["rolling_std_7"] == pytest.approx(np.std(range(21, 28), ddof=1))
    assert row["rolling_mean_28"] == pytest.approx(sum(range(0, 28)) / 28)


def test_calendar_and_cyclic_features() -> None:
    dates = pd.date_range("2023-01-01", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
    result = create_features(source_frame(dates, list(range(40))))
    row = result.loc[result["reference_date"] == pd.Timestamp("2023-01-29")].iloc[0]

    assert row["weekday"] == 6
    assert row["day_of_month"] == 29
    assert row["month"] == 1
    assert row["iso_week"] == 4
    assert row["day_of_year"] == 29
    assert row["weekend"] == 1
    assert row["weekday_sin"] == pytest.approx(np.sin(2 * np.pi * 6 / 7))
    assert row["month_sin"] == 0


def test_h1_alignment_and_feature_columns() -> None:
    dates = pd.date_range("2023-01-01", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
    result = create_features(source_frame(dates, list(range(40))))
    row = result.loc[result["reference_date"] == pd.Timestamp("2023-01-29")].iloc[0]

    assert row["target_date"] == pd.Timestamp("2023-01-30")
    assert row["target_h1"] == 29
    assert result.columns.tolist() == list(FEATURE_COLUMNS)
    assert not any(column in result.columns for column in EXPECTED_COLUMNS[2:])


def test_gap_is_not_crossed_by_lags_or_rolling() -> None:
    dates = pd.date_range("2015-12-01", "2016-01-10", freq="D")
    dates = dates[dates != pd.Timestamp("2015-12-31")].strftime("%Y-%m-%d").tolist()
    result = create_features(source_frame(dates, list(range(len(dates)))))

    assert pd.Timestamp("2015-12-31") not in result["reference_date"].tolist()
    assert pd.Timestamp("2016-01-01") not in result["reference_date"].tolist()


def test_requires_28_days_and_h1_target() -> None:
    dates = pd.date_range("2023-01-01", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
    result = create_features(source_frame(dates, list(range(40))))

    assert result["reference_date"].min() == pd.Timestamp("2023-01-29")
    assert result["reference_date"].max() == pd.Timestamp("2023-02-08")
    assert len(result) == 11
