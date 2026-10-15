# Service boundaries

This is a proposed domain decomposition based on the five supplied ECom360
datasets. It documents ownership seams; it does not claim that the proposed
services are deployed or that the source CSVs are already partitioned into
independently owned databases.

## Implemented boundary

| Service | Responsibility and data | Contract | Status |
|---|---|---|---|
| `RegionalRevenue` | Read-only regional transaction counts and revenue totals, served from archived regional aggregates. | `session3.proto`: `GetRegion`, `GetSummary`, and server-streaming `ListRegions`. The local gRPC backend is in `grpc_backend.py`; the HTTP/JSON comparison is in `services.py`. | **Implemented** |
| `ConfigService` | Read-only snapshot of active Session 3 runtime settings: contract package, canonical region key, loaded region count, and gRPC worker limit. | `session3.proto`: `GetConfig`; implemented in `grpc_backend.py`. | **Implemented** |
| `EntitlementService` | Accepts a customer ID and entitlement key; currently reports `ENTITLEMENT_STATUS_NOT_CONFIGURED`. No entitlement data or policy is supplied, so it makes no access decision. | `session3.proto`: `EvaluateEntitlement`; implemented in `grpc_backend.py` as an explicit unconfigured response. | **RPC implemented; policy not configured** |
| `CustomerService` | Read-only resolution by `customer_id` from `data/Datasets/crm_50000_customers_dirty_v3.csv`; returns limited identity/location fields, archive source, and duplicate-resolution status. It omits contact details, street address, date of birth, and device IDs. | `session3.proto`: `ResolveCustomer`; archive loading is in `customer_archive.py`, with the RPC in `grpc_backend.py`. Duplicate IDs are reported as ambiguous rather than arbitrarily selecting a row. | **Archive-backed RPC implemented; no live customer store** |

`RegionalRevenue` is an aggregate/read-model service. It does not own customer
profiles, catalog entries, individual orders, support tickets, clickstream
events, or payment processing. Its current results originate from the Session
1 baseline and Session 2 stream output, and the GUI checks them against those
archives. No transaction-level RPC is implemented: the Session 1/2 communication
archives expose aggregates, not transaction records. `CustomerService` is a
separate read-only lookup from the supplied customer-profile source CSV and is
not a live customer store or write API. `RegionalRevenue` contains aggregates
only and cannot resolve an individual customer.

### Regional domain key and partitioning evidence

The cross-session logical key is the canonical `region` identifier:

| Source | Physical key field |
|---|---|
| Session 1 `baseline_result.csv` | `state` |
| Session 2 `streamed_regional_revenue.csv` | `region` |
| Session 3 `RegionRequest` / `RegionResponse` | `region` |

The application trims surrounding whitespace when mapping archived keys and
checks that Session 1 and Session 2 have identical regional key sets. This
establishes domain-key alignment only; it does not establish a Kafka topic
partition key or partition count. The supplied Session 2 RAR contains no Kafka
partition configuration, so Kafka partitioning is **not verified/configured**
by this project. The Contract drift report carries this finding explicitly.

## Proposed boundaries not implemented

The five source files are analytical inputs to this project, not proof of
running microservices. The following boundaries are proposals; their services,
contracts, persistence, and independent deployment are **not implemented**.

| Proposed service | Data boundary / source evidence | Responsibility and boundary rule | Status |
|---|---|---|---|
| `Customer` | Customer profile lifecycle and canonical identity are not implemented. The archive-backed `CustomerService` is read-only and is not an independently owned customer domain. | A future service would own profile lifecycle; other services should retain the customer ID rather than treat this archive lookup as an authority. | **Domain service not implemented; archive lookup exists** |
| `Catalog` | Product entity; `product_catalog_dirty_30pct.csv`, keyed by `product_id`. | Own product descriptions and catalog attributes. Orders may retain product IDs and purchase-time snapshots without becoming catalog owners. | **Not implemented** |
| `Order` | The Session 1/2 aggregate communication archives contain no transaction-level records; no TransactionService RPC is exposed. | A future service would own order lifecycle and order status/amount facts. Coordinate with Customer and Catalog by identifiers/contracts, not cross-service table joins. | **Not implemented** |
| `Support` | Support-ticket event; `support_tickets_30000_dirty.csv`, keyed by `ticket_id`, with customer references. | Own ticket lifecycle and support interactions. Reference Customer by ID; do not own customer profile data. | **Not implemented** |
| `Clickstream` | Behavioral event stream; `clickstream_500k_events.csv`, keyed by `event_id`. | Ingest and expose customer activity events for analysis. Keep event capture separate from transactional order state. | **Not implemented** |
| `Payment` | No standalone payment dataset is supplied; orders include a `payment_method` field. `adapters.py` defines only a provider-neutral adapter interface. | Own authorization/capture/refund interactions and normalized payment outcomes if implemented. Keep provider credentials and provider-specific payloads behind the adapter; do not treat `payment_method` as proof that a payment was processed. | **Not implemented** |

## Interaction and ownership rules

- Services exchange stable identifiers and versioned contracts; they do not
  share writable database tables.
- `Order` may request payment through `Payment`, but payment authorization
  outcomes and order lifecycle state remain separate facts.
- Customer, Catalog, Order, Support, and Clickstream may provide source data
  for future analytics. `RegionalRevenue` remains a derived read model and
  should not become the owner of those domains.
- These boundaries are conceptual only. No APIs, event topics, storage systems,
  deployment topology, or service-level guarantees are defined for the six
  proposed services in this repository.
