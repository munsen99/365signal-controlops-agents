"""PR15.5 public, GET-only the402 readiness tests."""

from __future__ import annotations

import inspect
from typing import Any

from aea.marketplace.live.the402 import BASE_MAINNET_CHAIN_ID, BASE_MAINNET_USDC, TransportResponse
from aea.marketplace.live.the402_readiness import (
    ALLOWED_HTTP_METHODS,
    PublicThe402ReadinessClient,
    classify_readiness,
)

CHECKED = "2026-09-06T12:00:00Z"


def _health(*, paused: bool = False) -> dict[str, Any]:
    return {
        "status": "paused" if paused else "ok",
        "paused": paused,
        "pause_reason": "compliance review" if paused else None,
        "network": "base",
    }


def _candidate(**overrides: Any) -> dict[str, Any]:
    posting: dict[str, Any] = {
        "posting_id": "post_public_1",
        "title": "Summarize supplied public-domain text",
        "description": "Create a concise summary from supplied public-domain text.",
        "category": "content",
        "allowed_deliverable_type": "text",
        "status": "open",
        "created_at": "2026-09-06T11:00:00Z",
        "deadline": "2026-09-07T11:00:00Z",
        "funded": True,
        "network": "base",
        "chain_id": BASE_MAINNET_CHAIN_ID,
        "currency": "USDC",
        "token": BASE_MAINNET_USDC,
        "participant_role": "provider",
        "payout_wallet_type": "external",
        "provider_capital_required": False,
        "escrow_funding_required": False,
        "custody_required": False,
        "wallet_signing_required": False,
        "eip712_required": False,
        "eip3009_required": False,
        "approval_required": False,
        "permit_required": False,
        "public_hosting_required": False,
        "budget_min_usd": "3.00",
        "provider_fee_bps": 500,
    }
    posting.update(overrides)
    return posting


def test_platform_paused_is_normal_state() -> None:
    result = classify_readiness(
        _health(paused=True), {"postings": []}, checked_at=CHECKED
    )
    assert result.state == "PLATFORM_PAUSED"
    assert result.operator_onboarding == "BLOCKED"
    assert result.pr16 == "NOT_READY"


def test_unpaused_before_onboarding_is_onboarding_ready() -> None:
    result = classify_readiness(_health(), {"postings": [_candidate()]}, checked_at=CHECKED)
    assert result.state == "ONBOARDING_READY"
    assert result.eligible_postings == 1
    assert result.operator_onboarding == "REQUIRED"
    assert result.pr16 == "NOT_READY"


def test_onboarded_without_eligible_demand() -> None:
    incompatible = _candidate(token="0x0000000000000000000000000000000000000001")
    result = classify_readiness(
        _health(), {"postings": [incompatible]}, onboarding_complete=True, checked_at=CHECKED
    )
    assert result.state == "NO_ELIGIBLE_DEMAND"
    assert result.funded_postings == 1
    assert result.eligible_postings == 0


def test_onboarded_candidate_requires_review() -> None:
    result = classify_readiness(
        _health(), {"postings": [_candidate()]}, onboarding_complete=True, checked_at=CHECKED
    )
    assert result.state == "PR16_CANDIDATE_FOUND"
    assert result.pr16 == "REVIEW_REQUIRED"
    assert result.candidate is not None
    assert result.candidate.posting_id == "post_public_1"
    assert result.candidate.net_reward == "2.850000"
    assert result.candidate.output_type == "text"
    assert result.candidate.task_age_seconds == 3600


def test_missing_or_untrusted_material_fields_fail_closed() -> None:
    malformed = classify_readiness({}, {"postings": []}, checked_at=CHECKED)
    assert malformed.state == "UNKNOWN"
    malformed_postings = classify_readiness(_health(), {"postings": "bad"}, checked_at=CHECKED)
    assert malformed_postings.state == "UNKNOWN"
    missing = _candidate()
    del missing["wallet_signing_required"]
    result = classify_readiness(
        _health(), {"postings": [missing]}, onboarding_complete=True, checked_at=CHECKED
    )
    assert result.state == "NO_ELIGIBLE_DEMAND"
    assert result.eligible_postings == 0


def test_low_reward_and_unsupported_work_rejected() -> None:
    low = _candidate(budget_min_usd="2.00")
    unsafe = _candidate(
        posting_id="post_unsafe", title="Exploit a private network", category="security"
    )
    result = classify_readiness(
        _health(), {"postings": [low, unsafe]}, onboarding_complete=True, checked_at=CHECKED
    )
    assert result.state == "NO_ELIGIBLE_DEMAND"


class _SpyClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str] | None, dict[str, str] | None]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        **_kwargs: object,
    ) -> TransportResponse:
        self.calls.append((method, path, query, headers))
        body = b'{"paused":false,"network":"base"}' if path == "/health" else b'{"postings":[]}'
        return TransportResponse(200, {"content-type": "application/json"}, body, "https://api.the402.ai" + path)


def test_command_client_is_get_only_and_unauthenticated() -> None:
    spy = _SpyClient()
    client = PublicThe402ReadinessClient(spy)  # type: ignore[arg-type]
    assert client.get_health()["paused"] is False
    assert client.get_postings(limit=20)["postings"] == []
    assert ALLOWED_HTTP_METHODS == ("GET",)
    assert [call[:2] for call in spy.calls] == [
        ("GET", "/health"),
        ("GET", "/v1/postings"),
    ]
    assert all(call[3] is None for call in spy.calls)
    assert not hasattr(client, "post")
    assert not hasattr(client, "put")
    assert not hasattr(client, "delete")
    assert set(inspect.signature(PublicThe402ReadinessClient).parameters) == {"client"}
