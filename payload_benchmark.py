"""Measure live HTTP/JSON and protobuf response sizes for regional RPCs."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from transport import create_transport


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"


def run_payload_benchmark(
    records: Sequence[Sequence[Any]],
    http_endpoint: str,
    grpc_endpoint: str,
    output_dir: Path = OUT,
) -> dict[str, Any]:
    """Measure matching live GetRegion responses and persist a reproducible report."""
    if not records:
        raise ValueError("Payload benchmark requires at least one regional record")

    json_transport = create_transport("json", http_endpoint)
    grpc_transport = create_transport("grpc", grpc_endpoint)
    measurements = []
    for region, *_ in records:
        _, json_request_bytes, json_response_bytes = json_transport.call(
            "GetRegion", region
        )
        _, grpc_request_bytes, grpc_response_bytes = grpc_transport.call(
            "GetRegion", region
        )
        measurements.append(
            {
                "region": region,
                "json_request_bytes": json_request_bytes,
                "json_response_bytes": json_response_bytes,
                "grpc_request_bytes": grpc_request_bytes,
                "grpc_response_bytes": grpc_response_bytes,
                "response_bytes_saved": json_response_bytes - grpc_response_bytes,
                "response_reduction_percent": (
                    1 - grpc_response_bytes / json_response_bytes
                )
                * 100,
            }
        )

    report = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "passed": len(measurements) == len(records)
        and all(
            row["json_response_bytes"] > 0
            and row["grpc_response_bytes"] > 0
            and row["json_request_bytes"] > 0
            for row in measurements
        ),
        "regions_measured": len(measurements),
        "transports": ["HTTP/JSON", "gRPC/protobuf"],
        "size_scope": "Serialized request/response bodies/messages; excludes HTTP/2 framing and headers",
        "measurements": measurements,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "payload_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    with (output_dir / "payload_sizes.csv").open(
        "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.DictWriter(output, fieldnames=list(measurements[0]))
        writer.writeheader()
        writer.writerows(measurements)
    return report


if __name__ == "__main__":
    from grpc_backend import make_grpc_service
    from services import make_service
    from session3_data import summary

    records = summary()["rows"]
    http_server = make_service(records)
    grpc_server, grpc_port = make_grpc_service(records)
    try:
        report = run_payload_benchmark(
            records,
            f"http://127.0.0.1:{http_server.server_port}",
            f"127.0.0.1:{grpc_port}",
        )
    finally:
        http_server.shutdown()
        http_server.server_close()
        grpc_server.stop(0).wait()
    print(
        f"Payload benchmark {'PASSED' if report['passed'] else 'FAILED'}: "
        f"{report['regions_measured']} regions; wrote "
        "results/payload_report.json and results/payload_sizes.csv"
    )
    raise SystemExit(0 if report["passed"] else 1)
