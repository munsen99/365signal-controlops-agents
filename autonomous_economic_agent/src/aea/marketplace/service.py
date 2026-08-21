"""Mock marketplace HTTP process. ASGI on 127.0.0.1:18705.

Requires AEA_MARKETPLACE_TOKEN. Model token is FORBIDDEN. Optional wallet
credit rail uses AEA_WALLET_CREDIT_TOKEN only. No debit, signer, or HMAC.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from decimal import Decimal
from hmac import compare_digest
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx
from pydantic import ValidationError

from aea.marketplace.mock import MockMarketplace
from aea.marketplace.protocol import (
    MARKETPLACE_HOST,
    MARKETPLACE_PORT,
    AcceptRequest,
    MarketplaceError,
    SubmitRequest,
)
from aea.policy.reasons import HttpCode
from aea.types import format_amount

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")


def _scrub(payload: dict[str, Any], *, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    blocked = {n.lower() for n in secrets}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        low = key.lower()
        if any(part in low for part in ("token", "secret", "password", "hmac", "private_key", "seed")):
            continue
        if isinstance(value, str) and value in secrets:
            continue
        if isinstance(value, str) and value.lower() in blocked:
            continue
        out[key] = value
    return out


async def _read_body(receive: Receive) -> bytes:
    chunks = bytearray()
    more = True
    while more:
        message = await receive()
        chunks.extend(message.get("body", b""))
        more = bool(message.get("more_body"))
    return bytes(chunks)


async def _send_json(
    send: Send, *, status: int, payload: dict[str, Any], secrets: tuple[str, ...] = ()
) -> None:
    body = _json_bytes(_scrub(payload, secrets=secrets))
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _header_map(scope: Scope) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        headers[key.decode("latin1").lower()] = value.decode("latin1")
    return headers


def _bearer(headers: dict[str, str]) -> str | None:
    raw = headers.get("authorization")
    if raw is None:
        return None
    if not raw.startswith("Bearer "):
        return None
    token = raw[len("Bearer ") :].strip()
    return token or None


def _status_for(code: str) -> int:
    return {
        HttpCode.UNAUTHENTICATED: 401,
        HttpCode.FORBIDDEN: 403,
        HttpCode.VALIDATION_ERROR: 400,
        HttpCode.NOT_FOUND: 404,
        HttpCode.IDEMPOTENCY_CONFLICT: 409,
        HttpCode.CONFLICT: 409,
        HttpCode.NETWORK_FAILURE: 503,
        HttpCode.MARKETPLACE_UNAVAILABLE: 503,
        HttpCode.INTERNAL_ERROR: 500,
    }.get(code, 400)


def _query(scope: Scope) -> dict[str, str]:
    raw = scope.get("query_string") or b""
    text = raw.decode("latin1")
    out: dict[str, str] = {}
    if not text:
        return out
    for part in text.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[unquote(k)] = unquote(v)
        elif part:
            out[unquote(part)] = ""
    return out


class MarketplaceService:
    def __init__(
        self,
        *,
        adapter: MockMarketplace,
        marketplace_token: str,
        model_token: str | None = None,
        control_token: str | None = None,
        credit_token: str | None = None,
        debit_token: str | None = None,
    ) -> None:
        if not marketplace_token:
            raise ValueError("marketplace token is required")
        if debit_token:
            raise ValueError("marketplace must not hold a wallet debit token")
        self._adapter = adapter
        self._market = marketplace_token
        self._model = model_token
        self._control = control_token
        self._credit = credit_token

    def _secrets(self) -> tuple[str, ...]:
        return tuple(t for t in (self._market, self._model, self._control, self._credit) if t)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        headers = _header_map(scope)
        if method == "GET" and path == "/health":
            await _send_json(
                send, status=200, payload={"ok": True, "code": HttpCode.OK, "adapter": "mock"}
            )
            return
        denied = self._authorize(headers)
        if denied:
            await _send_json(
                send,
                status=_status_for(denied),
                payload={"ok": False, "code": denied},
                secrets=self._secrets(),
            )
            return
        try:
            if method == "GET" and path == "/v1/marketplace/jobs":
                await self._discover(scope, send)
                return
            if method == "GET" and path.startswith("/v1/marketplace/jobs/"):
                await self._get_job(path, send)
                return
            if method == "POST" and path.startswith("/v1/marketplace/jobs/"):
                await self._mutate(path, receive, send)
                return
        except MarketplaceError as exc:
            await _send_json(
                send,
                status=_status_for(exc.code),
                payload={"ok": False, "code": exc.code, "message": exc.message},
                secrets=self._secrets(),
            )
            return
        await _send_json(
            send,
            status=404,
            payload={"ok": False, "code": HttpCode.NOT_FOUND},
            secrets=self._secrets(),
        )

    def _authorize(self, headers: dict[str, str]) -> HttpCode | None:
        token = _bearer(headers)
        if token is None:
            return HttpCode.UNAUTHENTICATED
        if compare_digest(token, self._market):
            return None
        known = [t for t in (self._model, self._control, self._credit) if t]
        for other in known:
            if compare_digest(token, other):
                return HttpCode.FORBIDDEN
        return HttpCode.UNAUTHENTICATED

    def _split(self, path: str) -> tuple[str, str]:
        rest = unquote(path.removeprefix("/v1/marketplace/jobs/"))
        if "/" in rest:
            ref, action = rest.rsplit("/", 1)
            return ref, action
        return rest, ""

    async def _discover(self, scope: Scope, send: Send) -> None:
        q = _query(scope)
        limit = int(q.get("limit") or "10")
        cursor = q.get("cursor") or None
        page = self._adapter.discover(limit=limit, cursor=cursor)
        await _send_json(
            send,
            status=200,
            payload={"ok": True, "code": HttpCode.OK, **page.model_dump(mode="json")},
            secrets=self._secrets(),
        )

    async def _get_job(self, path: str, send: Send) -> None:
        ref, action = self._split(path)
        if action == "requirements":
            payload = self._adapter.get_requirements(ref).model_dump(mode="json")
        elif action == "payment-terms":
            payload = self._adapter.get_payment_terms(ref).model_dump(mode="json")
        elif action == "status":
            payload = self._adapter.get_status(ref).model_dump(mode="json")
        elif action == "payment":
            payload = self._adapter.verify_payment(ref).model_dump(mode="json")
        elif action == "counterparty":
            payload = self._adapter.get_counterparty(ref).model_dump(mode="json")
        elif action == "":
            payload = self._adapter.get_status(ref).model_dump(mode="json")
        else:
            await _send_json(
                send,
                status=404,
                payload={"ok": False, "code": HttpCode.NOT_FOUND},
                secrets=self._secrets(),
            )
            return
        await _send_json(
            send,
            status=200,
            payload={"ok": True, "code": HttpCode.OK, **payload},
            secrets=self._secrets(),
        )

    async def _mutate(self, path: str, receive: Receive, send: Send) -> None:
        ref, action = self._split(path)
        raw = await _read_body(receive)
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                secrets=self._secrets(),
            )
            return
        if not isinstance(payload, dict):
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                secrets=self._secrets(),
            )
            return
        try:
            if action == "accept":
                req = AcceptRequest.model_validate(payload)
                result = self._adapter.accept(ref, idempotency_key=req.idempotency_key)
            elif action == "submit":
                req_s = SubmitRequest.model_validate(payload)
                result = self._adapter.submit(
                    ref,
                    artefact_digest=req_s.artefact_digest,
                    artefact_uri=req_s.artefact_uri,
                    idempotency_key=req_s.idempotency_key,
                )
            else:
                await _send_json(
                    send,
                    status=404,
                    payload={"ok": False, "code": HttpCode.NOT_FOUND},
                    secrets=self._secrets(),
                )
                return
        except ValidationError:
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                secrets=self._secrets(),
            )
            return
        dumped = result.model_dump(mode="json")
        await _send_json(
            send,
            status=200,
            payload=dumped,
            secrets=self._secrets(),
        )


def create_app(
    *,
    adapter: MockMarketplace | None = None,
    marketplace_token: str,
    model_token: str | None = None,
    control_token: str | None = None,
    credit_token: str | None = None,
) -> MarketplaceService:
    return MarketplaceService(
        adapter=adapter or MockMarketplace(),
        marketplace_token=marketplace_token,
        model_token=model_token,
        control_token=control_token,
        credit_token=credit_token,
        debit_token=None,
    )


def _read_token(env_name: str, file_env: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    path = os.environ.get(file_env)
    if path:
        return Path(path).read_text(encoding="utf-8").rstrip("\n")
    return None


def create_app_from_env() -> MarketplaceService:
    token = _read_token("AEA_MARKETPLACE_TOKEN", "AEA_MARKETPLACE_TOKEN_FILE")
    if not token:
        raise ValueError("AEA_MARKETPLACE_TOKEN is required")
    credit = _read_token("AEA_WALLET_CREDIT_TOKEN", "AEA_WALLET_CREDIT_TOKEN_FILE")
    wallet_url = os.environ.get("AEA_WALLET_URL", "http://127.0.0.1:18704")

    def credit_fn(
        *,
        asset: str,
        amount: Decimal,
        tx_id: str,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, str]:
        if not credit:
            raise MarketplaceError(HttpCode.INTERNAL_ERROR, "credit token missing")
        response = httpx.post(
            f"{wallet_url.rstrip('/')}/v1/wallet/credit",
            json={
                "asset": asset,
                "amount": format_amount(amount),
                "reason": reason,
                "idempotency_key": idempotency_key,
                "tx_id": tx_id,
            },
            headers={"Authorization": f"Bearer {credit}"},
            timeout=10.0,
        )
        body = response.json()
        if not body.get("ok"):
            raise MarketplaceError(str(body.get("code") or HttpCode.NETWORK_FAILURE))
        return body.get("tx") or {"tx_id": tx_id}

    adapter = MockMarketplace(credit_fn=credit_fn if credit else None)
    return create_app(
        adapter=adapter,
        marketplace_token=token,
        model_token=_read_token("AEA_MODEL_TOKEN", "AEA_MODEL_TOKEN_FILE"),
        control_token=_read_token("AEA_CONTROL_TOKEN", "AEA_CONTROL_TOKEN_FILE"),
        credit_token=credit,
    )


def main() -> None:
    import uvicorn

    uvicorn.run(create_app_from_env(), host=MARKETPLACE_HOST, port=MARKETPLACE_PORT, log_level="info")


if __name__ == "__main__":
    main()
