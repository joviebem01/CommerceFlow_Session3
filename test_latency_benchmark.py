"""Tests for timestamped local latency measurements."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from grpc_backend import make_grpc_service
from latency_benchmark import run_latency_benchmark
from services import make_service


class LatencyBenchmarkTests(unittest.TestCase):
    def test_benchmarks_both_transports_and_saves_results(self) -> None:
        records = [("Region", 2, 10.5, 2, 10.5)]
        http_server = make_service(records)
        grpc_server, grpc_port = make_grpc_service(records)
        try:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                report = run_latency_benchmark(
                    records,
                    f"http://127.0.0.1:{http_server.server_port}",
                    f"127.0.0.1:{grpc_port}",
                    calls_per_transport=3,
                    output_dir=output,
                )
                self.assertTrue(report["passed"])
                self.assertIsNotNone(
                    datetime.fromisoformat(report["measured_at"]).tzinfo
                )
                self.assertIn("not student-hardware", report["scope"])
                self.assertEqual(
                    [row["calls"] for row in report["measurements"]], [3, 3]
                )
                saved = json.loads(
                    (output / "latency_report.json").read_text(encoding="utf-8")
                )
                self.assertEqual(saved, report)
                with (output / "latency_benchmark.csv").open(
                    newline="", encoding="utf-8"
                ) as source:
                    rows = list(csv.DictReader(source))
                self.assertEqual(len(rows), 2)
        finally:
            http_server.shutdown()
            http_server.server_close()
            grpc_server.stop(0).wait()

    def test_invalid_call_count_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            run_latency_benchmark([], "", "", output_dir=Path("."))


if __name__ == "__main__":
    unittest.main()
