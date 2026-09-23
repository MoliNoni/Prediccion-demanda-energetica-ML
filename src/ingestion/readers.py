from pathlib import Path

import pandas as pd

from ingestion.constants import ALTERNATIVE_SHEET, EXPECTED_COLUMNS, EXPECTED_SHEET


class UnsupportedFormatError(ValueError):
    """Raised when a source file is not an approved spreadsheet format."""


class SpreadsheetReadError(ValueError):
    """Raised when an approved spreadsheet cannot be read."""


def resolve_sheet_name(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        raise UnsupportedFormatError(f"Unsupported spreadsheet format: {path.suffix}")
    engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
    try:
        sheet_names = pd.ExcelFile(path, engine=engine).sheet_names
    except Exception as error:
        raise SpreadsheetReadError(f"Could not inspect {path.name}: {error}") from error
    for accepted_name in (EXPECTED_SHEET, ALTERNATIVE_SHEET):
        if accepted_name in sheet_names:
            return accepted_name
    raise SpreadsheetReadError(
        f"Expected sheet not found in {path.name}; accepted names are "
        f"{EXPECTED_SHEET!r} and {ALTERNATIVE_SHEET!r}"
    )


def read_spreadsheet(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        engine = "openpyxl"
    elif suffix == ".xls":
        engine = "xlrd"
    else:
        raise UnsupportedFormatError(f"Unsupported spreadsheet format: {path.suffix}")

    sheet_name = resolve_sheet_name(path)
    try:
        frame = pd.read_excel(
            path,
            sheet_name=sheet_name,
            header=3,
            engine=engine,
        )
    except Exception as error:
        raise SpreadsheetReadError(f"Could not read {path.name}: {error}") from error

    if tuple(frame.columns) != EXPECTED_COLUMNS:
        raise ValueError(
            f"Unexpected columns in {path.name}: {tuple(frame.columns)!r}"
        )
    return frame
