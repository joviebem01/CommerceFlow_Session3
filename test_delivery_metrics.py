"""Tests for server-confirmed abandoned response accounting."""
from __future__ import annotations

import time
import unittest
import urllib.request

import grpc
from google.protobuf.empty_pb2 import Empty

import session3_pb2_grpc
from delivery_metrics import AbandonedResponseCounter
from grpc_backend import make_grpc_service
from services import make_service
from transport import create_transport


def wait_for_count(counter: AbandonedResponseCounter, expected: int) -> bool:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if counter.count >= expected:
            return True
        time.sleep(0.01)
    return counter.count >= expected


class AbandonedResponseTests(unittest.TestCase):
    def test_completed_http_response_is_not_counted(self) -> None:
        counter = AbandonedResponseCounter()
        server = make_service([("Region", 1, 1.0, None, None)], counter)
        try:
            result, _, _ = create_transport(
                "json", f"http://127.0.0.1:{server.server_port}"
            ).call("GetRegion", "Region")
            self.assertEqual(result["region"], "Region")
            self.assertEqual(counter.count, 0)
        finally:
            server.shutdown()
            server.server_close()

    def test_completed_grpc_calls_and_not_found_are_not_counted(self) -> None:
        counter = AbandonedResponseCounter()
        server, port = make_grpc_service(
            [("Region", 1, 1.0, None, None)], counter
        )
        target = f"127.0.0.1:{port}"
        try:
            transport = create_transport("grpc", target)
            transport.call("GetRegion", "Region")
            transport.call("ListRegions")
            with self.assertRaises(grpc.RpcError) as error:
                transport.call("GetRegion", "Unknown")
            self.assertEqual(error.exception.code(), grpc.StatusCode.NOT_FOUND)
            self.assertEqual(counter.count, 0)
        finally:
            server.stop(0).wait()

    def test_http_stream_disconnect_is_counted_once(self) -> None:
        counter = AbandonedResponseCounter()
        records = [("Region", 1, 1.0, None, None)] * 100_000
        server = make_service(records, counter)
        try:
            request = urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/stream", timeout=5
            )
            request.readline()
            request.close()
            self.assertTrue(wait_for_count(counter, 1))
            self.assertEqual(counter.count, 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_grpc_stream_cancellation_is_counted_once(self) -> None:
        counter = AbandonedResponseCounter()
        records = [("Region", 1, 1.0, None, None)] * 100_000
        server, port = make_grpc_service(records, counter)
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        try:
            stub = session3_pb2_grpc.RegionalRevenueStub(channel)
            response = stub.ListRegions(Empty(), timeout=10)
            next(response)
            response.cancel()
            self.assertTrue(wait_for_count(counter, 1))
            self.assertEqual(counter.count, 1)
        finally:
            channel.close()
            server.stop(0).wait()


if __name__ == "__main__":
    unittest.main()
