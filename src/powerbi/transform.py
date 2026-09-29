"""Pure transformations that build the star-schema tables for Power BI."""

from datetime import date, timedelta

import pandas as pd

from ingestion.constants import EXPECTED_COLUMNS
from powerbi.sources import enso_phase

MONTH_NAMES_ES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
WEEKDAY_NAMES_ES = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")

SCHEMAS: dict[str, tuple[list[str], list[str]]] = {
    "dim_date": (
        [
            "date_key",
            "date",
            "year",
            "quarter",
            "month",
            "month_name_es",
            "year_month",
            "iso_week",
            "weekday_number",
            "weekday_name_es",
            "is_weekend",
            "is_colombian_holiday",
            "holiday_name",
        ],
        ["date_key"],
    ),
    "fact_demand_daily": (
        ["date_key", "demand_kwh", "generation_kwh", "unserved_kwh", "exports_kwh", "imports_kwh"],
        ["date_key"],
    ),
    "fact_market_daily": (
        ["date_key", "spot_price_cop_kwh", "reservoir_pct", "inflows_kwh"],
        ["date_key"],
    ),
    "dim_enso_monthly": (
        ["year_month", "year", "month", "oni_anom", "enso_phase"],
        ["year_month"],
    ),
    "dim_model": (
        ["model_key", "model_name", "model_version", "horizon_days", "is_active", "created_at"],
        ["model_key"],
    ),
    "fact_prediction": (
        ["date_key", "model_key", "predicted_kwh", "actual_kwh"],
        ["date_key", "model_key"],
    ),
}


class SchemaValidationError(ValueError):
    """Raised when a table breaks its declared columns or key uniqueness."""


def validate_table(name: str, frame: pd.DataFrame) -> pd.DataFrame:
    columns, key = SCHEMAS[name]
    if list(frame.columns) != columns:
        raise SchemaValidationError(
            f"{name}: expected columns {columns}, got {list(frame.columns)}"
        )
    if frame.duplicated(key).any():
        raise SchemaValidationError(f"{name}: duplicate values for key {key}")
    return frame


def to_date_key(values: pd.Series) -> pd.Series:
    """Convert a datetime-like series to integer ``yyyymmdd`` keys."""
    return pd.to_datetime(values).dt.strftime("%Y%m%d").astype("int64")


def easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Meeus/Jones/Butcher algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    weekday_offset = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday_offset) // 451
    month, day = divmod(h + weekday_offset - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _next_monday(value: date) -> date:
    """Ley Emiliani: a holiday not falling on Monday moves to the following Monday."""
    return value + timedelta(days=(7 - value.weekday()) % 7)


def colombian_holidays(year: int) -> dict[date, str]:
    """Return the Colombian public holidays of ``year`` as ``{date: name}``."""
    easter = easter_sunday(year)
    holidays: dict[date, str] = {
        date(year, 1, 1): "Año Nuevo",
        date(year, 5, 1): "Día del Trabajo",
        date(year, 7, 20): "Día de la Independencia",
        date(year, 8, 7): "Batalla de Boyacá",
        date(year, 12, 8): "Inmaculada Concepción",
        date(year, 12, 25): "Navidad",
        easter - timedelta(days=3): "Jueves Santo",
        easter - timedelta(days=2): "Viernes Santo",
        # Ascension, Corpus Christi and Sagrado Corazón are already their Monday-moved dates.
        easter + timedelta(days=43): "Ascensión del Señor",
        easter + timedelta(days=64): "Corpus Christi",
        easter + timedelta(days=71): "Sagrado Corazón",
    }
    moved = {
        date(year, 1, 6): "Reyes Magos",
        date(year, 3, 19): "San José",
        date(year, 6, 29): "San Pedro y San Pablo",
        date(year, 8, 15): "Asunción de la Virgen",
        date(year, 10, 12): "Día de la Raza",
        date(year, 11, 1): "Todos los Santos",
        date(year, 11, 11): "Independencia de Cartagena",
    }
    for original, name in moved.items():
        holidays[_next_monday(original)] = name
    return holidays


def build_dim_date(start: date, end: date) -> pd.DataFrame:
    holidays: dict[date, str] = {}
    for year in range(start.year, end.year + 1):
        holidays.update(colombian_holidays(year))
    frame = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
    frame["date_key"] = to_date_key(frame["date"])
    frame["year"] = frame["date"].dt.year
    frame["quarter"] = frame["date"].dt.quarter
    frame["month"] = frame["date"].dt.month
    frame["month_name_es"] = frame["month"].map(lambda m: MONTH_NAMES_ES[m - 1])
    frame["year_month"] = frame["year"] * 100 + frame["month"]
    frame["iso_week"] = frame["date"].dt.isocalendar().week.astype("int64")
    frame["weekday_number"] = frame["date"].dt.weekday + 1  # 1 = Monday
    frame["weekday_name_es"] = frame["weekday_number"].map(lambda d: WEEKDAY_NAMES_ES[d - 1])
    frame["is_weekend"] = frame["weekday_number"] >= 6
    frame["holiday_name"] = frame["date"].dt.date.map(holidays).fillna("")
    frame["is_colombian_holiday"] = frame["holiday_name"] != ""
    frame["date"] = frame["date"].dt.date
    return validate_table("dim_date", frame[SCHEMAS["dim_date"][0]])


def build_fact_demand_daily(demand: pd.DataFrame) -> pd.DataFrame:
    """Map the ingested daily parquet (Spanish column names) to the demand fact table."""
    missing = set(EXPECTED_COLUMNS).difference(demand.columns)
    if missing:
        raise SchemaValidationError(f"demand input is missing columns {sorted(missing)}")
    frame = pd.DataFrame(
        {
            "date_key": to_date_key(demand["Fecha"]),
            "demand_kwh": demand["Demanda Energia SIN kWh"],
            "generation_kwh": demand["Generación kWh"],
            "unserved_kwh": demand["Demanda No Atendida kWh"],
            "exports_kwh": demand["Exportaciones kWh"],
            "imports_kwh": demand["Importaciones kWh"],
        }
    )
    return validate_table("fact_demand_daily", frame.sort_values("date_key", ignore_index=True))


def build_fact_market_daily(
    price: pd.DataFrame, reservoir: pd.DataFrame, inflows: pd.DataFrame
) -> pd.DataFrame:
    """Combine three XM ``date, value`` series; the reservoir fraction becomes a percentage."""
    merged = (
        price.rename(columns={"value": "spot_price_cop_kwh"})
        .merge(
            reservoir.assign(reservoir_pct=reservoir["value"] * 100).drop(columns="value"),
            on="date",
            how="outer",
        )
        .merge(inflows.rename(columns={"value": "inflows_kwh"}), on="date", how="outer")
    )
    merged["date_key"] = to_date_key(merged["date"]) if len(merged) else pd.Series(dtype="int64")
    if not merged["reservoir_pct"].dropna().between(0, 100).all():
        raise SchemaValidationError("reservoir_pct outside 0..100")
    out = merged[SCHEMAS["fact_market_daily"][0]].sort_values("date_key", ignore_index=True)
    return validate_table("fact_market_daily", out)


def build_dim_enso_monthly(oni: pd.DataFrame) -> pd.DataFrame:
    frame = oni.copy()
    frame["year_month"] = frame["year"] * 100 + frame["month"]
    frame["enso_phase"] = frame["oni_anom"].map(enso_phase)
    frame = frame[SCHEMAS["dim_enso_monthly"][0]].sort_values("year_month", ignore_index=True)
    return validate_table("dim_enso_monthly", frame)


def _ordered_models(models: pd.DataFrame) -> pd.DataFrame:
    return models.sort_values(["name", "version"], ignore_index=True)


def build_dim_model(models: pd.DataFrame) -> pd.DataFrame:
    """Build the model dimension from the ``models`` DB table (empty input allowed)."""
    columns, _ = SCHEMAS["dim_model"]
    if models.empty:
        return pd.DataFrame(columns=columns)
    ordered = _ordered_models(models)
    frame = pd.DataFrame(
        {
            "model_key": range(1, len(ordered) + 1),
            "model_name": ordered["name"],
            "model_version": ordered["version"],
            "horizon_days": ordered["horizon"],
            "is_active": ordered["is_active"],
            "created_at": pd.to_datetime(ordered["created_at"]).dt.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )
    return validate_table("dim_model", frame)


def build_fact_prediction(predictions: pd.DataFrame, models: pd.DataFrame) -> pd.DataFrame:
    """Join stored predictions to model surrogate keys (empty input allowed)."""
    columns, _ = SCHEMAS["fact_prediction"]
    if predictions.empty or models.empty:
        return pd.DataFrame(columns=columns)
    ordered = _ordered_models(models)
    key_by_id = {str(model_id): key for key, model_id in enumerate(ordered["id"], start=1)}
    frame = pd.DataFrame(
        {
            "date_key": to_date_key(predictions["target_date"]),
            "model_key": predictions["model_id"].astype(str).map(key_by_id),
            "predicted_kwh": predictions["predicted_demand_kwh"],
            "actual_kwh": predictions["actual_demand_kwh"],
        }
    )
    frame = frame.dropna(subset=["model_key"]).astype({"model_key": "int64"})
    frame = frame.sort_values(["date_key", "model_key"], ignore_index=True)
    return validate_table("fact_prediction", frame)
