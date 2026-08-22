"""Signer-only Phase-C live-spend gate inspection."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

LIVE_CONFIRMATION = "CONFIRM_LIVE_USDC_TRANSFER"


@dataclass(frozen=True)
class LiveGateInspection:
    enabled: bool
    reason: str


def inspect_live_spend_gate(path: Path | str | None, *, operator_intent: str | None) -> LiveGateInspection:
    """Require both M0 operator intent and an owner-only confirmation file.

    Missing, malformed, unreadable, non-regular, symlinked, or permissive state
    is disabled. The gate has no mutation API and never auto-recovers.
    """
    if operator_intent != "1":
        return LiveGateInspection(False, "operator_intent_missing")
    if path is None:
        return LiveGateInspection(False, "gate_path_missing")
    gate = Path(path)
    try:
        info = os.lstat(gate)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return LiveGateInspection(False, "gate_not_regular")
        if info.st_uid != os.geteuid():
            return LiveGateInspection(False, "gate_owner_mismatch")
        if stat.S_IMODE(info.st_mode) & 0o077:
            return LiveGateInspection(False, "gate_permissions_unsafe")
        content = gate.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return LiveGateInspection(False, "gate_unreadable")
    if content != LIVE_CONFIRMATION + "\n":
        return LiveGateInspection(False, "gate_confirmation_invalid")
    return LiveGateInspection(True, "enabled")
