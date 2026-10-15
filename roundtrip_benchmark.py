"""Measure live batching, N+1, and streaming round trips."""
from __future__ import annotations

import csv
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.request import Request, urlopen

import grpc
from google.protobuf.empty_pb2 import Empty

import session3_pb2_grpc
from transport import create_transport


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"


def run_roundtrip_benchmark(
    records: Sequence[Sequence[Any]],
    http_endpoint: str,
    grpc_endpoint: str,
    output_dir: Path = OUT,
) -> dict[str, Any]:
    """Measure batching, per-region calls, and first-row/full streaming times."""
    if not records:
        raise ValueError("Round-trip benchmark requires at least one regional record")

    measurements = []
    json_transport = create_transport("json", http_endpoint)

    started = time.perf_counter()
    batch_result, _, _ = json_transport.call("ListRegions")
    batch_ms = (time.perf_counter() - started) * 1000
    batch_rows = batch_result.get("regions")
    if not isinstance(batch_rows, list):
        raise RuntimeError("Batched HTTP response did not contain a regions list")
    measurements.append(
        {
            "test": "Single batched RPC",
            "transport": "HTTP / JSON",
            "requests": 1,
            "elapsed_ms": batch_ms,
            "time_to_first_row_ms": batch_ms,
            "rows_returned": len(batch_rows),
            "notes": "Full response read before decoding",
        }
    )

    started = time.perf_counter()
    individual_results = [
        json_transport.call("GetRegion", str(record[0]))[0] for record in records
    ]
    n_plus_one_ms = (time.perf_counter() - started) * 1000
    measurements.append(
        {
            "test": "N individual RPCs",
            "transport": "HTTP / JSON",
            "requests": len(individual_results),
            "elapsed_ms": n_plus_one_ms,
            "time_to_first_row_ms": None,
            "rows_returned": len(individual_results),
            "notes": "One HTTP request per region",
        }
    )

    request = Request(f"{http_endpoint}/stream")
    started = time.perf_counter()
    with urlopen(request, timeout=15) as response:
        first_line = response.readline()
        first_row_ms = (time.perf_counter() - started) * 1000
        http_rows = [json.loads(first_line)] if first_line else []
        http_rows.extend(json.loads(line) for line in response)
    http_stream_ms = (time.perf_counter() - started) * 1000
    measurements.append(
        {
            "test": "NDJSON server stream",
            "transport": "HTTP / JSON",
            "requests": 1,
            "elapsed_ms": http_stream_ms,
            "time_to_first_row_ms": first_row_ms,
            "rows_returned": len(http_rows),
            "notes": "First row measured from live HTTP stream",
        }
    )

    channel = grpc.insecure_channel(grpc_endpoint)
    try:
        stub = session3_pb2_grpc.RegionalRevenueStub(channel)
        started = time.perf_counter()
        stream = iter(stub.ListRegions(Empty(), timeout=15))
        first = next(stream, None)
        grpc_first_row_ms = (time.perf_counter() - started) * 1000
        grpc_rows = [first] if first is not None else []
        grpc_rows.extend(stream)
        grpc_stream_ms = (time.perf_counter() - started) * 1000
    finally:
        channel.close()
    measurements.append(
        {
            "test": "gRPC server stream",
            "transport": "gRPC / typed protobuf",
            "requests": 1,
            "elapsed_ms": grpc_stream_ms,
            "time_to_first_row_ms": grpc_first_row_ms,
            "rows_returned": len(grpc_rows),
            "notes": "Typed protobuf server-streaming RPC",
        }
    )

    expected_rows = len(records)
    passed = (
        len(batch_rows) == expected_rows
        and len(individual_results) == expected_rows
        and len(http_rows) == expected_rows
        and len(grpc_rows) == expected_rows
    )
    report = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Local loopback benchmark; not student-hardware results",
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "regions_expected": expected_rows,
        "passed": passed,
        "measurements": measurements,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "roundtrip_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    for filename, selected in (
        ("roundtrip_benchmark.csv", measurements[:2]),
        ("streaming_benchmark.csv", measurements[2:]),
    ):
        with (output_dir / filename).open(
            "w", newline="", encoding="utf-8"
        ) as output:
            writer = csv.DictWriter(
                output, fieldnames=["measured_at", *measurements[0].keys()]
            )
            writer.writeheader()
            for measurement in selected:
                writer.writerow(
                    {"measured_at": report["measured_at"], **measurement}
                )
    return report


if __name__ == "__main__":
    from grpc_backend import make_grpc_service
    from services import make_service
    from session3_data import summary

    records = summary()["rows"]
    http_server = make_service(records)
    grpc_server, grpc_port = make_grpc_service(records)
    try:
        result = run_roundtrip_benchmark(
            records,
            f"http://127.0.0.1:{http_server.server_port}",
            f"127.0.0.1:{grpc_port}",
        )
    finally:
        http_server.shutdown()
        http_server.server_close()
        grpc_server.stop(0).wait()
    print(
        f"Round-trip benchmark {'PASSED' if result['passed'] else 'FAILED'}: "
        f"{result['regions_expected']} regions, {result['scope']}; "
        f"measured at {result['measured_at']}"
    )
    for measurement in result["measurements"]:
        print(
            f"  {measurement['test']}: {measurement['elapsed_ms']:.3f} ms; "
            f"{measurement['rows_returned']} rows"
        )
    raise SystemExit(0 if result["passed"] else 1)
