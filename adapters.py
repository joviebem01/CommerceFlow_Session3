"""Provider-neutral payment adapter contract for future gateway integrations."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Protocol


class PaymentStatus(str, Enum):
    APPROVED = "approved"
    DECLINED = "declined"
    PENDING = "pending"
    REQUIRES_ACTION = "requires_action"


@dataclass(frozen=True)
class PaymentRequest:
    amount: Decimal
    currency: str
    payment_method: str
    idempotency_key: str


@dataclass(frozen=True)
class PaymentResult:
    status: PaymentStatus
    transaction_id: str | None = None
    message: str | None = None


class PaymentAdapter(Protocol):
    """Interface implemented by a concrete payment provider adapter."""

    def charge(self, request: PaymentRequest) -> PaymentResult:
        """Submit one payment request and normalize its result."""
