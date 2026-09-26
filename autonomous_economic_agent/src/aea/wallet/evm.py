"""Keyless EVM JSON-RPC rail and narrow ERC-20 transfer primitives."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

import httpx
from eth_abi import encode
from eth_utils import is_checksum_address, keccak, to_checksum_address
from pydantic import Field, field_validator, model_validator

from aea.hashing import canonical_json_hash
from aea.types import AeaBaseModel, format_amount, parse_unsigned_amount

BASE_MAINNET_CHAIN_ID = 8453
BASE_SEPOLIA_CHAIN_ID = 84532
BASE_MAINNET_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
TRANSFER_SELECTOR = "0x" + keccak(text="transfer(address,uint256)")[:4].hex()
BALANCE_OF_SELECTOR = "0x" + keccak(text="balanceOf(address)")[:4].hex()
DECIMALS_SELECTOR = "0x" + keccak(text="decimals()")[:4].hex()
TRANSFER_TOPIC = "0x" + keccak(text="Transfer(address,address,uint256)").hex()
EVM_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

EvmState = Literal["prepared", "signed", "broadcast", "pending", "confirmed", "accepted", "reverted", "unknown"]


class EvmRailError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class EvmConfig(AeaBaseModel):
    wallet_phase: Literal["E"] = "E"
    rail: Literal["evm"] = "evm"
    network: Literal["base-local", "base-sepolia", "base-mainnet"]
    chain_id: int = Field(gt=0)
    rpc_url: str = Field(min_length=1)
    public_wallet: str
    token_contract: str
    token_decimals: int = 6
    confirmations: int = Field(default=12, ge=1, le=1000)
    confirmation_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    rpc_timeout_seconds: int = Field(default=20, ge=1, le=120)
    max_gas_limit: int = Field(default=100_000, ge=21_000, le=1_000_000)
    max_fee_per_gas_wei: int = Field(default=2_000_000_000, gt=0)
    max_priority_fee_per_gas_wei: int = Field(default=100_000_000, ge=0)
    max_total_fee_wei: int = Field(default=200_000_000_000_000, gt=0)
    live_spend: bool = False

    @field_validator("public_wallet", "token_contract")
    @classmethod
    def _address(cls, value: str) -> str:
        checksum = to_checksum_address(value)
        if not is_checksum_address(checksum):
            raise ValueError("invalid EVM address")
        return checksum

    @field_validator("rpc_url")
    @classmethod
    def _url(cls, value: str) -> str:
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("invalid EVM RPC URL")
        return value

    @model_validator(mode="after")
    def _network(self) -> "EvmConfig":
        expected = {"base-mainnet": BASE_MAINNET_CHAIN_ID, "base-sepolia": BASE_SEPOLIA_CHAIN_ID}
        if self.network in expected and self.chain_id != expected[self.network]:
            raise ValueError("configured EVM chain ID does not match network")
        if self.network == "base-mainnet" and self.token_contract != to_checksum_address(BASE_MAINNET_USDC):
            raise ValueError("Base mainnet requires canonical native USDC")
        if self.network == "base-sepolia" and self.token_contract != to_checksum_address(BASE_SEPOLIA_USDC):
            raise ValueError("Base Sepolia requires Circle test USDC")
        if self.token_decimals != 6:
            raise ValueError("EVM USDC rail requires six decimals")
        if self.network == "base-local":
            from urllib.parse import urlsplit
            if urlsplit(self.rpc_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("local EVM RPC must be loopback")
        return self

    def sanitized_rpc_endpoint(self) -> str:
        from urllib.parse import urlsplit, urlunsplit
        p = urlsplit(self.rpc_url)
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


class EvmTransferIntent(AeaBaseModel):
    rail: Literal["evm"] = "evm"
    network: str
    chain_id: int = Field(gt=0)
    operation: Literal["erc20_transfer"] = "erc20_transfer"
    payer: str
    token_contract: str
    destination: str
    asset: Literal["USDC"] = "USDC"
    amount: Decimal
    amount_base_units: int = Field(gt=0)
    decimals: int = 6
    request_id: str
    job_id: str
    policy_version: str
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: str
    max_gas_limit: int = Field(gt=0)
    max_fee_per_gas_wei: int = Field(gt=0)
    max_priority_fee_per_gas_wei: int = Field(ge=0)
    max_total_fee_wei: int = Field(gt=0)

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("payer", "token_contract", "destination")
    @classmethod
    def _addr(cls, value: str) -> str:
        return to_checksum_address(value)

    @model_validator(mode="after")
    def _units(self) -> "EvmTransferIntent":
        if self.operation != "erc20_transfer" or self.decimals != 6:
            raise ValueError("unsupported EVM operation")
        scaled = self.amount * Decimal(10**self.decimals)
        if scaled != scaled.to_integral_value() or int(scaled) != self.amount_base_units:
            raise ValueError("amount/base units mismatch")
        return self

    @property
    def intent_hash(self) -> str:
        return canonical_json_hash(self.model_dump(mode="json"))


class SignedEvmTransfer(AeaBaseModel):
    transaction_hash: str
    raw_transaction: bytes
    nonce: int = Field(ge=0)
    intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    gas_limit: int = Field(gt=0)
    max_fee_per_gas_wei: int = Field(gt=0)
    max_priority_fee_per_gas_wei: int = Field(ge=0)


class EvmTxEvidence(AeaBaseModel):
    transaction_hash: str
    state: EvmState
    rail: Literal["evm"] = "evm"
    network: str
    chain_id: int
    block_number: int | None = None
    confirmations: int = 0
    gas_used: int | None = None
    effective_gas_price_wei: int | None = None
    l1_fee_wei: int = Field(default=0, ge=0)
    fee_wei: int | None = None
    transfer_verified: bool = False
    token_contract: str | None = None
    source: str | None = None
    destination: str | None = None
    amount_base_units: int | None = None
    error: str | None = None
    observed_at: datetime

    @field_validator("transaction_hash")
    @classmethod
    def _hash(cls, value: str) -> str:
        if not EVM_TX_RE.fullmatch(value):
            raise ValueError("invalid EVM transaction hash")
        return value.lower()


def erc20_transfer_calldata(destination: str, amount_base_units: int) -> str:
    return TRANSFER_SELECTOR + encode(["address", "uint256"], [to_checksum_address(destination), amount_base_units]).hex()


class EvmWallet:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def _rpc(self, config: EvmConfig, method: str, params: list[Any]) -> Any:
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=config.rpc_timeout_seconds) as client:
                response = await client.post(config.rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or body.get("error") is not None or "result" not in body:
                raise EvmRailError("NETWORK_FAILURE")
            return body["result"]
        except EvmRailError:
            raise
        except Exception as exc:
            raise EvmRailError("NETWORK_FAILURE", "EVM RPC request failed") from exc

    async def validate(self, config: EvmConfig, *, for_spend: bool = False) -> None:
        chain = int(await self._rpc(config, "eth_chainId", []), 16)
        if chain != config.chain_id:
            raise EvmRailError("RPC_CHAIN_ID_MISMATCH")
        code = await self._rpc(config, "eth_getCode", [config.token_contract, "latest"])
        if not isinstance(code, str) or code in {"0x", "0x0"}:
            raise EvmRailError("TOKEN_CONTRACT_MISSING")
        raw_decimals = await self._rpc(config, "eth_call", [{"to": config.token_contract, "data": DECIMALS_SELECTOR}, "latest"])
        if int(raw_decimals, 16) != config.token_decimals:
            raise EvmRailError("TOKEN_DECIMALS_MISMATCH")
        if for_spend and not config.live_spend and config.network in {"base-mainnet", "base-sepolia"}:
            raise EvmRailError("LIVE_SPEND_DISABLED")

    async def balances(self, config: EvmConfig) -> dict[str, Decimal]:
        native = int(await self._rpc(config, "eth_getBalance", [config.public_wallet, "latest"]), 16)
        data = BALANCE_OF_SELECTOR + encode(["address"], [config.public_wallet]).hex()
        token = int(await self._rpc(config, "eth_call", [{"to": config.token_contract, "data": data}, "latest"]), 16)
        return {"ETH": Decimal(native) / Decimal(10**18), "USDC": Decimal(token) / Decimal(10**config.token_decimals)}

    async def prepare_and_sign(self, config: EvmConfig, intent: EvmTransferIntent, account: Any) -> SignedEvmTransfer:
        if account.address != config.public_wallet or intent.payer != config.public_wallet:
            raise EvmRailError("PAYER_MISMATCH")
        if intent.chain_id != config.chain_id or intent.network != config.network:
            raise EvmRailError("CHAIN_ID_MISMATCH")
        if intent.token_contract != config.token_contract or intent.operation != "erc20_transfer":
            raise EvmRailError("TOKEN_CONTRACT_MISMATCH")
        data = erc20_transfer_calldata(intent.destination, intent.amount_base_units)
        nonce = int(await self._rpc(config, "eth_getTransactionCount", [config.public_wallet, "pending"]), 16)
        estimate = int(await self._rpc(config, "eth_estimateGas", [{"from": config.public_wallet, "to": config.token_contract, "value": "0x0", "data": data}]), 16)
        gas_limit = (estimate * 120 + 99) // 100
        if gas_limit > min(config.max_gas_limit, intent.max_gas_limit):
            raise EvmRailError("GAS_LIMIT_EXCEEDED")
        block = await self._rpc(config, "eth_getBlockByNumber", ["latest", False])
        base_fee = int(block.get("baseFeePerGas", "0x0"), 16)
        try:
            priority = int(await self._rpc(config, "eth_maxPriorityFeePerGas", []), 16)
        except EvmRailError:
            priority = 0
        priority = min(priority, config.max_priority_fee_per_gas_wei, intent.max_priority_fee_per_gas_wei)
        max_fee = base_fee * 2 + priority
        if max_fee > min(config.max_fee_per_gas_wei, intent.max_fee_per_gas_wei):
            raise EvmRailError("GAS_PRICE_EXCEEDED")
        if gas_limit * max_fee > min(config.max_total_fee_wei, intent.max_total_fee_wei):
            raise EvmRailError("TOTAL_FEE_EXCEEDED")
        tx = {"type": 2, "chainId": config.chain_id, "nonce": nonce, "to": config.token_contract,
              "value": 0, "data": data, "gas": gas_limit, "maxFeePerGas": max_fee,
              "maxPriorityFeePerGas": priority}
        signed = account.sign_transaction(tx)
        transaction_hash = signed.hash.hex()
        if not transaction_hash.startswith("0x"):
            transaction_hash = "0x" + transaction_hash
        return SignedEvmTransfer(transaction_hash=transaction_hash, raw_transaction=bytes(signed.raw_transaction),
                                 nonce=nonce, intent_hash=intent.intent_hash, gas_limit=gas_limit,
                                 max_fee_per_gas_wei=max_fee, max_priority_fee_per_gas_wei=priority)

    async def submit(self, config: EvmConfig, signed: SignedEvmTransfer) -> str:
        result = await self._rpc(config, "eth_sendRawTransaction", ["0x" + signed.raw_transaction.hex()])
        if str(result).lower() != signed.transaction_hash.lower():
            raise EvmRailError("TRANSACTION_HASH_MISMATCH")
        return signed.transaction_hash

    async def lookup(self, config: EvmConfig, transaction_hash: str) -> EvmTxEvidence:
        if not EVM_TX_RE.fullmatch(transaction_hash):
            raise EvmRailError("VALIDATION_ERROR")
        receipt = await self._rpc(config, "eth_getTransactionReceipt", [transaction_hash])
        now = datetime.now(timezone.utc)
        if receipt is None:
            return EvmTxEvidence(transaction_hash=transaction_hash, state="pending", network=config.network,
                                 chain_id=config.chain_id, observed_at=now)
        block_number = int(receipt["blockNumber"], 16)
        latest = int(await self._rpc(config, "eth_blockNumber", []), 16)
        confirmations = max(0, latest - block_number + 1)
        gas_used = int(receipt["gasUsed"], 16)
        gas_price = int(receipt.get("effectiveGasPrice", "0x0"), 16)
        l1_fee = int(receipt.get("l1Fee", "0x0"), 16)
        ok = int(receipt["status"], 16) == 1
        state: EvmState = "reverted" if not ok else ("accepted" if confirmations >= config.confirmations else "confirmed")
        return EvmTxEvidence(transaction_hash=transaction_hash, state=state, network=config.network,
                             chain_id=config.chain_id, block_number=block_number, confirmations=confirmations,
                             gas_used=gas_used, effective_gas_price_wei=gas_price, l1_fee_wei=l1_fee,
                             fee_wei=gas_used * gas_price + l1_fee,
                             error=None if ok else "transaction reverted", observed_at=now)

    async def wait_for_settlement(self, config: EvmConfig, transaction_hash: str) -> EvmTxEvidence:
        deadline = asyncio.get_running_loop().time() + config.confirmation_timeout_seconds
        while True:
            evidence = await self.lookup(config, transaction_hash)
            if evidence.state in {"accepted", "reverted"}:
                return evidence
            if asyncio.get_running_loop().time() >= deadline:
                return evidence.model_copy(update={"state": "unknown", "error": "confirmation timeout"})
            await asyncio.sleep(1)

    async def verify_transfer(self, config: EvmConfig, transaction_hash: str, intent: EvmTransferIntent) -> EvmTxEvidence:
        evidence = await self.lookup(config, transaction_hash)
        if evidence.state not in {"confirmed", "accepted"}:
            raise EvmRailError("TRANSACTION_NOT_SETTLED")
        tx = await self._rpc(config, "eth_getTransactionByHash", [transaction_hash])
        receipt = await self._rpc(config, "eth_getTransactionReceipt", [transaction_hash])
        expected_data = erc20_transfer_calldata(intent.destination, intent.amount_base_units).lower()
        if (int(tx["chainId"], 16) != config.chain_id or to_checksum_address(tx["from"]) != config.public_wallet
                or to_checksum_address(tx["to"]) != config.token_contract or int(tx["value"], 16) != 0
                or str(tx["input"]).lower() != expected_data):
            raise EvmRailError("CHAIN_TRANSFER_MISMATCH")
        source_topic = "0x" + encode(["address"], [config.public_wallet]).hex()
        destination_topic = "0x" + encode(["address"], [intent.destination]).hex()
        matches = [log for log in receipt.get("logs", []) if to_checksum_address(log["address"]) == config.token_contract
                   and len(log.get("topics", [])) == 3 and log["topics"][0].lower() == TRANSFER_TOPIC.lower()
                   and log["topics"][1].lower() == source_topic.lower()
                   and log["topics"][2].lower() == destination_topic.lower()
                   and int(log["data"], 16) == intent.amount_base_units]
        if len(matches) != 1:
            raise EvmRailError("TRANSFER_LOG_MISMATCH")
        return evidence.model_copy(update={"transfer_verified": True, "token_contract": config.token_contract,
            "source": config.public_wallet, "destination": intent.destination,
            "amount_base_units": intent.amount_base_units})
