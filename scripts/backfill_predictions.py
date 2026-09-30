import argparse
import logging
import sys
from datetime import date
from functools import partial

from application.backfill import BackfillAbortedError, BackfillRangeError, backfill, date_range
from application.prediction import PredictionService
from database.repositories import ModelRepository
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
    parser.add_argument(
        "--model-version",
        help="predict with this registered model instead of the active one (e.g. 1.2.0)",
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

    try:
        engine = create_database_engine()
    except Exception as error:
        print(f"Backfill setup failed: {error!r}", file=sys.stderr)
        return 1
    try:
        try:
            predict = PredictionService().predict
            if args.model_version is not None:
                with engine.connect() as connection:
                    registered = ModelRepository().get_by_version(connection, args.model_version)
                if registered is None:
                    print(
                        f"Backfill setup failed: model version {args.model_version} "
                        "is not registered",
                        file=sys.stderr,
                    )
                    return 1
                predict = partial(predict, model_version=args.model_version)
        except Exception as error:
            print(f"Backfill setup failed: {error!r}", file=sys.stderr)
            return 1
        result = backfill(dates, predict, engine.begin)
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
