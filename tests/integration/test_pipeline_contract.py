from pathlib import Path

import pandas as pd

from ingestion.constants import EXPECTED_COLUMNS, INTERIM_OUTPUT
from ingestion.pipeline import run_ingestion


def test_pipeline_writes_parquet_and_audit(
    monkeypatch, tmp_path: Path
) -> None:
    frame = pd.DataFrame(
        [["2023-01-01", 10, 11, None, None, None]],
        columns=EXPECTED_COLUMNS,
    )
    source = tmp_path / "Demanda_Energia_SIN_2023.xlsx"
    source.touch()
    for year in range(2000, 2023):
        suffix = ".xls" if year in (2011, 2012) else ".xlsx"
        (tmp_path / f"Demanda_Energia_SIN_{year}{suffix}").touch()

    def fake_reader(path: Path) -> pd.DataFrame:
        year = int(path.stem.rsplit("_", 1)[-1])
        result = frame.copy()
        result["Fecha"] = [f"{year}-01-01"]
        return result

    monkeypatch.setattr("ingestion.pipeline.read_spreadsheet", fake_reader)
    monkeypatch.setattr(
        "ingestion.pipeline.resolve_sheet_name",
        lambda path: "Demanda_Energia_SIN.rdl"
        if path.suffix == ".xls"
        else "Demanda_Energia_SIN",
    )
    output = tmp_path / "energy_demand_daily.parquet"
    audit_output = tmp_path / "ingestion_audit.json"

    audits = run_ingestion(tmp_path, output, audit_output)

    assert len(audits) == 24
    assert output.exists()
    assert audit_output.exists()
    assert pd.read_parquet(output).columns.tolist() == list(EXPECTED_COLUMNS)
    assert INTERIM_OUTPUT.name == "energy_demand_daily.parquet"
