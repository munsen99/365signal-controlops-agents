"""`python -m controlops_research.runtime doctor`."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import shutil
import sys

from .errors import RuntimeFailure
from .http_client import Transport
from .probe import LMStudioProbe


def doctor(
    *,
    transport: Transport | None = None,
    environ: Mapping[str, str] | None = None,
    workspace: Path | None = None,
    stdout=None,
    stderr=None,
) -> int:
    """Check bubblewrap and exact model readiness. Exit 0 only when both hold.

    `workspace` is accepted so callers share the runtime root. Doctor does not
    mount a jail and does not POST.
    """
    del workspace
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    failures: list[str] = []
    if shutil.which("bwrap") is None:
        failures.append("BWRAP_NOT_AVAILABLE")
    try:
        model = LMStudioProbe(transport=transport, environ=environ).require_ready()
    except RuntimeFailure as error:
        failures.append(error.code)
        model = ""
    if failures:
        for code in dict.fromkeys(failures):
            print(code, file=err)
        return 1
    print(f"READY {model}", file=out)
    return 0
