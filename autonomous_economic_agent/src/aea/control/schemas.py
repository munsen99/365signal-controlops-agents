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


class ResearchOpportunitiesRequest(AeaBaseModel):
    query: str = Field(min_length=3, max_length=200)
    limit: int = Field(default=10, ge=1, le=10)


class DiscoverCounterpartiesRequest(AeaBaseModel):
    query: str = Field(default="legitimate bounded digital work", min_length=3, max_length=200)
    limit: int = Field(default=10, ge=1, le=10)


MessageIntent = Literal[
    "ask_work_available",
    "ask_task_details",
    "offer_bounded_capability",
    "propose_non_binding_collaboration",
    "ask_settlement_requirements",
    "negotiate_non_binding_terms",
    "respond_to_inbound",
    "request_clarification",
]
MessageChannel = Literal["marketplace_api", "agent_protocol"]


class SendMessageRequest(AeaBaseModel):
    counterparty_id: str = Field(min_length=3, max_length=200)
    channel: MessageChannel
    intent: MessageIntent
    message: str = Field(min_length=10, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128)


class GetCounterpartyProfileRequest(AeaBaseModel):
    counterparty_id: str = Field(min_length=3, max_length=200)


class PostServiceOfferRequest(AeaBaseModel):
    marketplace: str = Field(default="local", min_length=3, max_length=64)
    service_id: str | None = Field(default=None, min_length=3, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ReadMessagesRequest(AeaBaseModel):
    counterparty_id: str | None = Field(default=None, min_length=3, max_length=200)
    conversation_id: str | None = Field(default=None, min_length=36, max_length=36)
    limit: int = Field(default=10, ge=1, le=20)


class FollowUpMessageRequest(AeaBaseModel):
    conversation_id: str = Field(min_length=36, max_length=36)
    message: str = Field(min_length=10, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ProposeCollaborationRequest(AeaBaseModel):
    counterparty_id: str = Field(min_length=3, max_length=200)
    channel: MessageChannel = "marketplace_api"
    proposal: str = Field(min_length=10, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128)


class GetMarketStatusRequest(AeaBaseModel):
    marketplace: str | None = Field(default=None, min_length=3, max_length=64)


class ListActiveConversationsRequest(AeaBaseModel):
    limit: int = Field(default=10, ge=1, le=20)


class WebSearchRequest(AeaBaseModel):
    query: str = Field(min_length=3, max_length=200)
    limit: int = Field(default=5, ge=1, le=8)


class WebExtractRequest(AeaBaseModel):
    url: str = Field(min_length=8, max_length=2048)


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
    "research_opportunities": ResearchOpportunitiesRequest,
    "discover_counterparties": DiscoverCounterpartiesRequest,
    "send_message": SendMessageRequest,
    "get_counterparty_profile": GetCounterpartyProfileRequest,
    "post_service_offer": PostServiceOfferRequest,
    "read_messages": ReadMessagesRequest,
    "follow_up_message": FollowUpMessageRequest,
    "propose_collaboration": ProposeCollaborationRequest,
    "get_market_status": GetMarketStatusRequest,
    "list_active_conversations": ListActiveConversationsRequest,
    "web_search": WebSearchRequest,
    "web_extract": WebExtractRequest,
}
