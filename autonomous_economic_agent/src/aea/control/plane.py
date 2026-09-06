"""Durable nine-tool implementations. Postgres + wallet evidence is the truth."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from aea import AGENT_ID, CONSTITUTION_VERSION, POLICY_VERSION
from aea.config import LoadedPolicy
from aea.control.freeze import ControlSafety
from aea.ledger.errors import LedgerError
from aea.ledger.models import (
    AuditWrite,
    CostCreate,
    DecisionCreate,
    JobAccept,
    JobTransition,
    OpportunityCreate,
    RevenueCreate,
)
from aea.ledger.service import LedgerService
from aea.marketplace.protocol import DiscoveredJob, MarketplaceAdapter, MarketplaceError
from aea.payment.service import PaymentOrchestrator
from aea.policy.reasons import HttpCode, ReasonCode
from aea.policy.risk import AgentRiskInput, JobAcceptInput, evaluate_agent_risk, evaluate_job_accept
from aea.types import format_amount
from aea.workers.registry import run_worker

WalletTxLookup = Callable[[str], Any]
WalletBalances = Callable[[], dict[str, Decimal]]

_PERMANENT_DECLINE = frozenset(
    {
        ReasonCode.MARGIN_NOT_MET,
        ReasonCode.PROHIBITED_TOKEN,
        HttpCode.PROMPT_INJECTION_DETECTED,
        ReasonCode.PROHIBITED_DESTINATION,
        HttpCode.POLICY_REJECTED,
        ReasonCode.OPEN_JOBS_EXCEEDED,
        HttpCode.AGENT_RISK_VETO,
    }
)


def compute_mark(tokens_in: int, tokens_out: int, wall_seconds: Decimal, policy: LoadedPolicy) -> Decimal:
    rates = policy.document.cost_rates
    raw = (
        Decimal(tokens_in) / Decimal("1000") * rates.compute_usd_per_1k_tokens_in
        + Decimal(tokens_out) / Decimal("1000") * rates.compute_usd_per_1k_tokens_out
        + wall_seconds * rates.compute_usd_per_wall_second
    )
    if raw < rates.compute_floor_usdc:
        return rates.compute_floor_usdc
    return raw


class EconomicPlane:
    """Nine tools against LedgerService + marketplace + payment orchestrator."""

    def __init__(
        self,
        *,
        ledger: LedgerService,
        marketplace: MarketplaceAdapter,
        policy: LoadedPolicy,
        safety: Callable[[], ControlSafety],
        payment: PaymentOrchestrator | None = None,
        wallet_get_tx: WalletTxLookup | None = None,
        wallet_balances: WalletBalances | None = None,
    ) -> None:
        self._ledger = ledger
        self._marketplace = marketplace
        self._policy = policy
        self._safety = safety
        self._payment = payment
        self._wallet_get_tx = wallet_get_tx
        self._wallet_balances = wallet_balances

    def dispatch(self, name: str, req: Any, *, correlation_id: str) -> dict[str, Any]:
        try:
            result = {
                "find_jobs": self.find_jobs,
                "evaluate_job": self.evaluate_job,
                "accept_job": self.accept_job,
                "perform_job": self.perform_job,
                "submit_work": self.submit_work,
                "check_payment": self.check_payment,
                "request_payment": self.request_payment,
                "get_financial_state": self.get_financial_state,
                "record_decision": self.record_decision,
            }[name](req, correlation_id=correlation_id)
            return result
        except LedgerError as exc:
            return {"ok": False, "code": exc.code}
        except MarketplaceError as exc:
            code = exc.code if exc.code in {
                HttpCode.NETWORK_FAILURE,
                HttpCode.NOT_FOUND,
                HttpCode.CONFLICT,
                HttpCode.FORBIDDEN,
                HttpCode.VALIDATION_ERROR,
                HttpCode.PROMPT_INJECTION_DETECTED,
                HttpCode.POLICY_REJECTED,
                HttpCode.TIMEOUT,
                HttpCode.MARKETPLACE_UNAVAILABLE,
            } else HttpCode.MARKETPLACE_UNAVAILABLE
            payload: dict[str, Any] = {"ok": False, "code": code}
            if exc.message and exc.message != exc.code:
                payload["detail"] = exc.message
            return payload
        except Exception:
            return {"ok": False, "code": HttpCode.INTERNAL_ERROR}

    def find_jobs(self, req: Any, *, correlation_id: str) -> dict[str, Any]:
        page = self._marketplace.discover(limit=req.limit, cursor=req.cursor)
        jobs = []
        for item in page.jobs:
            dumped = item.model_dump(mode="json")
            row = self._ledger.record_opportunity(
                OpportunityCreate.model_validate(
                    {
                        "source": "mock",
                        "external_reference": dumped["external_reference"],
                        "description_hash": dumped["description_hash"].removeprefix("sha256:"),
                        "expected_revenue": dumped["expected_revenue"]["amount"],
                        "expected_cost": dumped["estimated_cost"]["amount"],
                        "artefact_uri": dumped["external_reference"],
                        "policy_version": self._policy.document.policy_version,
                        "idempotency_key": f"opp-{dumped['external_reference']}"[:128],
                    }
                )
            )
            jobs.append(
                {
                    "opportunity_id": str(row["opportunity_id"]),
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

    def _discovered(self, opportunity_id: UUID) -> tuple[dict[str, Any], DiscoveredJob] | dict[str, Any]:
        opp = self._ledger.get_opportunity(opportunity_id)
        listed = self._marketplace.lookup(opp["external_reference"])
        return opp, listed

    def evaluate_job(self, req: Any, *, correlation_id: str) -> dict[str, Any]:
        try:
            opp, listed = self._discovered(req.opportunity_id)
        except LedgerError as exc:
            return {"ok": False, "code": exc.code}
        except MarketplaceError as exc:
            return {"ok": False, "code": exc.code}
        dumped = listed.model_dump(mode="json")
        revenue = Decimal(str(dumped["expected_revenue"]["amount"]))
        cost = Decimal(str(dumped["estimated_cost"]["amount"]))
        asset = dumped["payment_asset"]
        flags = list(dumped.get("flags") or [])
        blockers: list[str] = []
        if "prompt_injection" in flags:
            blockers.append(HttpCode.PROMPT_INJECTION_DETECTED)
        if asset != "USDC":
            blockers.append(ReasonCode.PROHIBITED_TOKEN)
        hist = self._ledger.history_payment_rate(source="mock")
        base = 0.90
        prob = float(base if hist is None else max(0.05, min(0.99, 0.5 * base + 0.5 * hist)))
        open_jobs = self._ledger.count_open_jobs()
        safety = self._safety()
        accept = evaluate_job_accept(
            JobAcceptInput.model_validate(
                {
                    "expected_revenue_usdc": format_amount(revenue),
                    "expected_cost_usdc": format_amount(cost),
                    "probability_payment": prob,
                    "open_jobs": open_jobs,
                    "frozen": safety.frozen,
                    "asset": "USDC" if asset == "USDC" else "USDC",
                }
            ),
            self._policy.document,
        )
        if asset != "USDC":
            accept = accept.model_copy(
                update={"allowed": False, "reason_code": ReasonCode.PROHIBITED_TOKEN}
            )
        if HttpCode.PROMPT_INJECTION_DETECTED in blockers:
            accept = accept.model_copy(
                update={"allowed": False, "reason_code": HttpCode.PROMPT_INJECTION_DETECTED}
            )
        try:
            exposure = self._ledger.outstanding_exposure_usdc()
        except LedgerError:
            blockers.append(ReasonCode.CAPITAL_AT_RISK_EXCEEDED)
            accept = accept.model_copy(
                update={"allowed": False, "reason_code": ReasonCode.CAPITAL_AT_RISK_EXCEEDED}
            )
        else:
            if exposure + cost > self._policy.document.limits.max_capital_at_risk_usdc:
                blockers.append(ReasonCode.CAPITAL_AT_RISK_EXCEEDED)
                accept = accept.model_copy(
                    update={"allowed": False, "reason_code": ReasonCode.CAPITAL_AT_RISK_EXCEEDED}
                )
        try:
            self._ledger.set_opportunity_decision(req.opportunity_id, "evaluated")
        except LedgerError:
            pass
        margin = revenue - cost
        bps = int((margin / cost) * 10000) if cost > 0 else 0
        reputation = dumped.get("counterparty_reputation") or {}
        risk = evaluate_agent_risk(
            AgentRiskInput.model_validate(
                {
                    "expected_revenue_usdc": format_amount(revenue),
                    "expected_cost_usdc": format_amount(cost),
                    "probability_payment": prob,
                    "max_job_compute_usdc": format_amount(
                        self._policy.document.limits.max_job_compute_usdc
                    ),
                    "worker": dumped.get("worker") or "",
                    "credits_wallet_on_submit": bool(dumped.get("credits_wallet_on_submit", True)),
                    "completed": int(reputation.get("completed") or 0),
                    "disputed": int(reputation.get("disputed") or 0),
                    "flags": flags,
                    "title": dumped.get("title") or "",
                    "description_preview": dumped.get("untrusted_description_preview") or "",
                    "payment_asset": asset,
                }
            )
        )
        mission_codes = {
            ReasonCode.CAPITAL_AT_RISK_EXCEEDED,
            ReasonCode.OPEN_JOBS_EXCEEDED,
            ReasonCode.FROZEN,
        }
        mission_passed = not any(code in mission_codes for code in blockers) and not safety.frozen
        # accept_allowed is policy permission, not a recommendation.
        rec = "accept" if accept.allowed and mission_passed and risk.passed and not blockers else "decline"
        return {
            "ok": True,
            "code": HttpCode.OK,
            "opportunity_id": str(req.opportunity_id),
            "expected_revenue": dumped["expected_revenue"],
            "expected_costs": [
                {"category": "compute", "amount": format_amount(cost), "asset": "USDC"}
            ],
            "expected_cost_total": {"amount": format_amount(cost), "asset": "USDC"},
            "expected_margin": {"amount": format_amount(margin), "asset": "USDC"},
            "expected_margin_bps": bps,
            "probability_completion": 0.95,
            "probability_payment": prob,
            "risk_score": 0.12 if risk.passed else 0.85,
            "risk_factors": risk.factors or flags or ["none"],
            "risk_veto": not risk.passed,
            "risk_reason_code": risk.reason_code,
            "meets_required_margin": accept.meets_required_margin,
            "policy_blockers": blockers,
            "mission_constraints_passed": mission_passed,
            "recommendation": rec,
            "accept_allowed": accept.allowed,
            "reason_code": accept.reason_code,
        }

    def accept_job(self, req: Any, *, correlation_id: str) -> dict[str, Any]:
        evaluation = self.evaluate_job(
            type("R", (), {"opportunity_id": req.opportunity_id})(),
            correlation_id=correlation_id,
        )
        if evaluation.get("code") == HttpCode.NOT_FOUND:
            return evaluation
        opp = self._ledger.get_opportunity(req.opportunity_id)
        blockers = evaluation.get("policy_blockers") or []
        if blockers:
            code = blockers[0]
            if code in _PERMANENT_DECLINE:
                try:
                    self._ledger.set_opportunity_decision(
                        req.opportunity_id, "declined", reason=str(code)
                    )
                except LedgerError:
                    pass
            return {"ok": False, "code": code, "opportunity_id": str(req.opportunity_id)}
        if not evaluation.get("accept_allowed"):
            code = evaluation.get("reason_code") or ReasonCode.MARGIN_NOT_MET
            if code in _PERMANENT_DECLINE:
                try:
                    self._ledger.set_opportunity_decision(
                        req.opportunity_id, "declined", reason=str(code)
                    )
                except LedgerError:
                    pass
            return {
                "ok": False,
                "code": code,
                "opportunity_id": str(req.opportunity_id),
            }
        if evaluation.get("risk_veto"):
            code = evaluation.get("risk_reason_code") or HttpCode.AGENT_RISK_VETO
            if code in _PERMANENT_DECLINE:
                try:
                    self._ledger.set_opportunity_decision(
                        req.opportunity_id, "declined", reason=str(code)
                    )
                except LedgerError:
                    pass
            return {
                "ok": False,
                "code": code,
                "opportunity_id": str(req.opportunity_id),
                "risk_factors": evaluation.get("risk_factors") or [],
            }
        if not evaluation.get("mission_constraints_passed"):
            code = ReasonCode.CAPITAL_AT_RISK_EXCEEDED
            return {
                "ok": False,
                "code": code,
                "opportunity_id": str(req.opportunity_id),
            }
        self._marketplace.accept(opp["external_reference"], idempotency_key=req.idempotency_key)
        job = self._ledger.accept_job(
            JobAccept.model_validate(
                {
                    "opportunity_id": str(req.opportunity_id),
                    "expected_revenue": format_amount(_dec(opp["expected_revenue"])),
                    "policy_version": self._policy.document.policy_version,
                    "idempotency_key": req.idempotency_key,
                }
            )
        )
        return {
            "ok": True,
            "code": HttpCode.IDEMPOTENT_REPLAY if job.get("replay") else HttpCode.OK,
            "job_id": str(job["job_id"]),
            "opportunity_id": str(req.opportunity_id),
            "status": job["status"],
        }

    def perform_job(self, req: Any, *, correlation_id: str) -> dict[str, Any]:
        job = self._ledger.get_job_bundle(req.job_id)
        if job["status"] not in {"accepted", "performing", "performed"}:
            if job["status"] == "performed":
                return {
                    "ok": True,
                    "code": HttpCode.IDEMPOTENT_REPLAY,
                    "job_id": str(job["job_id"]),
                    "status": "performed",
                    "deliverable_digest": job.get("deliverable_hash"),
                }
            return {"ok": False, "code": HttpCode.CONFLICT}
        if job["status"] == "accepted":
            self._ledger.transition_job(
                JobTransition.model_validate(
                    {
                        "job_id": str(req.job_id),
                        "status": "performing",
                        "idempotency_key": f"perf-start-{req.idempotency_key}"[:128],
                    }
                )
            )
        result = run_worker(job["external_reference"])
        mark = compute_mark(result.tokens_in, result.tokens_out, result.wall_seconds, self._policy)
        cap = self._policy.document.limits.max_job_compute_usdc
        runaway = result.reason_code == HttpCode.RUNAWAY_COST or mark > cap
        if runaway:
            mark = min(mark, cap)
        self._ledger.record_cost(
            CostCreate.model_validate(
                {
                    "job_id": str(req.job_id),
                    "category": "compute",
                    "amount": format_amount(mark),
                    "asset": "USDC",
                    "idempotency_key": f"cost-{req.idempotency_key}",
                    "correlation_id": correlation_id,
                    "evidence_reference": result.digest,
                }
            )
        )
        if runaway:
            self._ledger.transition_job(
                JobTransition.model_validate(
                    {
                        "job_id": str(req.job_id),
                        "status": "failed",
                        "deliverable_hash": result.digest,
                        "idempotency_key": f"perf-fail-{req.idempotency_key}"[:128],
                    }
                )
            )
            return {
                "ok": False,
                "code": HttpCode.RUNAWAY_COST,
                "job_id": str(req.job_id),
                "deliverable_digest": result.digest,
            }
        if not result.ok:
            self._ledger.transition_job(
                JobTransition.model_validate(
                    {
                        "job_id": str(req.job_id),
                        "status": "failed",
                        "deliverable_hash": result.digest,
                        "idempotency_key": f"perf-fail-{req.idempotency_key}"[:128],
                    }
                )
            )
            return {
                "ok": False,
                "code": result.reason_code or HttpCode.JOB_FAILED,
                "job_id": str(req.job_id),
                "deliverable_digest": result.digest,
            }
        self._ledger.transition_job(
            JobTransition.model_validate(
                {
                    "job_id": str(req.job_id),
                    "status": "performed",
                    "deliverable_hash": result.digest,
                    "idempotency_key": req.idempotency_key,
                }
            )
        )
        return {
            "ok": True,
            "code": HttpCode.OK,
            "job_id": str(req.job_id),
            "status": "performed",
            "deliverable_digest": result.digest,
        }

    def submit_work(self, req: Any, *, correlation_id: str) -> dict[str, Any]:
        job = self._ledger.get_job_bundle(req.job_id)
        if job["status"] == "submitted":
            return {
                "ok": True,
                "code": HttpCode.IDEMPOTENT_REPLAY,
                "job_id": str(job["job_id"]),
                "status": "submitted",
                "transaction_reference": None,
                "credited": False,
            }
        if job["status"] != "performed" or not job.get("deliverable_hash"):
            return {"ok": False, "code": HttpCode.CONFLICT}
        submitted = self._marketplace.submit(
            job["external_reference"],
            artefact_digest=job["deliverable_hash"],
            artefact_uri=f"artefacts/{job['deliverable_hash']}",
            idempotency_key=req.idempotency_key,
        )
        self._ledger.transition_job(
            JobTransition.model_validate(
                {
                    "job_id": str(req.job_id),
                    "status": "submitted",
                    "deliverable_hash": job["deliverable_hash"],
                    "idempotency_key": f"sub-{req.idempotency_key}"[:128],
                }
            )
        )
        dumped = submitted.model_dump(mode="json")
        return {
            "ok": True,
            "code": HttpCode.OK,
            "job_id": str(job["job_id"]),
            "status": "submitted",
            "transaction_reference": dumped.get("transaction_reference"),
            "credited": dumped.get("credited"),
        }

    def check_payment(self, req: Any, *, correlation_id: str) -> dict[str, Any]:
        job = self._ledger.get_job_bundle(req.job_id)
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
        expected = _dec(job["expected_revenue"])
        if wallet_tx is None:
            return {
                "ok": False,
                "code": HttpCode.FAKE_PAYMENT,
                "status": "fake",
                "verified": False,
                "transaction_reference": tx_id,
            }
        amount = wallet_tx.amount if hasattr(wallet_tx, "amount") else None
        asset = wallet_tx.asset if hasattr(wallet_tx, "asset") else None
        if amount is None and isinstance(wallet_tx, dict):
            amount = wallet_tx.get("amount")
            asset = wallet_tx.get("asset")
        if asset != "USDC" or amount is None or format_amount(_dec(amount)) != format_amount(expected):
            return {
                "ok": False,
                "code": HttpCode.FAKE_PAYMENT,
                "status": "fake",
                "verified": False,
                "transaction_reference": tx_id,
            }
        self._ledger.record_verified_revenue(
            RevenueCreate.model_validate(
                {
                    "job_id": str(req.job_id),
                    "amount": format_amount(expected),
                    "asset": "USDC",
                    "transaction_reference": tx_id,
                    "verified": True,
                    "idempotency_key": req.idempotency_key,
                }
            )
        )
        if self._wallet_balances is not None:
            recon = self._ledger.reconcile_with_wallet(self._wallet_balances())
            if not recon["ok"]:
                self._ledger.write_audit(
                    AuditWrite.model_validate(
                        {
                            "event_type": "wallet_ledger_mismatch",
                            "payload": {
                                "code": recon.get("code"),
                                "mismatches": recon.get("mismatches"),
                            },
                        }
                    )
                )
        return {
            "ok": True,
            "code": HttpCode.OK,
            "status": "settled",
            "verified": True,
            "transaction_reference": tx_id,
        }

    def request_payment(self, req: Any, *, correlation_id: str) -> dict[str, Any]:
        safety = self._safety()
        if safety.frozen:
            return {
                "ok": False,
                "code": HttpCode.AGENT_FROZEN,
                "policy_decision": "pending",
                "transaction_reference": None,
            }
        if not safety.loop_enabled:
            return {
                "ok": False,
                "code": HttpCode.LOOP_STOPPED,
                "policy_decision": "pending",
                "transaction_reference": None,
            }
        if not safety.signer_enabled:
            return {
                "ok": False,
                "code": HttpCode.SIGNER_DISABLED,
                "policy_decision": "pending",
                "reason_code": HttpCode.SIGNER_DISABLED,
                "transaction_reference": None,
            }
        if self._payment is None:
            return {
                "ok": False,
                "code": HttpCode.SIGNER_UNAVAILABLE,
                "policy_decision": "pending",
                "transaction_reference": None,
            }
        result = self._payment.request(
            req,
            correlation_id=UUID(correlation_id) if _is_uuid(correlation_id) else uuid4(),
            frozen=safety.frozen,
            signer_enabled=safety.signer_enabled,
            loop_enabled=safety.loop_enabled,
        )
        return result

    def get_financial_state(self, req: Any, *, correlation_id: str) -> dict[str, Any]:
        state = self._ledger.get_financial_state()
        safety = self._safety()
        state["frozen"] = bool(state.get("frozen")) or safety.frozen
        state["signer_enabled"] = bool(state.get("signer_enabled")) and safety.signer_enabled
        state["loop_enabled"] = bool(state.get("loop_enabled")) and safety.loop_enabled
        state["ok"] = True
        state["code"] = HttpCode.OK
        state.setdefault("constitution_version", CONSTITUTION_VERSION)
        state.setdefault("unit_of_account", "USDC")
        state.setdefault("agent_id", AGENT_ID)
        state.setdefault("policy_version", self._policy.document.policy_version or POLICY_VERSION)
        return state

    def record_decision(self, req: Any, *, correlation_id: str) -> dict[str, Any]:
        row = self._ledger.record_decision(
            DecisionCreate.model_validate(
                {
                    "decision_type": req.decision_type,
                    "decision": req.decision,
                    "reasoning_summary": req.reasoning_summary,
                    "idempotency_key": req.idempotency_key,
                    "opportunity_id": str(req.opportunity_id) if req.opportunity_id else None,
                    "job_id": str(req.job_id) if req.job_id else None,
                    "expected_value": req.expected_value if req.expected_value not in {None, ""} else None,
                    "confidence": req.confidence,
                    "input_summary": req.input_summary,
                    "policy_version": self._policy.document.policy_version,
                    "constitution_version": CONSTITUTION_VERSION,
                }
            )
        )
        return {
            "ok": True,
            "code": HttpCode.IDEMPOTENT_REPLAY if row.get("replay") else HttpCode.OK,
            "decision_id": str(row["decision_id"]),
            "applied": False,
        }


def _dec(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError):
        return False
