"""Read-only public marketplace probes. GET only. No wallet, bid, or spend."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from aea.marketplace.intelligence import MarketObservation
from aea.marketplace.protocol import MarketplaceError
from aea.policy.reasons import HttpCode
from aea.types import format_amount

HTTP_TIMEOUT_SECONDS = 10.0
HTTP_BODY_MAX_BYTES = 262144
USER_AGENT = "aea-market-discovery/1"

ALLOWED_ORIGINS: dict[str, str] = {
    "the402": "https://api.the402.ai",
    "moltjobs": "https://api.moltjobs.io",
    "workpnp": "https://workpnp.com",
    "hober": "https://www.hober.dev",
    "bothire": "https://www.bothire.io",
}

ALLOWED_PATHS: dict[str, tuple[str, ...]] = {
    "the402": ("/v1/postings", "/health"),
    "moltjobs": ("/v1/jobs", "/v1/stats"),
    "workpnp": ("/api/v1/jobs",),
    "hober": ("/api/marketplace/jobs",),
    "bothire": ("/api/stats",),
}

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE", "CONNECT"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _path_allowed(market: str, path: str) -> bool:
    allowed = ALLOWED_PATHS.get(market, ())
    split = urlsplit(path)
    if split.scheme or split.netloc or not path.startswith("/") or path.startswith("//"):
        return False
    return any(split.path == prefix or split.path.startswith(prefix + "/") for prefix in allowed)


class ReadOnlyDiscoveryClient:
    """Pinned HTTPS GET client. Refuses mutating methods and model-supplied auth."""

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._owns = client is None
        self._client = client or httpx.Client(
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def get(self, market: str, path: str, *, query: dict[str, str] | None = None) -> dict[str, Any]:
        if market not in ALLOWED_ORIGINS:
            raise MarketplaceError(HttpCode.FORBIDDEN, "marketplace origin is not allow-listed")
        if not _path_allowed(market, path):
            raise MarketplaceError(HttpCode.FORBIDDEN, "path is outside discovery allow-list")
        origin = ALLOWED_ORIGINS[market]
        url = urljoin(origin + "/", path.lstrip("/"))
        parsed = urlsplit(url)
        expected = urlsplit(origin)
        if parsed.scheme != "https" or parsed.hostname != expected.hostname:
            raise MarketplaceError(HttpCode.FORBIDDEN, "discovery origin rejected")
        try:
            response = self._client.request(
                "GET",
                url,
                params=query,
                timeout=HTTP_TIMEOUT_SECONDS,
                follow_redirects=False,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )
        except httpx.TimeoutException as exc:
            raise MarketplaceError(HttpCode.TIMEOUT, "discovery timed out") from exc
        except httpx.HTTPError as exc:
            raise MarketplaceError(HttpCode.NETWORK_FAILURE, "discovery transport failed") from exc
        if 300 <= response.status_code < 400:
            raise MarketplaceError(HttpCode.FORBIDDEN, "discovery redirect rejected")
        if response.status_code >= 400:
            raise MarketplaceError(HttpCode.MARKETPLACE_UNAVAILABLE, "discovery HTTP error")
        if len(response.content) > HTTP_BODY_MAX_BYTES:
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "discovery response too large")
        ctype = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ctype not in {"application/json", "application/problem+json"}:
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "discovery content-type rejected")
        try:
            payload = json.loads(response.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "malformed discovery JSON") from exc
        if not isinstance(payload, dict):
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "discovery JSON schema rejected")
        return payload

    def request(self, method: str, *_args: object, **_kwargs: object) -> None:
        if method.upper() in MUTATING_METHODS:
            raise MarketplaceError(HttpCode.FORBIDDEN, "discovery is GET-only")
        raise MarketplaceError(HttpCode.FORBIDDEN, "discovery is GET-only")


def _age_days(created: datetime | None, now: datetime) -> str | None:
    if created is None:
        return None
    delta = now - created
    days = Decimal(str(max(delta.total_seconds(), 0))) / Decimal("86400")
    return format_amount(days)


def _parse_ts(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        ts = float(value)
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def observations_the402(payload: dict[str, Any], *, now: datetime | None = None, source: str) -> list[MarketObservation]:
    now = now or _now()
    items = payload.get("postings") if isinstance(payload.get("postings"), list) else []
    out: list[MarketObservation] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        created = _parse_ts(item.get("created_at") or item.get("createdAt"))
        reward = item.get("budget_min_usd") or item.get("budget_max_usd")
        out.append(
            MarketObservation(
                marketplace="the402",
                observed_at=now,
                source=source,
                external_id=str(item.get("posting_id") or "") or None,
                poster_id=str(item.get("buyer_id") or item.get("poster_id") or "") or None,
                category=str(item.get("category") or "") or None,
                title=str(item.get("title") or "")[:200] or None,
                reward_usd=None if reward is None else str(reward).replace("$", ""),
                asset="USDC",
                chain="base",
                funded=bool(item.get("funded")),
                public_hosting_required=False,
                status=str(item.get("status") or "open"),
                age_days=_age_days(created, now),
            )
        )
    return out


def observations_moltjobs(payload: dict[str, Any], *, now: datetime | None = None, source: str) -> list[MarketObservation]:
    now = now or _now()
    jobs = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("jobs")
    if not isinstance(jobs, list):
        jobs = []
    out: list[MarketObservation] = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        created = _parse_ts(item.get("createdAt"))
        criteria = item.get("acceptanceCriteria") or []
        hosting = False
        blob = json.dumps(item.get("inputData") or {}) + json.dumps(criteria)
        if "outputData.url" in blob or "HTTP 200" in blob:
            hosting = True
        poster = item.get("poster") if isinstance(item.get("poster"), dict) else {}
        poster_id = str(item.get("posterId") or poster.get("id") or "") or None
        funded = bool(item.get("escrowTxHash")) and str(item.get("paymentProvider") or "") == "ON_CHAIN_USDC"
        out.append(
            MarketObservation(
                marketplace="moltjobs",
                observed_at=now,
                source=source,
                external_id=str(item.get("id") or "") or None,
                poster_id=poster_id,
                category=str(item.get("vertical") or item.get("templateId") or "") or None,
                title=str(item.get("title") or "")[:200] or None,
                reward_usd=None if item.get("budgetUsdc") is None else str(item.get("budgetUsdc")),
                asset=str(item.get("tokenSymbol") or "USDC"),
                chain="base" if item.get("chainId") in {8453, "8453"} else None,
                funded=funded,
                public_hosting_required=hosting,
                custody_or_vendor_wallet_required=True,
                vendor_clarification_required=True,
                status=str(item.get("status") or ""),
                age_days=_age_days(created, now),
                ineligibility_reason="turnkey_wallet_and_chain_docs",
            )
        )
    return out


def observations_workpnp(payload: dict[str, Any], *, now: datetime | None = None, source: str) -> list[MarketObservation]:
    now = now or _now()
    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
    out: list[MarketObservation] = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        created = _parse_ts(item.get("created_at"))
        budget = item.get("budget")
        reward = None
        if isinstance(budget, int) and not isinstance(budget, bool):
            reward = format_amount(Decimal(budget) / Decimal("1000000"))
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        text = f"{item.get('title') or ''} {item.get('description') or ''} {item.get('acceptance_criteria') or ''}"
        github = "pull request" in text.lower() or "github" in text.lower()
        out.append(
            MarketObservation(
                marketplace="workpnp",
                observed_at=now,
                source=source,
                external_id=str(item.get("id") or "") or None,
                poster_id=str(item.get("poster_name") or item.get("poster_id") or "") or None,
                category=",".join(str(tag) for tag in tags)[:64] or None,
                title=str(item.get("title") or "")[:200] or None,
                reward_usd=reward,
                asset="USDC",
                chain="base",
                funded=str(item.get("status") or "") == "funded",
                authenticated_account_required=github,
                operator_action_required=True,
                status=str(item.get("status") or ""),
                age_days=_age_days(created, now),
                ineligibility_reason="github_pr_outreach" if github else None,
            )
        )
    return out


def observations_hober(payload: dict[str, Any], *, now: datetime | None = None, source: str) -> list[MarketObservation]:
    now = now or _now()
    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
    out: list[MarketObservation] = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").upper() != "OPEN":
            continue
        created = _parse_ts(item.get("createdAt"))
        budget = item.get("budgetUsd")
        out.append(
            MarketObservation(
                marketplace="hober",
                observed_at=now,
                source=source,
                external_id=str(item.get("id") or "") or None,
                poster_id=str(item.get("provider") or item.get("clientWallet") or "") or None,
                title=str(item.get("model") or "")[:200] or None,
                reward_usd=None if budget is None else str(budget),
                asset="USDC",
                chain="base",
                funded=False,
                custody_or_vendor_wallet_required=True,
                status="OPEN",
                age_days=_age_days(created, now),
                ineligibility_reason="siwx_or_gateway_signing",
            )
        )
    return out


def bothire_board_observation(payload: dict[str, Any], *, now: datetime | None = None, source: str) -> MarketObservation:
    now = now or _now()
    tasks = payload.get("total_tasks")
    hires = payload.get("active_hires")
    return MarketObservation(
        marketplace="bothire",
        observed_at=now,
        source=source,
        category="catalog",
        reward_usd=None,
        asset="USDC",
        chain="base",
        funded=False,
        custody_or_vendor_wallet_required=True,
        status="no_open_tasks",
        ineligibility_reason="generate_wallet_private_key",
        title=f"tasks={tasks};active_hires={hires}",
    )


def probe_public_board(
    client: ReadOnlyDiscoveryClient,
    market: str,
    *,
    now: datetime | None = None,
) -> list[MarketObservation]:
    now = now or _now()
    if market == "the402":
        payload = client.get("the402", "/v1/postings", query={"limit": "20"})
        return observations_the402(payload, now=now, source="GET /v1/postings")
    if market == "moltjobs":
        payload = client.get("moltjobs", "/v1/jobs", query={"status": "OPEN", "limit": "20"})
        return observations_moltjobs(payload, now=now, source="GET /v1/jobs?status=OPEN")
    if market == "workpnp":
        payload = client.get("workpnp", "/api/v1/jobs", query={"status": "open", "limit": "20"})
        return observations_workpnp(payload, now=now, source="GET /api/v1/jobs?status=open")
    if market == "hober":
        payload = client.get("hober", "/api/marketplace/jobs")
        return observations_hober(payload, now=now, source="GET /api/marketplace/jobs")
    if market == "bothire":
        payload = client.get("bothire", "/api/stats")
        return [bothire_board_observation(payload, now=now, source="GET /api/stats")]
    raise MarketplaceError(HttpCode.NOT_FOUND, "unknown discovery market")
