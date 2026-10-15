"""Compare live transport adapters against the same regional service contract."""
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
REVENUE_TOLERANCE = 1e-6


def run_adapter_comparison(
    records: Sequence[Sequence[Any]],
    http_endpoint: str,
    grpc_endpoint: str,
    output_dir: Path = OUT,
) -> dict[str, Any]:
    """Measure both live adapters and verify their values against archive records."""
    if not records:
        raise ValueError("Adapter comparison requires at least one regional record")

    configurations = (
        ("HTTP / JSON", "json", http_endpoint),
        ("gRPC / typed protobuf", "grpc", grpc_endpoint),
    )
    comparisons = []
    results_by_transport: list[list[dict[str, Any]]] = []
    for label, kind, endpoint in configurations:
        transport = create_transport(kind, endpoint)
        elapsed_ms = []
        sent_bytes = 0
        received_bytes = 0
        results = []
        for region, expected_count, expected_revenue, *_ in records:
            started = time.perf_counter()
            result, sent, received = transport.call("GetRegion", str(region))
            elapsed_ms.append((time.perf_counter() - started) * 1000)
            sent_bytes += sent
            received_bytes += received
            results.append(result)
            if (
                result.get("region") != region
                or result.get("transaction_count") != int(expected_count)
                or not isinstance(result.get("revenue_total"), (int, float))
                or abs(float(result["revenue_total"]) - float(expected_revenue))
                > REVENUE_TOLERANCE
            ):
                raise RuntimeError(
                    f"{label} returned an unexpected GetRegion response for {region}"
                )
        results_by_transport.append(results)
        comparisons.append(
            {
                "transport": label,
                "calls": len(results),
                "mean_ms_per_call": statistics.mean(elapsed_ms),
                "sent_bytes": sent_bytes,
                "received_bytes": received_bytes,
            }
        )

    identical = all(
        first["region"] == second["region"]
        and first["transaction_count"] == second["transaction_count"]
        and abs(first["revenue_total"] - second["revenue_total"])
        <= REVENUE_TOLERANCE
        for first, second in zip(*results_by_transport)
    )
    report = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Live loopback adapter comparison; not student-hardware results",
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "regions_compared": len(records),
        "identical_responses": identical,
        "passed": identical
        and all(row["calls"] == len(records) for row in comparisons),
        "transports": comparisons,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "adapter_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    with (output_dir / "adapter_comparison.csv").open(
        "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.DictWriter(
            output, fieldnames=["measured_at", *comparisons[0].keys()]
        )
        writer.writeheader()
        for comparison in comparisons:
            writer.writerow({"measured_at": report["measured_at"], **comparison})
    return report


if __name__ == "__main__":
    from grpc_backend import make_grpc_service
    from services import make_service
    from session3_data import summary

    records = summary()["rows"]
    http_server = make_service(records)
    grpc_server, grpc_port = make_grpc_service(records)
    try:
        result = run_adapter_comparison(
            records,
            f"http://127.0.0.1:{http_server.server_port}",
            f"127.0.0.1:{grpc_port}",
        )
    finally:
        http_server.shutdown()
        http_server.server_close()
        grpc_server.stop(0).wait()
    print(
        f"Adapter comparison {'PASSED' if result['passed'] else 'FAILED'}: "
        f"{result['regions_compared']} regions; {result['scope']}; "
        f"measured at {result['measured_at']}"
    )
    raise SystemExit(0 if result["passed"] else 1)
