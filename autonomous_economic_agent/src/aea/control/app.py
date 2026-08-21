"""Model-facing control ASGI on 127.0.0.1:18700.

POST /v1/tools/{nine} accepts AEA_MODEL_TOKEN only. POST /v1/payment-requests
accepts AEA_CONTROL_TOKEN only. Control never holds signer HMAC or debit.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError

from aea import AGENT_ID, CONSTITUTION_VERSION, NINE_TOOLS, POLICY_VERSION
from aea.config import LoadedPolicy, load_policy
from aea.control.auth import authorize_control_only, authorize_model_tools, bearer_token
from aea.control.freeze import inspect_control_safety, tool_is_mutating
from aea.control.plane import EconomicPlane
from aea.control.schemas import TOOL_MODELS, RequestPaymentRequest
from aea.hashing import canonical_json_hash
from aea.ledger.service import LedgerService
from aea.marketplace.mock import MockMarketplace
from aea.marketplace.protocol import MarketplaceAdapter, MarketplaceError
from aea.payment.service import PaymentOrchestrator
from aea.policy.reasons import HttpCode, ReasonCode
from aea.types import format_amount

CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 18700

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

WalletTxLookup = Callable[[str], Any]


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")


def _scrub(payload: dict[str, Any], *, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    blocked = {s.lower() for s in secrets}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        low = key.lower()
        if any(p in low for p in ("token", "secret", "password", "hmac", "authorization", "bearer")):
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
        HttpCode.SIGNER_UNAVAILABLE: 200,
        HttpCode.AGENT_FROZEN: 200,
        HttpCode.FAKE_PAYMENT: 200,
        HttpCode.PROMPT_INJECTION_DETECTED: 200,
        HttpCode.JOB_FAILED: 200,
        HttpCode.RUNAWAY_COST: 200,
        HttpCode.SIGNER_DISABLED: 200,
        HttpCode.LOOP_STOPPED: 200,
        HttpCode.POLICY_REJECTED: 200,
        HttpCode.DUPLICATE_PAYMENT: 200,
        HttpCode.TIMEOUT: 200,
        HttpCode.WALLET_LEDGER_MISMATCH: 200,
        ReasonCode.MARGIN_NOT_MET: 200,
        ReasonCode.PROHIBITED_TOKEN: 200,
        ReasonCode.OPEN_JOBS_EXCEEDED: 200,
    }.get(code, 200)


class ControlService:
    """ASGI app for model-scoped economic tools."""

    def __init__(
        self,
        *,
        model_token: str,
        freeze_path: Path | str | None,
        marketplace: MarketplaceAdapter,
        policy: LoadedPolicy,
        control_token: str | None = None,
        supervisor_token: str | None = None,
        signer_token: str | None = None,
        hmac_key: str | None = None,
        debit_token: str | None = None,
        credit_token: str | None = None,
        marketplace_token: str | None = None,
        wallet_get_tx: WalletTxLookup | None = None,
        state_reader: Callable[[], Any] | None = None,
        ledger: LedgerService | None = None,
        payment: PaymentOrchestrator | None = None,
        wallet_balances: Callable[[], Any] | None = None,
        auto_commit: bool = True,
    ) -> None:
        if not model_token:
            raise ValueError("model_token is required")
        if debit_token or signer_token or hmac_key:
            raise ValueError("control tools facade must not hold debit/signer/hmac credentials")
        self._model = model_token
        self._control = control_token
        self._supervisor = supervisor_token
        self._credit = credit_token
        self._marketplace_token = marketplace_token
        self._freeze_path = freeze_path
        self._marketplace = marketplace
        self._policy = policy
        self._wallet_get_tx = wallet_get_tx
        self._state_reader = state_reader
        self._ledger = ledger
        self._payment = payment
        self._wallet_balances = wallet_balances
        self._auto_commit = auto_commit
        self._idem: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        self._plane = None
        if ledger is not None:
            self._plane = EconomicPlane(
                ledger=ledger,
                marketplace=marketplace,
                policy=policy,
                safety=self._safety,
                payment=payment,
                wallet_get_tx=wallet_get_tx,
                wallet_balances=wallet_balances,
            )

    def _secrets(self) -> tuple[str, ...]:
        return tuple(
            t
            for t in (
                self._model,
                self._control,
                self._supervisor,
                self._credit,
                self._marketplace_token,
            )
            if t
        )

    def _known_rejected(self) -> tuple[str, ...]:
        return tuple(
            t
            for t in (self._control, self._supervisor, self._credit, self._marketplace_token)
            if t
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        headers = _header_map(scope)
        if method == "GET" and path == "/health":
            await _send_json(send, status=200, payload={"ok": True, "code": HttpCode.OK})
            return
        if method == "POST" and path.startswith("/v1/tools/"):
            name = path.removeprefix("/v1/tools/")
            await self._tool(name, headers, receive, send)
            return
        if method == "POST" and path == "/v1/payment-requests":
            await self._payment_requests(headers, receive, send)
            return
        await _send_json(
            send,
            status=404,
            payload={"ok": False, "code": HttpCode.NOT_FOUND},
            secrets=self._secrets(),
        )

    async def _tool(
        self,
        name: str,
        headers: dict[str, str],
        receive: Receive,
        send: Send,
    ) -> None:
        if name not in NINE_TOOLS:
            await _send_json(
                send,
                status=404,
                payload={"ok": False, "code": HttpCode.NOT_FOUND},
                secrets=self._secrets(),
            )
            return
        denied = authorize_model_tools(
            bearer_token(headers),
            model_token=self._model,
            known_rejected=self._known_rejected(),
        )
        if denied:
            await _send_json(
                send,
                status=_status_for(denied),
                payload={"ok": False, "code": denied},
                secrets=self._secrets(),
            )
            return
        raw = await _read_body(receive)
        if not raw:
            payload: Any = {}
        else:
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
            req = TOOL_MODELS[name].model_validate(payload)
        except ValidationError:
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                secrets=self._secrets(),
            )
            return
        safety = self._safety()
        if tool_is_mutating(name) and safety.frozen:
            await _send_json(
                send,
                status=200,
                payload={"ok": False, "code": HttpCode.AGENT_FROZEN},
                secrets=self._secrets(),
            )
            return
        if tool_is_mutating(name) and not safety.loop_enabled:
            await _send_json(
                send,
                status=200,
                payload={"ok": False, "code": HttpCode.LOOP_STOPPED},
                secrets=self._secrets(),
            )
            return
        body = req.model_dump(mode="json")
        idem = body.get("idempotency_key")
        if idem:
            digest = canonical_json_hash(body)
            prior = self._idem.get((name, idem))
            if prior is not None:
                if prior[0] != digest:
                    await _send_json(
                        send,
                        status=409,
                        payload={"ok": False, "code": HttpCode.IDEMPOTENCY_CONFLICT},
                        secrets=self._secrets(),
                    )
                    return
                replay = dict(prior[1])
                replay["code"] = HttpCode.IDEMPOTENT_REPLAY
                await _send_json(
                    send, status=200, payload=replay, secrets=self._secrets()
                )
                return
        try:
            result = self._dispatch(name, req, correlation_id=headers.get("x-aea-correlation-id") or str(uuid4()))
        except MarketplaceError as exc:
            code = exc.code if exc.code in {HttpCode.NETWORK_FAILURE, HttpCode.NOT_FOUND, HttpCode.CONFLICT} else HttpCode.MARKETPLACE_UNAVAILABLE
            result = {"ok": False, "code": code}
        except Exception:
            result = {"ok": False, "code": HttpCode.INTERNAL_ERROR}
        result.setdefault("ok", result.get("code") == HttpCode.OK)
        result.setdefault("correlation_id", headers.get("x-aea-correlation-id") or str(uuid4()))
        if self._ledger is not None and self._auto_commit:
            if str(result.get("code")) == HttpCode.INTERNAL_ERROR:
                self._ledger.rollback()
            else:
                self._ledger.commit()
        if idem:
            stored = dict(result)
            self._idem[(name, idem)] = (canonical_json_hash(body), stored)
        await _send_json(
            send,
            status=_status_for(str(result.get("code") or HttpCode.OK)),
            payload=result,
            secrets=self._secrets(),
        )

    def _safety(self):
        db_kw: dict[str, Any] = {}
        if self._state_reader is not None:
            try:
                snap = self._state_reader()
            except Exception:
                snap = None
            if not isinstance(snap, dict):
                db_kw = {
                    "db_frozen": None,
                    "db_signer_enabled": None,
                    "db_loop_enabled": None,
                }
            else:
                db_kw = {
                    "db_frozen": snap.get("frozen"),
                    "db_signer_enabled": snap.get("signer_enabled"),
                    "db_loop_enabled": snap.get("loop_enabled"),
                }
        return inspect_control_safety(self._freeze_path, **db_kw)

    def _dispatch(self, name: str, req: Any, *, correlation_id: str) -> dict[str, Any]:
        if self._plane is not None:
            return self._plane.dispatch(name, req, correlation_id=correlation_id)
        if name == "get_financial_state":
            return self._snapshot_without_ledger()
        if name == "find_jobs":
            page = self._marketplace.discover(limit=req.limit, cursor=req.cursor)
            jobs = []
            for item in page.jobs:
                dumped = item.model_dump(mode="json")
                jobs.append(
                    {
                        "opportunity_id": str(uuid4()),
                        "external_reference": dumped["external_reference"],
                        "title": dumped["title"],
                        "description_hash": dumped["description_hash"],
                        "untrusted_description_preview": dumped["untrusted_description_preview"],
                        "expected_revenue": dumped["expected_revenue"],
                        "payment_asset": dumped["payment_asset"],
                        "payment_terms": dumped["payment_terms"],
                        "counterparty_id": dumped["counterparty_id"],
                        "counterparty_reputation": dumped["counterparty_reputation"],
                        "flags": dumped["flags"],
                    }
                )
            return {
                "ok": True,
                "code": HttpCode.OK,
                "adapter": "mock",
                "jobs": jobs,
                "next_cursor": page.next_cursor,
            }
        if name == "record_decision":
            return {"ok": True, "code": HttpCode.OK, "decision_id": str(uuid4()), "applied": False}
        return {"ok": False, "code": HttpCode.INTERNAL_ERROR}

    def _snapshot_without_ledger(self) -> dict[str, Any]:
        safety = self._safety()
        limits = self._policy.document.limits
        return {
            "ok": True,
            "code": HttpCode.OK,
            "agent_id": AGENT_ID,
            "policy_version": self._policy.document.policy_version or POLICY_VERSION,
            "wallet_phase": self._policy.document.wallet_phase,
            "frozen": safety.frozen,
            "signer_enabled": safety.signer_enabled,
            "loop_enabled": safety.loop_enabled,
            "balances": {"USDC": "20.000000", "SOL": "0.050000"},
            "opening_usdc": "20.000000",
            "realised_pnl_usdc": "0.000000",
            "revenue_usdc": "0.000000",
            "cost_usdc": "0.000000",
            "daily_spend_usdc": "0.000000",
            "daily_remaining_usdc": format_amount(limits.max_daily_discretionary_usdc),
            "capital_at_risk_usdc": "0.000000",
            "capital_at_risk_remaining_usdc": format_amount(limits.max_capital_at_risk_usdc),
            "max_outbound_usdc": format_amount(limits.max_outbound_usdc),
            "open_jobs": 0,
            "unit_of_account": "USDC",
            "constitution_version": CONSTITUTION_VERSION,
        }

    async def _payment_requests(self, headers: dict[str, str], receive: Receive, send: Send) -> None:
        denied = authorize_control_only(
            bearer_token(headers),
            control_token=self._control or "",
            known_rejected=tuple(
                t for t in (self._model, self._supervisor, self._credit, self._marketplace_token) if t
            ),
        )
        if denied:
            await _send_json(
                send,
                status=_status_for(denied),
                payload={"ok": False, "code": denied},
                secrets=self._secrets(),
            )
            return
        raw = await _read_body(receive)
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                secrets=self._secrets(),
            )
            return
        try:
            req = RequestPaymentRequest.model_validate(payload)
        except ValidationError:
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                secrets=self._secrets(),
            )
            return
        if self._plane is None:
            await _send_json(
                send,
                status=200,
                payload={"ok": False, "code": HttpCode.SIGNER_UNAVAILABLE},
                secrets=self._secrets(),
            )
            return
        result = self._plane.request_payment(
            req, correlation_id=headers.get("x-aea-correlation-id") or str(uuid4())
        )
        result.setdefault("ok", result.get("code") == HttpCode.OK)
        if self._ledger is not None and self._auto_commit:
            if str(result.get("code")) == HttpCode.INTERNAL_ERROR:
                self._ledger.rollback()
            else:
                self._ledger.commit()
        await _send_json(
            send,
            status=_status_for(str(result.get("code") or HttpCode.OK)),
            payload=result,
            secrets=self._secrets(),
        )

def create_app(
    *,
    model_token: str,
    freeze_path: Path | str | None,
    marketplace: MarketplaceAdapter | None = None,
    policy: LoadedPolicy | None = None,
    control_token: str | None = None,
    wallet_get_tx: WalletTxLookup | None = None,
    supervisor_token: str | None = None,
    credit_token: str | None = None,
    marketplace_token: str | None = None,
    state_reader: Callable[[], Any] | None = None,
    ledger: LedgerService | None = None,
    payment: PaymentOrchestrator | None = None,
    wallet_balances: Callable[[], Any] | None = None,
    auto_commit: bool = True,
    hmac_key: str | None = None,
    debit_token: str | None = None,
    signer_token: str | None = None,
) -> ControlService:
    return ControlService(
        model_token=model_token,
        freeze_path=freeze_path,
        marketplace=marketplace or MockMarketplace(),
        policy=policy or load_policy(),
        control_token=control_token,
        supervisor_token=supervisor_token,
        credit_token=credit_token,
        marketplace_token=marketplace_token,
        wallet_get_tx=wallet_get_tx,
        state_reader=state_reader,
        ledger=ledger,
        payment=payment,
        wallet_balances=wallet_balances,
        auto_commit=auto_commit,
        hmac_key=hmac_key,
        debit_token=debit_token,
        signer_token=signer_token,
    )


def _read_token(env_name: str, file_env: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    path = os.environ.get(file_env)
    if path:
        return Path(path).read_text(encoding="utf-8").rstrip("\n")
    return None


def create_app_from_env() -> ControlService:
    model = _read_token("AEA_MODEL_TOKEN", "AEA_MODEL_TOKEN_FILE")
    if not model:
        raise ValueError("AEA_MODEL_TOKEN is required to verify inbound tool calls")
    freeze = os.environ.get("AEA_FREEZE_PATH")
    if not freeze:
        raise ValueError("AEA_FREEZE_PATH is required")
    control = _read_token("AEA_CONTROL_TOKEN", "AEA_CONTROL_TOKEN_FILE")
    from aea.ledger.service import LedgerService
    from aea.payment.service import policy_execute_via_http

    ledger = LedgerService.from_env()
    payment = None
    policy_url = os.environ.get("AEA_POLICY_URL")
    wallet_url = os.environ.get("AEA_WALLET_URL", "http://127.0.0.1:18704")
    read_token = _read_token("AEA_WALLET_READ_TOKEN", "AEA_WALLET_READ_TOKEN_FILE")
    market_url = os.environ.get("AEA_MARKETPLACE_URL")
    market_token = _read_token("AEA_MARKETPLACE_TOKEN", "AEA_MARKETPLACE_TOKEN_FILE")

    def _wallet_balances() -> dict:
        from decimal import Decimal

        import httpx

        if not read_token:
            return {}
        try:
            response = httpx.get(
                wallet_url.rstrip("/") + "/v1/wallet/balances",
                headers={"Authorization": f"Bearer {read_token}"},
                timeout=10.0,
            )
            body = response.json()
        except Exception:
            return {}
        bals = body.get("balances") if isinstance(body, dict) else None
        if not isinstance(bals, dict):
            bals = body if isinstance(body, dict) else {}
        out = {}
        for key, value in bals.items():
            if key in {"USDC", "SOL"}:
                out[key] = Decimal(str(value))
        return out

    def _wallet_tx(tx_id: str):
        import httpx

        if not read_token:
            return None
        try:
            response = httpx.get(
                wallet_url.rstrip("/") + f"/v1/wallet/tx/{tx_id}",
                headers={"Authorization": f"Bearer {read_token}"},
                timeout=10.0,
            )
            body = response.json()
        except Exception:
            return None
        return body.get("tx") if isinstance(body, dict) else None

    marketplace = None
    if market_url and market_token:
        from aea.marketplace.client import HttpMarketplace

        marketplace = HttpMarketplace(market_url, market_token)
    if control and policy_url:
        payment = PaymentOrchestrator(
            ledger=ledger,
            policy=load_policy(),
            policy_execute=policy_execute_via_http(policy_url, control),
            wallet_balances=_wallet_balances,
            control_token=control,
        )
    return create_app(
        model_token=model,
        freeze_path=freeze,
        control_token=control,
        marketplace=marketplace,
        marketplace_token=market_token,
        ledger=ledger,
        payment=payment,
        wallet_get_tx=_wallet_tx,
        wallet_balances=_wallet_balances,
    )


def main() -> None:
    import uvicorn

    uvicorn.run(create_app_from_env(), host=CONTROL_HOST, port=CONTROL_PORT, log_level="info")


if __name__ == "__main__":
    main()
