from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import (
    URL,
    MetaData,
    Table,
    create_engine,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.types import Text

from proc.data_summary import print_summary, summarize_csv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_DIRECTORY = PROJECT_ROOT / "data"
TABLE_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
IMPORT_CHUNK_SIZE = 1000
POSTGRES_IDENTIFIER_LIMIT = 63
POSTGRES_RESERVED_WORDS = (
    postgresql.dialect().identifier_preparer.reserved_words
)


@dataclass(frozen=True)
class ImportOutcome:
    filename: str
    status: Literal["imported", "skipped", "failed"]
    message: str


class ImportAlreadyRecordedError(Exception):
    pass


def table_name_from_csv(csv_path: Path) -> str:
    if csv_path.suffix.lower() != ".csv":
        raise ValueError(f"Input file must have a .csv extension: {csv_path.name}")

    table_name = csv_path.stem.lower()
    if TABLE_NAME_PATTERN.fullmatch(table_name) is None:
        raise ValueError(
            f"CSV filename cannot be used as a PostgreSQL table name: "
            f"{csv_path.name!r}. The name must start with a letter or underscore "
            "and contain only letters, numbers, and underscores."
        )
    if len(table_name) > POSTGRES_IDENTIFIER_LIMIT:
        raise ValueError(
            f"CSV filename is too long for a PostgreSQL table name: "
            f"{csv_path.name!r}."
        )

    return table_name


def normalize_column_names(df: pd.DataFrame) -> list[tuple[str, str]]:
    used_names: set[str] = set()
    normalized_names: list[str] = []
    changes: list[tuple[str, str]] = []

    for position, source_name in enumerate(df.columns, start=1):
        source_name = str(source_name)
        normalized = re.sub(r"[^A-Za-z0-9_]+", "_", source_name.strip())
        normalized = normalized.strip("_").lower()
        if not normalized:
            normalized = f"column_{position}"
        if normalized[0].isdigit():
            normalized = f"column_{normalized}"
        if normalized in POSTGRES_RESERVED_WORDS:
            normalized = f"{normalized}_field"

        base_name = normalized[:POSTGRES_IDENTIFIER_LIMIT].rstrip("_")
        candidate = base_name or f"column_{position}"
        suffix = 2
        while candidate in used_names:
            suffix_text = f"_{suffix}"
            candidate = (
                f"{base_name[:POSTGRES_IDENTIFIER_LIMIT - len(suffix_text)].rstrip('_')}"
                f"{suffix_text}"
            )
            suffix += 1

        used_names.add(candidate)
        normalized_names.append(candidate)
        if source_name != candidate:
            changes.append((source_name, candidate))

    df.columns = normalized_names
    return changes


def create_database_engine() -> Engine:
    load_dotenv(PROJECT_ROOT / ".env.local")

    required_settings = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
    settings = {key: os.environ.get(key) for key in required_settings}
    missing = [key for key, value in settings.items() if not value]
    if missing:
        raise ValueError(
            "Missing database settings: "
            + ", ".join(missing)
            + ". Configure .env.local or environment variables."
        )

    try:
        port = int(settings["DB_PORT"] or "")
    except ValueError as exc:
        raise ValueError("DB_PORT must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("DB_PORT must be between 1 and 65535.")

    username = settings["DB_USER"]
    password = settings["DB_PASSWORD"]
    host = settings["DB_HOST"]
    database = settings["DB_NAME"]
    if not username or not password or not host or not database:
        raise ValueError("Database connection settings cannot be empty.")

    database_url = URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    return create_engine(database_url, pool_pre_ping=True)


def is_already_imported(
    filename: str,
    table_name: str,
    imported_filenames: set[str],
    imported_table_names: set[str],
) -> bool:
    return (
        filename in imported_filenames
        or f"logs.{table_name}" in imported_table_names
    )


def find_csv_files(csv_directory: Path) -> list[Path]:
    if not csv_directory.is_dir():
        raise FileNotFoundError(f"CSV directory not found: {csv_directory}")

    return sorted(
        (
            path
            for path in csv_directory.iterdir()
            if path.is_file() and path.suffix.lower() == ".csv"
        ),
        key=lambda path: path.name.casefold(),
    )


def _import_dataframe(
    engine: Engine,
    csv_path: Path,
    df: pd.DataFrame,
    table_name: str,
) -> int:
    with engine.begin() as connection:
        recorded_import = connection.execute(
            text(
                """
                SELECT 1
                FROM public.import_history
                WHERE filename = :filename OR table_name = :table_name
                LIMIT 1
                """
            ),
            {
                "filename": csv_path.name,
                "table_name": f"logs.{table_name}",
            },
        ).first()
        if recorded_import is not None:
            raise ImportAlreadyRecordedError(
                "An import-history entry was created while this batch was running."
            )

        if inspect(connection).has_table(table_name, schema="logs"):
            raise FileExistsError(
                f"Table logs.{table_name} already exists without a matching "
                "import-history record; refusing to overwrite it."
            )

        df.to_sql(
            name=table_name,
            con=connection,
            schema="logs",
            if_exists="fail",
            index=False,
            dtype={column: Text() for column in df.columns},
            chunksize=IMPORT_CHUNK_SIZE,
            method="multi",
        )

        imported_table = Table(
            table_name,
            MetaData(),
            schema="logs",
            autoload_with=connection,
        )
        rows_in_database = connection.scalar(
            select(func.count()).select_from(imported_table)
        )
        if rows_in_database is None:
            raise RuntimeError("PostgreSQL did not return an imported row count.")
        if rows_in_database != len(df):
            raise RuntimeError(
                f"Imported row count mismatch: DataFrame has {len(df)} rows, "
                f"but PostgreSQL reports {rows_in_database}."
            )

        connection.execute(
            text(
                """
                INSERT INTO public.import_history
                    (filename, table_name, row_count, import_status)
                VALUES
                    (:filename, :table_name, :row_count, :import_status)
                """
            ),
            {
                "filename": csv_path.name,
                "table_name": f"logs.{table_name}",
                "row_count": rows_in_database,
                "import_status": "success",
            },
        )

    return rows_in_database


def import_csv_directory(csv_directory: Path) -> list[ImportOutcome]:
    csv_files = find_csv_files(csv_directory)
    if not csv_files:
        return []

    engine = create_database_engine()
    outcomes: list[ImportOutcome] = []

    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            if not inspector.has_schema("logs"):
                raise RuntimeError(
                    "PostgreSQL schema 'logs' does not exist. "
                    "Run .\\run_db_setup.ps1 first."
                )
            if not inspector.has_table("import_history", schema="public"):
                raise RuntimeError(
                    "public.import_history does not exist. "
                    "Run .\\run_db_setup.ps1 first."
                )

            history_rows = connection.execute(
                text("SELECT filename, table_name FROM public.import_history")
            ).all()
            imported_filenames = {row.filename for row in history_rows}
            imported_table_names = {row.table_name for row in history_rows}

        for csv_path in csv_files:
            if csv_path.name in imported_filenames:
                outcomes.append(
                    ImportOutcome(
                        filename=csv_path.name,
                        status="skipped",
                        message="already recorded in public.import_history",
                    )
                )
                continue

            try:
                table_name = table_name_from_csv(csv_path)
            except ValueError as exc:
                outcomes.append(
                    ImportOutcome(
                        filename=csv_path.name,
                        status="failed",
                        message=str(exc),
                    )
                )
                continue

            if is_already_imported(
                csv_path.name,
                table_name,
                imported_filenames,
                imported_table_names,
            ):
                outcomes.append(
                    ImportOutcome(
                        filename=csv_path.name,
                        status="skipped",
                        message=f"logs.{table_name} already recorded in public.import_history",
                    )
                )
                continue

            try:
                df, summary = summarize_csv(csv_path)
                print_summary(summary)
                column_name_changes = normalize_column_names(df)
                if column_name_changes:
                    print("Normalized column names:")
                    for source_name, column_name in column_name_changes:
                        print(f"  {source_name!r} -> {column_name}")
                rows_imported = _import_dataframe(
                    engine,
                    csv_path,
                    df,
                    table_name,
                )
            except ImportAlreadyRecordedError as exc:
                outcomes.append(
                    ImportOutcome(
                        filename=csv_path.name,
                        status="skipped",
                        message=str(exc),
                    )
                )
            except (OSError, ValueError, RuntimeError) as exc:
                outcomes.append(
                    ImportOutcome(
                        filename=csv_path.name,
                        status="failed",
                        message=str(exc),
                    )
                )
            except DBAPIError as exc:
                outcomes.append(
                    ImportOutcome(
                        filename=csv_path.name,
                        status="failed",
                        message=f"Database import failed: {exc.orig}",
                    )
                )
            except SQLAlchemyError as exc:
                outcomes.append(
                    ImportOutcome(
                        filename=csv_path.name,
                        status="failed",
                        message=f"Database import failed ({type(exc).__name__}).",
                    )
                )
            else:
                imported_filenames.add(csv_path.name)
                imported_table_names.add(f"logs.{table_name}")
                outcomes.append(
                    ImportOutcome(
                        filename=csv_path.name,
                        status="imported",
                        message=f"created logs.{table_name} with {rows_imported} rows",
                    )
                )
    finally:
        engine.dispose()

    return outcomes
