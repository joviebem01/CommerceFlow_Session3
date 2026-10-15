"""Live wire-format verification for the HTTP/JSON and protobuf/gRPC adapters."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Sequence

import session3_pb2
from grpc_backend import make_grpc_service
from customer_archive import DEFAULT_CUSTOMERS_PATH, load_customer_archive
from services import make_service
from transport import create_transport
from wire import responses_match


ROOT = Path(__file__).resolve().parent
WIRE_REPORT = ROOT / "results" / "wire_report.json"


def verify_wire(
    records: Sequence[Sequence[Any]] | None = None,
    report_path: Path | None = WIRE_REPORT,
    customer_records: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    """Exercise each operation over both live transports and check response parity."""
    if records is None:
        from session3_data import summary

        records = summary()["rows"]
    if not records:
        raise ValueError("Wire verification requires at least one regional record")
    if customer_records is None:
        customer_records = load_customer_archive(DEFAULT_CUSTOMERS_PATH)
    http_server = make_service(records)
    grpc_server = None
    checks: list[dict[str, Any]] = []
    try:
        grpc_server, grpc_port = make_grpc_service(
            records,
            customer_records=customer_records,
        )
        http_url = f"http://127.0.0.1:{http_server.server_port}"
        grpc_target = f"127.0.0.1:{grpc_port}"

        for region, count, revenue, _, _ in records:
            json_result, _, _ = create_transport("json", http_url).call(
                "GetRegion", region
            )
            grpc_result, _, _ = create_transport("grpc", grpc_target).call(
                "GetRegion", region
            )
            expected = {
                "region": region,
                "transaction_count": count,
                "revenue_total": revenue,
            }
            checks.append(
                {
                    "name": f"GetRegion({region})",
                    "passed": responses_match(json_result, expected)
                    and responses_match(grpc_result, expected)
                    and responses_match(json_result, grpc_result),
                    "http_json": json_result,
                    "grpc_protobuf": grpc_result,
                }
            )

        expected_summary = {
            "regions": len(records),
            "transactions": sum(row[1] for row in records),
            "revenue_total": sum(row[2] for row in records),
        }
        for method in ("GetSummary", "ListRegions"):
            json_result, _, _ = create_transport("json", http_url).call(method)
            grpc_result, _, _ = create_transport("grpc", grpc_target).call(method)
            if method == "GetSummary":
                expected = expected_summary
            else:
                expected = {
                    "regions": [
                        {
                            "region": region,
                            "transaction_count": count,
                            "revenue_total": revenue,
                        }
                        for region, count, revenue, _, _ in records
                    ]
                }
            checks.append(
                {
                    "name": method,
                    "passed": responses_match(json_result, expected)
                    and responses_match(grpc_result, expected)
                    and responses_match(json_result, grpc_result),
                    "http_json": json_result,
                    "grpc_protobuf": grpc_result,
                }
            )

        config_result, _, _ = create_transport("grpc", grpc_target).call("GetConfig")
        expected_config = {
            "service_name": "RegionalRevenue",
            "contract_package": "cmaflow.v1",
            "canonical_region_key": "region",
            "region_count": len(records),
            "grpc_max_workers": 10,
        }
        checks.append(
            {
                "name": "ConfigService.GetConfig",
                "passed": responses_match(config_result, expected_config),
                "grpc_protobuf": config_result,
            }
        )

        entitlement_result, _, _ = create_transport(
            "grpc", grpc_target
        ).call(
            "EvaluateEntitlement",
            customer_id="example-customer",
            entitlement_key="premium-access",
        )
        expected_entitlement = {
            "status": "ENTITLEMENT_STATUS_NOT_CONFIGURED",
            "message": (
                "Entitlement decisions are unavailable: no entitlement "
                "policies or entitlement data are configured."
            ),
        }
        checks.append(
            {
                "name": "EntitlementService.EvaluateEntitlement",
                "passed": responses_match(entitlement_result, expected_entitlement),
                "grpc_protobuf": entitlement_result,
            }
        )

        unique_customer = next(
            (
                (customer_id, matches[0])
                for customer_id, matches in customer_records.items()
                if len(matches) == 1
            ),
            None,
        )
        if unique_customer is None:
            raise ValueError("Customer archive contains no unambiguous customer IDs")
        customer_id, archived_customer = unique_customer
        customer_result, _, _ = create_transport(
            "grpc", grpc_target
        ).call("ResolveCustomer", customer_id=customer_id)
        expected_customer = {
            "status": "CUSTOMER_RESOLUTION_STATUS_FOUND",
            "archive_backed": True,
            "source_file": "data/Datasets/crm_50000_customers_dirty_v3.csv",
            "customer_id": customer_id,
            "match_count": 1,
            **archived_customer,
        }
        checks.append(
            {
                "name": "CustomerService.ResolveCustomer (unique)",
                "passed": responses_match(customer_result, expected_customer),
                "grpc_protobuf": customer_result,
            }
        )

        duplicate_customer_id = next(
            (
                customer_id
                for customer_id, matches in customer_records.items()
                if len(matches) > 1
            ),
            None,
        )
        if duplicate_customer_id is not None:
            ambiguous_result, _, _ = create_transport(
                "grpc", grpc_target
            ).call(
                "ResolveCustomer", customer_id=duplicate_customer_id
            )
            expected_ambiguous = {
                "status": "CUSTOMER_RESOLUTION_STATUS_AMBIGUOUS",
                "archive_backed": True,
                "source_file": "data/Datasets/crm_50000_customers_dirty_v3.csv",
                "customer_id": duplicate_customer_id,
                "match_count": len(customer_records[duplicate_customer_id]),
                "first_name": "",
                "last_name": "",
                "city": "",
                "state": "",
                "country": "",
            }
            checks.append(
                {
                    "name": "CustomerService.ResolveCustomer (ambiguous ID)",
                    "passed": responses_match(ambiguous_result, expected_ambiguous),
                    "grpc_protobuf": ambiguous_result,
                }
            )

        missing_customer_id = "__wire_verification_missing_customer__"
        while missing_customer_id in customer_records:
            missing_customer_id += "_"
        missing_result, _, _ = create_transport(
            "grpc", grpc_target
        ).call("ResolveCustomer", customer_id=missing_customer_id)
        expected_missing = {
            "status": "CUSTOMER_RESOLUTION_STATUS_NOT_FOUND",
            "archive_backed": True,
            "source_file": "data/Datasets/crm_50000_customers_dirty_v3.csv",
            "customer_id": missing_customer_id,
            "match_count": 0,
            "first_name": "",
            "last_name": "",
            "city": "",
            "state": "",
            "country": "",
        }
        checks.append(
            {
                "name": "CustomerService.ResolveCustomer (not found)",
                "passed": responses_match(missing_result, expected_missing),
                "grpc_protobuf": missing_result,
            }
        )
    finally:
        http_server.shutdown()
        http_server.server_close()
        if grpc_server is not None:
            grpc_server.stop(0).wait()

    report = {
        "passed": all(check["passed"] for check in checks),
        "transports": ["HTTP/JSON", "gRPC/protobuf"],
        "operations_checked": len(checks),
        "checks": checks,
        "protobuf_service": session3_pb2.DESCRIPTOR.services_by_name[
            "RegionalRevenue"
        ].full_name,
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


class WireVerificationTests(unittest.TestCase):
    def test_live_http_json_and_grpc_protobuf_agree(self) -> None:
        records = [
            ("Example A", 3, 12.5, None, None),
            ("Example B", 7, 42.25, None, None),
        ]
        archived_customers = {
            "customer-1": [
                {
                    "customer_id": "customer-1",
                    "first_name": "Example",
                    "last_name": "Customer",
                    "city": "Example City",
                    "state": "Example State",
                    "country": "Example Country",
                }
            ],
            "duplicate-customer": [
                {
                    "customer_id": "duplicate-customer",
                    "first_name": "First",
                    "last_name": "Record",
                    "city": "Example City",
                    "state": "Example State",
                    "country": "Example Country",
                },
                {
                    "customer_id": "duplicate-customer",
                    "first_name": "Second",
                    "last_name": "Record",
                    "city": "Example City",
                    "state": "Example State",
                    "country": "Example Country",
                },
            ],
        }
        report = verify_wire(
            records,
            report_path=None,
            customer_records=archived_customers,
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["operations_checked"], 9)
        config_check = next(
            check for check in report["checks"] if check["name"] == "ConfigService.GetConfig"
        )
        self.assertEqual(config_check["grpc_protobuf"]["region_count"], len(records))
        entitlement_check = next(
            check
            for check in report["checks"]
            if check["name"] == "EntitlementService.EvaluateEntitlement"
        )
        self.assertEqual(
            entitlement_check["grpc_protobuf"]["status"],
            "ENTITLEMENT_STATUS_NOT_CONFIGURED",
        )
        ambiguous_customer_check = next(
            check
            for check in report["checks"]
            if check["name"] == "CustomerService.ResolveCustomer (ambiguous ID)"
        )
        self.assertEqual(
            ambiguous_customer_check["grpc_protobuf"]["status"],
            "CUSTOMER_RESOLUTION_STATUS_AMBIGUOUS",
        )

    def test_response_shape_and_values_are_required(self) -> None:
        expected = {
            "region": "Example A",
            "transaction_count": 3,
            "revenue_total": 12.5,
        }
        self.assertFalse(
            responses_match(
                {"region": "Example A", "transaction_count": 4, "revenue_total": 12.5},
                expected,
            )
        )
        self.assertFalse(responses_match({**expected, "extra": True}, expected))



if __name__ == "__main__":
    result = verify_wire()
    print(
        f"Wire verification: {'PASSED' if result['passed'] else 'FAILED'} "
        f"({result['operations_checked']} checks)"
    )
    for check in result["checks"]:
        print(f"  {'OK' if check['passed'] else 'MISMATCH'}: {check['name']}")
    raise SystemExit(0 if result["passed"] else 1)
