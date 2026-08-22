from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import httpx
from pydantic import ValidationError
from solders.keypair import Keypair
from spl.token.instructions import get_associated_token_address

from aea.config import load_policy
from aea.signer.backend import ApprovedRequest, SignRequest, canonical_approved_hash, compute_request_hmac
from aea.signer.solana import SolanaSigner, load_protected_keypair
from aea.wallet.solana import (
    SolanaBackendError, SolanaConfig, SolanaTransferIntent, SolanaTxEvidence,
    SignedTransfer, SolanaWallet, scrub_rpc_error,
)
from aea.wallet.service import SolanaReadService

HMAC = "phase-b-hmac-key-that-is-long-enough-0001"
NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def _config(key: Keypair, mint: Keypair, source: Keypair) -> SolanaConfig:
    return SolanaConfig.model_validate({
        "wallet_phase": "B", "network": "devnet", "rpc_url": "https://rpc.invalid/?api-key=very-secret",
        "public_wallet": str(key.pubkey()), "token_mint": str(mint.pubkey()),
        "token_decimals": 6, "source_token_account": str(source.pubkey()),
        "commitment": "confirmed", "confirmation_timeout_seconds": 2,
    })


def test_phase_b_rejects_mainnet_and_credential_userinfo() -> None:
    key, mint, source = Keypair(), Keypair(), Keypair()
    body = _config(key, mint, source).model_dump()
    for network in ("mainnet", "mainnet-beta", "unknown"):
        with pytest.raises(ValidationError):
            SolanaConfig.model_validate({**body, "network": network})
    with pytest.raises(ValidationError):
        SolanaConfig.model_validate({**body, "rpc_url": "https://user:password@rpc.invalid"})


def test_rpc_key_scrubbed() -> None:
    url = "https://rpc.invalid/path?api-key=very-secret"
    text = scrub_rpc_error(f"failed at {url} very-secret", url)
    assert "very-secret" not in text
    assert "api-key" not in text


def test_key_file_permissions_shape_and_symlink(tmp_path: Path) -> None:
    key = Keypair()
    path = tmp_path / "signer.key"
    path.write_text(json.dumps(list(bytes(key))), encoding="utf-8")
    path.chmod(0o600)
    assert load_protected_keypair(path).pubkey() == key.pubkey()
    path.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        load_protected_keypair(path)
    path.chmod(0o600)
    link = tmp_path / "link.key"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="non-symlink"):
        load_protected_keypair(link)
    path.write_text("[1,2]", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        load_protected_keypair(path)


def test_intent_requires_exact_integer_base_units() -> None:
    key, mint, source, owner = Keypair(), Keypair(), Keypair(), Keypair()
    body = {
        "network": "devnet", "payer": str(key.pubkey()), "source_mint": str(mint.pubkey()),
        "source_token_account": str(source.pubkey()), "destination_owner": str(owner.pubkey()),
        "destination_token_account": str(get_associated_token_address(owner.pubkey(), mint.pubkey())),
        "asset": "USDC", "amount": "0.010000", "amount_base_units": 10000, "decimals": 6,
        "request_id": "request", "job_id": "job", "policy_version": "policy/v0.1.0",
        "policy_hash": "a" * 64, "approval_hash": "b" * 64,
        "idempotency_key": "request", "purpose": "test",
    }
    intent = SolanaTransferIntent.model_validate(body)
    assert len(intent.intent_hash) == 64
    with pytest.raises(ValidationError, match="base-unit"):
        SolanaTransferIntent.model_validate({**body, "amount_base_units": 9999})
    with pytest.raises(ValidationError):
        SolanaTransferIntent.model_validate({**body, "amount": "0.0000001", "amount_base_units": 0})


class FakeRpc:
    def __init__(self) -> None:
        self.prepared = []
        self.submitted = []
        self.state = "unknown"
        self.fail_submit = False

    async def validate(self, config): pass
    async def balances(self, config): return {"USDC": Decimal("1"), "SOL": Decimal("0.1")}
    async def prepare_and_sign(self, config, intent, keypair):
        self.prepared.append(intent)
        sig = str(Keypair().sign_message(intent.intent_hash.encode()))
        return SignedTransfer(signature=sig, raw_transaction=b"signed-once", intent_hash=intent.intent_hash, last_valid_block_height=1)
    async def submit(self, config, signed):
        self.submitted.append(signed.raw_transaction)
        if self.fail_submit:
            raise SolanaBackendError("NETWORK_FAILURE")
        self.state = "confirmed"
        return signed.signature
    async def lookup(self, config, signature):
        return SolanaTxEvidence(signature=signature, state=self.state, network=config.network, observed_at=NOW)
    async def wait_for_settlement(self, config, signature):
        return SolanaTxEvidence(signature=signature, state=self.state, network=config.network,
            fee_lamports=5000 if self.state == "confirmed" else None, observed_at=NOW)


def _approved(loaded, destination: str, signer=None, **changes) -> ApprovedRequest:
    body = {"request_id": str(uuid4()), "amount": "0.010000", "asset": "USDC",
        "destination": destination, "purpose": "devnet_test_transfer", "job_id": str(uuid4()),
        "policy_version": loaded.document.policy_version, "policy_hash": loaded.policy_hash,
        "approved_amount": "0.010000", "approved_at": NOW.isoformat(), "correlation_id": str(uuid4())}
    if signer is not None:
        owner = next(iter(signer._destinations.values()))
        mint = signer._config.token_mint
        body["phase_b_context"] = {
            "network": signer._config.network, "payer": signer._config.public_wallet,
            "source_mint": mint, "source_token_account": signer._config.source_token_account,
            "destination_owner": owner,
            "destination_token_account": str(get_associated_token_address(
                __import__("solders.pubkey", fromlist=["Pubkey"]).Pubkey.from_string(owner),
                __import__("solders.pubkey", fromlist=["Pubkey"]).Pubkey.from_string(mint))),
            "amount_base_units": 10000, "decimals": 6,
        }
    body.update(changes)
    return ApprovedRequest.model_validate(body)


def _request(approved: ApprovedRequest) -> SignRequest:
    digest = canonical_approved_hash(approved)
    return SignRequest(approved_request=approved, canonical_hash=digest,
        policy_version=approved.policy_version,
        request_hmac=compute_request_hmac(HMAC, approved_request=approved,
            canonical_hash=digest, policy_version=approved.policy_version))


def _signer(tmp_path: Path, rpc: FakeRpc):
    loaded = load_policy()
    key, mint, source, owner = Keypair(), Keypair(), Keypair(), Keypair()
    signer = SolanaSigner(freeze_path=tmp_path / "FREEZE",
        expected_policy_version=loaded.document.policy_version, expected_policy_hash=loaded.policy_hash,
        hmac_key=HMAC, config=_config(key, mint, source), keypair=key, rpc=rpc,
        approved_destinations={"devnet:test:recipient": str(owner.pubkey())})
    return loaded, signer


def test_phase_b_exact_transfer_confirmation_fee_and_replay(tmp_path: Path) -> None:
    rpc = FakeRpc()
    loaded, signer = _signer(tmp_path, rpc)
    req = _request(_approved(loaded, "devnet:test:recipient", signer))
    first = asyncio.run(signer.sign(req))
    second = asyncio.run(signer.sign(req))
    assert first.ok and first.fee_lamports == 5000
    assert second.ok and second.replay and second.tx_id == first.tx_id
    assert len(rpc.prepared) == len(rpc.submitted) == 1
    assert rpc.prepared[0].amount_base_units == 10000


def test_unknown_destination_and_mutated_approval_never_submit(tmp_path: Path) -> None:
    rpc = FakeRpc()
    loaded, signer = _signer(tmp_path, rpc)
    denied = asyncio.run(signer.sign(_request(_approved(loaded, "arbitrary-address", signer))))
    assert denied.code == "PROHIBITED_DESTINATION"
    original = _approved(loaded, "devnet:test:recipient", signer)
    assert asyncio.run(signer.sign(_request(original))).ok
    changed = original.model_copy(update={"amount": Decimal("0.020000"), "approved_amount": Decimal("0.020000")})
    conflict = asyncio.run(signer.sign(_request(changed)))
    assert conflict.code == "POLICY_TAMPER"
    assert len(rpc.submitted) == 1


def test_freeze_before_broadcast_and_signer_disable(tmp_path: Path) -> None:
    rpc = FakeRpc()
    loaded, signer = _signer(tmp_path, rpc)
    signer.set_enabled(False)
    assert asyncio.run(signer.sign(_request(_approved(loaded, "devnet:test:recipient", signer)))).code == "SIGNER_DISABLED"
    signer.set_enabled(True)
    (tmp_path / "FREEZE").write_text("1\n", encoding="utf-8")
    assert asyncio.run(signer.sign(_request(_approved(loaded, "devnet:test:recipient", signer)))).code == "AGENT_FROZEN"
    assert rpc.submitted == []


def test_uncertain_retry_reuses_same_signed_bytes(tmp_path: Path) -> None:
    rpc = FakeRpc()
    rpc.fail_submit = True
    loaded, signer = _signer(tmp_path, rpc)
    req = _request(_approved(loaded, "devnet:test:recipient", signer))
    assert asyncio.run(signer.sign(req)).code == "NETWORK_FAILURE"
    rpc.fail_submit = False
    assert asyncio.run(signer.sign(req)).ok
    assert len(rpc.prepared) == 1
    assert rpc.submitted == [b"signed-once", b"signed-once"]


def test_phase_b_wallet_http_is_keyless_and_mutations_forbidden() -> None:
    key, mint, source = Keypair(), Keypair(), Keypair()
    config = _config(key, mint, source)
    rpc = FakeRpc()
    app = SolanaReadService(wallet=rpc, config=config, read_token="read-token",
        debit_token="debit-token", credit_token="credit-token", model_token="model-token")

    async def call(method, path, token):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://wallet") as client:
            return await client.request(method, path, headers={"Authorization": f"Bearer {token}"}, json={})

    balances = asyncio.run(call("GET", "/v1/wallet/balances", "read-token"))
    assert balances.status_code == 200 and balances.json()["balances"]["USDC"] == "1.000000"
    assert "private" not in balances.text.lower() and "seed" not in balances.text.lower()
    for token in ("debit-token", "model-token"):
        denied = asyncio.run(call("POST", "/v1/wallet/debit", token))
        assert denied.status_code == 403


def test_wrong_mint_or_source_fails_before_signing(tmp_path: Path) -> None:
    rpc = FakeRpc()
    loaded, signer = _signer(tmp_path, rpc)
    request = _request(_approved(loaded, "devnet:test:recipient", signer))
    intent = signer._intent(request)
    bad = intent.model_copy(update={"source_mint": str(Keypair().pubkey())})
    with pytest.raises(SolanaBackendError, match="MINT_MISMATCH"):
        asyncio.run(SolanaWallet().prepare_and_sign(signer._config, bad, signer._keypair))
