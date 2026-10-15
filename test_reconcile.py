"""Tests for the three-way reconciliation gate."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from reconcile import reconcile_records


class ReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.archived_rows: list[list[Any]] = [
            ["North", 3, 12.5, 3, 12.5],
            ["South", 7, 42.25, 7, 42.25],
        ]
        self.live_records = [
            {"region": "North", "transaction_count": 3, "revenue_total": 12.5},
            {"region": "South", "transaction_count": 7, "revenue_total": 42.25},
        ]
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output_dir = Path(self.temp_dir.name)

    def test_matching_three_sources_passes_and_writes_outputs(self) -> None:
        rows, report = reconcile_records(
            self.archived_rows, self.live_records, self.output_dir
        )
        self.assertTrue(report["passed"])
        self.assertTrue(all(report["gates"].values()))
        self.assertEqual(len(rows), 2)
        self.assertTrue((self.output_dir / "session3_reconciliation.json").is_file())
        self.assertTrue((self.output_dir / "session3_regional_revenue.csv").is_file())

    def test_mismatch_fails_relevant_gate(self) -> None:
        self.live_records[0]["transaction_count"] = 4
        _, report = reconcile_records(
            self.archived_rows, self.live_records, self.output_dir
        )
        self.assertFalse(report["passed"])
        self.assertFalse(report["gates"]["s1_s3_transaction_counts"])
        self.assertFalse(report["gates"]["s2_s3_transaction_counts"])

    def test_unexpected_live_region_fails_region_set_gate(self) -> None:
        self.live_records.append(
            {"region": "West", "transaction_count": 1, "revenue_total": 1.0}
        )
        _, report = reconcile_records(
            self.archived_rows, self.live_records, self.output_dir
        )
        self.assertFalse(report["passed"])
        self.assertFalse(report["gates"]["region_set"])
        self.assertEqual(report["unexpected_regions"], ["West"])

    def test_duplicate_live_region_is_rejected(self) -> None:
        self.live_records.append(self.live_records[0])
        with self.assertRaisesRegex(ValueError, "duplicate region"):
            reconcile_records(self.archived_rows, self.live_records, self.output_dir)


if __name__ == "__main__":
    unittest.main()
