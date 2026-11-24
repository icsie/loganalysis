import tempfile
import unittest
from pathlib import Path

import pandas as pd

from proc.csv_import import (
    find_csv_files,
    is_already_imported,
    normalize_column_names,
    table_name_from_csv,
)
from proc.data_summary import load_csv


class TableNameTests(unittest.TestCase):
    def test_derives_lowercase_name_from_valid_csv_filename(self) -> None:
        self.assertEqual(
            table_name_from_csv(Path("VPN_Access_01.CSV")),
            "vpn_access_01",
        )

    def test_rejects_filename_that_starts_with_a_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "must start with a letter"):
            table_name_from_csv(Path("20261123_13_36_23.csv"))

    def test_rejects_non_csv_extension(self) -> None:
        with self.assertRaisesRegex(ValueError, "must have a .csv extension"):
            table_name_from_csv(Path("vpn_access.txt"))

    def test_rejects_table_name_over_postgresql_identifier_limit(self) -> None:
        long_name = "a" * 64 + ".csv"
        with self.assertRaisesRegex(ValueError, "too long"):
            table_name_from_csv(Path(long_name))


class ColumnNameTests(unittest.TestCase):
    def test_normalizes_names_and_resolves_collisions(self) -> None:
        df = pd.DataFrame(
            [["1.2.3.4", "1980-01-01", "admin", "x", "y", "z"]],
            columns=[
                "Source IP",
                "Date",
                "User",
                "Source-IP",
                "1st Field",
                "Select",
            ],
        )

        changes = normalize_column_names(df)

        self.assertEqual(
            list(df.columns),
            [
                "source_ip",
                "date",
                "user_field",
                "source_ip_2",
                "column_1st_field",
                "select_field",
            ],
        )
        self.assertEqual(df.iloc[0, 0], "1.2.3.4")
        self.assertIn(("Source IP", "source_ip"), changes)


class ImportHistoryTests(unittest.TestCase):
    def test_skips_csv_when_filename_is_already_recorded(self) -> None:
        self.assertTrue(
            is_already_imported(
                "vpn_access.csv",
                "vpn_access",
                {"vpn_access.csv"},
                set(),
            )
        )

    def test_skips_csv_when_derived_table_is_already_recorded(self) -> None:
        self.assertTrue(
            is_already_imported(
                "another_vpn_access.csv",
                "vpn_access",
                set(),
                {"logs.vpn_access"},
            )
        )

    def test_does_not_skip_unrecorded_csv(self) -> None:
        self.assertFalse(
            is_already_imported(
                "vpn_access.csv",
                "vpn_access",
                set(),
                set(),
            )
        )


class CsvDiscoveryTests(unittest.TestCase):
    def test_finds_csv_files_in_order_without_descending_into_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "zeta.csv").touch()
            (data_dir / "Alpha.CSV").touch()
            (data_dir / "readme.txt").touch()
            nested_dir = data_dir / "nested"
            nested_dir.mkdir()
            (nested_dir / "nested.csv").touch()

            self.assertEqual(
                [path.name for path in find_csv_files(data_dir)],
                ["Alpha.CSV", "zeta.csv"],
            )


class CsvHeaderTests(unittest.TestCase):
    def test_rejects_duplicate_headers_before_pandas_renames_them(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "duplicate_headers.csv"
            csv_path.write_text(
                "source_ip,source_ip\n1.2.3.4,5.6.7.8\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate column names"):
                load_csv(csv_path)

    def test_csv_loader_preserves_original_spaced_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "spaced_headers.csv"
            csv_path.write_text(
                '"Source IP",Date\n1.2.3.4,2026-11-23\n',
                encoding="utf-8",
            )

            df = load_csv(csv_path)

            self.assertEqual(list(df.columns), ["Source IP", "Date"])
