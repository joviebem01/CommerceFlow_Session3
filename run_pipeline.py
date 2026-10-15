"""Run the complete Session 3 pipeline without starting the Tkinter GUI."""
from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from typing import Any

from adapter_benchmark import run_adapter_comparison
from contracts import write_contract_report
from customer_archive import DEFAULT_CUSTOMERS_PATH, load_customer_archive
from deadline_check import verify_generous_deadline
from grpc_backend import make_grpc_service
from latency_benchmark import run_latency_benchmark
from payload_benchmark import run_payload_benchmark
from reconcile import reconcile_records
from roundtrip_benchmark import run_roundtrip_benchmark
from session3_data import summary
from services import make_service
from test_wire import verify_wire


def _run_stage(
    name: str,
    action: Callable[[], Mapping[str, Any]],
    results: list[tuple[str, bool]],
) -> Mapping[str, Any]:
    print(f"\n[{name}] Running...", flush=True)
    report = action()
    passed = bool(report.get("passed"))
    results.append((name, passed))
    print(f"[{name}] {'PASSED' if passed else 'FAILED'}", flush=True)
    return report


def main() -> int:
    http_server = None
    grpc_server = None
    stage_results: list[tuple[str, bool]] = []
    try:
        archive_summary = summary()
        stage_results.append(("Session 1/2 archive comparison", archive_summary["passed"]))
        print(
            "[Session 1/2 archive comparison] "
            f"{'PASSED' if archive_summary['passed'] else 'FAILED'} - "
            f"{archive_summary['regions']} regions, "
            f"{archive_summary['transactions']:,} transactions; "
            f"maximum count/revenue differences "
            f"{archive_summary['max_count_diff']}/"
            f"{archive_summary['max_revenue_diff']:.6g}",
            flush=True,
        )

        records = archive_summary["rows"]
        customers = load_customer_archive(DEFAULT_CUSTOMERS_PATH)

        contract_report = _run_stage(
            "Contract drift",
            write_contract_report,
            stage_results,
        )
        wire_report = _run_stage(
            "Wire verification",
            lambda: verify_wire(records, customer_records=customers),
            stage_results,
        )

        http_server = make_service(records)
        grpc_server, grpc_port = make_grpc_service(
            records, customer_records=customers
        )
        http_endpoint = f"http://127.0.0.1:{http_server.server_port}"
        grpc_endpoint = f"127.0.0.1:{grpc_port}"
        stage_results.append(("Local service startup", True))
        print(
            f"\n[Local service startup] PASSED - HTTP :{http_server.server_port}; "
            f"gRPC :{grpc_port}",
            flush=True,
        )

        payload_report = _run_stage(
            "Payload benchmark",
            lambda: run_payload_benchmark(records, http_endpoint, grpc_endpoint),
            stage_results,
        )
        latency_report = _run_stage(
            "Unary latency benchmark",
            lambda: run_latency_benchmark(records, http_endpoint, grpc_endpoint),
            stage_results,
        )
        roundtrip_report = _run_stage(
            "Round-trip and streaming benchmark",
            lambda: run_roundtrip_benchmark(records, http_endpoint, grpc_endpoint),
            stage_results,
        )
        adapter_report = _run_stage(
            "Transport adapter comparison",
            lambda: run_adapter_comparison(records, http_endpoint, grpc_endpoint),
            stage_results,
        )
        deadline_report = _run_stage(
            "Generous deadline",
            lambda: verify_generous_deadline(records, grpc_endpoint),
            stage_results,
        )

        def reconcile() -> Mapping[str, Any]:
            from transport import create_transport

            live_regions = create_transport("grpc", grpc_endpoint).call(
                "ListRegions"
            )[0]["regions"]
            _, report = reconcile_records(records, live_regions)
            return report

        reconciliation_report = _run_stage(
            "Three-way reconciliation",
            reconcile,
            stage_results,
        )

        print("\nPipeline summary:", flush=True)
        for name, passed in stage_results:
            print(f"  {'PASS' if passed else 'FAIL'}  {name}", flush=True)
        print(
            "\nReports are in results/. Measurements are local loopback results, "
            "not student-hardware measurements.",
            flush=True,
        )

        reports = (
            contract_report,
            wire_report,
            payload_report,
            latency_report,
            roundtrip_report,
            adapter_report,
            deadline_report,
            reconciliation_report,
        )
        return 0 if all(passed for _, passed in stage_results) and all(
            report.get("passed", False) for report in reports
        ) else 1
    except Exception as exc:
        print(f"\nPipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if http_server is not None:
            http_server.shutdown()
            http_server.server_close()
        if grpc_server is not None:
            grpc_server.stop(0).wait()


if __name__ == "__main__":
    raise SystemExit(main())
