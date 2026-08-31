"""PR15.3 outbound service offer. Local by default. No bids, spends, or signing."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, field_serializer, field_validator

from aea.marketplace.intelligence import OpportunityClass
from aea.marketplace.presence import ServiceProfile, default_service_profile
from aea.marketplace.protocol import MarketplaceError
from aea.policy.reasons import HttpCode
from aea.types import AeaBaseModel, format_amount, parse_unsigned_amount

BINDING_PHRASES = (
    "accepted",
    "deal",
    "i will deliver",
    "job confirmed",
    "payment terms agreed",
    "we have a contract",
    "i commit",
)

NON_BINDING_STATUS = "This opportunity is being evaluated against execution and settlement policy."

MENU: tuple[dict[str, Any], ...] = (
    {
        "id": "quick_research",
        "name": "Quick Research Check",
        "capabilities": ("supplied_material_research", "text_summarization"),
        "output": ("markdown", "json"),
        "price_usd": "2.000000",
        "summary": "Concise research result with source links where the material is supplied or public.",
    },
    {
        "id": "structured_comparison",
        "name": "Structured Comparison",
        "capabilities": ("public_data_transformation", "classification"),
        "output": ("markdown", "json"),
        "price_usd": "5.000000",
        "summary": "Compare up to three options in a structured table with a short conclusion.",
    },
    {
        "id": "technical_research_brief",
        "name": "Technical Research Brief",
        "capabilities": ("supplied_material_research", "text_code_review"),
        "output": ("markdown",),
        "price_usd": "10.000000",
        "summary": "Structured Markdown brief with findings, conclusion, and cited sources.",
    },
)


class OfferService(AeaBaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    capabilities: list[str] = Field(min_length=1, max_length=8)
    output: list[str] = Field(min_length=1, max_length=8)
    price_usd: Decimal
    summary: str = Field(min_length=1, max_length=400)

    @field_validator("price_usd", mode="before")
    @classmethod
    def _price(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_serializer("price_usd")
    def _dump(self, value: Decimal) -> str:
        return format_amount(value)


class OutboundOffer(AeaBaseModel):
    agent: Literal["econo"] = "econo"
    services: list[OfferService] = Field(min_length=1, max_length=8)
    settlement: dict[str, str]
    constraints: dict[str, bool]
    restrictions: list[str]
    non_binding: Literal[True] = True
    requires_policy_approval: Literal[True] = True


class VenueAssessment(AeaBaseModel):
    marketplace: str
    compatible: bool
    reason: str
    required_blocked_action: str | None = None


class AdvertiseResult(AeaBaseModel):
    published: bool
    marketplace: str | None = None
    advertisement_id: str | None = None
    mode: Literal["local", "live"] = "local"
    reason: str
    payload: dict[str, Any]


class InboundInterest(AeaBaseModel):
    counterparty: str | None = None
    proposed_task: str | None = None
    proposed_reward_usd: Decimal | None = None
    asset: str | None = None
    chain: str | None = None
    output_requirement: str | None = None
    public_hosting_required: bool = False
    credentials_required: bool = False
    wallet_interaction_required: bool = False
    custody_required: bool = False

    @field_validator("proposed_reward_usd", mode="before")
    @classmethod
    def _reward(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return parse_unsigned_amount(value)


class ExperimentObservation(AeaBaseModel):
    marketplace: str
    advertisement_id: str | None = None
    published_at: datetime | None = None
    service_categories: list[str]
    advertised_prices_usd: list[str]
    view_or_response_count: int = 0
    unique_counterparties: int = 0
    experiment_status: str
    compatibility_outcome: str


def build_outbound_offer(profile: ServiceProfile | None = None) -> OutboundOffer:
    profile = profile or default_service_profile()
    allowed_caps = set(profile.capabilities)
    allowed_out = set(profile.outputs)
    services: list[OfferService] = []
    for item in MENU:
        if not set(item["capabilities"]).issubset(allowed_caps):
            continue
        outputs = [out for out in item["output"] if out in allowed_out]
        if not outputs:
            continue
        price = parse_unsigned_amount(item["price_usd"])
        if price < profile.minimum_net_reward_usd:
            continue
        services.append(
            OfferService(
                id=str(item["id"]),
                name=str(item["name"]),
                capabilities=list(item["capabilities"]),
                output=outputs,
                price_usd=format_amount(price),
                summary=str(item["summary"]),
            )
        )
    if not services:
        raise MarketplaceError(HttpCode.POLICY_REJECTED, "no menu item fits the service profile")
    preferred = profile.settlement[0]
    return OutboundOffer(
        services=services,
        settlement={"preferred_asset": preferred.asset, "preferred_chain": preferred.chain},
        constraints={
            "policy_evaluation_required": True,
            "custody_delegation": False,
            "arbitrary_signing": False,
            "public_hosting_supported": False,
            "escrow_funding_by_econo": False,
            "external_wallet_debit": False,
        },
        restrictions=list(profile.restrictions),
    )


def render_public_text(offer: OutboundOffer) -> str:
    lines = [
        "Econo — bounded research and analysis agent.",
        "Outputs: " + ", ".join(sorted({out for svc in offer.services for out in svc.output})) + ".",
        f"Preferred settlement: {offer.settlement.get('preferred_asset', 'USDC')}"
        + (f" on {offer.settlement['preferred_chain']}" if offer.settlement.get("preferred_chain") else "")
        + ".",
        "Paid work is evaluated against execution and settlement policy before any commitment.",
        "No custody delegation. No private-key sharing. No arbitrary signing. No escrow funding by Econo.",
        "",
        "Menu:",
    ]
    for svc in offer.services:
        lines.append(
            f"- {svc.name} ({format_amount(svc.price_usd)} USDC): {svc.summary} Outputs: {', '.join(svc.output)}."
        )
    lines.append("")
    lines.append("This listing is an advertisement only. It is not an accepted job, contract, or SLA.")
    text = "\n".join(lines)
    lowered = text.lower()
    if any(phrase in lowered for phrase in ("i will deliver", "job confirmed", "deal agreed")):
        raise MarketplaceError(HttpCode.POLICY_REJECTED, "offer text became binding")
    return text


def assess_publication_venues() -> list[VenueAssessment]:
    return [
        VenueAssessment(
            marketplace="workpnp",
            compatible=False,
            reason=(
                "Worker advertising requires POST /agents/register (API key issued once) "
                "and a human email+X claim; unclaimed agents cannot post. POST /jobs is "
                "buyer hiring and later x402 funding, not a service catalog."
            ),
            required_blocked_action="account_creation_secret_and_identity_claim",
        ),
        VenueAssessment(
            marketplace="the402",
            compatible=False,
            reason="Provider listing requires operator API credentials; marketplace is paused with zero postings.",
            required_blocked_action="operator_credentials",
        ),
        VenueAssessment(
            marketplace="moltjobs",
            compatible=False,
            reason="Turnkey wallet/withdraw authority and Base vs Polygon docs remain unresolved.",
            required_blocked_action="vendor_custody",
        ),
        VenueAssessment(
            marketplace="hober",
            compatible=False,
            reason="SIWX/session keys and gateway signing; not used merely to create activity.",
            required_blocked_action="wallet_signing",
        ),
        VenueAssessment(
            marketplace="bothire",
            compatible=False,
            reason="Official generate-wallet returns a private key; no usable open-task board.",
            required_blocked_action="private_key_generation",
        ),
    ]


def select_publication_venue() -> VenueAssessment | None:
    for item in assess_publication_venues():
        if item.compatible:
            return item
    return None


def classify_inbound_interest(interest: InboundInterest | None, profile: ServiceProfile | None = None) -> OpportunityClass:
    if interest is None:
        return OpportunityClass.NO_RESPONSE
    profile = profile or default_service_profile()
    if interest.custody_required or interest.wallet_interaction_required:
        return OpportunityClass.CUSTODY_REQUIREMENT_REJECTED
    if interest.credentials_required:
        return OpportunityClass.INELIGIBLE
    if interest.public_hosting_required:
        return OpportunityClass.HOSTING_REQUIREMENT_UNSUPPORTED
    if interest.proposed_reward_usd is None or not interest.proposed_task:
        return OpportunityClass.COUNTERPARTY_CLARIFICATION_REQUIRED
    reward = parse_unsigned_amount(interest.proposed_reward_usd)
    if reward < profile.minimum_net_reward_usd:
        return OpportunityClass.CAPITAL_REQUIREMENT_REJECTED
    if interest.asset and interest.asset != "USDC":
        return OpportunityClass.INELIGIBLE
    if interest.chain and interest.chain not in {rail.chain for rail in profile.settlement}:
        return OpportunityClass.INELIGIBLE
    return OpportunityClass.ELIGIBLE_FOR_PR16_REVIEW


def negotiation_reply() -> str:
    return NON_BINDING_STATUS


def assert_non_binding(text: str) -> None:
    lowered = text.lower()
    for phrase in BINDING_PHRASES:
        if phrase in lowered:
            raise MarketplaceError(HttpCode.POLICY_REJECTED, "binding negotiation language")


class OutboundAdapter:
    """Permits local advertisement rendering only. Rejects financial marketplace writes."""

    name = "outbound"

    def __init__(self, *, live: bool = False) -> None:
        if live:
            raise MarketplaceError(HttpCode.FORBIDDEN, "live outbound publication is disabled")
        self._live = False

    def advertise(self, offer: OutboundOffer | None = None) -> AdvertiseResult:
        offer = offer or build_outbound_offer()
        if offer.constraints.get("custody_delegation") or offer.constraints.get("arbitrary_signing"):
            raise MarketplaceError(HttpCode.POLICY_REJECTED, "offer constraints opened wallet authority")
        payload = {
            "canonical": offer.model_dump(mode="json"),
            "public_text": render_public_text(offer),
        }
        venue = select_publication_venue()
        if venue is None:
            return AdvertiseResult(
                published=False,
                marketplace=None,
                advertisement_id=None,
                mode="local",
                reason="no_safe_public_publication_venue",
                payload=payload,
            )
        raise MarketplaceError(HttpCode.FORBIDDEN, "live advertise path is not implemented")

    def bid(self, *_args: object, **_kwargs: object) -> None:
        raise MarketplaceError(HttpCode.FORBIDDEN, "outbound adapter cannot bid")

    def accept(self, *_args: object, **_kwargs: object) -> None:
        raise MarketplaceError(HttpCode.FORBIDDEN, "outbound adapter cannot accept")

    def submit(self, *_args: object, **_kwargs: object) -> None:
        raise MarketplaceError(HttpCode.FORBIDDEN, "outbound adapter cannot submit")

    def pay(self, *_args: object, **_kwargs: object) -> None:
        raise MarketplaceError(HttpCode.FORBIDDEN, "outbound adapter cannot pay")

    def fund_escrow(self, *_args: object, **_kwargs: object) -> None:
        raise MarketplaceError(HttpCode.FORBIDDEN, "outbound adapter cannot fund escrow")
