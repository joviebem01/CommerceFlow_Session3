"""Validation tests for loading the archived customer CSV."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from customer_archive import CUSTOMER_FIELDS, load_customer_archive


class CustomerArchiveTests(unittest.TestCase):
    def _write_archive(self, rows: list[dict[str, str]]) -> Path:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "customers.csv"
        with path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=CUSTOMER_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_loads_customer_profile_fields_without_contact_data(self) -> None:
        row = {field: f"value-{field}" for field in CUSTOMER_FIELDS}
        row["customer_id"] = "customer-1"
        archive = load_customer_archive(self._write_archive([row]))
        self.assertEqual(archive["customer-1"], [row])
        self.assertNotIn("email", archive["customer-1"][0])
        self.assertNotIn("phone_number", archive["customer-1"][0])

    def test_duplicate_customer_ids_are_preserved_for_ambiguous_resolution(self) -> None:
        first = {field: "first" for field in CUSTOMER_FIELDS}
        second = {field: "second" for field in CUSTOMER_FIELDS}
        first["customer_id"] = second["customer_id"] = "duplicate"
        archive = load_customer_archive(self._write_archive([first, second]))
        self.assertEqual(len(archive["duplicate"]), 2)

    def test_blank_customer_ids_are_rejected(self) -> None:
        row = {field: "value" for field in CUSTOMER_FIELDS}
        row["customer_id"] = " "
        with self.assertRaisesRegex(ValueError, "blank customer_id"):
            load_customer_archive(self._write_archive([row]))

    def test_missing_columns_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "customers.csv"
            path.write_text("customer_id,first_name\n1,A\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                load_customer_archive(path)


if __name__ == "__main__":
    unittest.main()
