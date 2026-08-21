"""Authoritative freeze-file writer under the freeze directory.

Writes a regular file only. Never follows symlinks. Missing, unreadable,
symlinked, or wrong-type paths fail closed. The inspector treats any
regular FREEZE file as frozen regardless of JSON contents.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from aea.signer.freeze import FreezeInspection, inspect_freeze_path


class FreezeFileError(RuntimeError):
    """Freeze file could not be written or removed fail-closed."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def resolve_freeze_targets(freeze_path: Path | str | None) -> tuple[Path, Path]:
    if freeze_path is None or freeze_path == "":
        raise FreezeFileError("missing_path")
    path = Path(freeze_path)
    try:
        if path.is_symlink():
            raise FreezeFileError("symlink")
        st = os.lstat(path)
    except FreezeFileError:
        raise
    except FileNotFoundError:
        return path.parent, path
    except OSError as exc:
        raise FreezeFileError("unreadable") from exc
    if stat.S_ISLNK(st.st_mode):
        raise FreezeFileError("symlink")
    if stat.S_ISDIR(st.st_mode):
        if path.name == "FREEZE":
            raise FreezeFileError("malformed")
        return path, path / "FREEZE"
    if stat.S_ISREG(st.st_mode):
        return path.parent, path
    raise FreezeFileError("malformed")


def _require_real_dir(directory: Path) -> None:
    if directory.is_symlink():
        raise FreezeFileError("symlink")
    try:
        st = os.lstat(directory)
    except FileNotFoundError as exc:
        raise FreezeFileError("missing_dir") from exc
    if stat.S_ISLNK(st.st_mode):
        raise FreezeFileError("symlink")
    if not stat.S_ISDIR(st.st_mode):
        raise FreezeFileError("malformed")
    if not os.access(directory, os.R_OK | os.W_OK | os.X_OK):
        raise FreezeFileError("unreadable")


def _lstat_file(path: Path) -> os.stat_result | None:
    if path.is_symlink():
        raise FreezeFileError("symlink")
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode):
        raise FreezeFileError("symlink")
    return st


def write_freeze_file(freeze_path: Path | str | None, payload: dict[str, Any]) -> Path:
    """Create or replace FREEZE as a regular 0600 file. Fail closed on symlink."""
    directory, freeze_file = resolve_freeze_targets(freeze_path)
    _require_real_dir(directory)
    existing = _lstat_file(freeze_file)
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise FreezeFileError("malformed")
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
    tmp = directory / f".FREEZE.tmp.{os.getpid()}.{os.getuid()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = None
    try:
        fd = os.open(tmp, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(body)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, freeze_file)
    except OSError as exc:
        raise FreezeFileError("unreadable") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if tmp.exists() or tmp.is_symlink():
            try:
                tmp.unlink()
            except OSError:
                pass
    written = _lstat_file(freeze_file)
    if written is None or not stat.S_ISREG(written.st_mode):
        raise FreezeFileError("malformed")
    return freeze_file


def remove_freeze_file(freeze_path: Path | str | None) -> None:
    """Unlink FREEZE if it is a regular file. Symlink/wrong type fail closed."""
    directory, freeze_file = resolve_freeze_targets(freeze_path)
    _require_real_dir(directory)
    existing = _lstat_file(freeze_file)
    if existing is None:
        return
    if not stat.S_ISREG(existing.st_mode):
        raise FreezeFileError("malformed")
    try:
        freeze_file.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise FreezeFileError("unreadable") from exc


def inspect_written_freeze(freeze_path: Path | str | None) -> FreezeInspection:
    return inspect_freeze_path(freeze_path)
