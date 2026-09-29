from datetime import date
from uuid import uuid4

import pandas as pd
import pytest

from ingestion.constants import EXPECTED_COLUMNS
from powerbi.sources import enso_phase
from powerbi.transform import (
    SchemaValidationError,
    build_dim_date,
    build_dim_enso_monthly,
    build_dim_model,
    build_fact_demand_daily,
    build_fact_market_daily,
    build_fact_prediction,
    colombian_holidays,
    easter_sunday,
)


def test_easter_sunday_known_dates() -> None:
    assert easter_sunday(2023) == date(2023, 4, 9)
    assert easter_sunday(2020) == date(2020, 4, 12)
    assert easter_sunday(2000) == date(2000, 4, 23)


@pytest.mark.parametrize(
    ("expected", "name"),
    [
        (date(2023, 1, 1), "Año Nuevo"),
        (date(2023, 1, 9), "Reyes Magos"),
        (date(2023, 3, 20), "San José"),
        (date(2023, 4, 6), "Jueves Santo"),
        (date(2023, 4, 7), "Viernes Santo"),
        (date(2023, 5, 1), "Día del Trabajo"),
        (date(2023, 5, 22), "Ascensión del Señor"),
        (date(2023, 6, 12), "Corpus Christi"),
        (date(2023, 6, 19), "Sagrado Corazón"),
        (date(2023, 7, 3), "San Pedro y San Pablo"),
        (date(2023, 7, 20), "Día de la Independencia"),
        (date(2023, 8, 7), "Batalla de Boyacá"),
        (date(2023, 8, 21), "Asunción de la Virgen"),
        (date(2023, 10, 16), "Día de la Raza"),
        (date(2023, 11, 6), "Todos los Santos"),
        (date(2023, 11, 13), "Independencia de Cartagena"),
        (date(2023, 12, 8), "Inmaculada Concepción"),
        (date(2023, 12, 25), "Navidad"),
    ],
)
def test_colombian_holidays_2023(expected: date, name: str) -> None:
    assert colombian_holidays(2023)[expected] == name


def test_colombian_holidays_2023_count_and_all_moved_are_mondays() -> None:
    holidays = colombian_holidays(2023)

    assert len(holidays) == 18
    monday_names = {
        "Reyes Magos", "San José", "Ascensión del Señor", "Corpus Christi", "Sagrado Corazón",
        "San Pedro y San Pablo", "Asunción de la Virgen", "Día de la Raza", "Todos los Santos",
        "Independencia de Cartagena",
    }  # fmt: skip
    assert all(day.weekday() == 0 for day, name in holidays.items() if name in monday_names)


def test_dim_date_is_unique_complete_and_flags_calendar_attributes() -> None:
    frame = build_dim_date(date(2023, 1, 1), date(2023, 12, 31))

    assert len(frame) == 365
    assert frame["date_key"].is_unique
    row = frame.loc[frame["date_key"] == 20230109].iloc[0]
    assert row["is_colombian_holiday"]
    assert row["weekday_name_es"] == "Lunes"
    assert row["month_name_es"] == "Enero"
    assert row["year_month"] == 202301
    saturday = frame.loc[frame["date_key"] == 20230107].iloc[0]
    assert saturday["is_weekend"]
    assert not saturday["is_colombian_holiday"]
    assert frame["is_colombian_holiday"].sum() == 18


def _demand_frame(dates: list[str]) -> pd.DataFrame:
    rows = [[pd.Timestamp(d), 100.0 + i, 90.0, 0.0, 1.0, 2.0] for i, d in enumerate(dates)]
    return pd.DataFrame(rows, columns=EXPECTED_COLUMNS)


def test_fact_demand_maps_columns_and_rejects_duplicates() -> None:
    fact = build_fact_demand_daily(_demand_frame(["2023-01-02", "2023-01-01"]))

    assert fact["date_key"].tolist() == [20230101, 20230102]
    assert "demand_kwh" in fact.columns

    with pytest.raises(SchemaValidationError):
        build_fact_demand_daily(_demand_frame(["2023-01-01", "2023-01-01"]))
    with pytest.raises(SchemaValidationError):
        build_fact_demand_daily(_demand_frame(["2023-01-01"]).drop(columns=["Fecha"]))


def test_fact_market_merges_series_and_converts_reservoir_to_percent() -> None:
    price = pd.DataFrame({"date": [date(2023, 3, 1), date(2023, 3, 2)], "value": [300.0, 310.0]})
    reservoir = pd.DataFrame({"date": [date(2023, 3, 1)], "value": [0.65]})
    inflows = pd.DataFrame({"date": [date(2023, 3, 2)], "value": [5.0e7]})

    fact = build_fact_market_daily(price, reservoir, inflows)

    assert fact["date_key"].tolist() == [20230301, 20230302]
    assert fact["reservoir_pct"].iloc[0] == pytest.approx(65.0)
    assert pd.isna(fact["reservoir_pct"].iloc[1])
    assert fact["inflows_kwh"].iloc[1] == 5.0e7


def test_fact_market_rejects_negative_reservoir() -> None:
    empty = pd.DataFrame({"date": [date(2023, 3, 1)], "value": [1.0]})
    with pytest.raises(SchemaValidationError):
        build_fact_market_daily(empty, empty.assign(value=-0.1), empty)


def test_fact_market_nulls_reservoir_above_full_capacity(caplog: pytest.LogCaptureFixture) -> None:
    # XM reports 140-149% for January 2000, an artefact at the start of the series.
    days = [date(2000, 1, 31), date(2000, 2, 1)]
    price = pd.DataFrame({"date": days, "value": [30.0, 31.0]})
    reservoir = pd.DataFrame({"date": days, "value": [1.40638, 0.74938]})

    fact = build_fact_market_daily(price, reservoir, price)

    assert pd.isna(fact["reservoir_pct"].iloc[0])
    assert fact["reservoir_pct"].iloc[1] == pytest.approx(74.938)
    assert "1 reservoir values above 100%" in caplog.text


def test_enso_phase_thresholds_and_dimension() -> None:
    assert enso_phase(0.5) == "El Niño"
    assert enso_phase(-0.5) == "La Niña"
    assert enso_phase(0.49) == "Neutral"

    oni = pd.DataFrame({"year": [2023, 2023], "month": [1, 12], "oni_anom": [-0.71, 1.95]})
    dim = build_dim_enso_monthly(oni)

    assert dim["year_month"].tolist() == [202301, 202312]
    assert dim["enso_phase"].tolist() == ["La Niña", "El Niño"]


def test_prediction_tables_join_models_and_allow_empty_input() -> None:
    model_id = uuid4()
    models = pd.DataFrame(
        [
            {
                "id": model_id, "name": "ridge", "version": "1", "horizon": 1,
                "is_active": True, "created_at": pd.Timestamp("2024-01-01T10:00:00Z"),
            }
        ]
    )  # fmt: skip
    predictions = pd.DataFrame(
        [
            {
                "target_date": date(2024, 1, 2), "predicted_demand_kwh": 10.0,
                "actual_demand_kwh": None, "model_id": model_id,
            }
        ]
    )  # fmt: skip

    dim = build_dim_model(models)
    fact = build_fact_prediction(predictions, models)

    assert dim["model_key"].tolist() == [1]
    assert fact.iloc[0].to_dict()["date_key"] == 20240102
    assert fact["model_key"].tolist() == [1]

    empty = build_fact_prediction(pd.DataFrame(), pd.DataFrame())
    assert empty.empty
    assert list(empty.columns) == ["date_key", "model_key", "predicted_kwh", "actual_kwh"]
    assert build_dim_model(pd.DataFrame()).empty
