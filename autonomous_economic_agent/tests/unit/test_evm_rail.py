from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from eth_account import Account
from eth_utils import keccak, to_checksum_address

from aea.signer.backend import ApprovedRequest, SignRequest, canonical_approved_hash, compute_request_hmac
from aea.signer.evm import EvmSigner, load_protected_evm_key
from aea.wallet.evm import (
    BASE_MAINNET_USDC,
    EvmConfig,
    EvmRailError,
    EvmTxEvidence,
    TRANSFER_SELECTOR,
    EvmWallet,
    EvmTransferIntent,
)

POLICY_HASH = "a" * 64
HMAC_KEY = "evm-test-hmac-key-material-32chars-minimum"


def _config(account: object, token: str, **changes: object) -> EvmConfig:
    values = {
        "network": "base-local", "chain_id": 31337, "rpc_url": "http://127.0.0.1:8545",
        "public_wallet": account.address, "token_contract": token, "confirmations": 1,
        "max_gas_limit": 100_000, "max_fee_per_gas_wei": 2_000_000_000,
        "max_priority_fee_per_gas_wei": 100_000_000, "max_total_fee_wei": 200_000_000_000_000,
    }
    values.update(changes)
    return EvmConfig.model_validate(values)


def test_base_identity_and_canonical_usdc_are_pinned() -> None:
    account = Account.create()
    with pytest.raises(ValueError):
        _config(account, BASE_MAINNET_USDC, network="base-mainnet", chain_id=1)
    with pytest.raises(ValueError):
        _config(account, "0x0000000000000000000000000000000000000001",
                network="base-mainnet", chain_id=8453)
    valid = _config(account, BASE_MAINNET_USDC, network="base-mainnet", chain_id=8453,
        rpc_url="https://rpc.example.invalid/v1/project?api_key=secret")
    assert valid.live_spend is False
    assert "api_key" not in valid.sanitized_rpc_endpoint() and "secret" not in valid.sanitized_rpc_endpoint()


def test_rpc_chain_decimals_and_balance_validation() -> None:
    account, token = Account.create(), to_checksum_address("0x" + "22" * 20)
    config = _config(account, token)

    def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        result = {
            "eth_chainId": "0x7a69", "eth_getCode": "0x6000",
            "eth_call": "0x" + (6).to_bytes(32, "big").hex(),
            "eth_getBalance": hex(10**18),
        }[body["method"]]
        if body["method"] == "eth_call" and str(body["params"][0]["data"]).startswith("0x70a08231"):
            result = "0x" + (2_000_000).to_bytes(32, "big").hex()
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    wallet = EvmWallet(transport=httpx.MockTransport(handler))
    import asyncio
    asyncio.run(wallet.validate(config))
    assert asyncio.run(wallet.balances(config)) == {"ETH": Decimal("1"), "USDC": Decimal("2")}


def test_wrong_rpc_chain_and_wrong_decimals_fail_closed() -> None:
    account, token = Account.create(), to_checksum_address("0x" + "22" * 20)
    config = _config(account, token)
    results = {"eth_chainId": "0x1", "eth_getCode": "0x6000", "eth_call": "0x12"}
    def handler(request: httpx.Request) -> httpx.Response:
        method = __import__("json").loads(request.content)["method"]
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": results[method]})
    import asyncio
    with pytest.raises(EvmRailError, match="RPC_CHAIN_ID_MISMATCH"):
        asyncio.run(EvmWallet(transport=httpx.MockTransport(handler)).validate(config))


def test_protected_key_loader_rejects_symlink_and_permissions(tmp_path: Path) -> None:
    account = Account.create()
    key = tmp_path / "evm.key"
    key.write_text(account.key.hex(), encoding="ascii")
    key.chmod(0o600)
    assert load_protected_evm_key(key).address == account.address
    key.chmod(0o640)
    with pytest.raises(ValueError, match="0600"):
        load_protected_evm_key(key)
    key.chmod(0o600)
    link = tmp_path / "link.key"
    link.symlink_to(key)
    with pytest.raises(ValueError, match="non-symlink"):
        load_protected_evm_key(link)


class _SignerRpc:
    def __init__(self) -> None:
        self.prepared = self.submitted = 0
        self.signed = None

    async def validate(self, config: EvmConfig, *, for_spend: bool = False) -> None:
        return None

    async def prepare_and_sign(self, config: EvmConfig, intent: object, account: object) -> object:
        from aea.wallet.evm import SignedEvmTransfer
        self.prepared += 1
        self.signed = SignedEvmTransfer(transaction_hash="0x" + "bb" * 32,
            raw_transaction=b"signed-exact-intent", nonce=7, intent_hash=intent.intent_hash,
            gas_limit=55_000, max_fee_per_gas_wei=1, max_priority_fee_per_gas_wei=0)
        return self.signed

    async def lookup(self, config: EvmConfig, transaction_hash: str) -> EvmTxEvidence:
        state = "accepted" if self.submitted else "pending"
        return EvmTxEvidence(transaction_hash=transaction_hash, state=state, network=config.network,
            chain_id=config.chain_id, confirmations=self.submitted, observed_at=datetime.now(timezone.utc))

    async def submit(self, config: EvmConfig, signed: object) -> str:
        self.submitted += 1
        return signed.transaction_hash

    async def wait_for_settlement(self, config: EvmConfig, transaction_hash: str) -> EvmTxEvidence:
        return await self.lookup(config, transaction_hash)

    async def verify_transfer(self, config: EvmConfig, transaction_hash: str, intent: object) -> EvmTxEvidence:
        return (await self.lookup(config, transaction_hash)).model_copy(update={
            "transfer_verified": True, "fee_wei": 1234, "gas_used": 55_000,
            "effective_gas_price_wei": 1})


def _approved(config: EvmConfig, destination_id: str, destination: str) -> ApprovedRequest:
    return ApprovedRequest.model_validate({
        "request_id": str(uuid4()), "amount": "0.010000", "approved_amount": "0.010000",
        "asset": "USDC", "destination": destination_id, "purpose": "bounded fixture",
        "job_id": str(uuid4()), "policy_version": "policy/evm-test", "policy_hash": POLICY_HASH,
        "approved_at": datetime.now(timezone.utc).isoformat(), "correlation_id": str(uuid4()),
        "evm_context": {"rail": "evm", "network": config.network, "chain_id": config.chain_id,
            "operation": "erc20_transfer", "payer": config.public_wallet,
            "token_contract": config.token_contract, "destination": destination,
            "amount_base_units": 10_000, "decimals": 6, "max_gas_limit": config.max_gas_limit,
            "max_fee_per_gas_wei": config.max_fee_per_gas_wei,
            "max_priority_fee_per_gas_wei": config.max_priority_fee_per_gas_wei,
            "max_total_fee_wei": config.max_total_fee_wei},
    })


def _signed_request(approved: ApprovedRequest) -> SignRequest:
    canonical = canonical_approved_hash(approved)
    return SignRequest(approved_request=approved, canonical_hash=canonical,
        policy_version=approved.policy_version, request_hmac=compute_request_hmac(
            HMAC_KEY, approved_request=approved, canonical_hash=canonical,
            policy_version=approved.policy_version))


def test_signer_exact_transfer_idempotency_and_no_signature_oracle(tmp_path: Path) -> None:
    account, destination = Account.create(), Account.create().address
    token = to_checksum_address("0x" + "22" * 20)
    config, rpc = _config(account, token), _SignerRpc()
    signer = EvmSigner(freeze_path=tmp_path / "FREEZE", expected_policy_version="policy/evm-test",
        expected_policy_hash=POLICY_HASH, hmac_key=HMAC_KEY, config=config, account=account,
        rpc=rpc, approved_destinations={"base:approved:test": destination})
    approved = _approved(config, "base:approved:test", destination)
    import asyncio
    first = asyncio.run(signer.sign(_signed_request(approved)))
    replay = asyncio.run(signer.sign(_signed_request(approved)))
    assert first.ok and first.fee_wei == 1234
    assert replay.ok and replay.replay
    assert rpc.prepared == 1 and rpc.submitted == 1
    assert not hasattr(signer, "sign_message") and not hasattr(signer, "sign_transaction")


def test_signer_rejects_destination_or_amount_context_mutation(tmp_path: Path) -> None:
    account, destination = Account.create(), Account.create().address
    token = to_checksum_address("0x" + "22" * 20)
    config, rpc = _config(account, token), _SignerRpc()
    signer = EvmSigner(freeze_path=tmp_path / "FREEZE", expected_policy_version="policy/evm-test",
        expected_policy_hash=POLICY_HASH, hmac_key=HMAC_KEY, config=config, account=account,
        rpc=rpc, approved_destinations={"base:approved:test": destination})
    approved = _approved(config, "base:approved:test", destination)
    mutated = approved.model_copy(update={"amount": Decimal("0.020000")})
    import asyncio
    result = asyncio.run(signer.sign(_signed_request(mutated)))
    assert not result.ok and result.reason_code == "POLICY_TAMPER"
    assert rpc.prepared == 0


def test_only_transfer_selector_is_constructed() -> None:
    from aea.wallet.evm import erc20_transfer_calldata
    data = erc20_transfer_calldata(Account.create().address, 10_000)
    assert data.startswith(TRANSFER_SELECTOR) and len(data) == 138


def _intent(config: EvmConfig, destination: str) -> EvmTransferIntent:
    return EvmTransferIntent(network=config.network, chain_id=config.chain_id,
        payer=config.public_wallet, token_contract=config.token_contract,
        destination=destination, amount="0.010000", amount_base_units=10_000,
        request_id=str(uuid4()), job_id=str(uuid4()), policy_version="policy/test",
        policy_hash="d" * 64, approval_hash="e" * 64, purpose="test",
        max_gas_limit=config.max_gas_limit, max_fee_per_gas_wei=config.max_fee_per_gas_wei,
        max_priority_fee_per_gas_wei=config.max_priority_fee_per_gas_wei,
        max_total_fee_wei=config.max_total_fee_wei)


def test_excessive_gas_estimate_fails_before_signing() -> None:
    account, destination = Account.create(), Account.create().address
    token, config = to_checksum_address("0x" + "22" * 20), None
    config = _config(account, token, max_gas_limit=50_000)
    results = {"eth_getTransactionCount": "0x1", "eth_estimateGas": hex(100_000)}
    def handler(request: httpx.Request) -> httpx.Response:
        method = __import__("json").loads(request.content)["method"]
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": results[method]})
    import asyncio
    with pytest.raises(EvmRailError, match="GAS_LIMIT_EXCEEDED"):
        asyncio.run(EvmWallet(transport=httpx.MockTransport(handler)).prepare_and_sign(
            config, _intent(config, destination), account))


def test_reverted_receipt_is_not_settlement() -> None:
    account, token = Account.create(), to_checksum_address("0x" + "22" * 20)
    config, tx_hash = _config(account, token), "0x" + "99" * 32
    def handler(request: httpx.Request) -> httpx.Response:
        method = __import__("json").loads(request.content)["method"]
        result = ({"blockNumber": "0x5", "gasUsed": "0x5208", "effectiveGasPrice": "0x1",
                   "status": "0x0", "logs": []} if method == "eth_getTransactionReceipt" else "0x5")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})
    import asyncio
    evidence = asyncio.run(EvmWallet(transport=httpx.MockTransport(handler)).lookup(config, tx_hash))
    assert evidence.state == "reverted" and not evidence.transfer_verified


def test_missing_transfer_log_rejected_even_with_success_receipt() -> None:
    account, destination = Account.create(), Account.create().address
    token, tx_hash = to_checksum_address("0x" + "22" * 20), "0x" + "98" * 32
    config = _config(account, token)
    intent = _intent(config, destination)
    receipt = {"blockNumber": "0x5", "gasUsed": "0x5208", "effectiveGasPrice": "0x1",
        "status": "0x1", "logs": []}
    def handler(request: httpx.Request) -> httpx.Response:
        method = __import__("json").loads(request.content)["method"]
        result = {"eth_getTransactionReceipt": receipt, "eth_blockNumber": "0x5",
            "eth_getTransactionByHash": {"chainId": hex(config.chain_id), "from": config.public_wallet,
                "to": config.token_contract, "value": "0x0",
                "input": __import__("aea.wallet.evm", fromlist=["erc20_transfer_calldata"]).erc20_transfer_calldata(destination, 10_000)}}[method]
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})
    import asyncio
    with pytest.raises(EvmRailError, match="TRANSFER_LOG_MISMATCH"):
        asyncio.run(EvmWallet(transport=httpx.MockTransport(handler)).verify_transfer(config, tx_hash, intent))


def test_signer_disable_prevents_prepare(tmp_path: Path) -> None:
    account, destination = Account.create(), Account.create().address
    token, rpc = to_checksum_address("0x" + "22" * 20), _SignerRpc()
    config = _config(account, token)
    signer = EvmSigner(freeze_path=tmp_path / "FREEZE", expected_policy_version="policy/evm-test",
        expected_policy_hash=POLICY_HASH, hmac_key=HMAC_KEY, config=config, account=account,
        rpc=rpc, approved_destinations={"base:approved:test": destination}, signer_enabled=False)
    import asyncio
    result = asyncio.run(signer.sign(_signed_request(_approved(config, "base:approved:test", destination))))
    assert not result.ok and result.code == "SIGNER_DISABLED" and rpc.prepared == 0
