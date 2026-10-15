"""Read-only customer resolution from the supplied archived customer CSV."""
from __future__ import annotations

import csv
from pathlib import Path


CUSTOMER_FIELDS = (
    "customer_id",
    "first_name",
    "last_name",
    "city",
    "state",
    "country",
)
DEFAULT_CUSTOMERS_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "Datasets"
    / "crm_50000_customers_dirty_v3.csv"
)


def load_customer_archive(
    path: Path = DEFAULT_CUSTOMERS_PATH,
) -> dict[str, list[dict[str, str]]]:
    """Load customers by ID while preserving duplicate IDs for explicit resolution."""
    customers: dict[str, list[dict[str, str]]] = {}
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        headers = reader.fieldnames or []
        missing = sorted(set(CUSTOMER_FIELDS) - set(headers))
        if missing:
            raise ValueError(
                f"Customer archive is missing required columns: {', '.join(missing)}"
            )
        for row_number, row in enumerate(reader, start=2):
            customer_id = (row.get("customer_id") or "").strip()
            if not customer_id:
                raise ValueError(
                    f"Customer archive has a blank customer_id on row {row_number}"
                )
            customer = {field: row.get(field) or "" for field in CUSTOMER_FIELDS}
            customer["customer_id"] = customer_id
            customers.setdefault(customer_id, []).append(customer)
    return customers
