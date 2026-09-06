"""Bounded source-specific economic outbound transport.

Installed transports may GET allow-listed public marketplace origins to confirm
reachability, then refuse writes that require operator identity, custody, or
unrestricted HTTP. No generic URL/method argument is accepted from the model.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

from aea.marketplace.discovery import ALLOWED_ORIGINS, ALLOWED_PATHS, HTTP_TIMEOUT_SECONDS, USER_AGENT
from aea.marketplace.protocol import MarketplaceError
from aea.policy.reasons import HttpCode

PROBE_PATHS: dict[str, str] = {
    "the402": "/health",
    "moltjobs": "/v1/jobs",
    "workpnp": "/api/v1/jobs",
    "hober": "/api/marketplace/jobs",
    "bothire": "/api/stats",
}

SOURCE_REFUSALS: dict[str, str] = {
    "the402": (
        "the402 outbound messaging/bids require operator X-API-Key; the public "
        "board is paused for compliance review and has no bounded non-binding "
        "message path"
    ),
    "moltjobs": (
        "moltjobs messaging requires Turnkey vendor custody; no bounded "
        "non-binding message path"
    ),
    "workpnp": (
        "workpnp outbound contact is POST /api/v1/jobs/{id}/bids after "
        "POST /agents/register (operator identity). No bounded non-binding "
        "message path"
    ),
    "hober": (
        "hober contact requires SIWX/gateway signing; no bounded non-binding "
        "message path"
    ),
    "bothire": (
        "bothire contact requires generate-wallet private-key issuance; no "
        "bounded non-binding message path"
    ),
}


class BoundedSourceTransport:
    """One marketplace origin. GET probe only; never bids, spends, or signs."""

    def __init__(self, source: str, *, client: httpx.Client) -> None:
        if source not in ALLOWED_ORIGINS:
            raise MarketplaceError(HttpCode.FORBIDDEN, "unknown source rejected")
        self.source = source
        self._client = client

    def send_non_binding_message(
        self, *, counterparty_reference: str, intent: str, message: str, idempotency_key: str
    ) -> dict[str, Any]:
        del counterparty_reference, intent, message, idempotency_key
        probe = self._probe()
        reason = SOURCE_REFUSALS.get(self.source, "no bounded non-binding message path")
        raise MarketplaceError(
            HttpCode.POLICY_REJECTED,
            f"{self.source}: {reason}. probe={probe}",
        )

    def _probe(self) -> str:
        origin = ALLOWED_ORIGINS[self.source]
        path = PROBE_PATHS.get(self.source)
        if path is None or path not in ALLOWED_PATHS.get(self.source, ()):
            return "no_allowlisted_probe_path"
        url = origin.rstrip("/") + path
        parsed = urlsplit(url)
        expected = urlsplit(origin)
        if parsed.scheme != "https" or parsed.hostname != expected.hostname:
            return "probe_origin_rejected"
        try:
            response = self._client.request(
                "GET",
                url,
                timeout=HTTP_TIMEOUT_SECONDS,
                follow_redirects=False,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )
        except httpx.TimeoutException:
            return f"GET {path} timed out"
        except httpx.HTTPError as exc:
            return f"GET {path} transport failed ({type(exc).__name__})"
        if 300 <= response.status_code < 400:
            return f"GET {path} HTTP {response.status_code} redirect rejected"
        host = parsed.hostname or self.source
        return f"GET {host}{path} HTTP {response.status_code}"


def default_bounded_transports(*, client: httpx.Client | None = None) -> dict[str, BoundedSourceTransport]:
    shared = client or httpx.Client(
        timeout=HTTP_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    return {name: BoundedSourceTransport(name, client=shared) for name in ALLOWED_ORIGINS}
