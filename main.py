from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from proc.csv_import import DEFAULT_CSV_DIRECTORY, import_csv_directory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import valid CSV files from a directory into PostgreSQL."
    )
    parser.add_argument(
        "csv_directory",
        nargs="?",
        type=Path,
        default=DEFAULT_CSV_DIRECTORY,
        help="Directory to scan for CSV files (default: ./data)",
    )
    return parser.parse_args()


def main() -> int:
    csv_directory = parse_args().csv_directory.resolve()

    try:
        outcomes = import_csv_directory(csv_directory)
    except DBAPIError as exc:
        print(f"Database connection failed: {exc.orig}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(
            f"Database setup failed ({type(exc).__name__}). "
            "Check the database and application permissions.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Batch import aborted: {exc}", file=sys.stderr)
        return 1

    if not outcomes:
        print(f"No CSV files found in {csv_directory}.", file=sys.stderr)
        return 1

    for outcome in outcomes:
        print(f"[{outcome.status.upper()}] {outcome.filename}: {outcome.message}")

    imported_count = sum(outcome.status == "imported" for outcome in outcomes)
    skipped_count = sum(outcome.status == "skipped" for outcome in outcomes)
    failed_count = sum(outcome.status == "failed" for outcome in outcomes)
    print(
        f"Batch complete: {imported_count} imported, "
        f"{skipped_count} skipped, {failed_count} failed."
    )
    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
