"""Model-facing control ASGI on 127.0.0.1:18700.

POST /v1/tools/{nine} accepts AEA_MODEL_TOKEN only. POST /v1/payment-requests
accepts AEA_CONTROL_TOKEN only. GET /observability/status accepts
AEA_OBSERVABILITY_TOKEN only. Control never holds signer HMAC or debit.
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

from aea import AGENT_ID, CALLABLE_MODEL_TOOLS, CONSTITUTION_VERSION, POLICY_VERSION
from aea.config import LoadedPolicy, load_policy
from aea.control.auth import (
    authorize_control_only,
    authorize_model_tools,
    authorize_observability,
    bearer_token,
)
from aea.control.freeze import inspect_control_safety, tool_is_mutating
from aea.control.idempotency import should_store_idempotent_result
from aea.control.plane import EconomicPlane
from aea.control.schemas import TOOL_MODELS, RequestPaymentRequest
from aea.hashing import canonical_json_hash
from aea.ledger.models import AuditWrite
from aea.ledger.service import LedgerService
from aea.marketplace.mock import MockMarketplace
from aea.marketplace.engagement import EconomicEngagementService
from aea.marketplace.protocol import MarketplaceAdapter, MarketplaceError
from aea.research.readonly import ReadOnlyWebService
from aea.payment.service import PaymentOrchestrator
from aea.policy.reasons import HttpCode, ReasonCode
from aea.types import format_amount

CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 18700

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

WalletTxLookup = Callable[[str], Any]


def _normalise_wallet_balances(body: Any) -> dict[str, Any]:
    """Keep every supported rail asset; discard response metadata."""
    from decimal import Decimal

    balances = body.get("balances") if isinstance(body, dict) else None
    if not isinstance(balances, dict):
        balances = body if isinstance(body, dict) else {}
    return {
        key: Decimal(str(value))
        for key, value in balances.items()
        if key in {"USDC", "SOL", "ETH"}
    }


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")


def _scrub(payload: Any, *, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(payload, list):
        return [_scrub(item, secrets=secrets) for item in payload]
    if not isinstance(payload, dict):
        if isinstance(payload, str) and payload in secrets:
            return "[redacted]"
        return payload
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
        out[key] = _scrub(value, secrets=secrets)
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
        HttpCode.AGENT_RISK_VETO: 200,
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
        observability_token: str | None = None,
        wallet_get_tx: WalletTxLookup | None = None,
        state_reader: Callable[[], Any] | None = None,
        ledger: LedgerService | None = None,
        payment: PaymentOrchestrator | None = None,
        wallet_balances: Callable[[], Any] | None = None,
        wallet_status: Callable[[], Any] | None = None,
        extra_wallet_status: tuple[Callable[[], Any], ...] = (),
        supervisor_status: Callable[[], Any] | None = None,
        live_gate: Any | None = None,
        configured_solana: dict[str, Any] | None = None,
        configured_evm: dict[str, Any] | None = None,
        discover_contexts: bool = False,
        engagement: EconomicEngagementService | None = None,
        web_research: ReadOnlyWebService | None = None,
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
        self._observability = observability_token
        self._freeze_path = freeze_path
        self._marketplace = marketplace
        self._policy = policy
        self._wallet_get_tx = wallet_get_tx
        self._state_reader = state_reader
        self._ledger = ledger
        self._payment = payment
        self._wallet_balances = wallet_balances
        self._wallet_status = wallet_status
        self._extra_wallet_status = extra_wallet_status
        self._supervisor_status = supervisor_status
        self._live_gate = live_gate
        self._configured_solana = configured_solana or {}
        self._configured_evm = configured_evm or {}
        self._discover_contexts = discover_contexts
        self._engagement = engagement or EconomicEngagementService()
        self._web = web_research or ReadOnlyWebService()
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
                self._observability,
            )
            if t
        )

    def _known_rejected(self) -> tuple[str, ...]:
        return tuple(
            t
            for t in (
                self._control,
                self._supervisor,
                self._credit,
                self._marketplace_token,
                self._observability,
            )
            if t
        )

    def _observability_rejected(self) -> tuple[str, ...]:
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

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        headers = _header_map(scope)
        if method == "GET" and path == "/health":
            await _send_json(send, status=200, payload={"ok": True, "code": HttpCode.OK})
            return
        if path == "/observability/status":
            if method != "GET":
                await _send_json(
                    send,
                    status=405,
                    payload={"ok": False, "code": HttpCode.NOT_FOUND},
                    secrets=self._secrets(),
                )
                return
            await self._observability_status(headers, send)
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

    async def _observability_status(self, headers: dict[str, str], send: Send) -> None:
        denied = authorize_observability(
            bearer_token(headers),
            observability_token=self._observability or "",
            known_rejected=self._observability_rejected(),
        )
        if denied:
            await _send_json(
                send,
                status=_status_for(denied),
                payload={"ok": False, "code": denied},
                secrets=self._secrets(),
            )
            return
        from aea.observability.sanitize import serialize_status
        from aea.observability.service import ObservabilityCollector

        collector = ObservabilityCollector(
            policy=self._policy,
            ledger=self._ledger,
            safety=self._safety(),
            wallet_status=self._wallet_status,
            extra_wallet_status=self._extra_wallet_status,
            supervisor_status=self._supervisor_status,
            live_gate=self._live_gate,
            configured_solana=self._configured_solana,
            configured_evm=self._configured_evm,
            discover_contexts=self._discover_contexts,
            secrets=self._secrets(),
        )
        status = collector.snapshot()
        payload = serialize_status(status, secrets=self._secrets())
        await _send_json(send, status=200, payload=payload, secrets=self._secrets())

    async def _tool(
        self,
        name: str,
        headers: dict[str, str],
        receive: Receive,
        send: Send,
    ) -> None:
        if name not in CALLABLE_MODEL_TOOLS:
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
            preserved = {
                HttpCode.NETWORK_FAILURE,
                HttpCode.NOT_FOUND,
                HttpCode.CONFLICT,
                HttpCode.FORBIDDEN,
                HttpCode.VALIDATION_ERROR,
                HttpCode.PROMPT_INJECTION_DETECTED,
                HttpCode.POLICY_REJECTED,
                HttpCode.TIMEOUT,
                HttpCode.MARKETPLACE_UNAVAILABLE,
                HttpCode.AGENT_RISK_VETO,
            }
            code = exc.code if exc.code in preserved else HttpCode.MARKETPLACE_UNAVAILABLE
            result = {"ok": False, "code": code}
            if exc.message and exc.message != exc.code:
                result["detail"] = exc.message
        except Exception:
            result = {"ok": False, "code": HttpCode.INTERNAL_ERROR}
        result.setdefault("ok", result.get("code") == HttpCode.OK)
        result.setdefault("correlation_id", headers.get("x-aea-correlation-id") or str(uuid4()))
        if self._ledger is not None and self._auto_commit:
            if str(result.get("code")) == HttpCode.INTERNAL_ERROR:
                self._ledger.rollback()
            else:
                self._ledger.commit()
        if idem and should_store_idempotent_result(result.get("code")):
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

    def _audit_engagement(self, event_type: str, result: dict[str, Any], correlation_id: str) -> None:
        if self._ledger is None:
            return
        payload = {
            "agent_id": AGENT_ID,
            "action": event_type,
            "result": result.get("code"),
            "counterparty_id": result.get("counterparty_id"),
            "conversation_id": result.get("conversation_id"),
            "message_id": result.get("message_id"),
            "offer_id": result.get("offer_id"),
            "intent": result.get("intent"),
            "channel": result.get("channel"),
            "marketplace": result.get("marketplace") or result.get("source"),
            "economic_context": {
                "non_binding": result.get("non_binding", True),
                "paid_subcontracting": result.get("paid_subcontracting", False),
            },
        }
        self._ledger.write_audit(
            AuditWrite.model_validate(
                {
                    "event_type": event_type,
                    "correlation_id": correlation_id,
                    "payload": payload,
                }
            )
        )

    def _dispatch(self, name: str, req: Any, *, correlation_id: str) -> dict[str, Any]:
        if name == "research_opportunities":
            return self._engagement.research_opportunities(query=req.query, limit=req.limit)
        if name == "discover_counterparties":
            return self._engagement.discover_counterparties(query=req.query, limit=req.limit)
        if name == "get_counterparty_profile":
            return self._engagement.get_counterparty_profile(counterparty_id=req.counterparty_id)
        if name == "get_market_status":
            return self._engagement.get_market_status(marketplace=req.marketplace)
        if name == "read_messages":
            return self._engagement.read_messages(
                counterparty_id=req.counterparty_id,
                conversation_id=req.conversation_id,
                limit=req.limit,
            )
        if name == "list_active_conversations":
            return self._engagement.list_active_conversations(limit=req.limit)
        if name == "send_message":
            result = self._engagement.send_message(
                counterparty_id=req.counterparty_id,
                channel=req.channel,
                intent=req.intent,
                message=req.message,
                idempotency_key=req.idempotency_key,
            )
            self._audit_engagement("bounded_message_sent", result, correlation_id)
            return result
        if name == "follow_up_message":
            result = self._engagement.follow_up_message(
                conversation_id=req.conversation_id,
                message=req.message,
                idempotency_key=req.idempotency_key,
            )
            self._audit_engagement("follow_up_sent", result, correlation_id)
            return result
        if name == "propose_collaboration":
            result = self._engagement.propose_collaboration(
                counterparty_id=req.counterparty_id,
                channel=req.channel,
                proposal=req.proposal,
                idempotency_key=req.idempotency_key,
            )
            self._audit_engagement("collaboration_proposed", result, correlation_id)
            return result
        if name == "post_service_offer":
            result = self._engagement.post_service_offer(
                marketplace=req.marketplace,
                service_id=req.service_id,
                idempotency_key=req.idempotency_key,
            )
            self._audit_engagement("service_offer_posted", result, correlation_id)
            return result
        if name == "web_search":
            return self._web.web_search(query=req.query, limit=req.limit)
        if name == "web_extract":
            return self._web.web_extract(url=req.url)
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
    observability_token: str | None = None,
    state_reader: Callable[[], Any] | None = None,
    ledger: LedgerService | None = None,
    payment: PaymentOrchestrator | None = None,
    wallet_balances: Callable[[], Any] | None = None,
    wallet_status: Callable[[], Any] | None = None,
    extra_wallet_status: tuple[Callable[[], Any], ...] = (),
    supervisor_status: Callable[[], Any] | None = None,
    live_gate: Any | None = None,
    configured_solana: dict[str, Any] | None = None,
    configured_evm: dict[str, Any] | None = None,
    discover_contexts: bool = False,
    engagement: EconomicEngagementService | None = None,
    web_research: ReadOnlyWebService | None = None,
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
        observability_token=observability_token,
        wallet_get_tx=wallet_get_tx,
        state_reader=state_reader,
        ledger=ledger,
        payment=payment,
        wallet_balances=wallet_balances,
        wallet_status=wallet_status,
        extra_wallet_status=extra_wallet_status,
        supervisor_status=supervisor_status,
        live_gate=live_gate,
        configured_solana=configured_solana,
        configured_evm=configured_evm,
        discover_contexts=discover_contexts,
        engagement=engagement,
        web_research=web_research,
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

    loaded_policy = load_policy()
    if loaded_policy.document.wallet_phase == "C" and os.environ.get("AEA_LIVE_WALLET") != "1":
        raise ValueError("Phase C Control requires explicit AEA_LIVE_WALLET=1 operator intent")
    ledger = LedgerService.from_env(policy=loaded_policy)
    payment = None
    policy_url = os.environ.get("AEA_POLICY_URL")
    wallet_url = os.environ.get("AEA_WALLET_URL", "http://127.0.0.1:18704")
    read_token = _read_token("AEA_WALLET_READ_TOKEN", "AEA_WALLET_READ_TOKEN_FILE")
    market_url = os.environ.get("AEA_MARKETPLACE_URL")
    market_token = _read_token("AEA_MARKETPLACE_TOKEN", "AEA_MARKETPLACE_TOKEN_FILE")

    def _wallet_balances() -> dict:
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
        return _normalise_wallet_balances(body)

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
            policy=loaded_policy,
            policy_execute=policy_execute_via_http(policy_url, control),
            wallet_balances=_wallet_balances,
            control_token=control,
        )
    observability = _read_token("AEA_OBSERVABILITY_TOKEN", "AEA_OBSERVABILITY_TOKEN_FILE")
    supervisor_url = os.environ.get("AEA_SUPERVISOR_URL", "http://127.0.0.1:18703")

    def _wallet_status() -> dict[str, Any]:
        import httpx

        if not read_token:
            return {"ok": False, "unavailable": True}
        try:
            response = httpx.get(
                wallet_url.rstrip("/") + "/v1/wallet/balances",
                headers={"Authorization": f"Bearer {read_token}"},
                timeout=3.0,
            )
            body = response.json()
        except Exception:
            return {"ok": False, "unavailable": True}
        if not isinstance(body, dict):
            return {"ok": False, "unavailable": True}
        balances = _normalise_wallet_balances(body)
        return {
            "ok": bool(body.get("ok", True)),
            "balances": {k: str(v) for k, v in balances.items()},
            "public_wallet": body.get("public_wallet"),
            "network": body.get("network"),
            "chain_id": body.get("chain_id"),
            "token_contract": body.get("token_contract") or body.get("token_mint"),
        }

    extra_status: list[Callable[[], Any]] = []
    extra_url = os.environ.get("AEA_EVM_WALLET_URL") or os.environ.get("AEA_SOLANA_WALLET_URL")
    if extra_url and extra_url.rstrip("/") != wallet_url.rstrip("/"):

        def _extra_wallet_status(url: str = extra_url) -> dict[str, Any]:
            import httpx

            if not read_token:
                return {"ok": False, "unavailable": True}
            try:
                response = httpx.get(
                    url.rstrip("/") + "/v1/wallet/balances",
                    headers={"Authorization": f"Bearer {read_token}"},
                    timeout=3.0,
                )
                body = response.json()
            except Exception:
                return {"ok": False, "unavailable": True}
            if not isinstance(body, dict):
                return {"ok": False, "unavailable": True}
            balances = _normalise_wallet_balances(body)
            return {
                "ok": bool(body.get("ok", True)),
                "balances": {k: str(v) for k, v in balances.items()},
                "public_wallet": body.get("public_wallet"),
                "network": body.get("network"),
                "chain_id": body.get("chain_id"),
                "token_contract": body.get("token_contract") or body.get("token_mint"),
            }

        extra_status.append(_extra_wallet_status)

    def _supervisor_status() -> dict[str, Any] | None:
        import httpx

        try:
            response = httpx.get(supervisor_url.rstrip("/") + "/v1/status", timeout=2.0)
            body = response.json()
        except Exception:
            return None
        return body if isinstance(body, dict) else None

    from aea.signer.live_gate import inspect_live_spend_gate

    live_gate = inspect_live_spend_gate(
        os.environ.get("AEA_LIVE_SPEND_FILE"),
        operator_intent=os.environ.get("AEA_LIVE_WALLET"),
    )

    from aea.observability.identity import evm_owner_wallet, solana_owner_wallet

    sol_mint = os.environ.get("AEA_SOLANA_TOKEN_MINT")
    configured_solana = {
        "network": os.environ.get("AEA_SOLANA_NETWORK"),
        "public_wallet": solana_owner_wallet(
            public_wallet=os.environ.get("AEA_SOLANA_PUBLIC_WALLET"),
            token_mint=sol_mint,
        ),
        "token_mint": sol_mint,
    }
    configured_solana = {k: v for k, v in configured_solana.items() if v}
    evm_token = os.environ.get("AEA_EVM_USDC_CONTRACT")
    configured_evm = {
        "network": os.environ.get("AEA_EVM_NETWORK"),
        "public_wallet": evm_owner_wallet(
            public_wallet=os.environ.get("AEA_EVM_PUBLIC_WALLET"),
            token_contract=evm_token,
        ),
        "token_contract": evm_token,
        "chain_id": os.environ.get("AEA_EVM_CHAIN_ID"),
    }
    if configured_evm.get("chain_id"):
        try:
            configured_evm["chain_id"] = int(configured_evm["chain_id"])
        except (TypeError, ValueError):
            configured_evm.pop("chain_id", None)
    configured_evm = {k: v for k, v in configured_evm.items() if v}

    from aea.marketplace.transport import default_bounded_transports

    return create_app(
        model_token=model,
        freeze_path=freeze,
        control_token=control,
        marketplace=marketplace,
        marketplace_token=market_token,
        observability_token=observability,
        ledger=ledger,
        payment=payment,
        wallet_get_tx=_wallet_tx,
        wallet_balances=_wallet_balances,
        wallet_status=_wallet_status,
        extra_wallet_status=tuple(extra_status),
        supervisor_status=_supervisor_status,
        live_gate=live_gate,
        configured_solana=configured_solana,
        configured_evm=configured_evm,
        discover_contexts=True,
        engagement=EconomicEngagementService(transports=default_bounded_transports()),
    )


def main() -> None:
    import uvicorn

    uvicorn.run(create_app_from_env(), host=CONTROL_HOST, port=CONTROL_PORT, log_level="info")


if __name__ == "__main__":
    main()
