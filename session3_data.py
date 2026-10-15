"""Shared Session 1 and Session 2 archive loading for GUI and CLI."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from domain_keys import normalize_domain_key


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        return list(csv.DictReader(source))


def summary() -> dict[str, Any]:
    """Load and compare the archived Session 1 baseline and Session 2 output."""
    session1_rows = read_csv(DATA / "session1" / "baseline_result.csv")
    session2_rows = read_csv(DATA / "session2" / "streamed_regional_revenue.csv")
    session2_by_region = {
        normalize_domain_key(row["region"]): row for row in session2_rows
    }
    rows = []
    for row in session1_rows:
        region = normalize_domain_key(row["state"])
        session2 = session2_by_region.get(region)
        if session2 is None:
            rows.append(
                [region, int(row["order_count"]), float(row["revenue_total"]), None, None]
            )
            continue
        rows.append(
            [
                region,
                int(row["order_count"]),
                float(row["revenue_total"]),
                int(session2["txn_count"]),
                float(session2["revenue_total"]),
            ]
        )

    matched = len(rows) == len(session2_rows) and all(
        row[3] is not None for row in rows
    )
    max_count_difference = max(
        (abs(row[1] - row[3]) for row in rows if row[3] is not None),
        default=float("inf"),
    )
    max_revenue_difference = max(
        (abs(row[2] - row[4]) for row in rows if row[4] is not None),
        default=float("inf"),
    )
    session1_revenue = sum(row[2] for row in rows)
    session2_revenue = sum(row[4] for row in rows if row[4] is not None)
    return {
        "rows": rows,
        "regions": len(rows),
        "transactions": sum(row[1] for row in rows),
        "revenue": session1_revenue,
        "stream_transactions": sum(int(row["txn_count"]) for row in session2_rows),
        "stream_revenue": session2_revenue,
        "max_count_diff": max_count_difference,
        "max_revenue_diff": max_revenue_difference,
        "passed": matched
        and max_count_difference == 0
        and max_revenue_difference <= 1e-6,
    }
