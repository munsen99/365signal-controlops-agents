"""Payment DTOs. extra='forbid'. Control never includes HMAC or debit tokens."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from aea.control.schemas import RequestPaymentRequest
from aea.types import AeaBaseModel, PolicyInput


class ExecutePaymentRequest(PolicyInput):
    """Policy-side evaluate-and-sign body. Includes ledger request_id.

    ``approved_at`` is the durable timestamp bound into the signer artifact
    (the payment row's ``requested_at``). Retries must send the same value.
    """

    request_id: UUID
    approved_at: datetime


class PaymentHttpRequest(RequestPaymentRequest):
    """POST /v1/payment-requests body. Control-token only."""

    correlation_id: UUID | None = None


class PolicyExecuteResult(AeaBaseModel):
    ok: bool
    code: str
    decision: str
    reason_code: str | None = None
    request_id: UUID | None = None
    tx_id: str | None = None
    canonical_hash: str | None = None
    policy_version: str | None = None
    policy_hash: str | None = None
    approved_amount: str | None = None
    replay: bool = False
