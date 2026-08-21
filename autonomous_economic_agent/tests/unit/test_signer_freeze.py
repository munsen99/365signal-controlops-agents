"""Fail-closed freeze inspector (file, symlink, malformed, DB snapshot)."""

from __future__ import annotations

import os
from pathlib import Path

from aea.signer.freeze import inspect_freeze, inspect_freeze_path


def test_missing_path_fail_closed() -> None:
    result = inspect_freeze_path(None)
    assert result.frozen is True
    assert result.detail == "missing_path"


def test_empty_path_fail_closed() -> None:
    result = inspect_freeze_path("")
    assert result.frozen is True
    assert result.detail == "missing_path"


def test_missing_dir_fail_closed(tmp_path: Path) -> None:
    result = inspect_freeze_path(tmp_path / "nope" / "FREEZE")
    assert result.frozen is True
    assert result.detail == "missing_dir"


def test_readable_dir_without_freeze_file_is_not_frozen(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    result = inspect_freeze_path(freeze_dir / "FREEZE")
    assert result.frozen is False
    assert result.detail == "not_frozen"
    assert inspect_freeze_path(freeze_dir).frozen is False


def test_freeze_file_present(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    (freeze_dir / "FREEZE").write_text("1\n", encoding="utf-8")
    result = inspect_freeze_path(freeze_dir / "FREEZE")
    assert result.frozen is True
    assert result.detail == "file_present"


def test_freeze_path_symlink_fail_closed(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "FREEZE").write_text("", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real)
    assert inspect_freeze_path(link).frozen is True
    assert inspect_freeze_path(link).detail == "symlink"
    file_link = tmp_path / "FREEZE"
    file_link.symlink_to(real / "FREEZE")
    assert inspect_freeze_path(file_link).detail == "symlink"
    parent_link = tmp_path / "parentlink"
    parent_link.symlink_to(real)
    assert inspect_freeze_path(parent_link / "FREEZE").detail == "symlink"


def test_malformed_freeze_is_directory(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    (freeze_dir / "FREEZE").mkdir()
    result = inspect_freeze_path(freeze_dir / "FREEZE")
    assert result.frozen is True
    assert result.detail == "malformed"


def test_malformed_freeze_fifo(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    os.mkfifo(freeze_dir / "FREEZE")
    result = inspect_freeze_path(freeze_dir / "FREEZE")
    assert result.frozen is True
    assert result.detail == "malformed"


def test_unreadable_freeze_dir(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    os.chmod(freeze_dir, 0)
    try:
        result = inspect_freeze_path(freeze_dir / "FREEZE")
        assert result.frozen is True
        assert result.detail == "unreadable"
    finally:
        os.chmod(freeze_dir, 0o700)


def test_db_frozen_or_file_frozen(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    path = freeze_dir / "FREEZE"
    assert inspect_freeze(path, db_frozen=False).frozen is False
    assert inspect_freeze(path, db_frozen=True).frozen is True
    assert inspect_freeze(path, db_frozen=True).detail == "inconsistent"
    (path).write_text("", encoding="utf-8")
    both = inspect_freeze(path, db_frozen=True)
    assert both.frozen is True
    assert both.detail == "file_present"
    stale = inspect_freeze(path, db_frozen=False)
    assert stale.frozen is True
    assert stale.detail == "inconsistent"


def test_unreadable_or_malformed_db_fail_closed(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    path = freeze_dir / "FREEZE"
    unread = inspect_freeze(path, db_frozen=None)
    assert unread.frozen is True
    assert unread.detail == "unreadable_db"
    malformed = inspect_freeze(path, db_frozen="yes")
    assert malformed.frozen is True
    assert malformed.detail == "malformed_db"


def test_file_hard_fail_wins_over_db(tmp_path: Path) -> None:
    result = inspect_freeze(tmp_path / "missing" / "FREEZE", db_frozen=False)
    assert result.frozen is True
    assert result.detail == "missing_dir"
