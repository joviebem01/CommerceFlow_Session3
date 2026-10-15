"""Verify that a regional RPC succeeds with a generous explicit deadline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from transport import create_transport


ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "results" / "deadline_report.json"
NORMAL_DEADLINE_SECONDS = 10.0
GENEROUS_DEADLINE_SECONDS = 30.0


def verify_generous_deadline(
    records: Sequence[Sequence[Any]],
    endpoint: str,
    report_path: Path | None = REPORT_PATH,
) -> dict[str, Any]:
    """Call the same GetRegion with normal and explicitly generous deadlines."""
    if not records:
        raise ValueError("Deadline verification requires at least one regional record")

    region, expected_count, expected_revenue = records[0][:3]
    normal_result, _, _ = create_transport(
        "grpc", endpoint, timeout=NORMAL_DEADLINE_SECONDS
    ).call("GetRegion", region)
    generous_result, _, _ = create_transport(
        "grpc", endpoint, timeout=GENEROUS_DEADLINE_SECONDS
    ).call("GetRegion", region)
    expected = {
        "region": region,
        "transaction_count": int(expected_count),
        "revenue_total": float(expected_revenue),
    }
    normal_matches = normal_result == expected
    generous_matches = (
        generous_result["region"] == expected["region"]
        and generous_result["transaction_count"] == expected["transaction_count"]
        and abs(generous_result["revenue_total"] - expected["revenue_total"]) <= 1e-6
    )
    same_result = (
        normal_result["region"] == generous_result["region"]
        and normal_result["transaction_count"] == generous_result["transaction_count"]
        and abs(normal_result["revenue_total"] - generous_result["revenue_total"])
        <= 1e-6
    )
    report = {
        "passed": normal_matches and generous_matches and same_result,
        "operation": "GetRegion",
        "region": region,
        "normal_deadline_seconds": NORMAL_DEADLINE_SECONDS,
        "generous_deadline_seconds": GENEROUS_DEADLINE_SECONDS,
        "normal_deadline_succeeded": normal_matches,
        "normal_response": normal_result,
        "generous_deadline_response": generous_result,
        "same_response": same_result,
        "matches_archived_record": normal_matches and generous_matches,
        "source": "Live typed gRPC service compared with archived regional record",
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
