from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from ingestion.constants import AUXILIARY_COLUMNS, EXPECTED_COLUMNS, TARGET_COLUMN


@dataclass
class FileAudit:
    file: str
    year: int
    format: str
    sheet: str | None = None
    records: int = 0
    date_min: str | None = None
    date_max: str | None = None
    nulls: dict[str, int] = field(default_factory=dict)
    duplicate_dates: int = 0
    missing_dates: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "BLOCKED" if self.blockers else "OBSERVATIONS" if self.observations else "OK"

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status
        return result


def _date_text(value: date) -> str:
    return value.isoformat()


def audit_frame(frame: pd.DataFrame, *, file_name: str, year: int) -> FileAudit:
    audit = FileAudit(file=file_name, year=year, format=file_name.rsplit(".", 1)[-1])
    audit.records = len(frame)
    audit.nulls = {column: int(frame[column].isna().sum()) for column in EXPECTED_COLUMNS}

    parsed_dates = pd.to_datetime(frame["Fecha"], errors="coerce")
    invalid_dates = parsed_dates.isna() & frame["Fecha"].notna()
    if invalid_dates.any():
        audit.blockers.append("Fecha contiene valores inválidos o no convertibles")
    if frame["Fecha"].isna().any():
        audit.blockers.append("Fecha contiene valores nulos")

    target = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
    invalid_target = target.isna() & frame[TARGET_COLUMN].notna()
    if invalid_target.any():
        audit.blockers.append(
            "El target contiene valores no numéricos distintos de nulo"
        )

    audit.duplicate_dates = int(parsed_dates.dropna().duplicated().sum())
    if audit.duplicate_dates:
        audit.blockers.append("Existen fechas duplicadas dentro del archivo")

    valid_dates = parsed_dates.dropna().dt.normalize().sort_values()
    if not valid_dates.empty:
        audit.date_min = valid_dates.iloc[0].date().isoformat()
        audit.date_max = valid_dates.iloc[-1].date().isoformat()
        expected = pd.date_range(valid_dates.iloc[0], valid_dates.iloc[-1], freq="D")
        observed = pd.DatetimeIndex(valid_dates.unique())
        audit.missing_dates = [
            _date_text(value.date()) for value in expected.difference(observed)
        ]
        if audit.missing_dates:
            audit.observations.append("Existen fechas faltantes dentro del rango observado")

        wrong_year = valid_dates.dt.year.ne(year)
        if wrong_year.any():
            audit.blockers.append("Existen registros cuya fecha no corresponde al año")

    auxiliary_invalid = []
    for column in AUXILIARY_COLUMNS:
        values = pd.to_numeric(frame[column], errors="coerce")
        invalid = values.isna() & frame[column].notna()
        if invalid.any():
            auxiliary_invalid.append(column)
    if auxiliary_invalid:
        audit.observations.append(
            "Columnas auxiliares con valores no numéricos: "
            + ", ".join(auxiliary_invalid)
        )
    if any(audit.nulls[column] for column in AUXILIARY_COLUMNS):
        audit.observations.append("Existen valores nulos en columnas auxiliares")

    if year == 2015 and (
        "2015-12-31" in audit.missing_dates or audit.date_max == "2015-12-30"
    ):
        audit.observations.append("Ausencia histórica conocida: 2015-12-31")

    return audit


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.loc[:, EXPECTED_COLUMNS].copy()
    normalized["Fecha"] = pd.to_datetime(normalized["Fecha"], errors="raise").dt.normalize()
    for column in EXPECTED_COLUMNS[1:]:
        normalized[column] = pd.to_numeric(normalized[column], errors="raise")
    return normalized
