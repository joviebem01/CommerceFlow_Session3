"""Tests for the generous-deadline gRPC check."""
from __future__ import annotations

import tempfile
import time
import unittest
from concurrent import futures
from pathlib import Path

import grpc

import session3_pb2
import session3_pb2_grpc
from deadline_check import verify_generous_deadline
from grpc_backend import make_grpc_service
from transport import create_transport


class DelayedRegionalRevenueService(
    session3_pb2_grpc.RegionalRevenueServicer
):
    def GetRegion(self, request, context):
        time.sleep(0.15)
        return session3_pb2.RegionResponse(
            region=request.region,
            transaction_count=1,
            revenue_total=2.5,
        )


class GenerousDeadlineTests(unittest.TestCase):
    def test_same_rpc_succeeds_with_normal_and_generous_deadlines(self) -> None:
        records = [("Test Region", 15, 123.45, 15, 123.45)]
        server, port = make_grpc_service(records)
        try:
            with tempfile.TemporaryDirectory() as directory:
                report = verify_generous_deadline(
                    records,
                    f"127.0.0.1:{port}",
                    Path(directory) / "deadline_report.json",
                )
                self.assertTrue(report["passed"])
                self.assertTrue(report["same_response"])
                self.assertTrue(report["matches_archived_record"])
                self.assertEqual(report["generous_deadline_seconds"], 30)
                self.assertTrue((Path(directory) / "deadline_report.json").is_file())
        finally:
            server.stop(0).wait()

    def test_empty_archive_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            verify_generous_deadline([], "127.0.0.1:1", report_path=None)

    def test_short_deadline_expires_and_generous_deadline_succeeds(self) -> None:
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        session3_pb2_grpc.add_RegionalRevenueServicer_to_server(
            DelayedRegionalRevenueService(), server
        )
        port = server.add_insecure_port("127.0.0.1:0")
        self.assertNotEqual(port, 0)
        server.start()
        endpoint = f"127.0.0.1:{port}"
        try:
            with self.assertRaises(grpc.RpcError) as error:
                create_transport("grpc", endpoint, timeout=0.01).call(
                    "GetRegion", "Slow Region"
                )
            self.assertEqual(error.exception.code(), grpc.StatusCode.DEADLINE_EXCEEDED)

            response, _, _ = create_transport(
                "grpc", endpoint, timeout=2
            ).call("GetRegion", "Slow Region")
            self.assertEqual(
                response,
                {
                    "region": "Slow Region",
                    "transaction_count": 1,
                    "revenue_total": 2.5,
                },
            )
        finally:
            server.stop(0).wait()


if __name__ == "__main__":
    unittest.main()
