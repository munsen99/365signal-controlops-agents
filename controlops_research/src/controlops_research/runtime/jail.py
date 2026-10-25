"""Host bubblewrap exec. The jail has no network and no GPU device nodes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import shutil
import subprocess

from .config import RUNTIME_DIR_NAMES, ensure_runtime_dirs
from .errors import RuntimeFailure

_SUBSTRATE = (
    "--die-with-parent",
    "--new-session",
    "--unshare-all",
    "--cap-drop",
    "ALL",
    "--clearenv",
    "--setenv",
    "PATH",
    "/usr/bin:/bin",
    "--setenv",
    "HOME",
    "/tmp",
    "--setenv",
    "TMPDIR",
    "/tmp",
    "--setenv",
    "LANG",
    "C.UTF-8",
    "--ro-bind",
    "/usr",
    "/usr",
    "--symlink",
    "usr/bin",
    "/bin",
    "--symlink",
    "usr/lib",
    "/lib",
    "--symlink",
    "usr/lib64",
    "/lib64",
    "--symlink",
    "usr/sbin",
    "/sbin",
    "--proc",
    "/proc",
    "--dev",
    "/dev",
    "--tmpfs",
    "/tmp",
    "--dir",
    "/opt",
    "--dir",
    "/opt/data",
    "--dir",
    "/opt/data/workspace",
    "--dir",
    "/opt/data/workspace/runtime",
)


def bwrap_argv(workspace: Path, command: Sequence[str]) -> list[str]:
    """Build the fixed jail argv. Environment cannot add `--share-net`."""
    if not command:
        raise RuntimeFailure("CONFIG_INVALID", "sandbox command is required")
    root = workspace / "runtime"
    argv = ["bwrap", *_SUBSTRATE]
    for name in RUNTIME_DIR_NAMES:
        argv.extend(["--bind", str(root / name), f"/opt/data/workspace/runtime/{name}"])
    argv.extend(["--chdir", "/opt/data/workspace/runtime/tmp", "--", *command])
    if "--share-net" in argv:
        raise RuntimeFailure("CONFIG_INVALID", "shared net is not available")
    return argv


def exec_command(
    command: Sequence[str],
    *,
    workspace: Path | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `command` inside the jail on the host. LM Studio is not contacted."""
    if shutil.which("bwrap") is None:
        raise RuntimeFailure("BWRAP_NOT_AVAILABLE", "bubblewrap is not installed")
    root = ensure_runtime_dirs(workspace)
    argv = bwrap_argv(root.parent, command)
    try:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeFailure("CONFIG_INVALID", "sandbox command timed out") from error
