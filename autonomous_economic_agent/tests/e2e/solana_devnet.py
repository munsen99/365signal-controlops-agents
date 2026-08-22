"""Explicit genuine Phase-B probe. Not collected by normal pytest.

Run only with protected ``AEA_*`` configuration. It never prints or stores key,
HMAC, or RPC credentials. Failure is a PR13 blocker, not a skipped acceptance.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from solders.pubkey import Pubkey
from spl.token.instructions import get_associated_token_address

from aea.config import load_policy
from aea.signer.backend import ApprovedRequest, SignRequest, canonical_approved_hash, compute_request_hmac
from aea.signer.solana import SolanaSigner, load_protected_keypair
from aea.wallet.solana import SolanaConfig, SolanaWallet


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required Phase-B setting: {name}")
    return value


async def run() -> dict:
    policy = load_policy(policy_path=Path(required("AEA_POLICY_FILE")),
                         destinations_path=Path(required("AEA_DESTINATIONS_FILE")))
    if policy.document.wallet_phase != "B":
        raise RuntimeError("genuine probe requires wallet_phase B")
    config = SolanaConfig.model_validate({
        "wallet_phase": "B", "network": required("AEA_SOLANA_NETWORK"),
        "rpc_url": required("AEA_SOLANA_RPC_URL"), "public_wallet": required("AEA_SOLANA_PUBLIC_WALLET"),
        "token_mint": required("AEA_SOLANA_TOKEN_MINT"),
        "token_decimals": required("AEA_SOLANA_TOKEN_DECIMALS"),
        "source_token_account": required("AEA_SOLANA_SOURCE_TOKEN_ACCOUNT"),
        "commitment": os.environ.get("AEA_SOLANA_COMMITMENT", "confirmed"),
        "confirmation_timeout_seconds": os.environ.get("AEA_SOLANA_CONFIRMATION_TIMEOUT", "90"),
        "rpc_timeout_seconds": os.environ.get("AEA_SOLANA_RPC_TIMEOUT", "20"),
    })
    rpc = SolanaWallet()
    await rpc.validate(config)
    keypair = load_protected_keypair(required("AEA_SIGNER_KEY_FILE"))
    destination_id = required("AEA_SOLANA_DESTINATION_ID")
    signer = SolanaSigner(freeze_path=required("AEA_FREEZE_PATH"),
        expected_policy_version=policy.document.policy_version, expected_policy_hash=policy.policy_hash,
        hmac_key=required("AEA_SIGNER_HMAC_KEY"), config=config, keypair=keypair, rpc=rpc,
        approved_destinations={destination_id: required("AEA_SOLANA_DESTINATION_OWNER")})
    before = await rpc.balances(config)
    amount = required("AEA_SOLANA_TEST_AMOUNT")
    destination_owner = required("AEA_SOLANA_DESTINATION_OWNER")
    destination_ata = str(get_associated_token_address(
        Pubkey.from_string(destination_owner), Pubkey.from_string(config.token_mint)))
    from decimal import Decimal
    base_units = int(Decimal(amount) * (Decimal(10) ** config.token_decimals))
    approved = ApprovedRequest.model_validate({
        "request_id": str(uuid4()), "amount": amount, "asset": "USDC", "destination": destination_id,
        "purpose": "pr13_genuine_devnet_transfer", "job_id": str(uuid4()),
        "policy_version": policy.document.policy_version, "policy_hash": policy.policy_hash,
        "approved_amount": amount, "approved_at": datetime.now(timezone.utc).isoformat(),
        "correlation_id": str(uuid4()),
        "phase_b_context": {
            "network": config.network, "payer": config.public_wallet,
            "source_mint": config.token_mint, "source_token_account": config.source_token_account,
            "destination_owner": destination_owner, "destination_token_account": destination_ata,
            "amount_base_units": base_units, "decimals": config.token_decimals,
        },
    })
    digest = canonical_approved_hash(approved)
    request = SignRequest(approved_request=approved, canonical_hash=digest,
        policy_version=approved.policy_version,
        request_hmac=compute_request_hmac(required("AEA_SIGNER_HMAC_KEY"), approved_request=approved,
            canonical_hash=digest, policy_version=approved.policy_version))
    signed = await signer.sign(request)
    if not signed.ok or not signed.tx_id:
        raise RuntimeError(f"Phase-B signer failed closed: {signed.code}")
    evidence = await rpc.lookup(config, signed.tx_id)
    after = await rpc.balances(config)
    expected = before["USDC"] - approved.amount
    if after["USDC"] != expected:
        raise RuntimeError("source token balance did not decrease by approved amount")
    if evidence.state not in {"confirmed", "finalized"}:
        raise RuntimeError("transaction lacks required chain confirmation")
    return {
        "result": "PASS", "wallet_phase": "B", "network": config.network,
        "rpc_endpoint": config.sanitized_rpc_endpoint(), "public_wallet": config.public_wallet,
        "test_token_mint": config.token_mint, "test_value_not_real_usdc": True,
        "policy_version": policy.document.policy_version, "policy_hash": policy.policy_hash,
        "amount": amount, "transaction_signature": signed.tx_id, "confirmation_state": evidence.state,
        "slot": evidence.slot, "fee_lamports": evidence.fee_lamports,
        "before": {k: str(v) for k, v in before.items()}, "after": {k: str(v) for k, v in after.items()},
        "source_balance_delta_reconciled": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    result = asyncio.run(run())
    output = Path(required("AEA_SOLANA_EVIDENCE_FILE"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "transaction_signature": result["transaction_signature"]}))


if __name__ == "__main__":
    main()
