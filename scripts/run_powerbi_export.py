import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from powerbi.export import DEFAULT_END, DEFAULT_OUTPUT_DIR, DEFAULT_START, run_export
from powerbi.sources import SourceError


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the Power BI star-schema CSV dataset.")
    parser.add_argument("--start", type=_parse_date, default=DEFAULT_START)
    parser.add_argument("--end", type=_parse_date, default=DEFAULT_END)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--skip-network", action="store_true", help="use cached API data only")
    parser.add_argument("--skip-db", action="store_true", help="do not read stored predictions")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        manifest = run_export(
            args.start,
            args.end,
            output_dir=args.output_dir,
            skip_network=args.skip_network,
            skip_db=args.skip_db,
        )
    except SourceError as error:
        print(f"Export failed: {error}", file=sys.stderr)
        return 1
    for name, info in manifest["tables"].items():
        print(f"{name}: {info['rows']} rows")
    print(f"Output: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
