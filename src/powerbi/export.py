"""Orchestrates the Power BI dataset export (CSV star schema plus manifest)."""

import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ingestion.constants import INTERIM_OUTPUT
from powerbi import sources, transform

logger = logging.getLogger(__name__)

DEFAULT_START = date(2000, 1, 1)
DEFAULT_END = date(2023, 12, 31)
DEFAULT_OUTPUT_DIR = Path("data/powerbi")

PredictionLoader = Callable[[], tuple[pd.DataFrame, pd.DataFrame]]


def load_predictions_from_database() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read ``(predictions, models)`` from PostgreSQL; raises if the DB is unreachable."""
    from sqlalchemy import select

    from database.schema import energy_predictions_table, models_table
    from database.session import create_database_engine

    engine = create_database_engine()
    with engine.connect() as connection:
        predictions = pd.DataFrame(connection.execute(select(energy_predictions_table)).mappings())
        models = pd.DataFrame(connection.execute(select(models_table)).mappings())
    return predictions, models


def _safe_load_predictions(
    loader: PredictionLoader, skip_db: bool
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if skip_db:
        return pd.DataFrame(), pd.DataFrame()
    try:
        return loader()
    except Exception as error:  # noqa: BLE001 - any DB/config failure must not abort the export
        logger.warning("Predictions unavailable (%s); writing empty prediction tables", error)
        return pd.DataFrame(), pd.DataFrame()


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig writes a BOM so Power BI does not guess Windows-1252 for accented names.
    frame.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")


def run_export(
    start: date = DEFAULT_START,
    end: date = DEFAULT_END,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    demand_path: Path = INTERIM_OUTPUT,
    skip_network: bool = False,
    skip_db: bool = False,
    fetch_json: sources.FetchJson = sources.http_post_json,
    fetch_text: sources.FetchText = sources.http_get_text,
    prediction_loader: PredictionLoader = load_predictions_from_database,
) -> dict[str, Any]:
    """Build every table, write CSVs to ``output_dir`` and return the manifest."""
    cache_dir = output_dir / "cache"
    use_network = not skip_network

    demand = pd.read_parquet(demand_path)
    demand = demand.loc[
        (pd.to_datetime(demand["Fecha"]).dt.date >= start)
        & (pd.to_datetime(demand["Fecha"]).dt.date <= end)
    ]
    series = {
        column: sources.fetch_xm_metric(
            metric, start, end, fetch_json=fetch_json, cache_dir=cache_dir, use_network=use_network
        )
        for metric, column in sources.XM_METRICS.items()
    }
    oni = sources.fetch_oni(fetch_text=fetch_text, cache_dir=cache_dir, use_network=use_network)
    oni = oni.loc[
        (oni["year"] * 100 + oni["month"]).between(
            start.year * 100 + start.month, end.year * 100 + end.month
        )
    ]
    predictions, models = _safe_load_predictions(prediction_loader, skip_db)

    fact_prediction = transform.build_fact_prediction(predictions, models)
    calendar_end = end
    if not predictions.empty:
        calendar_end = max(end, pd.to_datetime(predictions["target_date"]).max().date())

    tables = {
        "dim_date": transform.build_dim_date(start, calendar_end),
        "fact_demand_daily": transform.build_fact_demand_daily(demand),
        "fact_market_daily": transform.build_fact_market_daily(
            series["spot_price_cop_kwh"],
            series["reservoir_fraction"],
            series["inflows_kwh"],
        ),
        "dim_enso_monthly": transform.build_dim_enso_monthly(oni),
        "dim_model": transform.build_dim_model(models),
        "fact_prediction": fact_prediction,
    }
    for name, frame in tables.items():
        write_csv(frame, output_dir / f"{name}.csv")

    manifest = _build_manifest(tables, start, end)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def _key_range(frame: pd.DataFrame, column: str) -> list[int | None]:
    if frame.empty:
        return [None, None]
    return [int(frame[column].min()), int(frame[column].max())]


def _build_manifest(tables: dict[str, pd.DataFrame], start: date, end: date) -> dict[str, Any]:
    key_columns = {"dim_enso_monthly": "year_month"}
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "requested_range": [start.isoformat(), end.isoformat()],
        "tables": {
            name: {
                "rows": int(len(frame)),
                "columns": list(frame.columns),
                "key_range": _key_range(frame, key_columns.get(name, "date_key"))
                if name not in {"dim_model"}
                else None,
            }
            for name, frame in tables.items()
        },
        "sources": {
            "demand": "data/interim/energy_demand_daily.parquet (XM SIN daily demand)",
            "market": f"{sources.XM_DAILY_URL} metrics {', '.join(sources.XM_METRICS)}",
            "enso": sources.ONI_URL,
            "predictions": "PostgreSQL energy_predictions/models (optional)",
        },
    }
