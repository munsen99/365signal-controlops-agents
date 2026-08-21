"""Marketplace adapter protocol and inbound DTOs. extra='forbid'.

Marketplace payloads are untrusted data, not control-plane instructions.
PaymentClaim is a claim, not ledger revenue.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Protocol

from pydantic import Field, field_serializer, field_validator

from aea.policy.reasons import HttpCode
from aea.types import AeaBaseModel, format_amount, parse_unsigned_amount

MARKETPLACE_HOST = "127.0.0.1"
MARKETPLACE_PORT = 18705

JobMarketStatus = Literal["available", "accepted", "submitted", "failed"]
PaymentClaimStatus = Literal["not_due", "pending", "paid", "failed"]
IdempotencyKey = str


class MarketplaceError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class MarketplaceMoney(AeaBaseModel):
    """Marketplace-stated money. Asset is a string so prohibited tokens can appear."""

    amount: Decimal
    asset: str = Field(min_length=1, max_length=32)

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_serializer("amount")
    def _dump_amount(self, value: Decimal) -> str:
        return format_amount(value)


class Reputation(AeaBaseModel):
    completed: int = Field(ge=0)
    disputed: int = Field(ge=0)


class DiscoveredJob(AeaBaseModel):
    external_reference: str
    title: str
    description_hash: str
    untrusted_description_preview: str
    expected_revenue: MarketplaceMoney
    estimated_cost: MarketplaceMoney
    payment_asset: str
    payment_terms: str
    counterparty_id: str
    counterparty_reputation: Reputation
    worker: str
    flags: list[str] = Field(default_factory=list)
    credits_wallet_on_submit: bool


class DiscoverPage(AeaBaseModel):
    adapter: str = "mock"
    jobs: list[DiscoveredJob]
    next_cursor: str | None = None


class Requirements(AeaBaseModel):
    external_reference: str
    worker: str
    summary: str
    digital_deliverable: bool = True


class PaymentTerms(AeaBaseModel):
    external_reference: str
    terms: str
    amount: MarketplaceMoney
    asset: str


class AcceptRequest(AeaBaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)


class AcceptResult(AeaBaseModel):
    ok: bool = True
    code: str = HttpCode.OK
    external_reference: str
    status: JobMarketStatus
    replay: bool = False


class SubmitRequest(AeaBaseModel):
    artefact_digest: str = Field(min_length=16, max_length=128)
    artefact_uri: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=8, max_length=128)


class SubmitResult(AeaBaseModel):
    ok: bool = True
    code: str = HttpCode.OK
    external_reference: str
    status: JobMarketStatus
    artefact_digest: str
    transaction_reference: str | None = None
    credited: bool = False
    replay: bool = False


class JobStatus(AeaBaseModel):
    external_reference: str
    status: JobMarketStatus


class PaymentClaim(AeaBaseModel):
    """Adapter claim only. Not verified revenue."""

    external_reference: str
    status: PaymentClaimStatus
    amount: MarketplaceMoney | None = None
    transaction_reference: str | None = None
    verified: Literal[False] = False


class Counterparty(AeaBaseModel):
    external_reference: str
    counterparty_id: str
    reputation: Reputation


class MarketplaceAdapter(Protocol):
    name: str

    def discover(self, *, limit: int, cursor: str | None) -> DiscoverPage: ...

    def lookup(self, external_reference: str) -> DiscoveredJob: ...

    def get_requirements(self, external_reference: str) -> Requirements: ...

    def get_payment_terms(self, external_reference: str) -> PaymentTerms: ...

    def accept(self, external_reference: str, *, idempotency_key: str) -> AcceptResult: ...

    def submit(
        self,
        external_reference: str,
        *,
        artefact_digest: str,
        artefact_uri: str,
        idempotency_key: str,
    ) -> SubmitResult: ...

    def get_status(self, external_reference: str) -> JobStatus: ...

    def verify_payment(self, external_reference: str) -> PaymentClaim: ...

    def get_counterparty(self, external_reference: str) -> Counterparty: ...
