"""Fail-closed state machines for opportunities, jobs, and payment requests."""

from __future__ import annotations

from typing import Final

from aea.ledger.errors import LedgerError
from aea.policy.reasons import HttpCode

OPPORTUNITY_STATES: Final[frozenset[str]] = frozenset(
    {"discovered", "evaluated", "accepted", "declined", "expired"}
)
JOB_STATES: Final[frozenset[str]] = frozenset(
    {"accepted", "performing", "performed", "submitted", "completed", "failed", "cancelled"}
)
PAYMENT_STATES: Final[frozenset[str]] = frozenset({"pending", "approved", "rejected"})

OPEN_JOB_STATUSES: Final[frozenset[str]] = frozenset(
    {"accepted", "performing", "performed", "submitted"}
)

OPPORTUNITY_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "discovered": frozenset({"evaluated", "accepted", "declined", "expired"}),
    "evaluated": frozenset({"accepted", "declined", "expired"}),
    "accepted": frozenset(),
    "declined": frozenset(),
    "expired": frozenset(),
}

JOB_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "accepted": frozenset({"performing", "failed", "cancelled"}),
    "performing": frozenset({"performed", "failed"}),
    "performed": frozenset({"submitted", "failed"}),
    "submitted": frozenset({"completed", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}

PAYMENT_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "pending": frozenset({"approved", "rejected"}),
    "approved": frozenset(),
    "rejected": frozenset(),
}

SEED_TRANSFER_CLASSES: Final[frozenset[str]] = frozenset({"opening_capital", "fee_reserve"})
APP_TRANSFER_CLASSES: Final[frozenset[str]] = frozenset(
    {"operator_top_up", "operator_withdrawal", "refund", "not_revenue"}
)


def ensure_transition(kind: str, current: str, target: str) -> None:
    tables = {
        "opportunity": OPPORTUNITY_TRANSITIONS,
        "job": JOB_TRANSITIONS,
        "payment": PAYMENT_TRANSITIONS,
    }
    allowed = tables[kind]
    if current not in allowed:
        raise LedgerError(HttpCode.CONFLICT, f"unknown {kind} state {current}")
    if target == current:
        return
    if target not in allowed[current]:
        raise LedgerError(
            HttpCode.CONFLICT,
            f"illegal {kind} transition {current} -> {target}",
        )
