"""Non-blocking exclusive lock for infer calls."""

from __future__ import annotations

import fcntl
from pathlib import Path

from .config import ensure_runtime_dirs
from .errors import RuntimeFailure


class ModelLock:
    """Hold `$WORKSPACE/runtime/locks/model.lock` for one infer request."""

    def __init__(self, workspace: Path | None = None) -> None:
        root = ensure_runtime_dirs(workspace)
        self.path = root / "locks" / "model.lock"
        self._handle = None

    def __enter__(self) -> ModelLock:
        handle = self.path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.close()
            raise RuntimeFailure("MODEL_CONTENTION", "model lock is held") from error
        except OSError as error:
            handle.close()
            raise RuntimeFailure("CONFIG_INVALID", "model lock is unavailable") from error
        self._handle = handle
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
