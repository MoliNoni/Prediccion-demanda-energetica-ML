import argparse
import logging
import sys
from datetime import date

from application.backfill import BackfillAbortedError, BackfillRangeError, backfill, date_range
from application.prediction import PredictionService
from database.session import create_database_engine


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill day-ahead predictions for consecutive dates."
    )
    parser.add_argument("--start", type=_parse_date, required=True)
    parser.add_argument("--end", type=_parse_date, required=True, help="inclusive")
    parser.add_argument(
        "--dry-run", action="store_true", help="list the dates without touching the database"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        dates = date_range(args.start, args.end)
    except BackfillRangeError as error:
        print(f"Invalid range: {error}", file=sys.stderr)
        return 2

    if args.dry_run:
        for target_date in dates:
            print(target_date.isoformat())
        print(f"Dry run: {len(dates)} dates would be processed")
        return 0

    engine = create_database_engine()
    try:
        result = backfill(dates, PredictionService().predict, engine.begin)
    except BackfillAbortedError as error:
        print(
            f"Backfill failed on {error.target_date.isoformat()}: {error.__cause__!r}",
            file=sys.stderr,
        )
        print(f"Committed before failure: {error.result.summary()}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(f"Backfill complete: {result.summary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
