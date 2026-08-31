"""PR15.2 market presence, discovery, intelligence. No live bids."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from aea.marketplace.discovery import (
    MUTATING_METHODS,
    ReadOnlyDiscoveryClient,
    observations_moltjobs,
    observations_workpnp,
    probe_public_board,
)
from aea.marketplace.intelligence import (
    MarketObservation,
    OpportunityClass,
    classify_opportunity,
    concentration,
)
from aea.marketplace.presence import default_service_profile
from aea.marketplace.protocol import MarketplaceError
from aea.marketplace.scan import scan_observations
from aea.policy.reasons import HttpCode

ROOT = Path(__file__).resolve().parents[2] / "src" / "aea" / "marketplace"
NOW = datetime(2026, 8, 31, 17, 30, tzinfo=timezone.utc)


def test_default_profile_is_bounded() -> None:
    profile = default_service_profile()
    dumped = profile.model_dump(mode="json")
    assert dumped["agent"] == "econo"
    assert dumped["requires_policy_approval"] is True
    assert dumped["custody_delegation"] is False
    assert dumped["arbitrary_signing"] is False
    assert dumped["public_hosting_supported"] is False
    assert dumped["minimum_net_reward_usd"] == "2.000000"
    assert "text_summarization" in dumped["capabilities"]
    assert {"base", "solana"} <= {rail["chain"] for rail in dumped["settlement"]}


def test_advertisement_cannot_claim_wallet_authority() -> None:
    profile = default_service_profile()
    payload = profile.model_dump(mode="json")
    with pytest.raises(ValidationError):
        profile.__class__.model_validate({**payload, "custody_delegation": True})
    with pytest.raises(ValidationError):
        profile.__class__.model_validate({**payload, "arbitrary_signing": True})
    with pytest.raises(ValidationError):
        profile.__class__.model_validate({**payload, "capabilities": ["arbitrary_code_execution"]})


def test_classify_representative_opportunities() -> None:
    profile = default_service_profile()
    eligible = MarketObservation(
        marketplace="fixture",
        observed_at=NOW,
        source="test",
        external_id="job-1",
        poster_id="buyer-a",
        reward_usd="5.000000",
        asset="USDC",
        chain="base",
        funded=True,
    )
    assert classify_opportunity(eligible, profile).classification == OpportunityClass.ELIGIBLE
    hosting = eligible.model_copy(update={"public_hosting_required": True})
    assert classify_opportunity(hosting, profile).classification == OpportunityClass.HOSTING_REQUIREMENT_UNSUPPORTED
    unfunded = eligible.model_copy(update={"funded": False})
    assert classify_opportunity(unfunded, profile).classification == OpportunityClass.UNFUNDED
    cheap = eligible.model_copy(update={"reward_usd": "1.000000"})
    assert classify_opportunity(cheap, profile).classification == OpportunityClass.CAPITAL_REQUIREMENT_REJECTED
    stale = eligible.model_copy(update={"age_days": "20.000000"})
    assert classify_opportunity(stale, profile).classification == OpportunityClass.STALE
    custody = eligible.model_copy(update={"custody_or_vendor_wallet_required": True})
    assert classify_opportunity(custody, profile).classification == OpportunityClass.CUSTODY_REQUIREMENT_REJECTED
    vendor = eligible.model_copy(update={"vendor_clarification_required": True})
    assert classify_opportunity(vendor, profile).classification == OpportunityClass.VENDOR_CLARIFICATION_REQUIRED


def test_concentration_single_poster_burst() -> None:
    rows = [
        MarketObservation(
            marketplace="moltjobs",
            observed_at=NOW,
            source="test",
            external_id=f"job-{i}",
            poster_id="poster-1",
            reward_usd="5.000000",
            funded=True,
        )
        for i in range(7)
    ]
    report = concentration(rows, marketplace="moltjobs")
    assert report.open_jobs == 7
    assert report.unique_posters == 1
    assert report.largest_poster_share == Decimal("1.000000")
    assert report.market_concentration == "HIGH"
    assert report.largest_poster_id == "poster-1"


def test_moltjobs_and_workpnp_parsers() -> None:
    molt = observations_moltjobs(
        {
            "data": [
                {
                    "id": "abc",
                    "title": "Research note",
                    "posterId": "p1",
                    "budgetUsdc": "5",
                    "status": "OPEN",
                    "chainId": 8453,
                    "tokenSymbol": "USDC",
                    "paymentProvider": "ON_CHAIN_USDC",
                    "escrowTxHash": "0x" + "ab" * 32,
                    "createdAt": "2026-08-31T17:00:00Z",
                    "inputData": {"generalDescription": "put it in outputData.url"},
                    "acceptanceCriteria": [{"check": "outputData.url returns HTTP 200 over HTTPS and stays live"}],
                }
            ]
        },
        now=NOW,
        source="fixture",
    )
    assert molt[0].public_hosting_required is True
    assert molt[0].custody_or_vendor_wallet_required is True
    work = observations_workpnp(
        {
            "jobs": [
                {
                    "id": "job_x",
                    "title": "Submit OpenThomas to 2-3 relevant awesome-lists",
                    "description": "open a real pull request on GitHub",
                    "acceptance_criteria": "PR URL",
                    "tags": ["outreach"],
                    "budget": 2000000,
                    "status": "open",
                    "created_at": 1783683811,
                    "poster_name": "openthomas",
                }
            ]
        },
        now=NOW,
        source="fixture",
    )
    assert work[0].reward_usd == Decimal("2.000000")
    assert work[0].funded is False
    assert work[0].authenticated_account_required is True
    profile = default_service_profile()
    assert classify_opportunity(molt[0], profile).classification == OpportunityClass.VENDOR_CLARIFICATION_REQUIRED
    assert classify_opportunity(work[0], profile).classification == OpportunityClass.INELIGIBLE


def test_discovery_is_get_only() -> None:
    client = ReadOnlyDiscoveryClient()
    with pytest.raises(MarketplaceError) as exc:
        client.request("POST", "/v1/jobs")
    assert exc.value.code == HttpCode.FORBIDDEN
    for method in MUTATING_METHODS:
        with pytest.raises(MarketplaceError):
            client.request(method, "/v1/jobs")
    client.close()
    source = (ROOT / "discovery.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "private_key" not in node.value or node.value == "generate_wallet_private_key"


def test_discovery_rejects_auth_and_non_allowlisted_origin() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update({k.decode().lower(): v.decode() for k, v in request.headers.raw})
        return httpx.Response(200, json={"postings": [], "total": 0}, headers={"content-type": "application/json"})

    raw = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = ReadOnlyDiscoveryClient(client=raw)
    client.get("the402", "/v1/postings", query={"limit": "5"})
    assert "authorization" not in captured
    assert "x-api-key" not in captured
    assert "x-payment" not in captured
    with pytest.raises(MarketplaceError):
        client.get("the402", "/v1/register")
    with pytest.raises(MarketplaceError):
        client.get("unknown", "/v1/jobs")


def test_scan_records_no_capital_actions() -> None:
    rows = {
        "moltjobs": [
            MarketObservation(
                marketplace="moltjobs",
                observed_at=NOW,
                source="test",
                external_id=f"j{i}",
                poster_id="one",
                reward_usd="5.000000",
                funded=True,
                public_hosting_required=True,
                vendor_clarification_required=True,
            )
            for i in range(7)
        ]
    }
    result = scan_observations(rows)
    assert result["capital_bearing_actions"] == []
    assert result["wallet_authority_expansion"] is False
    assert result["pr16_started"] is False
    assert result["eligible_count"] == 0
    assert result["concentrations"]["moltjobs"]["market_concentration"] == "HIGH"
    assert result["profile"]["custody_delegation"] is False


def test_probe_uses_only_get(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Fake:
        def get(self, market: str, path: str, *, query: dict[str, str] | None = None) -> dict:
            calls.append(f"GET {market} {path}")
            if market == "the402":
                return {"postings": [], "total": 0}
            if market == "workpnp":
                return {"jobs": []}
            if market == "moltjobs":
                return {"data": []}
            if market == "hober":
                return {"jobs": []}
            return {"total_tasks": 0, "active_hires": 0}

    probe_public_board(Fake(), "the402")  # type: ignore[arg-type]
    assert calls == ["GET the402 /v1/postings"]
