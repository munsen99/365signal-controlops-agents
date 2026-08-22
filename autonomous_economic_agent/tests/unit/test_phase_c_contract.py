from pathlib import Path

import yaml

from aea.config import load_policy
from aea.wallet.solana import CANONICAL_MAINNET_USDC_MINT, MAINNET_GENESIS_HASH


ROOT = Path(__file__).resolve().parents[2]


def test_phase_c_profile_is_more_restrictive_and_mainnet_exact() -> None:
    loaded = load_policy(
        policy_path=ROOT / "config/policy.phase-c.example.yaml",
        destinations_path=ROOT / "config/destinations.phase-c.example.yaml",
    )
    assert loaded.document.wallet_phase == "C"
    assert str(loaded.document.limits.max_outbound_usdc) == "0.010000"
    assert str(loaded.document.limits.max_daily_discretionary_usdc) == "0.010000"
    assert str(loaded.document.limits.max_capital_at_risk_usdc) == "0.010000"
    assert loaded.document.assets.permitted_treasury == ["USDC"]
    assert MAINNET_GENESIS_HASH == "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
    assert CANONICAL_MAINNET_USDC_MINT == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def test_phase_c_compose_keeps_key_and_live_gate_signer_only() -> None:
    compose = yaml.safe_load((ROOT / "ops/compose.phase-c.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    signer = services["economic-signer"]
    assert signer["environment"]["AEA_WALLET_PHASE"] == "C"
    assert signer["environment"]["AEA_LIVE_SPEND_FILE"]
    assert signer["environment"]["AEA_SIGNER_KEY_FILE"]
    for name, service in services.items():
        if name == "economic-signer":
            continue
        serialized = yaml.safe_dump(service)
        assert "signer.key" not in serialized
        assert "AEA_SIGNER_KEY_FILE" not in serialized
        assert "AEA_LIVE_SPEND_FILE" not in serialized
        assert "CONFIRM_LIVE_USDC_TRANSFER" not in serialized


def test_operator_smoke_has_no_force_or_automatic_confirmation() -> None:
    script = (ROOT / "scripts/phase-c-live-smoke").read_text(encoding="utf-8")
    assert "CONFIRM_LIVE_USDC_TRANSFER" in script
    assert "--force" not in script
    assert "yes" not in script
    assert "sendTransaction" not in script
    assert "prepare_and_sign" not in script
    assert "solana transfer" not in script
