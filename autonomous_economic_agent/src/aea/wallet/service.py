"""Phase A wallet HTTP process. ASGI on 127.0.0.1:18704.

Debit: AEA_WALLET_DEBIT_TOKEN only (signer). Credit: AEA_WALLET_CREDIT_TOKEN
(marketplace/seed). Read: AEA_WALLET_READ_TOKEN. Model token is FORBIDDEN.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from hmac import compare_digest
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from aea.policy.reasons import HttpCode
from aea.types import format_amount, format_asset_amount
from aea.wallet.mock import MockWallet, new_tx_id
from aea.wallet.protocol import (
    WALLET_HOST,
    WALLET_PORT,
    CreditRequest,
    DebitRequest,
    FaultName,
    WalletError,
)

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

_KNOWN_FAULTS: frozenset[str] = frozenset(
    {"none", "insufficient_funds", "network", "timeout", "reject"}
)


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")


async def _read_body(receive: Receive) -> bytes:
    chunks = bytearray()
    more = True
    while more:
        message = await receive()
        chunks.extend(message.get("body", b""))
        more = bool(message.get("more_body"))
    return bytes(chunks)


async def _send_json(send: Send, *, status: int, payload: dict[str, Any]) -> None:
    body = _json_bytes(payload)
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
        "INSUFFICIENT_FUNDS": 200,
        "PROHIBITED_TOKEN": 400,
        "UNSUPPORTED_WALLET_PHASE": 400,
    }.get(code, 400)


class WalletService:
    def __init__(
        self,
        *,
        wallet: MockWallet,
        debit_token: str,
        credit_token: str,
        read_token: str,
        model_token: str | None = None,
        control_token: str | None = None,
        allow_faults: bool = False,
    ) -> None:
        if not debit_token or not credit_token or not read_token:
            raise ValueError("debit, credit, and read tokens are required")
        if len({debit_token, credit_token, read_token}) != 3:
            raise ValueError("debit, credit, and read tokens must be distinct")
        self._wallet = wallet
        self._debit = debit_token
        self._credit = credit_token
        self._read = read_token
        self._model = model_token
        self._control = control_token
        self._allow_faults = allow_faults
        if allow_faults:
            self._wallet.enable_faults()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        headers = _header_map(scope)
        if method == "GET" and path == "/health":
            await _send_json(send, status=200, payload={"ok": True, "code": HttpCode.OK})
            return
        if method == "GET" and path == "/v1/wallet/balances":
            await self._balances(headers, send)
            return
        if method == "GET" and path.startswith("/v1/wallet/tx/"):
            await self._get_tx(path, headers, send)
            return
        if method == "POST" and path == "/v1/wallet/debit":
            await self._mutate("debit", headers, receive, send)
            return
        if method == "POST" and path == "/v1/wallet/credit":
            await self._mutate("credit", headers, receive, send)
            return
        await _send_json(
            send, status=404, payload={"ok": False, "code": HttpCode.NOT_FOUND}
        )

    def _authorize(self, headers: dict[str, str], required: str) -> HttpCode | None:
        token = _bearer(headers)
        if token is None:
            return HttpCode.UNAUTHENTICATED
        if compare_digest(token, required):
            return None
        known = [
            t
            for t in (self._debit, self._credit, self._read, self._model, self._control)
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
        )

    async def _balances(self, headers: dict[str, str], send: Send) -> None:
        denied = self._authorize(headers, self._read)
        if denied:
            await self._denied(send, denied)
            return
        balances = {
            asset: format_amount(amount)
            for asset, amount in self._wallet.get_balances().items()
        }
        await _send_json(
            send,
            status=200,
            payload={"ok": True, "code": HttpCode.OK, "balances": balances},
        )

    async def _get_tx(self, path: str, headers: dict[str, str], send: Send) -> None:
        denied = self._authorize(headers, self._read)
        if denied:
            await self._denied(send, denied)
            return
        tx_id = path.removeprefix("/v1/wallet/tx/")
        tx = self._wallet.get_tx(tx_id)
        if tx is None:
            await _send_json(
                send,
                status=404,
                payload={"ok": False, "code": HttpCode.NOT_FOUND},
            )
            return
        await _send_json(
            send,
            status=200,
            payload={"ok": True, "code": HttpCode.OK, "tx": tx.model_dump(mode="json")},
        )

    async def _mutate(
        self,
        direction: str,
        headers: dict[str, str],
        receive: Receive,
        send: Send,
    ) -> None:
        required = self._debit if direction == "debit" else self._credit
        denied = self._authorize(headers, required)
        if denied:
            await self._denied(send, denied)
            return
        fault = headers.get("x-aea-fault")
        if fault:
            if not self._allow_faults:
                await _send_json(
                    send,
                    status=400,
                    payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                )
                return
            if fault not in _KNOWN_FAULTS:
                await _send_json(
                    send,
                    status=400,
                    payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                )
                return
            self._wallet.set_fault(fault)  # type: ignore[arg-type]
        raw = await _read_body(receive)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
            )
            return
        if not isinstance(payload, dict):
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
            )
            return
        try:
            if direction == "debit":
                req = DebitRequest.model_validate(payload)
                tx_id = req.tx_id or new_tx_id()
                tx = self._wallet.debit(
                    asset=req.asset,
                    amount=req.amount,
                    destination=req.destination,
                    tx_id=tx_id,
                    reason=req.reason,
                    idempotency_key=req.idempotency_key,
                )
            else:
                req = CreditRequest.model_validate(payload)
                tx_id = req.tx_id or new_tx_id()
                tx = self._wallet.credit(
                    asset=req.asset,
                    amount=req.amount,
                    tx_id=tx_id,
                    reason=req.reason,
                    idempotency_key=req.idempotency_key,
                )
        except ValidationError:
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
            )
            return
        except WalletError as exc:
            status = _status_for(exc.code)
            ok = False
            await _send_json(
                send,
                status=status,
                payload={"ok": ok, "code": exc.code, "message": exc.message},
            )
            return
        finally:
            if self._allow_faults:
                self._wallet.set_fault("none")
        await _send_json(
            send,
            status=200,
            payload={
                "ok": True,
                "code": HttpCode.OK,
                "tx": tx.model_dump(mode="json"),
            },
        )


class SolanaReadService:
    """Phase-B/C keyless wallet HTTP boundary: balances and chain evidence only."""

    def __init__(self, *, wallet: Any, config: Any, read_token: str,
                 debit_token: str, credit_token: str,
                 model_token: str | None = None, control_token: str | None = None) -> None:
        self._wallet = wallet
        self._config = config
        self._read = read_token
        self._debit = debit_token
        self._credit = credit_token
        self._model = model_token
        self._control = control_token

    def _authorize(self, headers: dict[str, str]) -> HttpCode | None:
        token = _bearer(headers)
        if token is None:
            return HttpCode.UNAUTHENTICATED
        if compare_digest(token, self._read):
            return None
        if any(compare_digest(token, known) for known in
               (self._debit, self._credit, self._model, self._control) if known):
            return HttpCode.FORBIDDEN
        return HttpCode.UNAUTHENTICATED

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        method, path = scope["method"], scope["path"]
        if method == "GET" and path == "/health":
            await _send_json(send, status=200, payload={"ok": True, "code": HttpCode.OK, "wallet_phase": self._config.wallet_phase})
            return
        if method == "POST" and path in {"/v1/wallet/debit", "/v1/wallet/credit"}:
            # The Phase-B wallet process cannot sign even with Phase-A mutation
            # credentials. Only the isolated signer talks to the transfer RPC path.
            await _send_json(send, status=403, payload={"ok": False, "code": HttpCode.FORBIDDEN})
            return
        denied = self._authorize(_header_map(scope))
        if denied:
            await _send_json(send, status=_status_for(denied), payload={"ok": False, "code": denied})
            return
        if method == "GET" and path == "/v1/wallet/balances":
            try:
                balances = await self._wallet.balances(self._config)
            except Exception:
                await _send_json(send, status=503, payload={"ok": False, "code": HttpCode.NETWORK_FAILURE})
                return
            await _send_json(send, status=200, payload={"ok": True, "code": HttpCode.OK,
                "balances": {k: format_asset_amount(v, k) for k, v in balances.items()},
                "public_wallet": self._config.public_wallet, "network": self._config.network})
            return
        if method == "GET" and path.startswith("/v1/wallet/tx/"):
            signature = path.removeprefix("/v1/wallet/tx/")
            try:
                evidence = await self._wallet.lookup(self._config, signature)
            except Exception:
                await _send_json(send, status=503, payload={"ok": False, "code": HttpCode.NETWORK_FAILURE})
                return
            await _send_json(send, status=200, payload={"ok": True, "code": HttpCode.OK,
                "tx": evidence.model_dump(mode="json")})
            return
        await _send_json(send, status=404, payload={"ok": False, "code": HttpCode.NOT_FOUND})


def create_app(
    *,
    wallet: MockWallet | None = None,
    debit_token: str,
    credit_token: str,
    read_token: str,
    model_token: str | None = None,
    control_token: str | None = None,
    allow_faults: bool = False,
) -> WalletService:
    return WalletService(
        wallet=wallet or MockWallet(phase="A"),
        debit_token=debit_token,
        credit_token=credit_token,
        read_token=read_token,
        model_token=model_token,
        control_token=control_token,
        allow_faults=allow_faults,
    )


def _read_token(env_name: str, file_env: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    path = os.environ.get(file_env)
    if path:
        return Path(path).read_text(encoding="utf-8").rstrip("\n")
    return None


def create_app_from_env() -> WalletService | SolanaReadService:
    debit = _read_token("AEA_WALLET_DEBIT_TOKEN", "AEA_WALLET_DEBIT_TOKEN_FILE")
    credit = _read_token("AEA_WALLET_CREDIT_TOKEN", "AEA_WALLET_CREDIT_TOKEN_FILE")
    read = _read_token("AEA_WALLET_READ_TOKEN", "AEA_WALLET_READ_TOKEN_FILE")
    if not debit or not credit or not read:
        raise ValueError("wallet debit, credit, and read tokens are required")
    phase = os.environ.get("AEA_WALLET_PHASE", "A")
    if phase in {"B", "C"}:
        from aea.wallet.solana import SolanaConfig, SolanaWallet
        config = SolanaConfig.model_validate({
            "wallet_phase": phase, "network": os.environ.get("AEA_SOLANA_NETWORK"),
            "rpc_url": _read_token("AEA_SOLANA_RPC_URL", "AEA_SOLANA_RPC_URL_FILE"),
            "public_wallet": os.environ.get("AEA_SOLANA_PUBLIC_WALLET"),
            "token_mint": os.environ.get("AEA_SOLANA_TOKEN_MINT"),
            "token_decimals": os.environ.get("AEA_SOLANA_TOKEN_DECIMALS", "6"),
            "source_token_account": os.environ.get("AEA_SOLANA_SOURCE_TOKEN_ACCOUNT"),
            "commitment": os.environ.get("AEA_SOLANA_COMMITMENT", "confirmed"),
            "confirmation_timeout_seconds": os.environ.get("AEA_SOLANA_CONFIRMATION_TIMEOUT", "60"),
            "rpc_timeout_seconds": os.environ.get("AEA_SOLANA_RPC_TIMEOUT", "15"),
        })
        return SolanaReadService(wallet=SolanaWallet(), config=config, read_token=read,
            debit_token=debit, credit_token=credit,
            model_token=_read_token("AEA_MODEL_TOKEN", "AEA_MODEL_TOKEN_FILE"),
            control_token=_read_token("AEA_CONTROL_TOKEN", "AEA_CONTROL_TOKEN_FILE"))
    if phase == "E":
        from aea.wallet.evm import EvmConfig, EvmWallet
        config = EvmConfig.model_validate({
            "network": os.environ.get("AEA_EVM_NETWORK"),
            "chain_id": os.environ.get("AEA_EVM_CHAIN_ID"),
            "rpc_url": _read_token("AEA_EVM_RPC_URL", "AEA_EVM_RPC_URL_FILE"),
            "public_wallet": os.environ.get("AEA_EVM_PUBLIC_WALLET"),
            "token_contract": os.environ.get("AEA_EVM_USDC_CONTRACT"),
            "token_decimals": os.environ.get("AEA_EVM_TOKEN_DECIMALS", "6"),
            "confirmations": os.environ.get("AEA_EVM_CONFIRMATIONS", "12"),
            "confirmation_timeout_seconds": os.environ.get("AEA_EVM_CONFIRMATION_TIMEOUT", "120"),
            "rpc_timeout_seconds": os.environ.get("AEA_EVM_RPC_TIMEOUT", "20"),
            "max_gas_limit": os.environ.get("AEA_EVM_MAX_GAS_LIMIT", "100000"),
            "max_fee_per_gas_wei": os.environ.get("AEA_EVM_MAX_FEE_PER_GAS_WEI", "2000000000"),
            "max_priority_fee_per_gas_wei": os.environ.get("AEA_EVM_MAX_PRIORITY_FEE_PER_GAS_WEI", "100000000"),
            "max_total_fee_wei": os.environ.get("AEA_EVM_MAX_TOTAL_FEE_WEI", "200000000000000"),
            "live_spend": False,
        })
        return SolanaReadService(wallet=EvmWallet(), config=config, read_token=read,
            debit_token=debit, credit_token=credit,
            model_token=_read_token("AEA_MODEL_TOKEN", "AEA_MODEL_TOKEN_FILE"),
            control_token=_read_token("AEA_CONTROL_TOKEN", "AEA_CONTROL_TOKEN_FILE"))
    if phase != "A":
        raise ValueError("wallet phase must be A, B, C, or E")
    return create_app(
        debit_token=debit,
        credit_token=credit,
        read_token=read,
        model_token=_read_token("AEA_MODEL_TOKEN", "AEA_MODEL_TOKEN_FILE"),
        control_token=_read_token("AEA_CONTROL_TOKEN", "AEA_CONTROL_TOKEN_FILE"),
        allow_faults=False,
    )


def main() -> None:
    import uvicorn

    uvicorn.run(create_app_from_env(), host=WALLET_HOST, port=WALLET_PORT, log_level="info")


if __name__ == "__main__":
    main()
