"""Three-way reconciliation gate for archived and live regional results."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
REVENUE_TOLERANCE = 1e-6


def reconcile_records(
    archived_rows: Sequence[Sequence[Any]],
    live_records: Sequence[dict[str, Any]],
    output_dir: Path = OUT,
) -> tuple[list[list[Any]], dict[str, Any]]:
    """Compare S1 and S2 archive rows with live S3 values, then persist the audit."""
    if not archived_rows:
        raise ValueError("Three-way reconciliation requires archived regional records")

    archived_regions = [str(row[0]) for row in archived_rows]
    if len(set(archived_regions)) != len(archived_regions):
        raise ValueError("Archived results contain duplicate regions")

    live_by_region: dict[str, dict[str, Any]] = {}
    for record in live_records:
        region = str(record["region"])
        if region in live_by_region:
            raise ValueError(f"Session 3 returned duplicate region: {region}")
        live_by_region[region] = record

    rows: list[list[Any]] = []
    differences: list[tuple[int, float, int, float, int, float]] = []
    for archived in archived_rows:
        region, s1_count, s1_revenue, s2_count, s2_revenue = archived
        if s2_count is None or s2_revenue is None:
            raise ValueError(f"Archived Session 2 is missing region: {region}")
        live = live_by_region.get(region)
        if live is None:
            raise ValueError(f"Session 3 missing state {region}")

        s3_count = int(live["transaction_count"])
        s3_revenue = float(live["revenue_total"])
        differences.append(
            (
                abs(int(s1_count) - int(s2_count)),
                abs(float(s1_revenue) - float(s2_revenue)),
                abs(s3_count - int(s1_count)),
                abs(s3_revenue - float(s1_revenue)),
                abs(s3_count - int(s2_count)),
                abs(s3_revenue - float(s2_revenue)),
            )
        )
        rows.append(
            [
                region,
                s1_count,
                s2_count,
                s3_count,
                f"{float(s1_revenue):,.2f}",
                f"{float(s2_revenue):,.2f}",
                f"{s3_revenue:,.2f}",
            ]
        )

    max_differences = [
        max(difference[index] for difference in differences) for index in range(6)
    ]
    unexpected_regions = sorted(live_by_region.keys() - set(archived_regions))
    gates = {
        "s1_s2_transaction_counts": max_differences[0] == 0,
        "s1_s2_revenue": max_differences[1] <= REVENUE_TOLERANCE,
        "s1_s3_transaction_counts": max_differences[2] == 0,
        "s1_s3_revenue": max_differences[3] <= REVENUE_TOLERANCE,
        "s2_s3_transaction_counts": max_differences[4] == 0,
        "s2_s3_revenue": max_differences[5] <= REVENUE_TOLERANCE,
        "region_set": len(live_records) == len(archived_rows) and not unexpected_regions,
    }
    report = {
        "passed": all(gates.values()),
        "gates": gates,
        "regions": len(archived_rows),
        "transaction_count": sum(int(row[1]) for row in archived_rows),
        "revenue_total": sum(float(row[2]) for row in archived_rows),
        "max_differences": [
            max_differences[2],
            max_differences[3],
            max_differences[4],
            max_differences[5],
        ],
        "unexpected_regions": unexpected_regions,
        "source": "Archived S1 baseline, archived S2 stream, live typed gRPC composed S3",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "session3_reconciliation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    with (output_dir / "session3_regional_revenue.csv").open(
        "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.writer(output)
        writer.writerow(["region", "transactions", "revenue_total"])
        for record in live_records:
            writer.writerow(
                [
                    record["region"],
                    int(record["transaction_count"]),
                    format(float(record["revenue_total"]), ".12f"),
                ]
            )
    return rows, report
