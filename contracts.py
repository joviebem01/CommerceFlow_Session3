"""Validate archived input schemas and the generated protobuf contract."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import session3_pb2
from domain_keys import check_archive_domain_keys


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "results"

CSV_CONTRACTS = {
    "session1/baseline_result.csv": (
        "state",
        "order_count",
        "successful_orders",
        "revenue_total",
        "aov",
    ),
    "session2/streamed_regional_revenue.csv": (
        "region",
        "txn_count",
        "revenue_total",
        "revenue_mean",
    ),
    "Datasets/crm_50000_customers_dirty_v3.csv": (
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "gender",
        "dob",
        "signup_date",
        "address",
        "city",
        "state",
        "country",
        "device_id(s)",
        "source",
    ),
}

PROTO_MESSAGE_CONTRACTS = {
    "RegionRequest": {"region": 9},
    "RegionResponse": {
        "region": 9,
        "transaction_count": 3,
        "revenue_total": 1,
    },
    "SummaryResponse": {
        "region_count": 5,
        "transaction_count": 3,
        "revenue_total": 1,
    },
    "ConfigResponse": {
        "service_name": 9,
        "contract_package": 9,
        "canonical_region_key": 9,
        "region_count": 5,
        "grpc_max_workers": 5,
    },
    "EntitlementRequest": {
        "customer_id": 9,
        "entitlement_key": 9,
    },
    "EntitlementResponse": {
        "status": 14,
        "message": 9,
    },
    "CustomerRequest": {"customer_id": 9},
    "CustomerResponse": {
        "status": 14,
        "archive_backed": 8,
        "source_file": 9,
        "customer_id": 9,
        "match_count": 5,
        "first_name": 9,
        "last_name": 9,
        "city": 9,
        "state": 9,
        "country": 9,
    },
}
PROTO_METHOD_CONTRACTS = {
    "GetRegion": ("cmaflow.v1.RegionRequest", "cmaflow.v1.RegionResponse", False),
    "GetSummary": ("google.protobuf.Empty", "cmaflow.v1.SummaryResponse", False),
    "ListRegions": ("google.protobuf.Empty", "cmaflow.v1.RegionResponse", True),
}
PROTO_SERVICE_CONTRACTS = {
    "RegionalRevenue": {
        name: (request, response, streaming)
        for name, (request, response, streaming) in PROTO_METHOD_CONTRACTS.items()
    },
    "ConfigService": {
        "GetConfig": ("google.protobuf.Empty", "cmaflow.v1.ConfigResponse", False),
    },
    "EntitlementService": {
        "EvaluateEntitlement": (
            "cmaflow.v1.EntitlementRequest",
            "cmaflow.v1.EntitlementResponse",
            False,
        ),
    },
    "CustomerService": {
        "ResolveCustomer": (
            "cmaflow.v1.CustomerRequest",
            "cmaflow.v1.CustomerResponse",
            False,
        ),
    },
}


def _compare_fields(expected: dict[str, int], actual: dict[str, int]) -> dict[str, Any]:
    missing = sorted(expected.keys() - actual.keys())
    unexpected = sorted(actual.keys() - expected.keys())
    wrong_types = {
        name: {"expected": expected[name], "actual": actual[name]}
        for name in sorted(expected.keys() & actual.keys())
        if expected[name] != actual[name]
    }
    return {
        "passed": not missing and not unexpected and not wrong_types,
        "missing": missing,
        "unexpected": unexpected,
        "wrong_types": wrong_types,
    }


def check_contracts(data_dir: Path = DATA) -> dict[str, Any]:
    """Compare the archived CSV headers and generated protobuf descriptors to contracts."""
    checks: list[dict[str, Any]] = []

    for relative_path, expected_columns in CSV_CONTRACTS.items():
        path = data_dir / relative_path
        if not path.is_file():
            checks.append(
                {
                    "name": relative_path,
                    "kind": "csv",
                    "expected": list(expected_columns),
                    "actual": None,
                    "passed": False,
                    "error": "required CSV file is missing",
                }
            )
            continue
        with path.open(newline="", encoding="utf-8-sig") as source:
            actual_columns = csv.DictReader(source).fieldnames or []
        comparison = _compare_fields(
            {column: 0 for column in expected_columns},
            {column: 0 for column in actual_columns},
        )
        duplicates = sorted(
            column for column in set(actual_columns) if actual_columns.count(column) > 1
        )
        checks.append(
            {
                "name": relative_path,
                "kind": "csv",
                "expected": list(expected_columns),
                "actual": actual_columns,
                "duplicates": duplicates,
                **comparison,
                "passed": comparison["passed"] and not duplicates,
            }
        )

    domain_key_check = check_archive_domain_keys(data_dir)
    checks.append(
        {
            "name": "canonical regional domain key",
            "kind": "domain_key",
            **domain_key_check,
        }
    )

    descriptor = session3_pb2.DESCRIPTOR
    for message_name, expected_fields in PROTO_MESSAGE_CONTRACTS.items():
        message = descriptor.message_types_by_name.get(message_name)
        actual_fields = (
            {field.name: field.type for field in message.fields} if message else {}
        )
        comparison = _compare_fields(expected_fields, actual_fields)
        checks.append(
            {
                "name": f"protobuf message {message_name}",
                "kind": "protobuf_message",
                "expected": expected_fields,
                "actual": actual_fields if message else None,
                "present": message is not None,
                **comparison,
                "passed": message is not None and comparison["passed"],
            }
        )

    for service_name, expected_methods in PROTO_SERVICE_CONTRACTS.items():
        service = descriptor.services_by_name.get(service_name)
        actual_methods = (
            {
                method.name: (
                    method.input_type.full_name,
                    method.output_type.full_name,
                    method.server_streaming,
                )
                for method in service.methods
            }
            if service
            else {}
        )
        missing = sorted(expected_methods.keys() - actual_methods.keys())
        unexpected = sorted(actual_methods.keys() - expected_methods.keys())
        changed = {
            name: {"expected": expected_methods[name], "actual": actual_methods[name]}
            for name in sorted(expected_methods.keys() & actual_methods.keys())
            if expected_methods[name] != actual_methods[name]
        }
        checks.append(
            {
                "name": f"protobuf service {service_name}",
                "kind": "protobuf_service",
                "expected": expected_methods,
                "actual": actual_methods if service else None,
                "present": service is not None,
                "passed": service is not None and not missing and not unexpected and not changed,
                "missing": missing,
                "unexpected": unexpected,
                "changed": changed,
            }
        )

    return {
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "partitioning": domain_key_check["kafka_partition_configuration"],
    }


def write_contract_report(
    data_dir: Path = DATA, output_path: Path = OUT / "contract_report.json"
) -> dict[str, Any]:
    report = check_contracts(data_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = write_contract_report()
    print(f"Contract drift check: {'PASSED' if result['passed'] else 'FAILED'}")
    for check in result["checks"]:
        print(f"  {'OK' if check['passed'] else 'DRIFT'}: {check['name']}")
    raise SystemExit(0 if result["passed"] else 1)
