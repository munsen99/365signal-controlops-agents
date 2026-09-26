"""Explicit economic-context descriptors. Isolated ledgers are never summed."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PUBLIC_ENV = frozenset(
    {
        "AEA_SOLANA_NETWORK",
        "AEA_SOLANA_PUBLIC_WALLET",
        "AEA_SOLANA_TOKEN_MINT",
        "AEA_EVM_NETWORK",
        "AEA_EVM_PUBLIC_WALLET",
        "AEA_EVM_USDC_CONTRACT",
        "AEA_EVM_CHAIN_ID",
        "AEA_POSTGRES_DB",
    }
)

_DEFAULT_ENV_DIR = Path.home() / ".config/controlops/economic"


@dataclass(frozen=True)
class ContextDescriptor:
    id: str
    purpose: str
    rail: str
    network: str | None
    database: str
    wallet_phase: str | None
    chain_id: int | None = None
    env_file: Path | None = None
    public_wallet_env: str | None = None
    token_env: str | None = None
    active: bool = True


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in _PUBLIC_ENV:
            continue
        out[key] = value.strip().strip("'").strip('"')
    return out


def public_identity(desc: ContextDescriptor) -> dict[str, Any]:
    """Owner/token identity from the context env file, then process env."""
    file_env = _parse_env_file(desc.env_file) if desc.env_file is not None else {}
    merged = dict(file_env)
    for key in _PUBLIC_ENV:
        if os.environ.get(key):
            # Process env fills gaps only; file wins for this context's own keys
            # when the file defined them.
            if key not in merged:
                merged[key] = os.environ[key]
    wallet = None
    token = None
    network = desc.network
    chain_id = desc.chain_id
    if desc.public_wallet_env:
        wallet = file_env.get(desc.public_wallet_env) or merged.get(desc.public_wallet_env)
    if desc.token_env:
        token = file_env.get(desc.token_env) or merged.get(desc.token_env)
    if desc.rail == "solana":
        network = file_env.get("AEA_SOLANA_NETWORK") or network
    if desc.rail == "evm":
        network = file_env.get("AEA_EVM_NETWORK") or network
        raw_chain = file_env.get("AEA_EVM_CHAIN_ID") or merged.get("AEA_EVM_CHAIN_ID")
        if raw_chain:
            try:
                chain_id = int(raw_chain)
            except (TypeError, ValueError):
                pass
    return {
        "public_wallet": wallet,
        "token_mint": token if desc.rail == "solana" else None,
        "token_contract": token if desc.rail == "evm" else None,
        "network": network,
        "chain_id": chain_id,
    }


def default_descriptors() -> list[ContextDescriptor]:
    return [
        ContextDescriptor(
            id="m1-default",
            purpose="core/default experiment",
            rail="mock",
            network="phase-a-mock",
            database="controlops",
            wallet_phase="A",
        ),
        ContextDescriptor(
            id="phase-c-solana",
            purpose="Solana Phase-C mainnet",
            rail="solana",
            network="mainnet-beta",
            database="controlops_phase_c",
            wallet_phase="C",
            env_file=_DEFAULT_ENV_DIR / "phase-c.env",
            public_wallet_env="AEA_SOLANA_PUBLIC_WALLET",
            token_env="AEA_SOLANA_TOKEN_MINT",
        ),
        ContextDescriptor(
            id="phase-e-evm",
            purpose="EVM Phase-E Base",
            rail="evm",
            network="base-sepolia",
            chain_id=84532,
            database="controlops_phase_e",
            wallet_phase="E",
            env_file=_DEFAULT_ENV_DIR / "evm.env",
            public_wallet_env="AEA_EVM_PUBLIC_WALLET",
            token_env="AEA_EVM_USDC_CONTRACT",
        ),
    ]
