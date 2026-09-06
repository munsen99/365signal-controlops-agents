"""Supervisor monitors. Evaluate snapshots; never unfreeze automatically.

Poll interval is ≤ 10s in the service. This module is I/O-free: callers
supply the snapshot. Unreadable safety-critical fields fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from aea.supervisor.incidents import (
    CAPITAL_AT_RISK,
    COMPUTE_VELOCITY,
    CONTROL_UNHEALTHY,
    DAILY_SPEND_CAP,
    DAILY_SPEND_WARN,
    FAILED_TXS,
    FAKE_PAYMENT,
    FOLLOWUP_DUE,
    IncidentDraft,
    JOB_FAILURE_RATE,
    POLICY_REJECTIONS,
    POLICY_TAMPER,
    UNEXPECTED_BALANCE,
    UNREADABLE_STATE,
    UNUSUAL_DESTINATION,
    WALLET_LEDGER_MISMATCH,
)

PERMITTED_TOKENS = frozenset({"USDC", "SOL"})
POLL_INTERVAL_SECONDS = 10


@dataclass(frozen=True)
class MonitorSnapshot:
    usdc: Decimal | None = None
    token_balances: dict[str, Decimal] | None = None
    daily_spend_usdc: Decimal | None = None
    daily_cap_usdc: Decimal = Decimal("3")
    capital_at_risk_usdc: Decimal | None = None
    max_capital_at_risk_usdc: Decimal = Decimal("5")
    failed_txs_10m: int | None = None
    policy_rejections_10m: int | None = None
    policy_tamper: bool = False
    unusual_destination: bool = False
    ledger_wallet_mismatch: bool | None = None
    compute_usdc_10m: Decimal | None = None
    max_job_compute_usdc: Decimal = Decimal("0.5")
    job_failures: int | None = None
    job_total: int | None = None
    control_healthy: bool | None = None
    fake_payment_count: int | None = None
    due_followups: int = 0


@dataclass(frozen=True)
class MonitorDecision:
    freeze_spend: bool = False
    disable_signer: bool = False
    stop_loop: bool = False
    incidents: tuple[IncidentDraft, ...] = ()


def evaluate_monitors(snapshot: MonitorSnapshot) -> MonitorDecision:
    """Map M0 §12.1 signals to restrictive actions. Never unfreeze."""
    freeze = False
    disable_signer = False
    stop_loop = False
    incidents: list[IncidentDraft] = []

    def note(severity: str, kind: str, message: str) -> None:
        incidents.append(IncidentDraft(severity=severity, kind=kind, message=message))

    if snapshot.usdc is None or snapshot.token_balances is None:
        freeze = True
        note("critical", UNREADABLE_STATE, "wallet balances unreadable")
    else:
        if snapshot.usdc < 0:
            freeze = True
            note("critical", UNEXPECTED_BALANCE, "USDC balance below zero")
        unexpected = sorted(set(snapshot.token_balances) - PERMITTED_TOKENS)
        if unexpected:
            freeze = True
            note(
                "critical",
                UNEXPECTED_BALANCE,
                f"unexpected token balances: {','.join(unexpected)}",
            )

    if snapshot.daily_spend_usdc is None:
        freeze = True
        note("critical", UNREADABLE_STATE, "daily spend unreadable")
    else:
        cap = snapshot.daily_cap_usdc
        if cap > 0 and snapshot.daily_spend_usdc >= cap:
            freeze = True
            note("critical", DAILY_SPEND_CAP, "daily discretionary spend at or above cap")
        elif cap > 0 and snapshot.daily_spend_usdc > cap * Decimal("0.9"):
            note("warn", DAILY_SPEND_WARN, "daily spend above 90 percent of cap")

    if snapshot.capital_at_risk_usdc is None:
        freeze = True
        note("critical", UNREADABLE_STATE, "capital at risk unreadable")
    elif snapshot.capital_at_risk_usdc > snapshot.max_capital_at_risk_usdc:
        freeze = True
        note("critical", CAPITAL_AT_RISK, "outstanding commitments exceed max_capital_at_risk")

    if snapshot.failed_txs_10m is None:
        freeze = True
        disable_signer = True
        note("critical", UNREADABLE_STATE, "failed transaction rate unreadable")
    elif snapshot.failed_txs_10m >= 3:
        disable_signer = True
        note("critical", FAILED_TXS, "failed transactions >= 3 in 10 minutes")

    if snapshot.policy_rejections_10m is None:
        freeze = True
        note("critical", UNREADABLE_STATE, "policy rejection rate unreadable")
    elif snapshot.policy_rejections_10m >= 5:
        note("warn", POLICY_REJECTIONS, "policy rejections >= 5 in 10 minutes")
        if snapshot.policy_tamper:
            freeze = True
            note("critical", POLICY_TAMPER, "policy tamper with rejection burst")
    elif snapshot.policy_tamper:
        freeze = True
        note("critical", POLICY_TAMPER, "policy tamper detected")

    if snapshot.unusual_destination:
        note("warn", UNUSUAL_DESTINATION, "destination not in classification file")

    if snapshot.ledger_wallet_mismatch is None:
        freeze = True
        note("critical", UNREADABLE_STATE, "ledger/wallet recon unreadable")
    elif snapshot.ledger_wallet_mismatch:
        freeze = True
        note("critical", WALLET_LEDGER_MISMATCH, "ledger vs wallet mismatch")

    if snapshot.compute_usdc_10m is None:
        freeze = True
        note("critical", UNREADABLE_STATE, "compute cost velocity unreadable")
    elif snapshot.compute_usdc_10m > snapshot.max_job_compute_usdc * 2:
        freeze = True
        note("critical", COMPUTE_VELOCITY, "compute cost velocity exceeded 2x max_job_compute")

    if snapshot.job_failures is None or snapshot.job_total is None:
        note("warn", UNREADABLE_STATE, "job failure rate unreadable")
    elif snapshot.job_total >= 4:
        rate = snapshot.job_failures / snapshot.job_total
        if rate > 0.5:
            note("warn", JOB_FAILURE_RATE, "job failure rate above 50 percent with n>=4")

    if snapshot.control_healthy is None:
        stop_loop = True
        note("critical", CONTROL_UNHEALTHY, "control health unreadable")
    elif snapshot.control_healthy is False:
        stop_loop = True
        note("critical", CONTROL_UNHEALTHY, "control /health failed")

    if snapshot.fake_payment_count is None:
        freeze = True
        note("critical", UNREADABLE_STATE, "fake payment counter unreadable")
    elif snapshot.fake_payment_count >= 2:
        freeze = True
        note("critical", FAKE_PAYMENT, "repeated FAKE_PAYMENT")

    if snapshot.due_followups > 0:
        note("info", FOLLOWUP_DUE, "supervisor-observed follow-up conversations are due")

    return MonitorDecision(
        freeze_spend=freeze,
        disable_signer=disable_signer,
        stop_loop=stop_loop,
        incidents=tuple(incidents),
    )


def snapshot_from_mapping(raw: dict[str, Any]) -> MonitorSnapshot:
    """Test helper. Unknown keys ignored; this is not an inbound HTTP DTO."""
    def dec(name: str) -> Decimal | None:
        value = raw.get(name)
        if value is None:
            return None
        return Decimal(str(value))

    tokens = raw.get("token_balances")
    token_balances = None
    if isinstance(tokens, dict):
        token_balances = {str(k): Decimal(str(v)) for k, v in tokens.items()}
    return MonitorSnapshot(
        usdc=dec("usdc"),
        token_balances=token_balances,
        daily_spend_usdc=dec("daily_spend_usdc"),
        daily_cap_usdc=Decimal(str(raw.get("daily_cap_usdc", "3"))),
        capital_at_risk_usdc=dec("capital_at_risk_usdc"),
        max_capital_at_risk_usdc=Decimal(str(raw.get("max_capital_at_risk_usdc", "5"))),
        failed_txs_10m=raw.get("failed_txs_10m"),
        policy_rejections_10m=raw.get("policy_rejections_10m"),
        policy_tamper=bool(raw.get("policy_tamper", False)),
        unusual_destination=bool(raw.get("unusual_destination", False)),
        ledger_wallet_mismatch=raw.get("ledger_wallet_mismatch"),
        compute_usdc_10m=dec("compute_usdc_10m"),
        max_job_compute_usdc=Decimal(str(raw.get("max_job_compute_usdc", "0.5"))),
        job_failures=raw.get("job_failures"),
        job_total=raw.get("job_total"),
        control_healthy=raw.get("control_healthy"),
        fake_payment_count=raw.get("fake_payment_count"),
        due_followups=int(raw.get("due_followups") or 0),
    )
