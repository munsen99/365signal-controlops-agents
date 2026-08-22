"""Explicit Phase-C mainnet read-only readiness probe.

This process has no signing key, signer token, HMAC key, or live-spend mutation
authority. It is safe to run before operator authorization of a live transfer.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from solders.pubkey import Pubkey
from spl.token.instructions import get_associated_token_address

from aea.config import load_policy
from aea.signer.live_gate import inspect_live_spend_gate
from aea.wallet.solana import (
    CANONICAL_MAINNET_USDC_MINT,
    MAINNET_GENESIS_HASH,
    SolanaConfig,
    SolanaWallet,
)


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required Phase-C read-only setting: {name}")
    return value


def read_rpc_url() -> str:
    path = Path(required("AEA_SOLANA_RPC_URL_FILE"))
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("RPC URL secret must be a regular non-symlink file")
    return path.read_text(encoding="utf-8").rstrip("\n")


async def run() -> dict[str, object]:
    policy = load_policy(policy_path=Path(required("AEA_POLICY_FILE")),
                         destinations_path=Path(required("AEA_DESTINATIONS_FILE")))
    if policy.document.wallet_phase != "C":
        raise RuntimeError("read-only probe requires wallet_phase C")
    owner = required("AEA_SOLANA_PUBLIC_WALLET")
    mint = required("AEA_SOLANA_TOKEN_MINT")
    destination_owner = required("AEA_SOLANA_DESTINATION_OWNER")
    source = str(get_associated_token_address(Pubkey.from_string(owner), Pubkey.from_string(mint)))
    destination = str(get_associated_token_address(
        Pubkey.from_string(destination_owner), Pubkey.from_string(mint)))
    if source != required("AEA_SOLANA_SOURCE_TOKEN_ACCOUNT"):
        raise RuntimeError("configured source ATA does not match wallet/mint derivation")
    if mint != CANONICAL_MAINNET_USDC_MINT:
        raise RuntimeError("configured mint is not canonical mainnet USDC")
    config = SolanaConfig.model_validate({
        "wallet_phase": "C", "network": required("AEA_SOLANA_NETWORK"),
        "rpc_url": read_rpc_url(), "public_wallet": owner, "token_mint": mint,
        "token_decimals": 6, "source_token_account": source,
        "commitment": required("AEA_SOLANA_COMMITMENT"),
        "confirmation_timeout_seconds": 120, "rpc_timeout_seconds": 30,
    })
    wallet = SolanaWallet()
    await wallet.validate(config)
    balances = await wallet.balances(config)
    async with httpx.AsyncClient(timeout=float(config.rpc_timeout_seconds)) as raw_client:
        health_response = await raw_client.post(config.rpc_url, json={
            "jsonrpc": "2.0", "id": 1, "method": "getHealth",
        })
        blockhash_response = await raw_client.post(config.rpc_url, json={
            "jsonrpc": "2.0", "id": 2, "method": "getLatestBlockhash",
            "params": [{"commitment": "finalized"}],
        })
    health_response.raise_for_status()
    blockhash_response.raise_for_status()
    health_body = health_response.json()
    blockhash_body = blockhash_response.json()
    if health_body.get("result") != "ok":
        raise RuntimeError("mainnet RPC health check failed")
    latest = blockhash_body.get("result", {}).get("value")
    if not isinstance(latest, dict) or not latest.get("blockhash"):
        raise RuntimeError("mainnet RPC finalized blockhash check failed")
    client = await wallet._client(config)
    try:
        version = await client.get_version()
        genesis = await client.get_genesis_hash()
    finally:
        await client.close()
    if str(genesis.value) != MAINNET_GENESIS_HASH:
        raise RuntimeError("mainnet genesis mismatch")
    gate = inspect_live_spend_gate(os.environ.get("AEA_LIVE_SPEND_FILE"),
                                   operator_intent=os.environ.get("AEA_LIVE_WALLET"))
    if gate.enabled:
        raise RuntimeError("read-only readiness must run with live spending disabled")
    return {
        "result": "PASS", "stage": "implementation/read-only-readiness",
        "network": config.network, "genesis_hash": str(genesis.value),
        "rpc_version": str(version.value), "rpc_endpoint": config.sanitized_rpc_endpoint(),
        "rpc_health": "ok", "finalized_blockhash_available": True,
        "last_valid_block_height": int(latest["lastValidBlockHeight"]),
        "public_wallet": owner, "canonical_usdc_mint": mint,
        "source_ata": source, "approved_destination_owner": destination_owner,
        "approved_destination_ata": destination,
        "balances": {key: str(value) for key, value in balances.items()},
        "live_spend_enabled": False, "live_spend_reason": gate.reason,
        "policy_version": policy.document.policy_version, "policy_hash": policy.policy_hash,
        "confirmation_requirement": config.commitment,
        "private_key_available_to_probe": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    result = asyncio.run(run())
    output = Path(required("AEA_SOLANA_EVIDENCE_FILE"))
    output.parent.mkdir(parents=True, exist_ok=False)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "network": result["network"],
                      "public_wallet": result["public_wallet"],
                      "live_spend_enabled": result["live_spend_enabled"]}))


if __name__ == "__main__":
    main()
