"""Keyless Phase-B/C Solana RPC adapter and narrow SPL transfer DTOs.

Cryptographic authority and key loading live only in :mod:`aea.signer.solana`;
this adapter exposes no generic signing operation.
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
SAFE_NETWORKS = frozenset({"devnet", "testnet", "localnet", "mainnet-beta"})
MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
CANONICAL_MAINNET_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
GENESIS_HASHES = {
    "devnet": "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG",
    "testnet": "4uhcVJyU9pJkvQyS88uRDiswHXSCkY3zQawwpjk2NsNY",
    "mainnet-beta": MAINNET_GENESIS_HASH,
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
    wallet_phase: Literal["B", "C"]
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
        if normalized == "mainnet":
            raise ValueError("use exact Solana cluster name mainnet-beta")
        if normalized not in SAFE_NETWORKS:
            raise ValueError("unsupported Solana network")
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
        if self.wallet_phase == "B" and self.network == "mainnet-beta":
            raise ValueError("mainnet is forbidden in Phase B")
        if self.wallet_phase == "C" and self.network != "mainnet-beta":
            raise ValueError("Phase C requires mainnet-beta")
        if self.wallet_phase == "C" and self.token_mint != CANONICAL_MAINNET_USDC_MINT:
            raise ValueError("Phase C requires canonical Solana USDC mint")
        if self.wallet_phase == "C" and self.token_decimals != 6:
            raise ValueError("Phase C USDC requires six decimals")
        if self.wallet_phase == "C" and self.commitment != "finalized":
            raise ValueError("Phase C settlement requires finalized commitment")
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
    transfer_verified: bool = False
    source_token_account: str | None = None
    destination_token_account: str | None = None
    mint: str | None = None
    amount_base_units: int | None = Field(default=None, ge=0)

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
    async def validate(self, config: SolanaConfig, *, for_spend: bool = False) -> None: ...
    async def balances(self, config: SolanaConfig) -> dict[str, Decimal]: ...
    async def validate_destination(self, config: SolanaConfig, destination_owner: str) -> str: ...
    async def prepare_and_sign(self, config: SolanaConfig, intent: SolanaTransferIntent, keypair: Any) -> SignedTransfer: ...
    async def submit(self, config: SolanaConfig, signed: SignedTransfer) -> str: ...
    async def lookup(self, config: SolanaConfig, signature: str) -> SolanaTxEvidence: ...
    async def wait_for_settlement(self, config: SolanaConfig, signature: str) -> SolanaTxEvidence: ...
    async def verify_transfer(self, config: SolanaConfig, signature: str,
                              intent: SolanaTransferIntent) -> SolanaTxEvidence: ...


class SolanaWallet:
    """Keyless RPC implementation. A keypair is accepted only by the single
    internal ``prepare_and_sign`` call made from the isolated signer process.
    No generic bytes/message/program signing API exists.
    """

    async def _client(self, config: SolanaConfig):
        from solana.rpc.async_api import AsyncClient
        return AsyncClient(config.rpc_url, timeout=float(config.rpc_timeout_seconds), commitment=config.commitment)

    async def validate(self, config: SolanaConfig, *, for_spend: bool = False) -> None:
        from solders.pubkey import Pubkey
        from solana.rpc.types import TokenAccountOpts
        from spl.token.constants import TOKEN_PROGRAM_ID
        from spl.token.instructions import get_associated_token_address
        try:
            owner = Pubkey.from_string(config.public_wallet)
            mint_key = Pubkey.from_string(config.token_mint)
            source = Pubkey.from_string(config.source_token_account)
            client = await self._client(config)
            try:
                version = await client.get_version()
                genesis = await client.get_genesis_hash()
                supply = await client.get_token_supply(mint_key, commitment=config.commitment)
                mint_info = await client.get_account_info(mint_key, commitment=config.commitment)
                source_info = await client.get_account_info(source, commitment=config.commitment)
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
            if mint_info.value is None or mint_info.value.owner != TOKEN_PROGRAM_ID:
                raise SolanaBackendError("MINT_PROGRAM_MISMATCH")
            expected_source = get_associated_token_address(owner, mint_key)
            if config.wallet_phase == "C" and source != expected_source:
                raise SolanaBackendError("SOURCE_TOKEN_ACCOUNT_MISMATCH")
            source_exists = source_info.value is not None
            if source_exists and source_info.value.owner != TOKEN_PROGRAM_ID:
                raise SolanaBackendError("SOURCE_TOKEN_PROGRAM_MISMATCH")
            if source_exists and str(source) not in {str(account.pubkey) for account in accounts.value}:
                raise SolanaBackendError("SOURCE_TOKEN_ACCOUNT_MISMATCH")
            if for_spend and not source_exists:
                raise SolanaBackendError("SOURCE_TOKEN_ACCOUNT_MISSING")
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
                source = Pubkey.from_string(config.source_token_account)
                info = await client.get_account_info(source, commitment=config.commitment)
                token = None if info.value is None else await client.get_token_account_balance(source, commitment=config.commitment)
            finally:
                await client.close()
            if token is None:
                if config.wallet_phase == "C":
                    return {"SOL": Decimal(sol.value) / Decimal(1_000_000_000), "USDC": Decimal("0")}
                raise SolanaBackendError("SOURCE_TOKEN_ACCOUNT_MISSING")
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

    async def validate_destination(self, config: SolanaConfig, destination_owner: str) -> str:
        from solders.pubkey import Pubkey
        from solana.rpc.types import TokenAccountOpts
        from spl.token.constants import TOKEN_PROGRAM_ID
        from spl.token.instructions import get_associated_token_address
        try:
            owner = Pubkey.from_string(destination_owner)
            mint = Pubkey.from_string(config.token_mint)
            destination = get_associated_token_address(owner, mint)
            client = await self._client(config)
            try:
                info = await client.get_account_info(destination, commitment=config.commitment)
                accounts = await client.get_token_accounts_by_owner(
                    owner, TokenAccountOpts(mint=mint), commitment=config.commitment
                )
                balance = None if info.value is None else await client.get_token_account_balance(
                    destination, commitment=config.commitment
                )
            finally:
                await client.close()
            if info.value is None:
                raise SolanaBackendError("DESTINATION_TOKEN_ACCOUNT_MISSING")
            if info.value.owner != TOKEN_PROGRAM_ID:
                raise SolanaBackendError("DESTINATION_TOKEN_PROGRAM_MISMATCH")
            if str(destination) not in {str(account.pubkey) for account in accounts.value}:
                raise SolanaBackendError("DESTINATION_ACCOUNT_MISMATCH")
            if balance is None or int(balance.value.decimals) != config.token_decimals:
                raise SolanaBackendError("MINT_DECIMALS_MISMATCH")
            return str(destination)
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

    async def verify_transfer(self, config: SolanaConfig, signature: str,
                              intent: SolanaTransferIntent) -> SolanaTxEvidence:
        """Verify finalized jsonParsed chain evidence against the approved intent."""
        import httpx

        request = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [
            signature, {"commitment": config.commitment, "encoding": "jsonParsed",
                        "maxSupportedTransactionVersion": 0},
        ]}
        try:
            async with httpx.AsyncClient(timeout=float(config.rpc_timeout_seconds)) as client:
                response = await client.post(config.rpc_url, json=request)
                response.raise_for_status()
                body = response.json()
            result = body.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("meta"), dict):
                raise SolanaBackendError("CHAIN_EVIDENCE_MISSING")
            meta = result["meta"]
            if meta.get("err") is not None:
                raise SolanaBackendError("CHAIN_TRANSACTION_FAILED")
            message = result.get("transaction", {}).get("message", {})
            keys = message.get("accountKeys", [])
            key_values = [item.get("pubkey") if isinstance(item, dict) else item for item in keys]
            if not key_values or key_values[0] != intent.payer:
                raise SolanaBackendError("CHAIN_PAYER_MISMATCH")
            matches: list[dict[str, Any]] = []
            for instruction in message.get("instructions", []):
                parsed = instruction.get("parsed") if isinstance(instruction, dict) else None
                if (not isinstance(instruction, dict) or instruction.get("program") != "spl-token"
                        or not isinstance(parsed, dict) or parsed.get("type") != "transferChecked"):
                    continue
                info = parsed.get("info")
                if isinstance(info, dict):
                    matches.append(info)
            if len(matches) != 1:
                raise SolanaBackendError("CHAIN_TRANSFER_MISMATCH")
            info = matches[0]
            token_amount = info.get("tokenAmount", {})
            exact = (
                info.get("source") == intent.source_token_account
                and info.get("destination") == intent.destination_token_account
                and info.get("mint") == intent.source_mint
                and info.get("authority") == intent.payer
                and str(token_amount.get("amount")) == str(intent.amount_base_units)
                and int(token_amount.get("decimals", -1)) == intent.decimals
            )
            if not exact:
                raise SolanaBackendError("CHAIN_TRANSFER_MISMATCH")
            state: TxState = "finalized" if config.commitment == "finalized" else "confirmed"
            return SolanaTxEvidence(
                signature=signature, state=state, network=config.network,
                slot=result.get("slot"), fee_lamports=int(meta.get("fee", 0)),
                observed_at=datetime.now(timezone.utc), transfer_verified=True,
                source_token_account=intent.source_token_account,
                destination_token_account=intent.destination_token_account,
                mint=intent.source_mint, amount_base_units=intent.amount_base_units,
            )
        except SolanaBackendError:
            raise
        except Exception as exc:
            raise SolanaBackendError("NETWORK_FAILURE", scrub_rpc_error(str(exc), config.rpc_url)) from exc


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
