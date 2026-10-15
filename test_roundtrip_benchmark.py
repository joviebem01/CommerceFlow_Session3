"""Tests for live round-trip and streaming measurements."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from grpc_backend import make_grpc_service
from roundtrip_benchmark import run_roundtrip_benchmark
from services import make_service


class RoundtripBenchmarkTests(unittest.TestCase):
    def test_measures_all_patterns_and_persists_timestamped_results(self) -> None:
        records = [
            ("North", 4, 12.5, 4, 12.5),
            ("South", 8, 42.0, 8, 42.0),
        ]
        http_server = make_service(records)
        grpc_server, grpc_port = make_grpc_service(records)
        try:
            with tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory)
                report = run_roundtrip_benchmark(
                    records,
                    f"http://127.0.0.1:{http_server.server_port}",
                    f"127.0.0.1:{grpc_port}",
                    output_dir,
                )
                self.assertTrue(report["passed"])
                self.assertIsNotNone(
                    datetime.fromisoformat(report["measured_at"]).tzinfo
                )
                self.assertIn("not student-hardware", report["scope"])
                self.assertEqual(
                    [row["rows_returned"] for row in report["measurements"]],
                    [2, 2, 2, 2],
                )
                self.assertEqual(
                    json.loads(
                        (output_dir / "roundtrip_report.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                    report,
                )
                for filename in (
                    "roundtrip_benchmark.csv",
                    "streaming_benchmark.csv",
                ):
                    with (output_dir / filename).open(
                        newline="", encoding="utf-8"
                    ) as source:
                        self.assertEqual(len(list(csv.DictReader(source))), 2)
        finally:
            http_server.shutdown()
            http_server.server_close()
            grpc_server.stop(0).wait()

    def test_empty_records_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            run_roundtrip_benchmark([], "", "", Path("."))


if __name__ == "__main__":
    unittest.main()
