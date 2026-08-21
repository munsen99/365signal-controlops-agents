"""M1 Gate B acceptance marker: a sanitized genuine Hermes run must pass.

There is intentionally no skip/xfail path.  A missing or failed live-model
evidence pack fails M1 rather than silently reducing Gate B to a unit test.
"""

from __future__ import annotations

import json
from pathlib import Path


EVIDENCE = Path(__file__).parent / "evidence" / "gate-b"


def test_genuine_hermes_lmstudio_gate_b_passed() -> None:
    results = sorted(EVIDENCE.glob("*/result.json"))
    assert results, "Gate B has no genuine Hermes + LM Studio evidence"
    passing = []
    for path in results:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("result") == "PASS":
            passing.append(payload)
    assert passing, "Gate B has no passing genuine Hermes + LM Studio run"
    latest = passing[-1]
    assert latest["model_session_started"] is True
    assert latest["human_economic_intervention"] is False
    assert latest["tool_registry_count"] == 9
    assert latest["wallet_ledger_reconciliation_delta"] == "0.000000"
    assert float(latest["realised_pnl_usdc"]) > 0
