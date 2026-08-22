"""Keyless Phase-B Solana RPC adapter and narrow SPL transfer DTOs.

This module is imported only when ``wallet_phase=B``.  It never loads or
accepts a private key.  Cryptographic signing lives in :mod:`aea.signer.solana`.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import Field, field_serializer, field_validator, model_validator

from aea.hashing import canonical_json_hash
from aea.types import AeaBaseModel, format_amount, parse_unsigned_amount

SOLANA_SIGNATURE_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{64,88}$")
SAFE_NETWORKS = frozenset({"devnet", "testnet", "localnet"})
GENESIS_HASHES = {
    "devnet": "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG",
    "testnet": "4uhcVJyU9pJkvQyS88uRDiswHXSCkY3zQawwpjk2NsNY",
}
Commitment = Literal["confirmed", "finalized"]
TxState = Literal[
    "constructed", "signed", "submitted", "processed", "confirmed",
    "finalized", "failed", "unknown", "timeout",
]


class SolanaBackendError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class SolanaConfig(AeaBaseModel):
    wallet_phase: Literal["B"]
    network: str
    rpc_url: str = Field(min_length=1)
    public_wallet: str = Field(min_length=32)
    token_mint: str = Field(min_length=32)
    token_decimals: int = Field(default=6, ge=0, le=18)
    source_token_account: str = Field(min_length=32)
    commitment: Commitment = "confirmed"
    confirmation_timeout_seconds: int = Field(default=60, ge=1, le=600)
    rpc_timeout_seconds: int = Field(default=15, ge=1, le=120)

    @field_validator("network")
    @classmethod
    def _safe_network(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"mainnet", "mainnet-beta"} or normalized not in SAFE_NETWORKS:
            raise ValueError("Phase B requires devnet, testnet, or localnet")
        return normalized

    @field_validator("rpc_url")
    @classmethod
    def _rpc_url(cls, value: str) -> str:
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("RPC endpoint must be an HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("RPC credentials must not use URL userinfo")
        return value

    @model_validator(mode="after")
    def _endpoint_network(self) -> "SolanaConfig":
        lower = self.rpc_url.lower()
        if "mainnet" in lower:
            raise ValueError("mainnet RPC endpoint is forbidden in Phase B")
        if self.network == "localnet":
            from urllib.parse import urlsplit
            if urlsplit(self.rpc_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("localnet RPC must be loopback")
        return self

    def sanitized_rpc_endpoint(self) -> str:
        from urllib.parse import urlsplit, urlunsplit
        parsed = urlsplit(self.rpc_url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


class SolanaTransferIntent(AeaBaseModel):
    network: str
    payer: str
    source_mint: str
    source_token_account: str
    destination_owner: str
    destination_token_account: str
    asset: Literal["USDC"]
    amount: Decimal
    amount_base_units: int = Field(gt=0)
    decimals: int = Field(ge=0, le=18)
    request_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1)
    purpose: str = Field(min_length=1)

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_serializer("amount")
    def _dump_amount(self, value: Decimal) -> str:
        return format_amount(value)

    @model_validator(mode="after")
    def _base_units_match(self) -> "SolanaTransferIntent":
        scaled = self.amount * (Decimal(10) ** self.decimals)
        if scaled != scaled.to_integral_value() or int(scaled) != self.amount_base_units:
            raise ValueError("amount/base-unit mismatch")
        return self

    @property
    def intent_hash(self) -> str:
        return canonical_json_hash(self.model_dump(mode="json"))


class SolanaTxEvidence(AeaBaseModel):
    signature: str
    state: TxState
    network: str
    slot: int | None = None
    fee_lamports: int | None = Field(default=None, ge=0)
    error: str | None = None
    observed_at: datetime

    @field_validator("signature")
    @classmethod
    def _signature(cls, value: str) -> str:
        if not SOLANA_SIGNATURE_RE.fullmatch(value):
            raise ValueError("invalid Solana transaction signature")
        return value


class SignedTransfer(AeaBaseModel):
    signature: str
    raw_transaction: bytes
    intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    last_valid_block_height: int = Field(ge=0)


class SolanaRpcPort(Protocol):
    async def validate(self, config: SolanaConfig) -> None: ...
    async def balances(self, config: SolanaConfig) -> dict[str, Decimal]: ...
    async def prepare_and_sign(self, config: SolanaConfig, intent: SolanaTransferIntent, keypair: Any) -> SignedTransfer: ...
    async def submit(self, config: SolanaConfig, signed: SignedTransfer) -> str: ...
    async def lookup(self, config: SolanaConfig, signature: str) -> SolanaTxEvidence: ...
    async def wait_for_settlement(self, config: SolanaConfig, signature: str) -> SolanaTxEvidence: ...


class SolanaWallet:
    """Keyless RPC implementation. A keypair is accepted only by the single
    internal ``prepare_and_sign`` call made from the isolated signer process.
    No generic bytes/message/program signing API exists.
    """

    async def _client(self, config: SolanaConfig):
        from solana.rpc.async_api import AsyncClient
        return AsyncClient(config.rpc_url, timeout=float(config.rpc_timeout_seconds), commitment=config.commitment)

    async def validate(self, config: SolanaConfig) -> None:
        from solders.pubkey import Pubkey
        from solana.rpc.types import TokenAccountOpts
        try:
            owner = Pubkey.from_string(config.public_wallet)
            mint_key = Pubkey.from_string(config.token_mint)
            source = Pubkey.from_string(config.source_token_account)
            client = await self._client(config)
            try:
                version = await client.get_version()
                genesis = await client.get_genesis_hash()
                supply = await client.get_token_supply(mint_key, commitment=config.commitment)
                accounts = await client.get_token_accounts_by_owner(
                    owner, TokenAccountOpts(mint=mint_key), commitment=config.commitment
                )
            finally:
                await client.close()
            if version.value is None:
                raise SolanaBackendError("RPC_VALIDATION_FAILED")
            expected_genesis = GENESIS_HASHES.get(config.network)
            if expected_genesis is not None and str(genesis.value) != expected_genesis:
                raise SolanaBackendError("RPC_NETWORK_MISMATCH")
            if int(supply.value.decimals) != config.token_decimals:
                raise SolanaBackendError("MINT_DECIMALS_MISMATCH")
            if str(source) not in {str(account.pubkey) for account in accounts.value}:
                raise SolanaBackendError("SOURCE_TOKEN_ACCOUNT_MISMATCH")
        except SolanaBackendError:
            raise
        except Exception as exc:
            raise SolanaBackendError("NETWORK_FAILURE", scrub_rpc_error(str(exc), config.rpc_url)) from exc

    async def balances(self, config: SolanaConfig) -> dict[str, Decimal]:
        from solders.pubkey import Pubkey
        try:
            client = await self._client(config)
            try:
                sol = await client.get_balance(Pubkey.from_string(config.public_wallet), commitment=config.commitment)
                token = await client.get_token_account_balance(Pubkey.from_string(config.source_token_account), commitment=config.commitment)
            finally:
                await client.close()
            raw = token.value
            if int(raw.decimals) != config.token_decimals:
                raise SolanaBackendError("MINT_DECIMALS_MISMATCH")
            return {
                "SOL": Decimal(sol.value) / Decimal(1_000_000_000),
                "USDC": Decimal(raw.amount) / (Decimal(10) ** config.token_decimals),
            }
        except SolanaBackendError:
            raise
        except Exception as exc:
            raise SolanaBackendError("NETWORK_FAILURE", scrub_rpc_error(str(exc), config.rpc_url)) from exc

    async def prepare_and_sign(self, config: SolanaConfig, intent: SolanaTransferIntent, keypair: Any) -> SignedTransfer:
        from solders.message import MessageV0
        from solders.pubkey import Pubkey
        from solders.transaction import VersionedTransaction
        from spl.token.constants import TOKEN_PROGRAM_ID
        from spl.token.instructions import TransferCheckedParams, get_associated_token_address, transfer_checked

        payer = keypair.pubkey()
        if str(payer) != config.public_wallet or intent.payer != config.public_wallet:
            raise SolanaBackendError("PAYER_MISMATCH")
        mint = Pubkey.from_string(config.token_mint)
        owner = Pubkey.from_string(intent.destination_owner)
        expected_dest = get_associated_token_address(owner, mint)
        if str(expected_dest) != intent.destination_token_account:
            raise SolanaBackendError("DESTINATION_ACCOUNT_MISMATCH")
        if intent.source_mint != config.token_mint or intent.source_token_account != config.source_token_account:
            raise SolanaBackendError("MINT_MISMATCH")
        client = await self._client(config)
        try:
            latest = await client.get_latest_blockhash(commitment=config.commitment)
        finally:
            await client.close()
        ix = transfer_checked(TransferCheckedParams(
            program_id=TOKEN_PROGRAM_ID,
            source=Pubkey.from_string(config.source_token_account),
            mint=mint,
            dest=expected_dest,
            owner=payer,
            amount=intent.amount_base_units,
            decimals=config.token_decimals,
            signers=[],
        ))
        message = MessageV0.try_compile(payer, [ix], [], latest.value.blockhash)
        tx = VersionedTransaction(message, [keypair])
        signature = str(tx.signatures[0])
        return SignedTransfer(
            signature=signature,
            raw_transaction=bytes(tx),
            intent_hash=intent.intent_hash,
            last_valid_block_height=latest.value.last_valid_block_height,
        )

    async def submit(self, config: SolanaConfig, signed: SignedTransfer) -> str:
        from solana.rpc.types import TxOpts
        try:
            client = await self._client(config)
            try:
                response = await client.send_raw_transaction(
                    signed.raw_transaction,
                    opts=TxOpts(skip_preflight=False, preflight_commitment=config.commitment, max_retries=3),
                )
            finally:
                await client.close()
            signature = str(response.value)
            if signature != signed.signature:
                raise SolanaBackendError("SIGNATURE_MISMATCH")
            return signature
        except SolanaBackendError:
            raise
        except Exception as exc:
            raise SolanaBackendError("NETWORK_FAILURE", scrub_rpc_error(str(exc), config.rpc_url)) from exc

    async def lookup(self, config: SolanaConfig, signature: str) -> SolanaTxEvidence:
        from solders.signature import Signature
        now = datetime.now(timezone.utc)
        try:
            sig = Signature.from_string(signature)
            client = await self._client(config)
            try:
                statuses = await client.get_signature_statuses([sig], search_transaction_history=True)
                status = statuses.value[0]
                tx = await client.get_transaction(sig, commitment=config.commitment, max_supported_transaction_version=0) if status is not None else None
            finally:
                await client.close()
            if status is None:
                state: TxState = "unknown"
                return SolanaTxEvidence(signature=signature, state=state, network=config.network, observed_at=now)
            if status.err is not None:
                return SolanaTxEvidence(signature=signature, state="failed", network=config.network, slot=status.slot, error="transaction_failed", observed_at=now)
            confirmation = str(status.confirmation_status or "processed").lower()
            state = "finalized" if "finalized" in confirmation else "confirmed" if "confirmed" in confirmation else "processed"
            fee = None if tx is None or tx.value is None or tx.value.transaction.meta is None else tx.value.transaction.meta.fee
            return SolanaTxEvidence(signature=signature, state=state, network=config.network, slot=status.slot, fee_lamports=fee, observed_at=now)
        except Exception as exc:
            raise SolanaBackendError("NETWORK_FAILURE", scrub_rpc_error(str(exc), config.rpc_url)) from exc

    async def wait_for_settlement(self, config: SolanaConfig, signature: str) -> SolanaTxEvidence:
        deadline = asyncio.get_running_loop().time() + config.confirmation_timeout_seconds
        required = config.commitment
        while asyncio.get_running_loop().time() < deadline:
            evidence = await self.lookup(config, signature)
            if evidence.state == "failed":
                return evidence
            if evidence.state == "finalized" or (required == "confirmed" and evidence.state == "confirmed"):
                return evidence
            await asyncio.sleep(1)
        return SolanaTxEvidence(signature=signature, state="timeout", network=config.network, observed_at=datetime.now(timezone.utc))


def scrub_rpc_error(message: str, rpc_url: str) -> str:
    """Remove the complete configured URL (including query API keys)."""
    redacted = message.replace(rpc_url, "<rpc-endpoint>")
    from urllib.parse import parse_qsl, urlsplit
    parsed = urlsplit(rpc_url)
    for value in (parsed.query, parsed.username, parsed.password):
        if value:
            redacted = redacted.replace(value, "<redacted>")
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key:
            redacted = redacted.replace(key, "<redacted>")
        if value:
            redacted = redacted.replace(value, "<redacted>")
    return redacted[:240]
