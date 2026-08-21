"""Outbound payment orchestration.

Control inserts a pending payment_request, asks policy to evaluate (and,
if approved, HMAC-sign via the signer). Control never holds HMAC or debit.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx

from aea.config import LoadedPolicy
from aea.control.schemas import RequestPaymentRequest
from aea.ledger.errors import LedgerError
from aea.ledger.models import (
    AuditWrite,
    CostCreate,
    PaymentCreate,
    PaymentDecisionWrite,
    PaymentSettle,
)
from aea.ledger.service import LedgerService
from aea.policy.reasons import HttpCode
from aea.types import format_amount

PolicyExecute = Callable[[dict[str, Any]], dict[str, Any]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PaymentOrchestrator:
    """In-process payment path used by /v1/tools/request_payment and
    POST /v1/payment-requests. Not a model-facing API.
    """

    def __init__(
        self,
        *,
        ledger: LedgerService,
        policy: LoadedPolicy,
        policy_execute: PolicyExecute,
        wallet_balances: Callable[[], dict[str, Decimal]],
        control_token: str,
    ) -> None:
        if not control_token:
            raise ValueError("payment orchestrator requires the control token to call policy")
        self._ledger = ledger
        self._policy = policy
        self._policy_execute = policy_execute
        self._wallet_balances = wallet_balances
        self._control_token = control_token

    def request(
        self,
        req: RequestPaymentRequest,
        *,
        correlation_id: UUID,
        frozen: bool,
        signer_enabled: bool,
        loop_enabled: bool,
    ) -> dict[str, Any]:
        if frozen:
            return {
                "ok": False,
                "code": HttpCode.AGENT_FROZEN,
                "policy_decision": "pending",
                "transaction_reference": None,
            }
        if not loop_enabled:
            return {
                "ok": False,
                "code": HttpCode.LOOP_STOPPED,
                "policy_decision": "pending",
                "transaction_reference": None,
            }
        if not signer_enabled:
            return {
                "ok": False,
                "code": HttpCode.SIGNER_DISABLED,
                "policy_decision": "pending",
                "reason_code": HttpCode.SIGNER_DISABLED,
                "transaction_reference": None,
            }
        existing = self._ledger.get_payment_by_idempotency(req.idempotency_key)
        if existing is None:
            blocked = self._recon_mismatch()
            if blocked is not None:
                return blocked
        try:
            pending = self._ledger.create_payment_request(
                PaymentCreate.model_validate(
                    {
                        "job_id": str(req.job_id),
                        "amount": format_amount(req.amount),
                        "asset": req.asset,
                        "destination": req.destination,
                        "purpose": req.purpose,
                        "policy_version": self._policy.document.policy_version,
                        "correlation_id": str(correlation_id),
                        "idempotency_key": req.idempotency_key,
                        "idempotency_ttl_seconds": self._policy.document.idempotency_ttl_seconds,
                    }
                )
            )
        except LedgerError as exc:
            return {"ok": False, "code": exc.code, "transaction_reference": None}

        request_id = pending["request_id"]
        if pending.get("replay") and pending.get("policy_decision") == "rejected":
            return {
                "ok": False,
                "code": HttpCode.POLICY_REJECTED,
                "request_id": str(request_id),
                "policy_decision": "rejected",
                "reason_code": pending.get("reason_code"),
                "transaction_reference": None,
            }
        if pending.get("transaction_reference"):
            return self._complete_settled(
                req,
                request_id=request_id,
                tx_id=str(pending["transaction_reference"]),
                correlation_id=correlation_id,
                replay=True,
            )

        dest = self._policy.classify(req.destination)
        try:
            balances = self._wallet_balances()
        except Exception:
            return {
                "ok": False,
                "code": HttpCode.NETWORK_FAILURE,
                "request_id": str(request_id),
                "transaction_reference": None,
            }
        daily = self._ledger.daily_spend_usdc()
        try:
            exposure = self._ledger.outstanding_exposure_usdc(excluding_request_id=request_id)
        except LedgerError:
            return {
                "ok": False,
                "code": HttpCode.INTERNAL_ERROR,
                "request_id": str(request_id),
                "transaction_reference": None,
            }
        flags = self._ledger.supervisor_flags()
        policy_body = {
            "amount": format_amount(req.amount),
            "asset": req.asset,
            "destination": req.destination,
            "destination_class": dest.class_,
            "destination_allowed": dest.allowed,
            "job_id": str(req.job_id),
            "purpose": req.purpose,
            "daily_spend_usdc": format_amount(daily),
            "outstanding_exposure_usdc": format_amount(exposure),
            "wallet_balances": {
                k: format_amount(v) if not isinstance(v, str) else v for k, v in balances.items()
            },
            "policy_version": self._policy.document.policy_version,
            "policy_hash": self._policy.policy_hash,
            "frozen": frozen or flags["frozen"],
            "signer_enabled": signer_enabled and flags["signer_enabled"],
            "wallet_phase": self._policy.document.wallet_phase,
            "correlation_id": str(pending["correlation_id"]),
            "request_id": str(request_id),
            "approved_at": pending["requested_at"].isoformat()
            if hasattr(pending["requested_at"], "isoformat")
            else str(pending["requested_at"]),
        }
        if req.expected_return is not None:
            policy_body["expected_return_usdc"] = format_amount(req.expected_return.amount)

        executed = self._policy_execute(policy_body)
        code = str(executed.get("code") or HttpCode.INTERNAL_ERROR)
        decision = executed.get("decision")
        tx_id = executed.get("tx_id")

        if pending.get("policy_decision") != "approved" and (
            decision == "rejected" or code == HttpCode.POLICY_REJECTED
        ):
            self._ledger.decide_payment_request(
                PaymentDecisionWrite.model_validate(
                    {
                        "request_id": str(request_id),
                        "decision": "rejected",
                        "reason_code": executed.get("reason_code") or code,
                        "idempotency_key": f"dec-{req.idempotency_key}",
                    }
                )
            )
            return {
                "ok": False,
                "code": HttpCode.POLICY_REJECTED,
                "request_id": str(request_id),
                "policy_decision": "rejected",
                "reason_code": executed.get("reason_code"),
                "transaction_reference": None,
            }

        if not executed.get("ok") or not tx_id:
            return {
                "ok": False,
                "code": code if code != HttpCode.OK else HttpCode.SIGNER_UNAVAILABLE,
                "request_id": str(request_id),
                "policy_decision": pending.get("policy_decision") or "pending",
                "reason_code": executed.get("reason_code") or code,
                "transaction_reference": None,
            }

        return self._complete_settled(
            req,
            request_id=request_id,
            tx_id=str(tx_id),
            correlation_id=correlation_id,
            replay=bool(executed.get("replay") or pending.get("replay")),
            approved_amount=executed.get("approved_amount") or format_amount(req.amount),
            canonical_hash=executed.get("canonical_hash"),
        )

    def _complete_settled(
        self,
        req: RequestPaymentRequest,
        *,
        request_id: UUID,
        tx_id: str,
        correlation_id: UUID,
        replay: bool,
        approved_amount: str | None = None,
        canonical_hash: str | None = None,
    ) -> dict[str, Any]:
        row = self._ledger.get_payment_request(request_id)
        if row["policy_decision"] != "approved":
            self._ledger.decide_payment_request(
                PaymentDecisionWrite.model_validate(
                    {
                        "request_id": str(request_id),
                        "decision": "approved",
                        "approved_amount": approved_amount or format_amount(req.amount),
                        "canonical_hash": canonical_hash,
                        "idempotency_key": f"dec-{req.idempotency_key}",
                    }
                )
            )
        self._ledger.settle_payment_request(
            PaymentSettle.model_validate(
                {
                    "request_id": str(request_id),
                    "transaction_reference": tx_id,
                    "idempotency_key": f"stl-{req.idempotency_key}",
                }
            )
        )
        self._ledger.record_cost(
            CostCreate.model_validate(
                {
                    "job_id": str(req.job_id),
                    "category": "purchased_service",
                    "amount": format_amount(req.amount),
                    "asset": req.asset,
                    "payment_request_id": str(request_id),
                    "idempotency_key": f"cash-{req.idempotency_key}",
                    "correlation_id": str(correlation_id),
                }
            )
        )
        mismatch = self._recon_mismatch(request_id=request_id, tx_id=tx_id)
        if mismatch is not None:
            return mismatch
        return {
            "ok": True,
            "code": HttpCode.IDEMPOTENT_REPLAY if replay else HttpCode.OK,
            "request_id": str(request_id),
            "policy_decision": "approved",
            "reason_code": None,
            "transaction_reference": tx_id,
        }

    def _recon_mismatch(self, *, request_id: UUID | None = None, tx_id: str | None = None) -> dict[str, Any] | None:
        try:
            balances = self._wallet_balances()
        except Exception:
            recon = {"ok": False, "code": HttpCode.WALLET_LEDGER_MISMATCH, "mismatches": ["wallet_unreadable"]}
        else:
            recon = self._ledger.reconcile_with_wallet(balances)
        if recon.get("ok"):
            return None
        self._ledger.write_audit(
            AuditWrite.model_validate(
                {
                    "event_type": "wallet_ledger_mismatch",
                    "payload": {
                        "code": recon.get("code"),
                        "mismatches": recon.get("mismatches"),
                        "request_id": str(request_id) if request_id else None,
                        "transaction_reference": tx_id,
                    },
                    "correlation_id": request_id,
                }
            )
        )
        out: dict[str, Any] = {
            "ok": False,
            "code": HttpCode.WALLET_LEDGER_MISMATCH,
            "policy_decision": "approved" if tx_id else "pending",
            "reason_code": HttpCode.WALLET_LEDGER_MISMATCH,
            "transaction_reference": tx_id,
        }
        if request_id is not None:
            out["request_id"] = str(request_id)
        return out


def _run_coro(coro):
    """Run a coroutine from sync code even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def policy_execute_via_asgi(app: Any, control_token: str) -> PolicyExecute:
    """Call policy POST /v1/execute-payment over ASGI. No HMAC in this process."""

    def call(body: dict[str, Any]) -> dict[str, Any]:
        async def run() -> dict[str, Any]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://policy") as client:
                response = await client.post(
                    "/v1/execute-payment",
                    json=body,
                    headers={"Authorization": f"Bearer {control_token}"},
                )
            try:
                payload = response.json()
            except ValueError:
                return {"ok": False, "code": HttpCode.NETWORK_FAILURE}
            return payload if isinstance(payload, dict) else {"ok": False, "code": HttpCode.NETWORK_FAILURE}

        return _run_coro(run())

    return call


def policy_execute_via_http(base_url: str, control_token: str) -> PolicyExecute:
    def call(body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                base_url.rstrip("/") + "/v1/execute-payment",
                json=body,
                headers={"Authorization": f"Bearer {control_token}"},
                timeout=30.0,
            )
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return {"ok": False, "code": HttpCode.NETWORK_FAILURE}
        return payload if isinstance(payload, dict) else {"ok": False, "code": HttpCode.NETWORK_FAILURE}

    return call
