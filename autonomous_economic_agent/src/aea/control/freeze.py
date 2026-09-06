"""Control-plane freeze/loop/signer checks. Mutating tools fail closed."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aea.signer.freeze import FreezeInspection, inspect_freeze

_UNSET = object()

MUTATING_TOOLS = frozenset(
    {
        "evaluate_job",
        "accept_job",
        "perform_job",
        "submit_work",
        "check_payment",
        "request_payment",
        "send_message",
        "post_service_offer",
        "follow_up_message",
        "propose_collaboration",
    }
)
OBSERVE_TOOLS = frozenset(
    {
        "find_jobs",
        "get_financial_state",
        "record_decision",
        "research_opportunities",
        "discover_counterparties",
        "get_counterparty_profile",
        "read_messages",
        "get_market_status",
        "list_active_conversations",
    }
)


def tool_is_mutating(name: str) -> bool:
    return name in MUTATING_TOOLS


def inspect_control_freeze(
    freeze_path: Path | str | None,
    *,
    db_frozen: Any = _UNSET,
) -> FreezeInspection:
    if db_frozen is _UNSET:
        return inspect_freeze(freeze_path)
    return inspect_freeze(freeze_path, db_frozen=db_frozen)


@dataclass(frozen=True)
class ControlSafety:
    frozen: bool
    freeze_detail: str
    signer_enabled: bool
    loop_enabled: bool


def inspect_control_safety(
    freeze_path: Path | str | None,
    *,
    db_frozen: Any = _UNSET,
    db_signer_enabled: Any = _UNSET,
    db_loop_enabled: Any = _UNSET,
) -> ControlSafety:
    freeze = inspect_control_freeze(freeze_path, db_frozen=db_frozen)
    signer_enabled = True
    if db_signer_enabled is not _UNSET:
        if db_signer_enabled is None or not isinstance(db_signer_enabled, bool):
            signer_enabled = False
        else:
            signer_enabled = db_signer_enabled
    loop_enabled = True
    if db_loop_enabled is not _UNSET:
        if db_loop_enabled is None or not isinstance(db_loop_enabled, bool):
            loop_enabled = False
        else:
            loop_enabled = db_loop_enabled
    return ControlSafety(
        frozen=freeze.frozen,
        freeze_detail=freeze.detail,
        signer_enabled=signer_enabled,
        loop_enabled=loop_enabled,
    )
