import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from ingestion.constants import EXPECTED_COLUMNS
from powerbi.export import run_export


def _fake_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
    value = "0.5" if body["MetricId"] == "PorcVoluUtilDiar" else "100.0"
    return {
        "Items": [{"Date": body["StartDate"], "DailyEntities": [{"Id": "Sistema", "Value": value}]}]
    }


def _failing_loader() -> tuple[pd.DataFrame, pd.DataFrame]:
    raise ConnectionError("db down")


def test_export_writes_star_schema_and_survives_unreachable_database(tmp_path: Path) -> None:
    parquet = tmp_path / "demand.parquet"
    pd.DataFrame(
        [[pd.Timestamp("2023-01-01"), 1.0, 2.0, 0.0, 0.0, 0.0]], columns=EXPECTED_COLUMNS
    ).to_parquet(parquet)
    oni_text = "SEAS YR TOTAL ANOM\n DJF 2023 26.5 -0.7\n"
    out = tmp_path / "out"

    manifest = run_export(
        date(2023, 1, 1),
        date(2023, 1, 31),
        output_dir=out,
        demand_path=parquet,
        fetch_json=_fake_json,
        fetch_text=lambda url: oni_text,
        prediction_loader=_failing_loader,
    )

    assert manifest["tables"]["dim_date"]["rows"] == 31
    assert manifest["tables"]["fact_demand_daily"]["rows"] == 1
    assert manifest["tables"]["fact_market_daily"]["rows"] == 1
    assert manifest["tables"]["dim_enso_monthly"]["rows"] == 1
    assert manifest["tables"]["fact_prediction"]["rows"] == 0
    raw = (out / "fact_prediction.csv").read_bytes()
    # The BOM makes Power BI detect UTF-8 instead of Windows-1252 (keeps "Niña", "Miércoles").
    assert raw.startswith(b"\xef\xbb\xbf")
    header = raw.decode("utf-8-sig").strip()
    assert header == "date_key,model_key,predicted_kwh,actual_kwh"
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["tables"]
