"""Fixed PR5-R configuration. The required model has no default."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path

from .errors import RuntimeFailure

REQUIRED_MODEL_ENV = "CONTROLOPS_REQUIRED_MODEL"
LMSTUDIO_BASE = "http://127.0.0.1:1234"
WORKSPACE = Path("/mnt/Storage/AI/Hermes/workspace")
RUNTIME_DIR_NAMES = ("locks", "tmp", "out", "runs")
PROBE_TIMEOUT_SECONDS = 5.0


def required_model(environ: Mapping[str, str] | None = None) -> str:
    """Return the exact configured id, or raise CONFIG_INVALID."""
    source = os.environ if environ is None else environ
    if REQUIRED_MODEL_ENV not in source:
        raise RuntimeFailure("CONFIG_INVALID", "CONTROLOPS_REQUIRED_MODEL is unset")
    value = source[REQUIRED_MODEL_ENV]
    if not isinstance(value, str) or value.strip() == "":
        raise RuntimeFailure("CONFIG_INVALID", "CONTROLOPS_REQUIRED_MODEL is empty")
    return value


def runtime_root(workspace: Path | None = None) -> Path:
    return (workspace or WORKSPACE) / "runtime"


def ensure_runtime_dirs(workspace: Path | None = None) -> Path:
    """Create the four runtime directories on first use, mode 0700."""
    root = runtime_root(workspace)
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    for name in RUNTIME_DIR_NAMES:
        path = root / name
        path.mkdir(exist_ok=True)
        os.chmod(path, 0o700)
    return root
