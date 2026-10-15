"""gRPC server backend for the typed RegionalRevenue contract."""
from __future__ import annotations

from concurrent import futures
from typing import Any, Mapping, Sequence

import grpc

import session3_pb2
import session3_pb2_grpc
from delivery_metrics import AbandonedResponseCounter


RegionalRecord = Sequence[Any]
ArchivedCustomer = Mapping[str, str]
GRPC_MAX_WORKERS = 10
CUSTOMER_SOURCE_FILE = "data/Datasets/crm_50000_customers_dirty_v3.csv"


def make_grpc_service(
    records: Sequence[RegionalRecord],
    abandoned_responses: AbandonedResponseCounter | None = None,
    customer_records: Mapping[str, Sequence[ArchivedCustomer]] | None = None,
):
    """Start the local gRPC server and return it with its dynamically bound port."""
    counter = abandoned_responses or AbandonedResponseCounter()

    def track_abandonment(context, completed: list[bool]) -> None:
        def record_if_cancelled() -> None:
            if (
                not completed[0]
                and not context.is_active()
                and context.code() in (None, grpc.StatusCode.CANCELLED)
            ):
                counter.record_abandoned()

        context.add_callback(record_if_cancelled)

    class RegionalRevenueService(session3_pb2_grpc.RegionalRevenueServicer):
        def _track_abandonment(self, context, completed: list[bool]) -> None:
            track_abandonment(context, completed)

        def GetRegion(self, request, context):
            completed = [False]
            self._track_abandonment(context, completed)
            region = request.region.strip()
            for name, count, revenue, *_ in records:
                if name == region:
                    response = session3_pb2.RegionResponse(
                        region=name,
                        transaction_count=count,
                        revenue_total=revenue,
                    )
                    completed[0] = True
                    return response
            context.abort(grpc.StatusCode.NOT_FOUND, f"unknown region: {region}")

        def GetSummary(self, request, context):
            completed = [False]
            self._track_abandonment(context, completed)
            response = session3_pb2.SummaryResponse(
                region_count=len(records),
                transaction_count=sum(row[1] for row in records),
                revenue_total=sum(row[2] for row in records),
            )
            completed[0] = True
            return response

        def ListRegions(self, request, context):
            completed = [False]
            self._track_abandonment(context, completed)
            for region, count, revenue, *_ in records:
                yield session3_pb2.RegionResponse(
                    region=region,
                    transaction_count=count,
                    revenue_total=revenue,
                )
            completed[0] = True

    class ConfigService(session3_pb2_grpc.ConfigServiceServicer):
        def GetConfig(self, request, context):
            completed = [False]
            track_abandonment(context, completed)
            response = session3_pb2.ConfigResponse(
                service_name="RegionalRevenue",
                contract_package=session3_pb2.DESCRIPTOR.package,
                canonical_region_key="region",
                region_count=len(records),
                grpc_max_workers=GRPC_MAX_WORKERS,
            )
            completed[0] = True
            return response

    class EntitlementService(session3_pb2_grpc.EntitlementServiceServicer):
        def EvaluateEntitlement(self, request, context):
            completed = [False]
            track_abandonment(context, completed)
            response = session3_pb2.EntitlementResponse(
                status=session3_pb2.ENTITLEMENT_STATUS_NOT_CONFIGURED,
                message=(
                    "Entitlement decisions are unavailable: no entitlement "
                    "policies or entitlement data are configured."
                ),
            )
            completed[0] = True
            return response

    class CustomerService(session3_pb2_grpc.CustomerServiceServicer):
        def ResolveCustomer(self, request, context):
            completed = [False]
            track_abandonment(context, completed)
            if customer_records is None:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    "Customer archive is not loaded; customer resolution is unavailable.",
                )
            customer_id = request.customer_id.strip()
            matches = customer_records.get(customer_id, ())
            if not matches:
                response = session3_pb2.CustomerResponse(
                    status=session3_pb2.CUSTOMER_RESOLUTION_STATUS_NOT_FOUND,
                    archive_backed=True,
                    source_file=CUSTOMER_SOURCE_FILE,
                    customer_id=customer_id,
                )
            elif len(matches) > 1:
                response = session3_pb2.CustomerResponse(
                    status=session3_pb2.CUSTOMER_RESOLUTION_STATUS_AMBIGUOUS,
                    archive_backed=True,
                    source_file=CUSTOMER_SOURCE_FILE,
                    customer_id=customer_id,
                    match_count=len(matches),
                )
            else:
                customer = matches[0]
                response = session3_pb2.CustomerResponse(
                    status=session3_pb2.CUSTOMER_RESOLUTION_STATUS_FOUND,
                    archive_backed=True,
                    source_file=CUSTOMER_SOURCE_FILE,
                    customer_id=customer_id,
                    match_count=1,
                    first_name=customer["first_name"],
                    last_name=customer["last_name"],
                    city=customer["city"],
                    state=customer["state"],
                    country=customer["country"],
                )
            completed[0] = True
            return response

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=GRPC_MAX_WORKERS))
    session3_pb2_grpc.add_RegionalRevenueServicer_to_server(
        RegionalRevenueService(), server
    )
    session3_pb2_grpc.add_ConfigServiceServicer_to_server(ConfigService(), server)
    session3_pb2_grpc.add_EntitlementServiceServicer_to_server(
        EntitlementService(), server
    )
    session3_pb2_grpc.add_CustomerServiceServicer_to_server(
        CustomerService(), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    if not port:
        raise RuntimeError("Could not bind the local gRPC service")
    server.start()
    return server, port
