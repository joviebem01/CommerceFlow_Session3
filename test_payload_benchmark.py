"""Tests for the live payload-size measurement and report."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from grpc_backend import make_grpc_service
from payload_benchmark import run_payload_benchmark
from services import make_service


class PayloadBenchmarkTests(unittest.TestCase):
    def test_records_live_sizes_and_persists_json_and_csv(self) -> None:
        records = [
            ("Region A", 12, 134.5, 12, 134.5),
            ("Region B", 25, 678.9, 25, 678.9),
        ]
        http_server = make_service(records)
        grpc_server, grpc_port = make_grpc_service(records)
        try:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                report = run_payload_benchmark(
                    records,
                    f"http://127.0.0.1:{http_server.server_port}",
                    f"127.0.0.1:{grpc_port}",
                    output,
                )
                self.assertTrue(report["passed"])
                self.assertEqual(report["regions_measured"], 2)
                self.assertIsNotNone(datetime.fromisoformat(report["measured_at"]).tzinfo)
                self.assertTrue(
                    all(row["json_response_bytes"] > 0 for row in report["measurements"])
                )
                self.assertTrue(
                    all(row["grpc_response_bytes"] > 0 for row in report["measurements"])
                )
                saved_report = json.loads(
                    (output / "payload_report.json").read_text(encoding="utf-8")
                )
                self.assertEqual(saved_report, report)
                with (output / "payload_sizes.csv").open(
                    newline="", encoding="utf-8"
                ) as source:
                    rows = list(csv.DictReader(source))
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["region"], "Region A")
        finally:
            http_server.shutdown()
            http_server.server_close()
            grpc_server.stop(0).wait()

    def test_empty_records_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            run_payload_benchmark([], "http://localhost", "localhost", Path("."))

if __name__ == "__main__":
    unittest.main()
