"""Independent freeze-state inspector. Fail closed.

M0 §4.4 / §5.2:
- Missing FREEZE file with a readable, real directory → not frozen.
- Unreadable or missing freeze directory → frozen.
- FREEZE present as a regular file → frozen (AGENT_FROZEN).
- Symlink freeze path or freeze directory → frozen (do not follow).
- Malformed FREEZE (not a regular file) → frozen.
- Configured path missing entirely → frozen (signer cannot prove unfrozen).
- DB frozen OR file frozen → frozen. Readable disagreement → frozen
  (inconsistent). Unreadable/malformed DB snapshot → frozen.

The inspector never consults the policy engine, LLM, or wallet.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_UNSET = object()


@dataclass(frozen=True)
class FreezeInspection:
    frozen: bool
    detail: str


def inspect_freeze(
    freeze_path: Path | str | None,
    *,
    db_frozen: Any = _UNSET,
) -> FreezeInspection:
    """Combine freeze-file inspection with an optional DB snapshot.

    ``db_frozen`` omitted: file only. ``None``: DB unreadable (fail closed).
    Non-bool values: malformed DB (fail closed).
    """
    file_insp = inspect_freeze_path(freeze_path)
    if db_frozen is _UNSET:
        return file_insp
    db_insp = _inspect_db(db_frozen)
    return _combine(file_insp, db_insp)


def inspect_freeze_path(freeze_path: Path | str | None) -> FreezeInspection:
    if freeze_path is None or freeze_path == "":
        return FreezeInspection(True, "missing_path")
    try:
        path = Path(freeze_path)
    except (TypeError, ValueError):
        return FreezeInspection(True, "malformed")
    try:
        return _inspect_path(path)
    except OSError:
        return FreezeInspection(True, "unreadable")


def _inspect_db(value: Any) -> FreezeInspection:
    if value is None:
        return FreezeInspection(True, "unreadable_db")
    if isinstance(value, bool):
        if value:
            return FreezeInspection(True, "db_frozen")
        return FreezeInspection(False, "not_frozen")
    return FreezeInspection(True, "malformed_db")


_FILE_HARD_FAIL = frozenset(
    {"missing_path", "missing_dir", "unreadable", "symlink", "malformed"}
)
_DB_HARD_FAIL = frozenset({"unreadable_db", "malformed_db"})


def _combine(file_insp: FreezeInspection, db_insp: FreezeInspection) -> FreezeInspection:
    if file_insp.detail in _FILE_HARD_FAIL:
        return file_insp
    if db_insp.detail in _DB_HARD_FAIL:
        return db_insp
    if file_insp.frozen != db_insp.frozen:
        return FreezeInspection(True, "inconsistent")
    if file_insp.frozen:
        return FreezeInspection(True, file_insp.detail)
    return FreezeInspection(False, "not_frozen")


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def _dir_ok(directory: Path) -> FreezeInspection | None:
    """Return a fail-closed inspection if the directory is not a real readable dir."""
    if directory.is_symlink():
        return FreezeInspection(True, "symlink")
    st = _lstat(directory)
    if st is None:
        return FreezeInspection(True, "missing_dir")
    if stat.S_ISLNK(st.st_mode):
        return FreezeInspection(True, "symlink")
    if not stat.S_ISDIR(st.st_mode):
        return FreezeInspection(True, "malformed")
    if not os.access(directory, os.R_OK | os.X_OK):
        return FreezeInspection(True, "unreadable")
    return None


def _inspect_freeze_file(freeze_file: Path, directory: Path) -> FreezeInspection:
    dir_fail = _dir_ok(directory)
    if dir_fail is not None:
        return dir_fail
    if freeze_file.is_symlink():
        return FreezeInspection(True, "symlink")
    st = _lstat(freeze_file)
    if st is None:
        return FreezeInspection(False, "not_frozen")
    if stat.S_ISLNK(st.st_mode):
        return FreezeInspection(True, "symlink")
    if stat.S_ISREG(st.st_mode):
        return FreezeInspection(True, "file_present")
    return FreezeInspection(True, "malformed")


def _inspect_path(path: Path) -> FreezeInspection:
    if path.is_symlink():
        return FreezeInspection(True, "symlink")
    st = _lstat(path)
    if st is None:
        return _inspect_freeze_file(path, path.parent)
    if stat.S_ISLNK(st.st_mode):
        return FreezeInspection(True, "symlink")
    if stat.S_ISDIR(st.st_mode):
        # AEA_FREEZE_PATH may be the freeze directory. A path named FREEZE
        # that is itself a directory is malformed, not a freeze root.
        if path.name == "FREEZE":
            return FreezeInspection(True, "malformed")
        return _inspect_freeze_file(path / "FREEZE", path)
    if stat.S_ISREG(st.st_mode):
        return _inspect_freeze_file(path, path.parent)
    return FreezeInspection(True, "malformed")
