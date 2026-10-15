"""Tests for regional domain-key normalization and archive alignment."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from domain_keys import check_archive_domain_keys, normalize_domain_key


class DomainKeyTests(unittest.TestCase):
    def test_normalizes_whitespace_and_rejects_empty_key(self) -> None:
        self.assertEqual(normalize_domain_key("  North  "), "North")
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            normalize_domain_key("  ")

    def test_archive_key_names_align_on_canonical_region(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "session1").mkdir()
            (root / "session2").mkdir()
            with (root / "session1" / "baseline_result.csv").open(
                "w", newline="", encoding="utf-8"
            ) as output:
                writer = csv.DictWriter(output, fieldnames=["state"])
                writer.writeheader()
                writer.writerows([{"state": "North"}, {"state": "South"}])
            with (root / "session2" / "streamed_regional_revenue.csv").open(
                "w", newline="", encoding="utf-8"
            ) as output:
                writer = csv.DictWriter(output, fieldnames=["region"])
                writer.writeheader()
                writer.writerows([{"region": " North "}, {"region": "South"}])

            result = check_archive_domain_keys(root)
            self.assertTrue(result["passed"])
            self.assertEqual(result["canonical_key"], "region")
            self.assertEqual(result["regions_compared"], 2)
            self.assertEqual(
                result["kafka_partition_configuration"]["status"], "NOT PRESENT"
            )


if __name__ == "__main__":
    unittest.main()
