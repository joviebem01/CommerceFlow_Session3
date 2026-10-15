"""Client-side transport adapters for the Session 3 service contract."""
from __future__ import annotations

import urllib.request
from typing import Any, Literal, Protocol

import grpc
from google.protobuf.empty_pb2 import Empty

import session3_pb2
import session3_pb2_grpc
from wire import JsonCodec, ProtobufCodec


TransportKind = Literal["json", "grpc"]
TransportResponse = tuple[dict[str, Any], int, int]


class Transport(Protocol):
    def call(
        self,
        method: str,
        state: str = "Alabama",
        *,
        customer_id: str = "",
        entitlement_key: str = "",
    ) -> TransportResponse:
        """Call a service operation and return its value and wire message sizes."""


class HttpJsonTransport:
    def __init__(self, endpoint: str, timeout: float = 10):
        self.endpoint = endpoint
        self.timeout = timeout

    def call(
        self,
        method: str,
        state: str = "Alabama",
        *,
        customer_id: str = "",
        entitlement_key: str = "",
    ) -> TransportResponse:
        if method in (
            "GetConfig",
            "EvaluateEntitlement",
            "ResolveCustomer",
        ):
            raise ValueError(f"{method} is available only over gRPC")
        request_data = {"method": method, "state": state}
        payload = JsonCodec.encode(request_data)
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = response.read()
        return JsonCodec.decode(data), len(payload), len(data)


class GrpcTransport:
    def __init__(self, endpoint: str, timeout: float = 10):
        self.endpoint = endpoint
        self.timeout = timeout

    def call(
        self,
        method: str,
        state: str = "Alabama",
        *,
        customer_id: str = "",
        entitlement_key: str = "",
    ) -> TransportResponse:
        with grpc.insecure_channel(self.endpoint) as channel:
            if method == "GetConfig":
                request = Empty()
                response = session3_pb2_grpc.ConfigServiceStub(channel).GetConfig(
                    request, timeout=self.timeout
                )
                return (
                    {
                        "service_name": response.service_name,
                        "contract_package": response.contract_package,
                        "canonical_region_key": response.canonical_region_key,
                        "region_count": response.region_count,
                        "grpc_max_workers": response.grpc_max_workers,
                    },
                    ProtobufCodec.size(request),
                    ProtobufCodec.size(response),
                )
            if method == "EvaluateEntitlement":
                request = session3_pb2.EntitlementRequest(
                    customer_id=customer_id,
                    entitlement_key=entitlement_key,
                )
                response = session3_pb2_grpc.EntitlementServiceStub(
                    channel
                ).EvaluateEntitlement(request, timeout=self.timeout)
                return (
                    {
                        "status": session3_pb2.EntitlementStatus.Name(
                            response.status
                        ),
                        "message": response.message,
                    },
                    ProtobufCodec.size(request),
                    ProtobufCodec.size(response),
                )
            if method == "ResolveCustomer":
                request = session3_pb2.CustomerRequest(customer_id=customer_id)
                response = session3_pb2_grpc.CustomerServiceStub(
                    channel
                ).ResolveCustomer(request, timeout=self.timeout)
                return (
                    {
                        "status": session3_pb2.CustomerResolutionStatus.Name(
                            response.status
                        ),
                        "archive_backed": response.archive_backed,
                        "source_file": response.source_file,
                        "customer_id": response.customer_id,
                        "match_count": response.match_count,
                        "first_name": response.first_name,
                        "last_name": response.last_name,
                        "city": response.city,
                        "state": response.state,
                        "country": response.country,
                    },
                    ProtobufCodec.size(request),
                    ProtobufCodec.size(response),
                )

            stub = session3_pb2_grpc.RegionalRevenueStub(channel)
            if method == "GetRegion":
                request = session3_pb2.RegionRequest(region=state)
                response = stub.GetRegion(request, timeout=self.timeout)
                return (
                    {
                        "region": response.region,
                        "transaction_count": response.transaction_count,
                        "revenue_total": response.revenue_total,
                    },
                    ProtobufCodec.size(request),
                    ProtobufCodec.size(response),
                )
            if method == "GetSummary":
                request = Empty()
                response = stub.GetSummary(request, timeout=self.timeout)
                return (
                    {
                        "regions": response.region_count,
                        "transactions": response.transaction_count,
                        "revenue_total": response.revenue_total,
                    },
                    ProtobufCodec.size(request),
                    ProtobufCodec.size(response),
                )
            if method == "ListRegions":
                request = Empty()
                regions = []
                response_bytes = 0
                for response in stub.ListRegions(request, timeout=self.timeout):
                    regions.append(
                        {
                            "region": response.region,
                            "transaction_count": response.transaction_count,
                            "revenue_total": response.revenue_total,
                        }
                    )
                    response_bytes += ProtobufCodec.size(response)
                return (
                    {"regions": regions},
                    ProtobufCodec.size(request),
                    response_bytes,
                )
            raise ValueError(f"Unsupported gRPC method: {method}")


def create_transport(
    kind: TransportKind, endpoint: str, timeout: float = 10
) -> Transport:
    if kind == "json":
        return HttpJsonTransport(endpoint, timeout)
    if kind == "grpc":
        return GrpcTransport(endpoint, timeout)
    raise ValueError(f"Unsupported transport: {kind}")
