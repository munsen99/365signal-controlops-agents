"""Inbound /v1/tools/* DTOs. extra='forbid'. Documented properties only."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, field_serializer, field_validator

from aea.types import AeaBaseModel, Money, TreasuryAsset, format_amount, parse_unsigned_amount

from decimal import Decimal

AdapterName = Literal["mock"]


class FindJobsRequest(AeaBaseModel):
    adapter: AdapterName = "mock"
    limit: int = Field(default=10, ge=1, le=20)
    cursor: str | None = None


class EvaluateJobRequest(AeaBaseModel):
    opportunity_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)


class AcceptJobRequest(AeaBaseModel):
    opportunity_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)


class PerformJobRequest(AeaBaseModel):
    job_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)


class SubmitWorkRequest(AeaBaseModel):
    job_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)
    note: str | None = Field(default=None, max_length=500)


class CheckPaymentRequest(AeaBaseModel):
    job_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)


class RequestPaymentRequest(AeaBaseModel):
    amount: Decimal
    asset: TreasuryAsset
    destination: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=3, max_length=200)
    job_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)
    expected_return: Money | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_serializer("amount")
    def _dump(self, value: Decimal) -> str:
        return format_amount(value)


class GetFinancialStateRequest(AeaBaseModel):
    """Empty body. Extra keys including force=true are VALIDATION_ERROR."""


class RecordDecisionRequest(AeaBaseModel):
    decision_type: Literal[
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
    decision: Literal["accept", "decline", "proceed", "abort", "record", "recommend"]
    reasoning_summary: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    opportunity_id: UUID | None = None
    job_id: UUID | None = None
    expected_value: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    input_summary: str | None = Field(default=None, max_length=2000)


TOOL_MODELS = {
    "find_jobs": FindJobsRequest,
    "evaluate_job": EvaluateJobRequest,
    "accept_job": AcceptJobRequest,
    "perform_job": PerformJobRequest,
    "submit_work": SubmitWorkRequest,
    "check_payment": CheckPaymentRequest,
    "request_payment": RequestPaymentRequest,
    "get_financial_state": GetFinancialStateRequest,
    "record_decision": RecordDecisionRequest,
}
