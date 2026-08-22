"""Signer HTTP process. Unix socket only in production.

POST /v1/sign requires AEA_SIGNER_TOKEN **and** request HMAC-SHA256
(AEA_SIGNER_HMAC_KEY). Model and control tokens are FORBIDDEN. The HMAC
key is distinct from the signer bearer and every wallet credential.
The service holds AEA_WALLET_DEBIT_TOKEN and is the only debit caller.
It never loads a credit token and never returns secrets.
"""

from __future__ import annotations

import json
import os
import socket
import stat
from collections.abc import Awaitable, Callable
from decimal import Decimal
from hmac import compare_digest
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from aea.policy.reasons import HttpCode
from aea.signer.backend import SignRequest, SignResult, SignerBackend, WalletDebitError
from aea.signer.mock import MockSigner
from aea.types import format_amount

SIGNER_SOCK_DEFAULT = "/run/aea/signer.sock"
SIGNER_SOCKET_MODE = 0o660
SIGNER_SOCKET_GROUP = "aea-signpipe"
WALLET_URL_DEFAULT = "http://127.0.0.1:18704"

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

_SECRET_NEEDLES = (
    "private_key",
    "seed_phrase",
    "seed phrase",
    "mnemonic",
    "wallet_debit",
    "AEA_WALLET_DEBIT_TOKEN",
    "AEA_SIGNER_TOKEN",
    "AEA_SIGNER_HMAC_KEY",
    "BEGIN ",
)


def _read_token(env_name: str, file_env: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    path = os.environ.get(file_env)
    if path:
        return Path(path).read_text(encoding="utf-8").rstrip("\n")
    return None


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")


def _scrub(payload: dict[str, Any], *, extra_secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    """Drop any accidental secret-shaped fields; never emit credential values."""
    blocked = {n.lower() for n in extra_secrets}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        low = key.lower()
        if any(part in low for part in ("token", "secret", "password", "private_key", "seed", "mnemonic", "hmac")):
            continue
        if isinstance(value, str) and value in extra_secrets:
            continue
        if isinstance(value, str) and any(n in value for n in _SECRET_NEEDLES):
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


async def _send_json(send: Send, *, status: int, payload: dict[str, Any], secrets: tuple[str, ...] = ()) -> None:
    body = _json_bytes(_scrub(payload, extra_secrets=secrets))
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
        HttpCode.SIGNER_UNAVAILABLE: 503,
        HttpCode.INTERNAL_ERROR: 500,
    }.get(code, 200)


class AsgiWalletDebit:
    """Debit-only client against the Phase A wallet ASGI app."""

    def __init__(self, app: Any, debit_token: str) -> None:
        if not debit_token:
            raise ValueError("debit token is required")
        self._app = app
        self._debit_token = debit_token

    async def debit(
        self,
        *,
        asset: str,
        amount: Decimal,
        destination: str,
        reason: str,
        idempotency_key: str,
    ) -> str:
        return await _wallet_debit(
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app),
                base_url="http://wallet",
            ),
            debit_token=self._debit_token,
            asset=asset,
            amount=amount,
            destination=destination,
            reason=reason,
            idempotency_key=idempotency_key,
        )


class HttpWalletDebit:
    """Debit-only HTTP client. No credit method, no read token."""

    def __init__(self, base_url: str, debit_token: str) -> None:
        if not debit_token:
            raise ValueError("debit token is required")
        self._base_url = base_url.rstrip("/")
        self._debit_token = debit_token

    async def debit(
        self,
        *,
        asset: str,
        amount: Decimal,
        destination: str,
        reason: str,
        idempotency_key: str,
    ) -> str:
        return await _wallet_debit(
            client_factory=lambda: httpx.AsyncClient(base_url=self._base_url),
            debit_token=self._debit_token,
            asset=asset,
            amount=amount,
            destination=destination,
            reason=reason,
            idempotency_key=idempotency_key,
        )


async def _wallet_debit(
    *,
    client_factory: Callable[[], httpx.AsyncClient],
    debit_token: str,
    asset: str,
    amount: Decimal,
    destination: str,
    reason: str,
    idempotency_key: str,
) -> str:
    payload = {
        "asset": asset,
        "amount": format_amount(amount),
        "destination": destination,
        "reason": reason,
        "idempotency_key": idempotency_key,
    }
    try:
        async with client_factory() as client:
            response = await client.post(
                "/v1/wallet/debit",
                json=payload,
                headers={"Authorization": f"Bearer {debit_token}"},
            )
    except httpx.HTTPError as exc:
        raise WalletDebitError(HttpCode.NETWORK_FAILURE, "wallet transport failed") from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise WalletDebitError(HttpCode.NETWORK_FAILURE, "wallet returned non-JSON") from exc
    if not isinstance(body, dict):
        raise WalletDebitError(HttpCode.NETWORK_FAILURE, "wallet returned non-object")
    code = str(body.get("code") or HttpCode.NETWORK_FAILURE)
    if response.status_code == 200 and body.get("ok") is True:
        tx = body.get("tx") or {}
        tx_id = tx.get("tx_id") if isinstance(tx, dict) else None
        if not isinstance(tx_id, str) or not tx_id.startswith("mocktx_"):
            raise WalletDebitError(HttpCode.INTERNAL_ERROR, "wallet returned invalid tx")
        return tx_id
    raise WalletDebitError(code)


def prepare_unix_socket(path: Path | str, *, mode: int = SIGNER_SOCKET_MODE) -> socket.socket:
    """Bind an AF_UNIX socket at ``path`` with mode 0660. Does not listen.

    Group ``aea-signpipe`` is applied when it exists and chown is permitted.
    """
    sock_path = Path(path)
    if sock_path.is_symlink() or sock_path.exists():
        sock_path.unlink()
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(str(sock_path))
        os.chmod(sock_path, mode)
        try:
            import grp

            gid = grp.getgrnam(SIGNER_SOCKET_GROUP).gr_gid
            os.chown(sock_path, -1, gid)
        except (KeyError, PermissionError, OSError):
            pass
    except Exception:
        sock.close()
        raise
    return sock


def socket_mode(path: Path | str) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


class SignerService:
    """ASGI app wrapping MockSigner. No TCP bind in production main()."""

    def __init__(
        self,
        *,
        signer: SignerBackend,
        signer_token: str,
        debit_token: str,
        model_token: str | None = None,
        control_token: str | None = None,
        supervisor_token: str | None = None,
        policy_token: str | None = None,
        read_token: str | None = None,
        credit_token: str | None = None,
    ) -> None:
        if not signer_token or not debit_token:
            raise ValueError("signer and wallet debit tokens are required")
        if signer_token == debit_token:
            raise ValueError("signer token and wallet debit token must be distinct")
        hmac_key = signer.hmac_key
        extras = [
            t
            for t in (
                model_token,
                control_token,
                supervisor_token,
                policy_token,
                read_token,
                credit_token,
            )
            if t
        ]
        known = [signer_token, debit_token, *extras]
        if len(set(known)) != len(known):
            raise ValueError("signer credentials must be distinct from other scopes")
        if hmac_key in known:
            raise ValueError("HMAC key must be distinct from bearer and wallet credentials")
        self._signer = signer
        self._signer_token = signer_token
        self._debit_token = debit_token
        self._hmac_key = hmac_key
        self._model = model_token
        self._control = control_token
        self._supervisor = supervisor_token
        self._policy = policy_token
        self._read = read_token
        self._credit = credit_token

    def _secrets(self) -> tuple[str, ...]:
        return tuple(
            t
            for t in (
                self._signer_token,
                self._debit_token,
                self._hmac_key,
                self._model,
                self._control,
                self._supervisor,
                self._policy,
                self._read,
                self._credit,
            )
            if t
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        headers = _header_map(scope)
        if method == "GET" and path == "/health":
            inspection = self._signer.inspect_current_freeze()
            await _send_json(
                send,
                status=200,
                payload={
                    "ok": True,
                    "code": HttpCode.OK,
                    "signer_enabled": self._signer.signer_enabled,
                    "frozen": inspection.frozen,
                },
                secrets=self._secrets(),
            )
            return
        if method == "POST" and path == "/v1/sign":
            await self._sign(headers, receive, send)
            return
        if method == "POST" and path == "/v1/disable":
            await self._disable(headers, send)
            return
        if method == "POST" and path == "/v1/enable":
            await self._enable(headers, send)
            return
        await _send_json(
            send,
            status=404,
            payload={"ok": False, "code": HttpCode.NOT_FOUND},
            secrets=self._secrets(),
        )

    def _classify(self, token: str | None, required: str) -> HttpCode | None:
        if token is None:
            return HttpCode.UNAUTHENTICATED
        if compare_digest(token, required):
            return None
        known = [
            t
            for t in (
                self._signer_token,
                self._debit_token,
                self._hmac_key,
                self._model,
                self._control,
                self._supervisor,
                self._policy,
                self._read,
                self._credit,
            )
            if t
        ]
        for other in known:
            if compare_digest(token, other):
                return HttpCode.FORBIDDEN
        return HttpCode.UNAUTHENTICATED

    async def _denied(self, send: Send, code: HttpCode) -> None:
        await _send_json(
            send,
            status=_status_for(code),
            payload={"ok": False, "code": code},
            secrets=self._secrets(),
        )

    async def _disable(self, headers: dict[str, str], send: Send) -> None:
        if not self._supervisor:
            await self._denied(send, HttpCode.UNAUTHENTICATED)
            return
        denied = self._classify(_bearer(headers), self._supervisor)
        if denied:
            await self._denied(send, denied)
            return
        self._signer.set_enabled(False)
        await _send_json(
            send,
            status=200,
            payload={"ok": True, "code": HttpCode.OK, "signer_enabled": False},
            secrets=self._secrets(),
        )

    async def _enable(self, headers: dict[str, str], send: Send) -> None:
        if not self._supervisor:
            await self._denied(send, HttpCode.UNAUTHENTICATED)
            return
        denied = self._classify(_bearer(headers), self._supervisor)
        if denied:
            await self._denied(send, denied)
            return
        self._signer.set_enabled(True)
        await _send_json(
            send,
            status=200,
            payload={"ok": True, "code": HttpCode.OK, "signer_enabled": True},
            secrets=self._secrets(),
        )

    async def _sign(self, headers: dict[str, str], receive: Receive, send: Send) -> None:
        denied = self._classify(_bearer(headers), self._signer_token)
        if denied:
            await self._denied(send, denied)
            return
        raw = await _read_body(receive)
        try:
            payload = json.loads(raw.decode("utf-8"))
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
            req = SignRequest.model_validate(payload)
        except ValidationError:
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                secrets=self._secrets(),
            )
            return
        result = await self._signer.sign(req)
        await _send_json(
            send,
            status=_status_for(result.code),
            payload=_result_payload(result),
            secrets=self._secrets(),
        )


def _result_payload(result: SignResult) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    payload["ok"] = result.ok
    return payload


def create_app(
    *,
    signer: SignerBackend,
    signer_token: str,
    debit_token: str,
    model_token: str | None = None,
    control_token: str | None = None,
    supervisor_token: str | None = None,
    policy_token: str | None = None,
    read_token: str | None = None,
    credit_token: str | None = None,
) -> SignerService:
    return SignerService(
        signer=signer,
        signer_token=signer_token,
        debit_token=debit_token,
        model_token=model_token,
        control_token=control_token,
        supervisor_token=supervisor_token,
        policy_token=policy_token,
        read_token=read_token,
        credit_token=credit_token,
    )


def create_app_from_env() -> SignerService:
    signer_token = _read_token("AEA_SIGNER_TOKEN", "AEA_SIGNER_TOKEN_FILE")
    debit_token = _read_token("AEA_WALLET_DEBIT_TOKEN", "AEA_WALLET_DEBIT_TOKEN_FILE")
    if not signer_token or not debit_token:
        raise ValueError("AEA_SIGNER_TOKEN and AEA_WALLET_DEBIT_TOKEN are required")
    hmac_key = _read_token("AEA_SIGNER_HMAC_KEY", "AEA_SIGNER_HMAC_KEY_FILE")
    if not hmac_key:
        raise ValueError("AEA_SIGNER_HMAC_KEY or AEA_SIGNER_HMAC_KEY_FILE is required")
    if hmac_key in {signer_token, debit_token}:
        raise ValueError("HMAC key must be distinct from signer and debit tokens")
    freeze_raw = os.environ.get("AEA_FREEZE_PATH")
    if not freeze_raw:
        raise ValueError("AEA_FREEZE_PATH is required")
    policy_version = os.environ.get("AEA_POLICY_VERSION")
    policy_hash = os.environ.get("AEA_POLICY_HASH")
    if not policy_version or not policy_hash:
        raise ValueError("AEA_POLICY_VERSION and AEA_POLICY_HASH are required")
    phase = os.environ.get("AEA_WALLET_PHASE", "A")
    if phase == "A":
        wallet_url = os.environ.get("AEA_WALLET_URL", WALLET_URL_DEFAULT)
        debit = HttpWalletDebit(wallet_url, debit_token)
        signer: SignerBackend = MockSigner(
            freeze_path=Path(freeze_raw), expected_policy_version=policy_version,
            expected_policy_hash=policy_hash, debit=debit, hmac_key=hmac_key,
        )
    elif phase in {"B", "C"}:
        import asyncio
        from aea.signer.solana import SolanaSigner, load_protected_keypair
        from aea.wallet.solana import SolanaConfig, SolanaWallet
        required = {
            "rpc_url": _read_token("AEA_SOLANA_RPC_URL", "AEA_SOLANA_RPC_URL_FILE"),
            "public_wallet": os.environ.get("AEA_SOLANA_PUBLIC_WALLET"),
            "token_mint": os.environ.get("AEA_SOLANA_TOKEN_MINT"),
            "source_token_account": os.environ.get("AEA_SOLANA_SOURCE_TOKEN_ACCOUNT"),
            "key_file": os.environ.get("AEA_SIGNER_KEY_FILE"),
            "destination_id": os.environ.get("AEA_SOLANA_DESTINATION_ID"),
            "destination_owner": os.environ.get("AEA_SOLANA_DESTINATION_OWNER"),
        }
        if any(not value for value in required.values()):
            raise ValueError("Solana signer configuration is incomplete")
        config = SolanaConfig.model_validate({
            "wallet_phase": phase, "network": os.environ.get("AEA_SOLANA_NETWORK"),
            "rpc_url": required["rpc_url"], "public_wallet": required["public_wallet"],
            "token_mint": required["token_mint"],
            "token_decimals": os.environ.get("AEA_SOLANA_TOKEN_DECIMALS", "6"),
            "source_token_account": required["source_token_account"],
            "commitment": os.environ.get("AEA_SOLANA_COMMITMENT", "confirmed"),
            "confirmation_timeout_seconds": os.environ.get("AEA_SOLANA_CONFIRMATION_TIMEOUT", "60"),
            "rpc_timeout_seconds": os.environ.get("AEA_SOLANA_RPC_TIMEOUT", "15"),
        })
        keypair = load_protected_keypair(str(required["key_file"]))
        rpc = SolanaWallet()
        asyncio.run(rpc.validate(config))
        signer = SolanaSigner(
            freeze_path=Path(freeze_raw), expected_policy_version=policy_version,
            expected_policy_hash=policy_hash, hmac_key=hmac_key, config=config,
            keypair=keypair, rpc=rpc,
            approved_destinations={str(required["destination_id"]): str(required["destination_owner"])},
            live_spend_path=os.environ.get("AEA_LIVE_SPEND_FILE") if phase == "C" else None,
            live_operator_intent=os.environ.get("AEA_LIVE_WALLET") if phase == "C" else None,
        )
    else:
        raise ValueError("wallet phase must be A, B, or C")
    return create_app(
        signer=signer,
        signer_token=signer_token,
        debit_token=debit_token,
        model_token=_read_token("AEA_MODEL_TOKEN", "AEA_MODEL_TOKEN_FILE"),
        control_token=_read_token("AEA_CONTROL_TOKEN", "AEA_CONTROL_TOKEN_FILE"),
        supervisor_token=_read_token("AEA_SUPERVISOR_TOKEN", "AEA_SUPERVISOR_TOKEN_FILE"),
        policy_token=_read_token("AEA_POLICY_TOKEN", "AEA_POLICY_TOKEN_FILE"),
        read_token=_read_token("AEA_WALLET_READ_TOKEN", "AEA_WALLET_READ_TOKEN_FILE"),
        credit_token=None,
    )


def serve_unix(app: SignerService, sock_path: Path | str) -> None:
    import uvicorn

    sock = prepare_unix_socket(sock_path)
    uvicorn.run(app, fd=sock.fileno(), log_level="info")


def main() -> None:
    sock = os.environ.get("AEA_SIGNER_SOCK", SIGNER_SOCK_DEFAULT)
    serve_unix(create_app_from_env(), sock)


if __name__ == "__main__":
    main()
