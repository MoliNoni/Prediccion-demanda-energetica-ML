import logging
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import Connection

from application.prediction import InsufficientHistoryError, PredictionAlreadyExistsError

MAX_BACKFILL_DAYS = 800

logger = logging.getLogger(__name__)


class BackfillRangeError(ValueError):
    """Raised when the requested date range is invalid."""


@dataclass
class BackfillResult:
    created: int = 0
    skipped_existing: int = 0
    skipped_insufficient_history: int = 0
    skipped_dates: list[date] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"created={self.created} skipped_existing={self.skipped_existing} "
            f"skipped_insufficient_history={self.skipped_insufficient_history}"
        )


class BackfillAbortedError(RuntimeError):
    """Raised when a day fails unexpectedly and the run stops."""

    def __init__(self, target_date: date, result: BackfillResult) -> None:
        super().__init__(f"Backfill stopped at {target_date.isoformat()}")
        self.target_date = target_date
        self.result = result


def date_range(start: date, end: date) -> list[date]:
    if start > end:
        raise BackfillRangeError("--start must not be after --end")
    days = (end - start).days + 1
    if days > MAX_BACKFILL_DAYS:
        raise BackfillRangeError(f"Range of {days} days exceeds the maximum of {MAX_BACKFILL_DAYS}")
    return [start + timedelta(days=offset) for offset in range(days)]


def backfill(
    dates: Iterable[date],
    predict_one: Callable[[Connection, date], object],
    connection_factory: Callable[[], AbstractContextManager[Connection]],
) -> BackfillResult:
    """Predict each date in its own transaction; committed days survive a later failure."""
    result = BackfillResult()
    for target_date in dates:
        try:
            with connection_factory() as connection:
                predict_one(connection, target_date)
        except PredictionAlreadyExistsError:
            result.skipped_existing += 1
            result.skipped_dates.append(target_date)
            logger.info("Skipped %s: prediction already exists", target_date)
        except InsufficientHistoryError as error:
            result.skipped_insufficient_history += 1
            result.skipped_dates.append(target_date)
            logger.info("Skipped %s: insufficient history (%s)", target_date, error)
        except Exception as error:
            raise BackfillAbortedError(target_date, result) from error
        else:
            result.created += 1
    return result
