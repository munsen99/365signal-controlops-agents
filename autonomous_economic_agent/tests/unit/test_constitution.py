"""Canonical constitution and Hermes copy must be byte-identical."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPO_ROOT / "autonomous_economic_agent" / "constitution" / "SOUL.md"
PROFILE_COPY = REPO_ROOT / "agents" / "economic-agent" / "runtime" / "SOUL.md"


def test_soul_copies_are_byte_identical() -> None:
    canonical = CANONICAL.read_bytes()
    profile = PROFILE_COPY.read_bytes()
    assert canonical == profile
    assert canonical.startswith(b"# Autonomous Economic Agent\n")
    assert b"constitution/v0.1.0" in canonical
    assert b"AEA_MODEL_TOKEN" not in canonical
    assert b"seed phrase" in canonical


def test_constitution_forbids_live_wallet_language_as_instruction() -> None:
    text = CANONICAL.read_text(encoding="utf-8")
    assert "You do not have\na wallet, a signer, or a policy editor." in text
    assert "USDC is the unit of account" in text
