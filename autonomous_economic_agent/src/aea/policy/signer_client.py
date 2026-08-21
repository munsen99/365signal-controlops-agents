"""Policy-side signer client. Holds AEA_SIGNER_TOKEN and HMAC; never debit.

Control, Hermes, and the model must not import this with live secrets.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from aea.policy.reasons import HttpCode
from aea.signer.backend import (
    ApprovedRequest,
    SignResult,
    canonical_approved_hash,
    compute_request_hmac,
)

SignerPost = Callable[[dict[str, Any], dict[str, str]], Awaitable[httpx.Response]]


class PolicySignerClient:
    """HMAC + bearer caller of POST /v1/sign. No wallet debit credential."""

    def __init__(
        self,
        *,
        hmac_key: str,
        signer_token: str,
        signer_app: Any | None = None,
        signer_sock: str | None = None,
    ) -> None:
        if not hmac_key or not signer_token:
            raise ValueError("policy signer client requires HMAC key and signer token")
        if hmac_key == signer_token:
            raise ValueError("HMAC key must be distinct from signer token")
        self._hmac_key = hmac_key
        self._signer_token = signer_token
        self._signer_app = signer_app
        self._signer_sock = signer_sock

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._signer_token}"}

    async def sign(self, approved: ApprovedRequest) -> SignResult:
        canonical = canonical_approved_hash(approved)
        body = {
            "approved_request": approved.model_dump(mode="json"),
            "canonical_hash": canonical,
            "policy_version": approved.policy_version,
            "request_hmac": compute_request_hmac(
                self._hmac_key,
                approved_request=approved,
                canonical_hash=canonical,
                policy_version=approved.policy_version,
            ),
        }
        try:
            response = await self._post(body)
        except httpx.HTTPError:
            return SignResult(
                ok=False,
                code=HttpCode.SIGNER_UNAVAILABLE,
                request_id=approved.request_id,
                correlation_id=approved.correlation_id,
                reason_code=HttpCode.SIGNER_UNAVAILABLE,
            )
        try:
            payload = response.json()
        except ValueError:
            return SignResult(
                ok=False,
                code=HttpCode.SIGNER_UNAVAILABLE,
                request_id=approved.request_id,
                correlation_id=approved.correlation_id,
                reason_code=HttpCode.SIGNER_UNAVAILABLE,
            )
        if not isinstance(payload, dict):
            return SignResult(
                ok=False,
                code=HttpCode.SIGNER_UNAVAILABLE,
                request_id=approved.request_id,
                correlation_id=approved.correlation_id,
            )
        return SignResult.model_validate(
            {
                "ok": bool(payload.get("ok")),
                "code": payload.get("code") or HttpCode.SIGNER_UNAVAILABLE,
                "request_id": payload.get("request_id") or approved.request_id,
                "correlation_id": payload.get("correlation_id") or approved.correlation_id,
                "reason_code": payload.get("reason_code") or payload.get("code"),
                "tx_id": payload.get("tx_id"),
                "canonical_hash": payload.get("canonical_hash"),
                "replay": bool(payload.get("replay")),
            }
        )

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        headers = self._headers()
        if self._signer_app is not None:
            transport = httpx.ASGITransport(app=self._signer_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://signer") as client:
                return await client.post("/v1/sign", json=body, headers=headers)
        if not self._signer_sock:
            raise httpx.ConnectError("signer socket not configured")
        transport = httpx.AsyncHTTPTransport(uds=self._signer_sock)
        async with httpx.AsyncClient(transport=transport, base_url="http://signer") as client:
            return await client.post("/v1/sign", json=body, headers=headers)
