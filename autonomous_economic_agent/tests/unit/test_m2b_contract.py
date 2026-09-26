from __future__ import annotations

from pathlib import Path

import yaml

from aea.config import load_policy
from aea.wallet.evm import BASE_MAINNET_CHAIN_ID, BASE_MAINNET_USDC

ROOT = Path(__file__).resolve().parents[2]


def test_phase_e_policy_is_exact_and_contract_calls_disabled() -> None:
    loaded = load_policy(policy_path=ROOT / "config/policy.evm.example.yaml",
        destinations_path=ROOT / "config/destinations.evm.example.yaml")
    assert loaded.document.wallet_phase == "E"
    assert loaded.document.evm is not None
    assert loaded.document.evm.chain_id == BASE_MAINNET_CHAIN_ID
    assert loaded.document.evm.usdc_contract == BASE_MAINNET_USDC
    assert loaded.document.evm.operation == "erc20_transfer"
    assert loaded.document.evm.contract_calls_enabled is False
    assert loaded.document.limits.max_outbound_usdc == loaded.document.limits.max_daily_discretionary_usdc


def test_evm_compose_mounts_private_key_only_into_signer() -> None:
    compose = yaml.safe_load((ROOT / "ops/compose.evm.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    key_marker = "evm-signer.key"
    state_marker = "evm-signer-state"
    recipients = []
    for name, service in services.items():
        combined = repr(service)
        if key_marker in combined or state_marker in combined:
            recipients.append(name)
    assert recipients == ["economic-signer"]
    assert "AEA_EVM_SIGNER_KEY_FILE" not in repr(services["economic-control"])
    assert "AEA_EVM_SIGNER_KEY_FILE" not in repr(services["economic-policy"])
    assert "AEA_EVM_SIGNER_KEY_FILE" not in repr(services["economic-wallet"])
    assert "AEA_LIVE_SPEND_FILE" not in repr(services["economic-control"])


def test_nine_model_tools_are_unchanged_and_no_chain_escape() -> None:
    from aea import NINE_TOOLS
    assert len(NINE_TOOLS) == 9
    assert not any(name in NINE_TOOLS for name in (
        "sign", "sign_message", "send_transaction", "call_contract", "http", "shell"))


def test_pr15_research_artifact_remains_present_and_unmodified_by_runtime() -> None:
    research = ROOT / "docs/m3-marketplace-research.md"
    assert research.is_file()
    text = research.read_text(encoding="utf-8")
    assert "MARKETPLACE SELECTION: BLOCKED" in text


def test_control_preserves_evm_native_fee_reserve_balance() -> None:
    from decimal import Decimal

    from aea.control.app import _normalise_wallet_balances

    assert _normalise_wallet_balances({"balances": {
        "USDC": "1.000000", "ETH": "0.000100", "metadata": "ignored",
    }}) == {"USDC": Decimal("1.000000"), "ETH": Decimal("0.000100")}


def test_eth_asset_format_preserves_wei_precision() -> None:
    from decimal import Decimal

    from aea.types import format_asset_amount

    assert format_asset_amount(Decimal("0.000099593798219532"), "ETH") == "0.000099593798219532"
    assert format_asset_amount(Decimal("0.000000406201780468"), "ETH") == "0.000000406201780468"
