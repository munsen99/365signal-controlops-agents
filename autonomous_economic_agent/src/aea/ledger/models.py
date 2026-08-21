"""Inbound ledger DTOs. extra='forbid'. Money is Decimal, never float."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_serializer, field_validator

from aea.types import AeaBaseModel, TreasuryAsset, format_amount, parse_unsigned_amount

IdempotencyKey = str
JobStatus = Literal[
    "accepted", "performing", "performed", "submitted", "completed", "failed", "cancelled"
]
OpportunityDecision = Literal["discovered", "evaluated", "accepted", "declined", "expired"]
PaymentDecision = Literal["pending", "approved", "rejected"]
CostCategory = Literal[
    "compute", "api", "data", "network_fee", "purchased_service", "other_approved"
]
TransferClass = Literal[
    "operator_top_up", "operator_withdrawal", "refund", "not_revenue"
]
TransferDirection = Literal["in", "out"]
DecisionType = Literal[
    "discover",
    "evaluate",
    "accept",
    "decline",
    "perform",
    "submit",
    "request_payment",
    "check_payment",
    "abort",
    "recommend_control_change",
]
DecisionValue = Literal["accept", "decline", "proceed", "abort", "record", "recommend"]


def _idempotency(value: str) -> str:
    text = value.strip()
    if not (8 <= len(text) <= 128):
        raise ValueError("idempotency_key must be 8-128 characters")
    return text


class OpportunityCreate(AeaBaseModel):
    source: str = Field(min_length=1, max_length=128)
    external_reference: str = Field(min_length=1, max_length=256)
    description_hash: str = Field(min_length=16, max_length=128)
    expected_revenue: Decimal
    expected_cost: Decimal
    expected_revenue_asset: Literal["USDC"] = "USDC"
    artefact_uri: str | None = None
    policy_version: str = "policy/v0.1.0"
    idempotency_key: str

    @field_validator("expected_revenue", "expected_cost", mode="before")
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("idempotency_key")
    @classmethod
    def _idem(cls, value: str) -> str:
        return _idempotency(value)

    @field_serializer("expected_revenue", "expected_cost")
    def _dump_money(self, value: Decimal) -> str:
        return format_amount(value)


class JobAccept(AeaBaseModel):
    opportunity_id: UUID
    expected_revenue: Decimal
    policy_version: str = "policy/v0.1.0"
    idempotency_key: str

    @field_validator("expected_revenue", mode="before")
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("idempotency_key")
    @classmethod
    def _idem(cls, value: str) -> str:
        return _idempotency(value)

    @field_serializer("expected_revenue")
    def _dump_money(self, value: Decimal) -> str:
        return format_amount(value)


class JobTransition(AeaBaseModel):
    job_id: UUID
    status: JobStatus
    deliverable_hash: str | None = None
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def _idem(cls, value: str) -> str:
        return _idempotency(value)


class CostCreate(AeaBaseModel):
    job_id: UUID | None = None
    category: CostCategory
    amount: Decimal
    asset: TreasuryAsset
    payment_request_id: UUID | None = None
    evidence_reference: str | None = None
    correlation_id: UUID | None = None
    idempotency_key: str

    @field_validator("amount", mode="before")
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("idempotency_key")
    @classmethod
    def _idem(cls, value: str) -> str:
        return _idempotency(value)

    @field_serializer("amount")
    def _dump_money(self, value: Decimal) -> str:
        return format_amount(value)


class RevenueCreate(AeaBaseModel):
    job_id: UUID
    amount: Decimal
    asset: Literal["USDC"] = "USDC"
    transaction_reference: str = Field(min_length=8, max_length=128)
    payer_reference: str | None = None
    verified: bool = True
    idempotency_key: str

    @field_validator("amount", mode="before")
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("idempotency_key")
    @classmethod
    def _idem(cls, value: str) -> str:
        return _idempotency(value)

    @field_serializer("amount")
    def _dump_money(self, value: Decimal) -> str:
        return format_amount(value)


class TransferCreate(AeaBaseModel):
    asset: TreasuryAsset
    amount: Decimal
    direction: TransferDirection
    classification: TransferClass
    transaction_reference: str | None = None
    idempotency_key: str

    @field_validator("amount", mode="before")
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("idempotency_key")
    @classmethod
    def _idem(cls, value: str) -> str:
        return _idempotency(value)

    @field_serializer("amount")
    def _dump_money(self, value: Decimal) -> str:
        return format_amount(value)


class PaymentCreate(AeaBaseModel):
    job_id: UUID
    amount: Decimal
    asset: TreasuryAsset
    destination: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=3, max_length=200)
    policy_version: str = "policy/v0.1.0"
    correlation_id: UUID
    idempotency_key: str
    idempotency_ttl_seconds: int = Field(default=86400, ge=1)

    @field_validator("amount", mode="before")
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("idempotency_key")
    @classmethod
    def _idem(cls, value: str) -> str:
        return _idempotency(value)

    @field_serializer("amount")
    def _dump_money(self, value: Decimal) -> str:
        return format_amount(value)


class PaymentDecisionWrite(AeaBaseModel):
    request_id: UUID
    decision: Literal["approved", "rejected"]
    reason_code: str | None = None
    rejection_reason: str | None = None
    approved_amount: Decimal | None = None
    canonical_hash: str | None = None
    idempotency_key: str

    @field_validator("approved_amount", mode="before")
    @classmethod
    def _opt_money(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_unsigned_amount(value)

    @field_validator("idempotency_key")
    @classmethod
    def _idem(cls, value: str) -> str:
        return _idempotency(value)


class PaymentSettle(AeaBaseModel):
    request_id: UUID
    transaction_reference: str = Field(min_length=8, max_length=128)
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def _idem(cls, value: str) -> str:
        return _idempotency(value)


class DecisionCreate(AeaBaseModel):
    decision_type: DecisionType
    decision: DecisionValue
    reasoning_summary: str = Field(min_length=1, max_length=2000)
    idempotency_key: str
    opportunity_id: UUID | None = None
    job_id: UUID | None = None
    expected_value: Decimal | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    input_summary: str | None = Field(default=None, max_length=2000)
    input_hash: str | None = None
    policy_version: str | None = None
    constitution_version: str | None = None

    @field_validator("expected_value", mode="before")
    @classmethod
    def _opt_money(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_unsigned_amount(value)

    @field_validator("idempotency_key")
    @classmethod
    def _idem(cls, value: str) -> str:
        return _idempotency(value)


class AuditWrite(AeaBaseModel):
    event_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID | None = None
