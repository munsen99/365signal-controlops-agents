"""Freeze-file writer fails closed on symlink, missing dir, wrong type."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aea.supervisor.freeze_file import (
    FreezeFileError,
    remove_freeze_file,
    write_freeze_file,
)
from aea.supervisor.schemas import (
    EnableSignerRequest,
    PermitLoopRequest,
    SupervisorMutationRequest,
    UnfreezeRequest,
)


def test_write_and_remove_regular_file(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    path = write_freeze_file(
        freeze_dir / "FREEZE",
        {"frozen": True, "reason": "test", "actor": "operator"},
    )
    assert path.is_file()
    assert not path.is_symlink()
    remove_freeze_file(freeze_dir / "FREEZE")
    assert not path.exists()


def test_write_rejects_symlink_dir(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(FreezeFileError) as exc:
        write_freeze_file(link / "FREEZE", {"frozen": True})
    assert exc.value.detail == "symlink"


def test_write_rejects_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(FreezeFileError) as exc:
        write_freeze_file(tmp_path / "nope" / "FREEZE", {"frozen": True})
    assert exc.value.detail == "missing_dir"


def test_remove_rejects_symlink_file(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    target = freeze_dir / "target"
    target.write_text("1\n", encoding="utf-8")
    link = freeze_dir / "FREEZE"
    link.symlink_to(target)
    with pytest.raises(FreezeFileError) as exc:
        remove_freeze_file(link)
    assert exc.value.detail == "symlink"
    assert target.exists()


def test_write_rejects_freeze_directory(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    (freeze_dir / "FREEZE").mkdir()
    with pytest.raises(FreezeFileError):
        write_freeze_file(freeze_dir / "FREEZE", {"frozen": True})


def test_unreadable_dir(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    os.chmod(freeze_dir, 0)
    try:
        with pytest.raises(FreezeFileError) as exc:
            write_freeze_file(freeze_dir / "FREEZE", {"frozen": True})
        assert exc.value.detail in {"unreadable", "missing_dir"}
    finally:
        os.chmod(freeze_dir, 0o700)


def test_mutation_dto_forbids_force_and_extra() -> None:
    with pytest.raises(Exception):
        SupervisorMutationRequest.model_validate(
            {
                "reason": "freeze now",
                "idempotency_key": "freeze-01-key",
                "force": True,
            }
        )
    with pytest.raises(Exception):
        UnfreezeRequest.model_validate(
            {
                "reason": "resume",
                "idempotency_key": "unfreeze01",
                "confirm": "unfreeze",
            }
        )
    ok = UnfreezeRequest.model_validate(
        {
            "reason": "resume spend",
            "idempotency_key": "unfreeze01",
            "confirm": "UNFREEZE",
        }
    )
    assert ok.confirm == "UNFREEZE"
    with pytest.raises(Exception):
        EnableSignerRequest.model_validate(
            {
                "reason": "turn signer on",
                "idempotency_key": "enable-01",
                "confirm": "UNFREEZE",
            }
        )
    with pytest.raises(Exception):
        PermitLoopRequest.model_validate(
            {
                "reason": "resume loop",
                "idempotency_key": "permit-01",
            }
        )
    assert (
        EnableSignerRequest.model_validate(
            {
                "reason": "turn signer on",
                "idempotency_key": "enable-01",
                "confirm": "ENABLE_SIGNER",
            }
        ).confirm
        == "ENABLE_SIGNER"
    )
    assert (
        PermitLoopRequest.model_validate(
            {
                "reason": "resume loop",
                "idempotency_key": "permit-01",
                "confirm": "PERMIT_LOOP",
            }
        ).confirm
        == "PERMIT_LOOP"
    )
