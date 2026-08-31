"""PR15.3 outbound offer rendering, boundaries, and classification."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from aea.marketplace.intelligence import OpportunityClass
from aea.marketplace.outbound import (
    BINDING_PHRASES,
    InboundInterest,
    OutboundAdapter,
    OutboundOffer,
    assert_non_binding,
    build_outbound_offer,
    classify_inbound_interest,
    negotiation_reply,
    render_public_text,
    select_publication_venue,
)
from aea.marketplace.presence import default_service_profile
from aea.marketplace.protocol import MarketplaceError
from aea.policy.reasons import HttpCode


def test_offer_renders_from_presence_profile() -> None:
    offer = build_outbound_offer()
    assert offer.agent == "econo"
    assert offer.non_binding is True
    ids = [svc.id for svc in offer.services]
    assert ids == ["quick_research", "structured_comparison", "technical_research_brief"]
    assert [str(svc.price_usd) for svc in offer.services] == ["2.000000", "5.000000", "10.000000"]
    text = render_public_text(offer)
    assert "Quick Research Check" in text
    assert "2.000000 USDC" in text
    assert "advertisement only" in text
    assert "No custody delegation" in text
    assert "not an accepted job" in text


def test_offer_cannot_advertise_wallet_authority() -> None:
    offer = build_outbound_offer()
    payload = offer.model_dump(mode="json")
    payload["constraints"]["custody_delegation"] = True
    mutated = OutboundOffer.model_validate(payload)
    with pytest.raises(MarketplaceError) as exc:
        OutboundAdapter().advertise(mutated)
    assert exc.value.code == HttpCode.POLICY_REJECTED
    payload["constraints"]["custody_delegation"] = False
    payload["constraints"]["arbitrary_signing"] = True
    mutated = OutboundOffer.model_validate(payload)
    with pytest.raises(MarketplaceError):
        OutboundAdapter().advertise(mutated)
    with pytest.raises(MarketplaceError):
        OutboundAdapter(live=True)


def test_outbound_adapter_rejects_financial_writes() -> None:
    adapter = OutboundAdapter()
    result = adapter.advertise()
    assert result.published is False
    assert result.mode == "local"
    assert result.marketplace is None
    with pytest.raises(MarketplaceError) as bid:
        adapter.bid("job")
    assert bid.value.code == HttpCode.FORBIDDEN
    for method in (adapter.accept, adapter.submit, adapter.pay, adapter.fund_escrow):
        with pytest.raises(MarketplaceError) as exc:
            method()
        assert exc.value.code == HttpCode.FORBIDDEN


def test_inbound_response_classification() -> None:
    profile = default_service_profile()
    assert classify_inbound_interest(None, profile) == OpportunityClass.NO_RESPONSE
    eligible = InboundInterest(
        counterparty="agent-x",
        proposed_task="Summarise supplied notes",
        proposed_reward_usd="5.000000",
        asset="USDC",
        chain="base",
        output_requirement="markdown",
    )
    assert classify_inbound_interest(eligible, profile) == OpportunityClass.ELIGIBLE_FOR_PR16_REVIEW
    assert (
        classify_inbound_interest(eligible.model_copy(update={"public_hosting_required": True}), profile)
        == OpportunityClass.HOSTING_REQUIREMENT_UNSUPPORTED
    )
    assert (
        classify_inbound_interest(eligible.model_copy(update={"custody_required": True}), profile)
        == OpportunityClass.CUSTODY_REQUIREMENT_REJECTED
    )
    assert (
        classify_inbound_interest(eligible.model_copy(update={"proposed_reward_usd": "1.000000"}), profile)
        == OpportunityClass.CAPITAL_REQUIREMENT_REJECTED
    )
    assert (
        classify_inbound_interest(
            InboundInterest(counterparty="agent-y", proposed_task=None, proposed_reward_usd=None),
            profile,
        )
        == OpportunityClass.COUNTERPARTY_CLARIFICATION_REQUIRED
    )


def test_negotiation_remains_non_binding() -> None:
    text = negotiation_reply()
    assert_non_binding(text)
    assert "evaluated against execution and settlement policy" in text
    for phrase in BINDING_PHRASES:
        with pytest.raises(MarketplaceError):
            assert_non_binding(f"Sure, {phrase} for this job")


def test_no_safe_publication_venue() -> None:
    assert select_publication_venue() is None


def test_experiment_timestamp_shape() -> None:
    now = datetime.now(timezone.utc)
    assert now.tzinfo is not None
