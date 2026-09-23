from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

HISTORICAL_DEMAND_PATH = Path("data/interim/energy_demand_daily.parquet")
DATE_COLUMN = "Fecha"
DEMAND_COLUMN = "Demanda Energia SIN kWh"


class HistoricalDemandError(RuntimeError):
    """Raised when the approved historical-demand artifact cannot be queried."""


class HistoricalDemandQuery:
    def __init__(self, path: Path = HISTORICAL_DEMAND_PATH) -> None:
        self.path = path

    def list(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        try:
            frame = pd.read_parquet(self.path, columns=[DATE_COLUMN, DEMAND_COLUMN])
        except (FileNotFoundError, OSError, ValueError) as error:
            raise HistoricalDemandError("Historical demand data is unavailable") from error
        if {DATE_COLUMN, DEMAND_COLUMN}.difference(frame.columns):
            raise HistoricalDemandError("Historical demand data has an invalid schema")

        frame[DATE_COLUMN] = pd.to_datetime(frame[DATE_COLUMN], errors="raise").dt.date
        frame = frame.sort_values(DATE_COLUMN)
        if start_date is not None:
            frame = frame.loc[frame[DATE_COLUMN] >= start_date]
        if end_date is not None:
            frame = frame.loc[frame[DATE_COLUMN] <= end_date]
        if frame[DEMAND_COLUMN].isna().any():
            raise HistoricalDemandError("Historical demand data contains null demand values")

        total = len(frame)
        start = (page - 1) * page_size
        items = [
            {"date": record[DATE_COLUMN], "demand_kwh": record[DEMAND_COLUMN]}
            for record in frame.iloc[start : start + page_size].to_dict("records")
        ]
        return items, total
