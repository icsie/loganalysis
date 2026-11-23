from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = PROJECT_ROOT / "data" / "20261123_13_36_23.csv"
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def summarize_csv(csv_path: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"CSV is not valid UTF-8: {csv_path}") from exc
    except pd.errors.ParserError as exc:
        raise ValueError(f"CSV could not be parsed: {csv_path}") from exc

    summary: dict[str, object] = {
        "file": str(csv_path),
        "shape": df.shape,
        "duplicate_rows": int(df.duplicated().sum()),
        "duplicate_column_names": [
            str(name) for name in df.columns[df.columns.duplicated()]
        ],
        "invalid_column_names": [
            str(name)
            for name in df.columns
            if IDENTIFIER_PATTERN.fullmatch(str(name)) is None
        ],
        "column_summary": pd.DataFrame(
            {
                "dtype": df.dtypes.astype(str),
                "non_null": df.notna().sum(),
                "null": df.isna().sum(),
                "unique": df.nunique(dropna=True),
            }
        ),
    }
    return df, summary


def print_summary(summary: dict[str, object]) -> None:
    print(f"File: {summary['file']}")
    print(f"df.shape: {summary['shape']}")
    print("\nData quality:")
    print(f"Duplicate rows: {summary['duplicate_rows']}")
    print(f"Duplicate column names: {summary['duplicate_column_names']}")
    print(f"Invalid PostgreSQL-style column names: {summary['invalid_column_names']}")
    print("\nColumn summary:")
    print(summary["column_summary"].to_string())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load a UTF-8 CSV and display its pandas DataFrame summary."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="CSV file to summarize (default: data/20261123_13_36_23.csv)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = args.csv_path.resolve()

    try:
        df, summary = summarize_csv(csv_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1

    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
