"""Market observations, opportunity class, and poster concentration."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_serializer, field_validator

from aea.marketplace.presence import ServiceProfile
from aea.types import AeaBaseModel, format_amount, parse_unsigned_amount

STALE_AFTER_DAYS = 14
HIGH_CONCENTRATION_SHARE = Decimal("0.50")
HIGH_CONCENTRATION_MIN_JOBS = 3


class OpportunityClass(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    VENDOR_CLARIFICATION_REQUIRED = "VENDOR_CLARIFICATION_REQUIRED"
    NO_LIVE_DEMAND = "NO_LIVE_DEMAND"
    STALE = "STALE"
    UNFUNDED = "UNFUNDED"
    CAPITAL_REQUIREMENT_REJECTED = "CAPITAL_REQUIREMENT_REJECTED"
    CUSTODY_REQUIREMENT_REJECTED = "CUSTODY_REQUIREMENT_REJECTED"
    HOSTING_REQUIREMENT_UNSUPPORTED = "HOSTING_REQUIREMENT_UNSUPPORTED"
    OPERATOR_ACTION_REQUIRED = "OPERATOR_ACTION_REQUIRED"


class MarketObservation(AeaBaseModel):
    marketplace: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    source: str = Field(min_length=1, max_length=256)
    external_id: str | None = None
    poster_id: str | None = None
    category: str | None = None
    title: str | None = None
    reward_usd: Decimal | None = None
    asset: str | None = None
    chain: str | None = None
    funded: bool | None = None
    output_type: str | None = None
    public_hosting_required: bool = False
    authenticated_account_required: bool = False
    custody_or_vendor_wallet_required: bool = False
    vendor_clarification_required: bool = False
    operator_action_required: bool = False
    age_days: Decimal | None = None
    status: str | None = None
    ineligibility_reason: str | None = None

    @field_validator("reward_usd", "age_days", mode="before")
    @classmethod
    def _opt_money(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return parse_unsigned_amount(value)

    @field_serializer("reward_usd", "age_days")
    def _dump_opt(self, value: Decimal | None) -> str | None:
        return None if value is None else format_amount(value)

    @field_serializer("observed_at")
    def _dump_ts(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ClassifiedOpportunity(AeaBaseModel):
    observation: MarketObservation
    classification: OpportunityClass
    reason: str


class ConcentrationReport(AeaBaseModel):
    marketplace: str
    open_jobs: int = Field(ge=0)
    unique_posters: int = Field(ge=0)
    largest_poster_id: str | None = None
    largest_poster_share: Decimal
    market_concentration: Literal["NONE", "LOW", "HIGH"]

    @field_validator("largest_poster_share", mode="before")
    @classmethod
    def _share(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_serializer("largest_poster_share")
    def _dump_share(self, value: Decimal) -> str:
        return format_amount(value)


def classify_opportunity(observation: MarketObservation, profile: ServiceProfile) -> ClassifiedOpportunity:
    if observation.vendor_clarification_required:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.VENDOR_CLARIFICATION_REQUIRED,
            reason=observation.ineligibility_reason or "vendor_unresolved",
        )
    if observation.custody_or_vendor_wallet_required:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.CUSTODY_REQUIREMENT_REJECTED,
            reason="vendor_wallet_or_debit_authority",
        )
    if observation.authenticated_account_required:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.INELIGIBLE,
            reason="authenticated_third_party_account",
        )
    if observation.public_hosting_required and not profile.public_hosting_supported:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.HOSTING_REQUIREMENT_UNSUPPORTED,
            reason="public_hosting_required",
        )
    if observation.ineligibility_reason:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.INELIGIBLE,
            reason=observation.ineligibility_reason,
        )
    if observation.funded is False:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.UNFUNDED,
            reason="escrow_not_funded",
        )
    age = None if observation.age_days is None else parse_unsigned_amount(observation.age_days)
    if age is not None and age >= STALE_AFTER_DAYS:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.STALE,
            reason="open_listing_older_than_stale_window",
        )
    if observation.reward_usd is None:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.INELIGIBLE,
            reason="reward_unknown",
        )
    reward = parse_unsigned_amount(observation.reward_usd)
    minimum = parse_unsigned_amount(profile.minimum_net_reward_usd)
    if reward < minimum:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.CAPITAL_REQUIREMENT_REJECTED,
            reason="below_minimum_net_reward",
        )
    if observation.asset and observation.asset != "USDC":
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.INELIGIBLE,
            reason="unsupported_asset",
        )
    if observation.chain and observation.chain not in {rail.chain for rail in profile.settlement}:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.INELIGIBLE,
            reason="unsupported_chain",
        )
    if observation.operator_action_required:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.OPERATOR_ACTION_REQUIRED,
            reason="operator_onboarding_or_claim",
        )
    if observation.funded is True:
        return ClassifiedOpportunity(
            observation=observation,
            classification=OpportunityClass.ELIGIBLE,
            reason="funded_envelope_match",
        )
    return ClassifiedOpportunity(
        observation=observation,
        classification=OpportunityClass.UNFUNDED,
        reason="funding_unconfirmed",
    )


def classify_board(observations: list[MarketObservation], profile: ServiceProfile) -> list[ClassifiedOpportunity]:
    if not observations:
        empty = MarketObservation(
            marketplace="none",
            observed_at=datetime.now(timezone.utc),
            source="local",
        )
        return [
            ClassifiedOpportunity(
                observation=empty,
                classification=OpportunityClass.NO_LIVE_DEMAND,
                reason="no_observations",
            )
        ]
    return [classify_opportunity(item, profile) for item in observations]


def concentration(observations: list[MarketObservation], *, marketplace: str) -> ConcentrationReport:
    posters = [item.poster_id or "unknown" for item in observations if item.external_id]
    n = len(posters)
    if n == 0:
        return ConcentrationReport(
            marketplace=marketplace,
            open_jobs=0,
            unique_posters=0,
            largest_poster_id=None,
            largest_poster_share="0.000000",
            market_concentration="NONE",
        )
    counts = Counter(posters)
    largest_id, largest_n = counts.most_common(1)[0]
    share = (Decimal(largest_n) / Decimal(n)).quantize(Decimal("0.000001"))
    unique = len(counts)
    if n >= HIGH_CONCENTRATION_MIN_JOBS and share >= HIGH_CONCENTRATION_SHARE:
        level: Literal["NONE", "LOW", "HIGH"] = "HIGH"
    elif unique == 1 and n > 1:
        level = "HIGH"
    else:
        level = "LOW"
    return ConcentrationReport(
        marketplace=marketplace,
        open_jobs=n,
        unique_posters=unique,
        largest_poster_id=largest_id,
        largest_poster_share=format_amount(share),
        market_concentration=level,
    )
