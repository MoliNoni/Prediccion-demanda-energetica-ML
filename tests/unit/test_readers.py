from pathlib import Path

import pandas as pd
import pytest

from ingestion.constants import EXPECTED_COLUMNS
from ingestion.readers import UnsupportedFormatError, read_spreadsheet


def test_xlsx_reader_uses_openpyxl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_read_excel(path: Path, **kwargs: object) -> pd.DataFrame:
        captured.update(kwargs)
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    monkeypatch.setattr(
        pd,
        "ExcelFile",
        lambda *args, **kwargs: type("Workbook", (), {"sheet_names": ["Demanda_Energia_SIN"]})(),
    )

    read_spreadsheet(tmp_path / "source.xlsx")

    assert captured["engine"] == "openpyxl"
    assert captured["sheet_name"] == "Demanda_Energia_SIN"
    assert captured["header"] == 3


def test_reads_valid_xlsx(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    frame = pd.DataFrame([["2023-01-01", 10, 11, None, None, None]], columns=EXPECTED_COLUMNS)
    frame.to_excel(source, sheet_name="Demanda_Energia_SIN", startrow=3, index=False)

    result = read_spreadsheet(source)

    assert result["Fecha"].tolist() == ["2023-01-01"]
    assert result["Demanda Energia SIN kWh"].tolist() == [10]
    assert result["Generación kWh"].tolist() == [11]
    assert result["Importaciones kWh"].isna().all()


def test_missing_column_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    incomplete = pd.DataFrame(columns=EXPECTED_COLUMNS[:-1])
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: incomplete)
    monkeypatch.setattr(
        pd,
        "ExcelFile",
        lambda *args, **kwargs: type("Workbook", (), {"sheet_names": ["Demanda_Energia_SIN"]})(),
    )

    with pytest.raises(ValueError, match="Unexpected columns"):
        read_spreadsheet(tmp_path / "source.xlsx")


def test_xls_reader_uses_xlrd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_read_excel(path: Path, **kwargs: object) -> pd.DataFrame:
        captured.update(kwargs)
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    monkeypatch.setattr(
        pd,
        "ExcelFile",
        lambda *args, **kwargs: type(
            "Workbook", (), {"sheet_names": ["Demanda_Energia_SIN.rdl"]}
        )(),
    )

    read_spreadsheet(tmp_path / "source.xls")

    assert captured["engine"] == "xlrd"


def test_unsupported_format_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedFormatError):
        read_spreadsheet(tmp_path / "source.csv")


def test_unapproved_sheet_name_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        pd,
        "ExcelFile",
        lambda *args, **kwargs: type("Workbook", (), {"sheet_names": ["Other"]})(),
    )

    with pytest.raises(ValueError, match="Expected sheet not found"):
        read_spreadsheet(tmp_path / "source.xlsx")
