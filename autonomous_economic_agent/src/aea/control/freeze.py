"""Control-plane freeze check. Mutating tools fail closed when frozen."""

from __future__ import annotations

from pathlib import Path

from aea.signer.freeze import FreezeInspection, inspect_freeze

MUTATING_TOOLS = frozenset(
    {
        "evaluate_job",
        "accept_job",
        "perform_job",
        "submit_work",
        "check_payment",
        "request_payment",
    }
)
OBSERVE_TOOLS = frozenset({"find_jobs", "get_financial_state", "record_decision"})


def tool_is_mutating(name: str) -> bool:
    return name in MUTATING_TOOLS


def inspect_control_freeze(freeze_path: Path | str | None) -> FreezeInspection:
    return inspect_freeze(freeze_path)
