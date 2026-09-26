from __future__ import annotations

import asyncio
import runpy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from aea.signer.freeze import inspect_freeze
from aea.wallet.evm import BASE_SEPOLIA_USDC, EvmConfig

ROOT = Path(__file__).resolve().parents[2]
NS = runpy.run_path(str(ROOT / "scripts/phase-e-baseline"))
require_operator_preconditions = NS["require_operator_preconditions"]
validate_existing_baseline = NS["validate_existing_baseline"]
baseline_payload = NS["baseline_payload"]
read_wallet = NS["read_wallet"]


def test_exact_confirmation_and_isolated_database_required(tmp_path: Path) -> None:
    require_operator_preconditions(confirmation="CONFIRM_PHASE_E_BASELINE",
        target="controlops_phase_e", live_intent="0", gate=tmp_path / "gate")
    with pytest.raises(SystemExit, match="exact confirmation"):
        require_operator_preconditions(confirmation="yes", target="controlops_phase_e",
            live_intent="0", gate=None)
    for forbidden in ("controlops", "controlops_phase_c", "controlops_phase_e_other"):
        with pytest.raises(SystemExit, match="isolated database"):
            require_operator_preconditions(confirmation="CONFIRM_PHASE_E_BASELINE",
                target=forbidden, live_intent="0", gate=None)


def test_active_intent_or_gate_rejected(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="disable Phase-E spend intent"):
        require_operator_preconditions(confirmation="CONFIRM_PHASE_E_BASELINE",
            target="controlops_phase_e", live_intent="1", gate=None)
    gate = tmp_path / "CONFIRM_LIVE_USDC_TRANSFER"
    gate.write_text("disabled tests must reject presence", encoding="utf-8")
    with pytest.raises(SystemExit, match="gate must be absent"):
        require_operator_preconditions(confirmation="CONFIRM_PHASE_E_BASELINE",
            target="controlops_phase_e", live_intent="0", gate=gate)
    gate.unlink()
    gate.symlink_to(tmp_path / "missing")
    with pytest.raises(SystemExit, match="gate must be absent"):
        require_operator_preconditions(confirmation="CONFIRM_PHASE_E_BASELINE",
            target="controlops_phase_e", live_intent="0", gate=gate)


def test_new_baseline_and_exact_repeat_are_safe() -> None:
    expected = {"USDC": Decimal("1.000000"), "ETH": Decimal("0.00010000")}
    assert validate_existing_baseline(history=0, accounts={}, transfers=[], expected=expected) is False
    accounts = {asset: (value, value) for asset, value in expected.items()}
    transfers = [("ETH", expected["ETH"], "fee_reserve"),
                 ("USDC", expected["USDC"], "opening_capital")]
    assert validate_existing_baseline(history=0, accounts=accounts,
        transfers=transfers, expected=expected) is True
    with pytest.raises(SystemExit, match="incompatible economic history"):
        validate_existing_baseline(history=1, accounts=accounts, transfers=transfers, expected=expected)
    with pytest.raises(SystemExit, match="conflicts"):
        validate_existing_baseline(history=0,
            accounts={**accounts, "USDC": (Decimal("2"), Decimal("2"))},
            transfers=transfers, expected=expected)


def test_payload_classifies_capital_and_fee_reserve_without_revenue() -> None:
    config = EvmConfig(network="base-sepolia", chain_id=84532,
        rpc_url="https://sepolia.base.org", public_wallet="0x7fc8ACC21e601c488e6EE4eE39AD67d3ecA12a7e",
        token_contract=BASE_SEPOLIA_USDC)
    payload = baseline_payload(config=config, usdc=Decimal("1"), native=Decimal("0.0001"))
    assert payload["usdc_opening_capital"] == "1.000000"
    assert payload["eth_fee_reserve"] == "0.0001"
    assert payload["revenue_created"] is False and payload["pnl_created"] is False
    assert payload["historical_transactions_fabricated"] is False
    assert payload["chain_id"] == 84532 and payload["usdc_contract"] == BASE_SEPOLIA_USDC


def test_chain_or_token_mismatch_fails_before_rpc() -> None:
    evm = SimpleNamespace(network="base-sepolia", chain_id=8453, usdc_contract=BASE_SEPOLIA_USDC,
        decimals=6, confirmations=12, max_gas_limit=100000, max_fee_per_gas_wei=2000000000,
        max_priority_fee_per_gas_wei=100000000, max_total_fee_wei=200000000000000)
    policy = SimpleNamespace(document=SimpleNamespace(wallet_phase="E", evm=evm))
    with pytest.raises(ValidationError):
        asyncio.run(read_wallet(policy=policy, rpc_url="https://sepolia.base.org",
            public_wallet="0x7fc8ACC21e601c488e6EE4eE39AD67d3ecA12a7e"))


def test_supervisor_unavailable_is_fail_closed(tmp_path: Path) -> None:
    assert inspect_freeze(tmp_path / "FREEZE", db_frozen=None).frozen is True
