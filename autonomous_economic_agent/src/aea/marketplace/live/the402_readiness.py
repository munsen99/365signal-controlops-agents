"""Public, GET-only readiness classification for the402.

This module deliberately has no provider credentials and no mutation methods.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from aea.marketplace.live.the402 import (
    BASE_MAINNET_CHAIN_ID,
    BASE_MAINNET_USDC,
    DISCOVER_LIMIT_MAX,
    The402HttpsClient,
    classify_posting,
)
from aea.marketplace.protocol import MarketplaceError
from aea.policy.reasons import HttpCode
from aea.types import format_amount, parse_unsigned_amount

ReadinessState = Literal[
    "PLATFORM_PAUSED",
    "ONBOARDING_READY",
    "NO_ELIGIBLE_DEMAND",
    "PR16_CANDIDATE_FOUND",
    "UNKNOWN",
]

MINIMUM_NET_REWARD_USDC = Decimal("2.000000")
ALLOWED_HTTP_METHODS = ("GET",)


@dataclass(frozen=True)
class ReadinessCandidate:
    posting_id: str
    reward: str
    net_reward: str
    asset: str
    chain: str
    task_type: str
    output_type: str
    task_age_seconds: int
    deadline: str | None
    status: str


@dataclass(frozen=True)
class The402ReadinessResult:
    marketplace: str
    state: ReadinessState
    paused: bool | None
    pause_reason: str | None
    open_postings: int
    funded_postings: int
    eligible_postings: int
    operator_onboarding: str
    pr16: str
    checked_at: str
    http_methods_used: tuple[str, ...] = ALLOWED_HTTP_METHODS
    authentication_used: bool = False
    capital_moved: bool = False
    wallet_authority_expansion: bool = False
    candidate: ReadinessCandidate | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class PublicThe402ReadinessClient:
    """Two fixed public GETs; no generic method or authentication input."""

    def __init__(self, client: The402HttpsClient | None = None) -> None:
        self._client = client or The402HttpsClient(api_key=None)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_health(self) -> dict[str, Any]:
        return self._object(self._client.request("GET", "/health"))

    def get_postings(self, *, limit: int) -> dict[str, Any]:
        if isinstance(limit, bool) or limit < 1 or limit > DISCOVER_LIMIT_MAX:
            raise ValueError(f"limit must be between 1 and {DISCOVER_LIMIT_MAX}")
        return self._object(
            self._client.request("GET", "/v1/postings", query={"limit": str(limit)})
        )

    @staticmethod
    def _object(response: object) -> dict[str, Any]:
        import json

        status = getattr(response, "status_code", None)
        if not isinstance(status, int) or status < 200 or status >= 300:
            raise MarketplaceError(HttpCode.NETWORK_FAILURE, "the402 public probe failed")
        try:
            payload = json.loads(getattr(response, "body").decode("utf-8"))
        except (AttributeError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("malformed the402 JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("malformed the402 object")
        return payload


def _unknown(*, checked_at: str, reason: str) -> The402ReadinessResult:
    return The402ReadinessResult(
        marketplace="the402",
        state="UNKNOWN",
        paused=None,
        pause_reason=None,
        open_postings=0,
        funded_postings=0,
        eligible_postings=0,
        operator_onboarding="BLOCKED",
        pr16="NOT_READY",
        checked_at=checked_at,
        error=reason,
    )


def _eligible(posting: dict[str, Any], *, now: datetime) -> ReadinessCandidate | None:
    """Conservative public-data gate; absence of a material field rejects."""

    task_type, reasons = classify_posting(posting)
    if reasons or task_type is None:
        return None
    if posting.get("status") not in {"open", "available"}:
        return None
    if posting.get("funded") is not True and posting.get("funding_status") not in {
        "funded",
        "escrowed",
    }:
        return None
    network = str(posting.get("network") or posting.get("chain") or "").lower()
    if network not in {"base", "base-mainnet"}:
        return None
    if posting.get("chain_id") not in {BASE_MAINNET_CHAIN_ID, str(BASE_MAINNET_CHAIN_ID)}:
        return None
    if str(posting.get("currency") or posting.get("asset") or "").upper() != "USDC":
        return None
    if str(posting.get("token") or posting.get("token_contract") or "").lower() != BASE_MAINNET_USDC.lower():
        return None
    if str(posting.get("participant_role") or posting.get("role") or "").lower() != "provider":
        return None
    if str(posting.get("payout_wallet_type") or "").lower() != "external":
        return None
    required_false = (
        "provider_capital_required",
        "escrow_funding_required",
        "custody_required",
        "wallet_signing_required",
        "eip712_required",
        "eip3009_required",
        "approval_required",
        "permit_required",
        "public_hosting_required",
    )
    if any(posting.get(field) is not False for field in required_false):
        return None
    raw_reward = posting.get("reward_usdc") or posting.get("budget_min_usd")
    raw_fee = posting.get("provider_fee_bps")
    if raw_reward is None or raw_fee is None:
        return None
    try:
        reward = parse_unsigned_amount(str(raw_reward).replace("$", ""))
        fee_bps = int(raw_fee)
    except (TypeError, ValueError):
        return None
    if fee_bps < 0 or fee_bps > 10_000:
        return None
    net = reward * (Decimal(10_000 - fee_bps) / Decimal(10_000))
    if net < MINIMUM_NET_REWARD_USDC:
        return None
    posting_id = posting.get("posting_id") or posting.get("id")
    if not isinstance(posting_id, str) or not posting_id or len(posting_id) > 128:
        return None
    created_at = posting.get("created_at")
    output_type = posting.get("allowed_deliverable_type") or posting.get("deliverable_type")
    if not isinstance(created_at, str) or not isinstance(output_type, str):
        return None
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        age_seconds = max(0, int((now - created.astimezone(UTC)).total_seconds()))
    except (TypeError, ValueError):
        return None
    return ReadinessCandidate(
        posting_id=posting_id,
        reward=format_amount(reward),
        net_reward=format_amount(net),
        asset="USDC",
        chain="Base",
        task_type=task_type,
        output_type=output_type,
        task_age_seconds=age_seconds,
        deadline=str(posting["deadline"]) if posting.get("deadline") is not None else None,
        status=str(posting["status"]),
    )


def classify_readiness(
    health: dict[str, Any],
    postings_payload: dict[str, Any],
    *,
    onboarding_complete: bool = False,
    checked_at: str | None = None,
) -> The402ReadinessResult:
    checked = checked_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    paused = health.get("paused")
    network = health.get("network")
    postings = postings_payload.get("postings")
    if not isinstance(paused, bool) or str(network).lower() != "base":
        return _unknown(checked_at=checked, reason="malformed_health")
    if not isinstance(postings, list) or any(not isinstance(item, dict) for item in postings):
        return _unknown(checked_at=checked, reason="malformed_postings")

    try:
        now = datetime.fromisoformat(checked.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return _unknown(checked_at=checked, reason="invalid_check_time")
    open_items = [item for item in postings if item.get("status") in {"open", "available"}]
    candidates = [
        candidate for item in open_items if (candidate := _eligible(item, now=now)) is not None
    ]
    funded = sum(
        1
        for item in open_items
        if item.get("funded") is True or item.get("funding_status") in {"funded", "escrowed"}
    )
    state: ReadinessState
    onboarding: str
    pr16: str
    if paused:
        state, onboarding, pr16 = "PLATFORM_PAUSED", "BLOCKED", "NOT_READY"
    elif not onboarding_complete:
        state, onboarding, pr16 = "ONBOARDING_READY", "REQUIRED", "NOT_READY"
    elif candidates:
        state, onboarding, pr16 = "PR16_CANDIDATE_FOUND", "COMPLETE", "REVIEW_REQUIRED"
    else:
        state, onboarding, pr16 = "NO_ELIGIBLE_DEMAND", "COMPLETE", "NOT_READY"
    return The402ReadinessResult(
        marketplace="the402",
        state=state,
        paused=paused,
        pause_reason=str(health.get("pause_reason")) if health.get("pause_reason") else None,
        open_postings=len(open_items),
        funded_postings=funded,
        eligible_postings=len(candidates),
        operator_onboarding=onboarding,
        pr16=pr16,
        checked_at=checked,
        candidate=candidates[0] if candidates else None,
    )
