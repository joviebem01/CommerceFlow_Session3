"""Measure unary HTTP/JSON and gRPC latency in the current environment."""
from __future__ import annotations

import csv
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from transport import create_transport


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"


def run_latency_benchmark(
    records: Sequence[Sequence[Any]],
    http_endpoint: str,
    grpc_endpoint: str,
    calls_per_transport: int = 100,
    output_dir: Path = OUT,
) -> dict[str, Any]:
    """Measure repeated live GetRegion calls and persist timestamped environment data."""
    if not records:
        raise ValueError("Latency benchmark requires at least one regional record")
    if calls_per_transport < 1:
        raise ValueError("calls_per_transport must be at least one")

    endpoints = {
        "HTTP / JSON": ("json", http_endpoint),
        "gRPC / typed protobuf": ("grpc", grpc_endpoint),
    }
    measurements = []
    for label, (kind, endpoint) in endpoints.items():
        transport = create_transport(kind, endpoint)
        samples_ms = []
        response_bytes = 0
        start = time.perf_counter()
        for index in range(calls_per_transport):
            region = records[index % len(records)][0]
            call_start = time.perf_counter()
            _, _, size = transport.call("GetRegion", region)
            samples_ms.append((time.perf_counter() - call_start) * 1000)
            response_bytes += size
        elapsed_seconds = time.perf_counter() - start
        measurements.append(
            {
                "transport": label,
                "calls": calls_per_transport,
                "median_ms": statistics.median(samples_ms),
                "mean_ms": statistics.mean(samples_ms),
                "requests_per_second": calls_per_transport / elapsed_seconds,
                "response_bytes": response_bytes,
                "elapsed_seconds": elapsed_seconds,
            }
        )

    report = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Local loopback service benchmark; not student-hardware results",
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "calls_per_transport": calls_per_transport,
        "passed": all(
            measurement["calls"] == calls_per_transport
            and measurement["median_ms"] > 0
            and measurement["mean_ms"] > 0
            and measurement["requests_per_second"] > 0
            and measurement["response_bytes"] > 0
            for measurement in measurements
        ),
        "measurements": measurements,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latency_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    with (output_dir / "latency_benchmark.csv").open(
        "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.DictWriter(
            output, fieldnames=["measured_at", *measurements[0].keys()]
        )
        writer.writeheader()
        for measurement in measurements:
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
        result = run_latency_benchmark(
            records,
            f"http://127.0.0.1:{http_server.server_port}",
            f"127.0.0.1:{grpc_port}",
        )
    finally:
        http_server.shutdown()
        http_server.server_close()
        grpc_server.stop(0).wait()
    print(
        f"Latency benchmark {'PASSED' if result['passed'] else 'FAILED'}: "
        f"{result['calls_per_transport']} calls per transport; "
        f"measured at {result['measured_at']}; scope: {result['scope']}"
    )
    for measurement in result["measurements"]:
        print(
            f"  {measurement['transport']}: median "
            f"{measurement['median_ms']:.4f} ms, mean "
            f"{measurement['mean_ms']:.4f} ms, "
            f"{measurement['requests_per_second']:.2f} requests/s"
        )
    raise SystemExit(0 if result["passed"] else 1)
