"""Model-facing control ASGI on 127.0.0.1:18700.

POST /v1/tools/{nine} accepts AEA_MODEL_TOKEN only. Spend tools do not call
the signer or wallet debit (PR10). request_payment returns SIGNER_UNAVAILABLE.
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
from aea.control.auth import authorize_model_tools, bearer_token
from aea.control.freeze import inspect_control_freeze, tool_is_mutating
from aea.control.schemas import TOOL_MODELS
from aea.hashing import canonical_json_hash
from aea.marketplace.mock import MockMarketplace
from aea.marketplace.protocol import MarketplaceAdapter, MarketplaceError
from aea.policy.reasons import HttpCode, ReasonCode
from aea.policy.risk import JobAcceptInput, evaluate_job_accept
from aea.types import format_amount
from aea.workers.registry import run_worker

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
        self._opps: dict[str, dict[str, Any]] = {}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._decisions: list[dict[str, Any]] = []
        self._idem: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        self._payments: list[dict[str, Any]] = []

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
        if tool_is_mutating(name) and inspect_control_freeze(self._freeze_path).frozen:
            await _send_json(
                send,
                status=200,
                payload={"ok": False, "code": HttpCode.AGENT_FROZEN},
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
            result = self._dispatch(name, req)
        except MarketplaceError as exc:
            code = exc.code if exc.code in {HttpCode.NETWORK_FAILURE, HttpCode.NOT_FOUND, HttpCode.CONFLICT} else HttpCode.MARKETPLACE_UNAVAILABLE
            result = {"ok": False, "code": code}
        except Exception:
            result = {"ok": False, "code": HttpCode.INTERNAL_ERROR}
        result.setdefault("ok", result.get("code") == HttpCode.OK)
        result.setdefault("correlation_id", headers.get("x-aea-correlation-id") or str(uuid4()))
        if idem:
            stored = dict(result)
            self._idem[(name, idem)] = (canonical_json_hash(body), stored)
        await _send_json(
            send,
            status=_status_for(str(result.get("code") or HttpCode.OK)),
            payload=result,
            secrets=self._secrets(),
        )

    def _dispatch(self, name: str, req: Any) -> dict[str, Any]:
        return {
            "find_jobs": self._find_jobs,
            "evaluate_job": self._evaluate_job,
            "accept_job": self._accept_job,
            "perform_job": self._perform_job,
            "submit_work": self._submit_work,
            "check_payment": self._check_payment,
            "request_payment": self._request_payment,
            "get_financial_state": self._get_financial_state,
            "record_decision": self._record_decision,
        }[name](req)

    def _find_jobs(self, req: Any) -> dict[str, Any]:
        page = self._marketplace.discover(limit=req.limit, cursor=req.cursor)
        jobs = []
        for item in page.jobs:
            existing = next(
                (o for o in self._opps.values() if o["external_reference"] == item.external_reference),
                None,
            )
            oid = existing["opportunity_id"] if existing else str(uuid4())
            dumped = item.model_dump(mode="json")
            row = {
                "opportunity_id": oid,
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
                "estimated_cost": dumped["estimated_cost"],
                "worker": dumped["worker"],
            }
            self._opps[oid] = row
            jobs.append({k: v for k, v in row.items() if k not in {"estimated_cost", "worker"}})
        return {
            "ok": True,
            "code": HttpCode.OK,
            "adapter": "mock",
            "jobs": jobs,
            "next_cursor": page.next_cursor,
        }

    def _evaluate_job(self, req: Any) -> dict[str, Any]:
        opp = self._opps.get(str(req.opportunity_id))
        if opp is None:
            return {"ok": False, "code": HttpCode.NOT_FOUND}
        revenue = Decimal(str(opp["expected_revenue"]["amount"]))
        cost = Decimal(str(opp["estimated_cost"]["amount"]))
        asset = opp["payment_asset"]
        flags = list(opp.get("flags") or [])
        blockers: list[str] = []
        if "prompt_injection" in flags:
            blockers.append(HttpCode.PROMPT_INJECTION_DETECTED)
        if asset != "USDC":
            blockers.append(ReasonCode.PROHIBITED_TOKEN)
        hist = Decimal("0.90")
        open_jobs = sum(1 for j in self._jobs.values() if j["status"] in {"accepted", "performing", "performed", "submitted"})
        accept = evaluate_job_accept(
            JobAcceptInput.model_validate(
                {
                    "expected_revenue_usdc": format_amount(revenue),
                    "expected_cost_usdc": format_amount(cost),
                    "probability_payment": float(hist),
                    "open_jobs": open_jobs,
                    "frozen": inspect_control_freeze(self._freeze_path).frozen,
                    "asset": "USDC" if asset == "USDC" else "USDC",
                }
            ),
            self._policy.document,
        )
        if asset != "USDC":
            accept = accept.model_copy(
                update={"allowed": False, "reason_code": ReasonCode.PROHIBITED_TOKEN}
            )
        if blockers and HttpCode.PROMPT_INJECTION_DETECTED in blockers:
            accept = accept.model_copy(
                update={"allowed": False, "reason_code": HttpCode.PROMPT_INJECTION_DETECTED}
            )
        margin = revenue - cost
        bps = int((margin / cost) * 10000) if cost > 0 else 0
        rec = "accept" if accept.allowed and not blockers else "decline"
        return {
            "ok": True,
            "code": HttpCode.OK,
            "opportunity_id": str(req.opportunity_id),
            "expected_revenue": opp["expected_revenue"],
            "expected_costs": [
                {"category": "compute", "amount": format_amount(cost), "asset": "USDC"}
            ],
            "expected_cost_total": {"amount": format_amount(cost), "asset": "USDC"},
            "expected_margin": {"amount": format_amount(margin), "asset": "USDC"},
            "expected_margin_bps": bps,
            "probability_completion": 0.95,
            "probability_payment": float(hist),
            "risk_score": 0.12,
            "risk_factors": flags or ["none"],
            "meets_required_margin": accept.meets_required_margin,
            "policy_blockers": blockers,
            "recommendation": rec,
            "accept_allowed": accept.allowed,
            "reason_code": accept.reason_code,
        }

    def _accept_job(self, req: Any) -> dict[str, Any]:
        evaluation = self._evaluate_job(type("R", (), {"opportunity_id": req.opportunity_id})())
        if evaluation.get("code") == HttpCode.NOT_FOUND:
            return evaluation
        opp = self._opps[str(req.opportunity_id)]
        if evaluation.get("policy_blockers"):
            code = evaluation["policy_blockers"][0]
            return {"ok": False, "code": code, "opportunity_id": str(req.opportunity_id)}
        if not evaluation.get("accept_allowed"):
            return {
                "ok": False,
                "code": evaluation.get("reason_code") or ReasonCode.MARGIN_NOT_MET,
                "opportunity_id": str(req.opportunity_id),
            }
        try:
            self._marketplace.accept(
                opp["external_reference"], idempotency_key=req.idempotency_key
            )
        except MarketplaceError as exc:
            return {"ok": False, "code": exc.code}
        job_id = str(uuid4())
        self._jobs[job_id] = {
            "job_id": job_id,
            "opportunity_id": str(req.opportunity_id),
            "external_reference": opp["external_reference"],
            "status": "accepted",
            "deliverable_digest": None,
            "expected_revenue": opp["expected_revenue"],
            "payment_asset": opp["payment_asset"],
        }
        return {
            "ok": True,
            "code": HttpCode.OK,
            "job_id": job_id,
            "opportunity_id": str(req.opportunity_id),
            "status": "accepted",
        }

    def _perform_job(self, req: Any) -> dict[str, Any]:
        job = self._jobs.get(str(req.job_id))
        if job is None:
            return {"ok": False, "code": HttpCode.NOT_FOUND}
        result = run_worker(job["external_reference"])
        job["deliverable_digest"] = result.digest
        job["status"] = "performed" if result.ok else "failed"
        if not result.ok:
            return {
                "ok": False,
                "code": result.reason_code or HttpCode.JOB_FAILED,
                "job_id": job["job_id"],
                "deliverable_digest": result.digest,
            }
        return {
            "ok": True,
            "code": HttpCode.OK,
            "job_id": job["job_id"],
            "status": "performed",
            "deliverable_digest": result.digest,
        }

    def _submit_work(self, req: Any) -> dict[str, Any]:
        job = self._jobs.get(str(req.job_id))
        if job is None:
            return {"ok": False, "code": HttpCode.NOT_FOUND}
        if not job.get("deliverable_digest"):
            return {"ok": False, "code": HttpCode.CONFLICT}
        try:
            submitted = self._marketplace.submit(
                job["external_reference"],
                artefact_digest=job["deliverable_digest"],
                artefact_uri=f"artefacts/{job['deliverable_digest']}",
                idempotency_key=req.idempotency_key,
            )
        except MarketplaceError as exc:
            return {"ok": False, "code": exc.code}
        job["status"] = "submitted"
        return {
            "ok": True,
            "code": HttpCode.OK,
            "job_id": job["job_id"],
            "status": "submitted",
            "transaction_reference": submitted.transaction_reference,
            "credited": submitted.credited,
        }

    def _check_payment(self, req: Any) -> dict[str, Any]:
        job = self._jobs.get(str(req.job_id))
        if job is None:
            return {"ok": False, "code": HttpCode.NOT_FOUND}
        claim = self._marketplace.verify_payment(job["external_reference"])
        dumped = claim.model_dump(mode="json")
        if dumped["status"] != "paid":
            return {
                "ok": True,
                "code": HttpCode.OK,
                "status": dumped["status"],
                "verified": False,
                "transaction_reference": dumped.get("transaction_reference"),
            }
        tx_id = dumped.get("transaction_reference")
        wallet_tx = self._wallet_get_tx(tx_id) if (self._wallet_get_tx and tx_id) else None
        if wallet_tx is None:
            return {
                "ok": False,
                "code": HttpCode.FAKE_PAYMENT,
                "status": "fake",
                "verified": False,
                "transaction_reference": tx_id,
            }
        return {
            "ok": True,
            "code": HttpCode.OK,
            "status": "settled",
            "verified": True,
            "transaction_reference": tx_id,
        }

    def _request_payment(self, req: Any) -> dict[str, Any]:
        job = self._jobs.get(str(req.job_id))
        if job is None:
            return {"ok": False, "code": HttpCode.NOT_FOUND}
        request_id = str(uuid4())
        self._payments.append(
            {
                "request_id": request_id,
                "job_id": str(req.job_id),
                "amount": format_amount(req.amount),
                "asset": req.asset,
                "destination": req.destination,
                "purpose": req.purpose,
                "policy_decision": "pending",
            }
        )
        return {
            "ok": False,
            "code": HttpCode.SIGNER_UNAVAILABLE,
            "request_id": request_id,
            "policy_decision": "pending",
            "reason_code": None,
            "transaction_reference": None,
        }

    def _get_financial_state(self, req: Any) -> dict[str, Any]:
        frozen = inspect_control_freeze(self._freeze_path).frozen
        open_jobs = sum(
            1
            for j in self._jobs.values()
            if j["status"] in {"accepted", "performing", "performed", "submitted"}
        )
        limits = self._policy.document.limits
        return {
            "ok": True,
            "code": HttpCode.OK,
            "agent_id": AGENT_ID,
            "policy_version": self._policy.document.policy_version or POLICY_VERSION,
            "wallet_phase": self._policy.document.wallet_phase,
            "frozen": frozen,
            "signer_enabled": True,
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
            "open_jobs": open_jobs,
            "unit_of_account": "USDC",
            "constitution_version": CONSTITUTION_VERSION,
        }

    def _record_decision(self, req: Any) -> dict[str, Any]:
        row = req.model_dump(mode="json")
        row["decision_id"] = str(uuid4())
        self._decisions.append(row)
        return {
            "ok": True,
            "code": HttpCode.OK,
            "decision_id": row["decision_id"],
            "applied": False,
        }


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
    return create_app(
        model_token=model,
        freeze_path=freeze,
        control_token=_read_token("AEA_CONTROL_TOKEN", "AEA_CONTROL_TOKEN_FILE"),
        marketplace_token=_read_token("AEA_MARKETPLACE_TOKEN", "AEA_MARKETPLACE_TOKEN_FILE"),
    )


def main() -> None:
    import uvicorn

    uvicorn.run(create_app_from_env(), host=CONTROL_HOST, port=CONTROL_PORT, log_level="info")


if __name__ == "__main__":
    main()
