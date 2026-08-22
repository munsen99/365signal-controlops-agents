"""Genuine local EVM execution using Py-EVM (no mocked chain state)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import vyper
from eth_account import Account
from eth_tester import EthereumTester, PyEVMBackend

from aea.signer.backend import ApprovedRequest, SignRequest, canonical_approved_hash, compute_request_hmac
from aea.signer.evm import EvmSigner
from aea.wallet.evm import EvmConfig, EvmWallet

pytestmark = pytest.mark.filterwarnings(
    "ignore:.*asyncio.iscoroutinefunction.*:DeprecationWarning"
)

TOKEN_SOURCE = """
# pragma version 0.4.3
decimals: public(uint8)
balanceOf: public(HashMap[address, uint256])
event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    value: uint256
@deploy
def __init__():
    self.decimals = 6
    self.balanceOf[msg.sender] = 1000000000
@external
def transfer(to: address, amount: uint256) -> bool:
    assert self.balanceOf[msg.sender] >= amount
    self.balanceOf[msg.sender] -= amount
    self.balanceOf[to] += amount
    log Transfer(sender=msg.sender, receiver=to, value=amount)
    return True
"""


def _hex(value: object) -> object:
    if isinstance(value, int):
        return hex(value)
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if hasattr(value, "hex"):
        result = value.hex()
        return result if str(result).startswith("0x") else "0x" + str(result)
    return value


class PyEvmRpc:
    def __init__(self) -> None:
        self.backend = PyEVMBackend()
        self.chain = EthereumTester(self.backend)
        self.account = Account.from_key(self.backend.account_keys[0].to_bytes())
        self.destination = self.chain.get_accounts()[1]
        bytecode = vyper.compile_code(TOKEN_SOURCE, output_formats=["bytecode"])["bytecode"]
        deploy_hash = self.chain.send_transaction({"from": self.account.address, "gas": 3_000_000, "data": bytecode})
        self.token = self.chain.get_transaction_receipt(deploy_hash)["contract_address"]
        self.lose_first_submit_response = True
        self.broadcasts = 0
        self.errors: list[tuple[str, str]] = []

    def _receipt(self, tx_hash: str) -> dict[str, object] | None:
        try:
            value = self.chain.get_transaction_receipt(tx_hash)
        except Exception:
            return None
        return {"transactionHash": _hex(value["transaction_hash"]), "blockNumber": hex(value["block_number"]),
            "gasUsed": hex(value["gas_used"]), "effectiveGasPrice": hex(value.get("effective_gas_price", 0)),
            "status": hex(value["status"]), "logs": [{"address": log["address"],
                "topics": [_hex(topic) for topic in log["topics"]], "data": _hex(log["data"])} for log in value["logs"]]}

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method, params = body["method"], body["params"]
        try:
            if method == "eth_chainId": result = hex(self.backend.chain.chain_id)
            elif method == "eth_getCode": result = _hex(self.chain.get_code(params[0]))
            elif method == "eth_getBalance": result = hex(self.chain.get_balance(params[0]))
            elif method == "eth_call": result = _hex(self.chain.call({"from": self.account.address, **params[0]}))
            elif method == "eth_getTransactionCount": result = hex(self.chain.get_nonce(params[0], block_number=params[1]))
            elif method == "eth_estimateGas":
                tx = dict(params[0])
                tx["value"] = int(tx.get("value", "0x0"), 16) if isinstance(tx.get("value"), str) else tx.get("value", 0)
                result = hex(self.chain.estimate_gas(tx))
            elif method == "eth_getBlockByNumber": result = {"baseFeePerGas": hex(self.chain.get_block_by_number(params[0])["base_fee_per_gas"])}
            elif method == "eth_maxPriorityFeePerGas": result = hex(1_000_000_000)
            elif method == "eth_sendRawTransaction":
                self.broadcasts += 1
                result = self.chain.send_raw_transaction(params[0])
                if self.lose_first_submit_response:
                    self.lose_first_submit_response = False
                    return httpx.Response(503, text="simulated response loss")
            elif method == "eth_getTransactionReceipt": result = self._receipt(params[0])
            elif method == "eth_blockNumber": result = hex(self.chain.get_block_by_number("latest")["number"])
            elif method == "eth_getTransactionByHash":
                tx = self.chain.get_transaction_by_hash(params[0])
                result = {"chainId": hex(self.backend.chain.chain_id), "from": tx["from"], "to": tx["to"],
                    "value": hex(tx["value"]), "input": _hex(tx["data"])}
            else: raise AssertionError(method)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})
        except Exception as exc:
            self.errors.append((method, repr(exc)))
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1,
                "error": {"code": -32000, "message": type(exc).__name__}})


def test_local_evm_transfer_response_loss_recovery_and_exact_log(tmp_path: Path) -> None:
    node = PyEvmRpc()
    config = EvmConfig(network="base-local", chain_id=node.backend.chain.chain_id,
        rpc_url="http://127.0.0.1:8545", public_wallet=node.account.address, token_contract=node.token,
        confirmations=1, max_gas_limit=100_000, max_fee_per_gas_wei=5_000_000_000,
        max_priority_fee_per_gas_wei=1_000_000_000, max_total_fee_wei=500_000_000_000_000)
    wallet = EvmWallet(transport=httpx.MockTransport(node.handler))
    state_dir = tmp_path / "signer-state"
    signer = EvmSigner(freeze_path=tmp_path / "FREEZE", expected_policy_version="policy/m2b-local",
        expected_policy_hash="c" * 64, hmac_key="local-chain-hmac-key-material-32-characters",
        config=config, account=node.account, rpc=wallet,
        approved_destinations={"base:approved:local-recipient": node.destination}, state_dir=state_dir)
    approved = ApprovedRequest.model_validate({"request_id": str(uuid4()), "amount": "0.010000",
        "approved_amount": "0.010000", "asset": "USDC", "destination": "base:approved:local-recipient",
        "purpose": "M2b local settlement", "job_id": str(uuid4()), "policy_version": "policy/m2b-local",
        "policy_hash": "c" * 64, "approved_at": datetime.now(timezone.utc).isoformat(),
        "correlation_id": str(uuid4()), "evm_context": {"network": "base-local",
            "chain_id": config.chain_id, "payer": config.public_wallet, "token_contract": config.token_contract,
            "destination": node.destination, "amount_base_units": 10_000, "decimals": 6,
            "max_gas_limit": config.max_gas_limit, "max_fee_per_gas_wei": config.max_fee_per_gas_wei,
            "max_priority_fee_per_gas_wei": config.max_priority_fee_per_gas_wei,
            "max_total_fee_wei": config.max_total_fee_wei}})
    canonical = canonical_approved_hash(approved)
    request = SignRequest(approved_request=approved, canonical_hash=canonical,
        policy_version=approved.policy_version, request_hmac=compute_request_hmac(
            signer.hmac_key, approved_request=approved, canonical_hash=canonical,
            policy_version=approved.policy_version))
    import asyncio
    before = asyncio.run(wallet.balances(config))
    lost = asyncio.run(signer.sign(request))
    # A fresh isolated signer process recovers the exact persisted signed bytes.
    signer = EvmSigner(freeze_path=tmp_path / "FREEZE", expected_policy_version="policy/m2b-local",
        expected_policy_hash="c" * 64, hmac_key="local-chain-hmac-key-material-32-characters",
        config=config, account=node.account, rpc=wallet,
        approved_destinations={"base:approved:local-recipient": node.destination}, state_dir=state_dir)
    recovered = asyncio.run(signer.sign(request))
    replay = asyncio.run(signer.sign(request))
    after = asyncio.run(wallet.balances(config))
    destination_config = config.model_copy(update={"public_wallet": node.destination})
    destination_balance = asyncio.run(wallet.balances(destination_config))["USDC"]
    assert not lost.ok and lost.code == "NETWORK_FAILURE"
    assert recovered.ok and recovered.fee_wei and recovered.gas_used, node.errors
    assert replay.ok and replay.replay
    assert node.broadcasts == 1
    assert before["USDC"] - after["USDC"] == __import__("decimal").Decimal("0.010000")
    assert destination_balance == __import__("decimal").Decimal("0.010000")
    assert int((before["ETH"] - after["ETH"]) * (10**18)) == recovered.fee_wei
    evidence_dir = os.environ.get("AEA_EVM_EVIDENCE_DIR")
    if evidence_dir:
        target = Path(evidence_dir)
        target.mkdir(parents=True, exist_ok=False)
        (target / "result.json").write_text(json.dumps({
            "gate": "M2b-E2", "result": "PASS", "rail": "evm", "network": "base-local",
            "chain_id": config.chain_id, "source": config.public_wallet,
            "token_contract": config.token_contract, "token_decimals": 6,
            "destination": node.destination, "operation": "erc20_transfer",
            "amount_usdc": "0.010000", "amount_base_units": 10000,
            "transaction_hash": recovered.tx_id, "receipt_status": "accepted",
            "gas_used": recovered.gas_used, "effective_gas_price_wei": recovered.effective_gas_price_wei,
            "fee_wei": recovered.fee_wei, "source_before": {k: str(v) for k, v in before.items()},
            "source_after": {k: str(v) for k, v in after.items()},
            "destination_usdc_after": str(destination_balance), "broadcast_count": node.broadcasts,
            "response_loss_recovered": True, "idempotent_replay": replay.replay,
            "ledger_expected_usdc": str(after["USDC"]), "ledger_expected_eth": str(after["ETH"]),
            "reconciliation_delta_usdc": "0.000000", "reconciliation_delta_eth": "0",
            "private_key_recorded": False, "mainnet_transaction_executed": False,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
