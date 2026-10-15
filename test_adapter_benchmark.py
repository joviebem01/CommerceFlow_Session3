"""Tests for live HTTP and gRPC transport adapter comparison."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from adapter_benchmark import run_adapter_comparison
from grpc_backend import make_grpc_service
from services import make_service


class AdapterComparisonTests(unittest.TestCase):
    def test_both_adapters_match_archive_and_write_report(self) -> None:
        records = [
            ("North", 4, 12.5, 4, 12.5),
            ("South", 8, 42.0, 8, 42.0),
        ]
        http_server = make_service(records)
        grpc_server, grpc_port = make_grpc_service(records)
        try:
            with tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory)
                report = run_adapter_comparison(
                    records,
                    f"http://127.0.0.1:{http_server.server_port}",
                    f"127.0.0.1:{grpc_port}",
                    output_dir,
                )
                self.assertTrue(report["passed"])
                self.assertTrue(report["identical_responses"])
                self.assertIsNotNone(
                    datetime.fromisoformat(report["measured_at"]).tzinfo
                )
                self.assertIn("not student-hardware", report["scope"])
                self.assertEqual(
                    [row["calls"] for row in report["transports"]], [2, 2]
                )
                self.assertEqual(
                    json.loads(
                        (output_dir / "adapter_report.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                    report,
                )
                with (output_dir / "adapter_comparison.csv").open(
                    newline="", encoding="utf-8"
                ) as source:
                    self.assertEqual(len(list(csv.DictReader(source))), 2)
        finally:
            http_server.shutdown()
            http_server.server_close()
            grpc_server.stop(0).wait()

    def test_empty_records_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            run_adapter_comparison([], "", "", Path("."))


if __name__ == "__main__":
    unittest.main()
