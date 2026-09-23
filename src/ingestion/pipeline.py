import json
from pathlib import Path

import pandas as pd

from ingestion.constants import (
    AUDIT_OUTPUT,
    EXPECTED_COLUMNS,
    EXPECTED_SHEET,
    INTERIM_OUTPUT,
    RAW_DIRECTORY,
)
from ingestion.readers import (
    SpreadsheetReadError,
    UnsupportedFormatError,
    read_spreadsheet,
    resolve_sheet_name,
)
from validation.audit import FileAudit, audit_frame, normalize_frame


class IngestionValidationError(RuntimeError):
    """Raised when one or more blocking ingestion validations fail."""


def expected_files(raw_directory: Path = RAW_DIRECTORY) -> list[tuple[int, Path]]:
    files = []
    for year in range(2000, 2024):
        suffix = ".xls" if year in (2011, 2012) else ".xlsx"
        files.append((year, raw_directory / f"Demanda_Energia_SIN_{year}{suffix}"))
    return files


def discover_files(raw_directory: Path = RAW_DIRECTORY) -> list[tuple[int, Path]]:
    discovered = []
    missing = []
    for year, path in expected_files(raw_directory):
        if path.is_file():
            discovered.append((year, path))
        else:
            missing.append(path.name)
    if missing:
        raise IngestionValidationError("Missing expected files: " + ", ".join(missing))
    return discovered


def _global_missing_dates(frames: list[pd.DataFrame]) -> list[str]:
    if not frames:
        return []
    dates = pd.concat([frame["Fecha"] for frame in frames], ignore_index=True)
    expected = pd.date_range(dates.min(), dates.max(), freq="D")
    return [
        value.date().isoformat() for value in expected.difference(pd.DatetimeIndex(dates.unique()))
    ]


def run_ingestion(
    raw_directory: Path = RAW_DIRECTORY,
    interim_output: Path = INTERIM_OUTPUT,
    audit_output: Path = AUDIT_OUTPUT,
) -> list[FileAudit]:
    audits: list[FileAudit] = []
    normalized_frames: list[pd.DataFrame] = []
    blocking_errors: list[str] = []

    try:
        files = discover_files(raw_directory)
    except IngestionValidationError:
        raise

    for year, path in files:
        try:
            sheet_name = resolve_sheet_name(path)
            frame = read_spreadsheet(path)
            audit = audit_frame(frame, file_name=path.name, year=year)
            audit.sheet = sheet_name
            audits.append(audit)
            if not audit.blockers:
                normalized_frames.append(normalize_frame(frame))
        except (SpreadsheetReadError, UnsupportedFormatError, ValueError) as error:
            blocking_errors.append(f"{path.name}: {error}")
            audits.append(
                FileAudit(
                    file=path.name,
                    year=year,
                    format=path.suffix.lstrip("."),
                    blockers=[str(error)],
                )
            )

    if blocking_errors or any(audit.blockers for audit in audits):
        details = blocking_errors + [
            f"{audit.file}: {', '.join(audit.blockers)}" for audit in audits if audit.blockers
        ]
        raise IngestionValidationError("Blocking validations failed: " + " | ".join(details))

    consolidated = pd.concat(normalized_frames, ignore_index=True)
    consolidated = consolidated.sort_values("Fecha", kind="stable").reset_index(drop=True)
    duplicate_dates = int(consolidated["Fecha"].duplicated().sum())
    if duplicate_dates:
        raise IngestionValidationError(
            f"Global validation failed: {duplicate_dates} duplicate dates"
        )

    global_missing = _global_missing_dates(normalized_frames)

    interim_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    consolidated.to_parquet(interim_output, index=False)
    audit_payload = {
        "sheet": EXPECTED_SHEET,
        "columns": list(EXPECTED_COLUMNS),
        "processed_files": len(files),
        "records": len(consolidated),
        "global_duplicate_dates": duplicate_dates,
        "global_missing_dates": global_missing,
        "files": [audit.as_dict() for audit in audits],
    }
    audit_output.write_text(
        json.dumps(audit_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return audits
