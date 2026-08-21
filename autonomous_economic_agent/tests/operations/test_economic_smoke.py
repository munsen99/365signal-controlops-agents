"""PR10 compose mount matrix smoke."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tests" / "operations" / "economic-smoke.sh"


def test_economic_smoke_mount_matrix() -> None:
    proc = subprocess.run(["bash", str(SCRIPT)], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
