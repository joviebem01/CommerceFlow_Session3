"""Canonical domain-key mapping for archived and live regional revenue data."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CANONICAL_DOMAIN_KEY = "region"
SOURCE_KEY_FIELDS = {
    "Session 1": ("session1/baseline_result.csv", "state"),
    "Session 2": ("session2/streamed_regional_revenue.csv", "region"),
    "Session 3": ("session3.proto", "RegionRequest.region / RegionResponse.region"),
}


def normalize_domain_key(value: Any) -> str:
    """Normalize a regional identifier consistently across service boundaries."""
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("Regional domain key cannot be empty")
    return normalized


def check_archive_domain_keys(data_dir: Path = DATA) -> dict[str, Any]:
    """Check exact key coverage between the two archived regional datasets."""
    source_keys: dict[str, set[str]] = {}
    for source, (relative_path, key_field) in list(SOURCE_KEY_FIELDS.items())[:2]:
        path = data_dir / relative_path
        with path.open(newline="", encoding="utf-8-sig") as input_file:
            reader = csv.DictReader(input_file)
            if key_field not in (reader.fieldnames or []):
                raise ValueError(
                    f"{source} archive lacks its declared key field {key_field!r}"
                )
            keys = [normalize_domain_key(row[key_field]) for row in reader]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{source} archive contains duplicate regional keys")
        source_keys[source] = set(keys)

    session1 = source_keys["Session 1"]
    session2 = source_keys["Session 2"]
    return {
        "passed": session1 == session2,
        "canonical_key": CANONICAL_DOMAIN_KEY,
        "source_key_fields": {
            "Session 1": "state",
            "Session 2": "region",
            "Session 3": "region",
        },
        "regions_compared": len(session1),
        "session1_missing_in_session2": sorted(session1 - session2),
        "session2_missing_in_session1": sorted(session2 - session1),
        "kafka_partition_configuration": {
            "status": "NOT PRESENT",
            "evidence": "The supplied Session 2 archive contains no Kafka partition configuration.",
        },
    }
