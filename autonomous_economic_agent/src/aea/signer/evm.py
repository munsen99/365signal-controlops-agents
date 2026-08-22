"""Isolated signer for one HMAC-approved ERC-20 USDC transfer operation."""

from __future__ import annotations

import os
import json
import stat
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Mapping
from uuid import UUID

from eth_account import Account
from eth_utils import to_checksum_address

from aea.policy.reasons import HttpCode, ReasonCode
from aea.signer.backend import HASH_RE, HMAC_MIN_KEY_CHARS, SignRequest, SignResult, canonical_approved_hash, verify_request_hmac
from aea.signer.freeze import inspect_freeze
from aea.signer.live_gate import inspect_live_spend_gate
from aea.types import format_amount
from aea.wallet.evm import EvmConfig, EvmRailError, EvmTransferIntent, EvmWallet, SignedEvmTransfer


def load_protected_evm_key(path: Path | str) -> Any:
    key_path = Path(path)
    try:
        info = os.lstat(key_path)
    except OSError as exc:
        raise ValueError("EVM signer key is missing or unreadable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("EVM signer key must be a regular non-symlink file")
    if info.st_uid != os.geteuid():
        raise ValueError("EVM signer key owner mismatch")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("EVM signer key mode must be 0600")
    try:
        raw = key_path.read_text(encoding="ascii").strip()
        if raw.startswith("0x"):
            raw = raw[2:]
        if len(raw) != 64 or any(c not in "0123456789abcdefABCDEF" for c in raw):
            raise ValueError
        return Account.from_key(bytes.fromhex(raw))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("EVM signer key is malformed") from exc


class EvmSigner:
    """No arbitrary calldata or message signing; only exact ERC-20 transfer."""

    def __init__(self, *, freeze_path: Path | str | None, expected_policy_version: str,
                 expected_policy_hash: str, hmac_key: str, config: EvmConfig, account: Any,
                 rpc: EvmWallet, approved_destinations: Mapping[str, str], signer_enabled: bool = True,
                 db_frozen_reader: Callable[[], Any] | None = None,
                 db_signer_enabled_reader: Callable[[], Any] | None = None,
                 live_spend_path: Path | str | None = None, live_operator_intent: str | None = None,
                 state_dir: Path | str | None = None) -> None:
        if not HASH_RE.fullmatch(expected_policy_hash) or len(hmac_key) < HMAC_MIN_KEY_CHARS:
            raise ValueError("invalid signer policy/HMAC configuration")
        if to_checksum_address(account.address) != config.public_wallet:
            raise ValueError("configured EVM wallet does not match signer key")
        if not approved_destinations:
            raise ValueError("at least one EVM destination is required")
        self._freeze_path, self._policy_version, self._policy_hash = freeze_path, expected_policy_version, expected_policy_hash
        self._hmac_key, self._config, self._account, self._rpc = hmac_key, config, account, rpc
        self._destinations = {key: to_checksum_address(value) for key, value in approved_destinations.items()}
        self._enabled = signer_enabled
        self._db_frozen_reader, self._db_signer_enabled_reader = db_frozen_reader, db_signer_enabled_reader
        self._live_spend_path, self._live_operator_intent = live_spend_path, live_operator_intent
        self._state_dir = Path(state_dir) if state_dir is not None else None
        if self._state_dir is not None:
            self._validate_state_dir()
        self._lock = Lock()
        self._results: dict[UUID, SignResult] = {}
        self._signed: dict[UUID, SignedEvmTransfer] = {}
        self._hashes: dict[UUID, str] = {}
        self._intent_hashes: dict[UUID, str] = {}
        self._in_flight: set[UUID] = set()

    def _validate_state_dir(self) -> None:
        assert self._state_dir is not None
        try:
            info = os.lstat(self._state_dir)
        except FileNotFoundError:
            self._state_dir.mkdir(mode=0o700, parents=True)
            info = os.lstat(self._state_dir)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("EVM signer state must be a regular non-symlink directory")
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("EVM signer state directory must be owner-only mode 0700")

    def _state_path(self, request_id: UUID) -> Path | None:
        return None if self._state_dir is None else self._state_dir / f"{request_id}.json"

    def _read_state(self, request_id: UUID) -> dict[str, Any] | None:
        path = self._state_path(request_id)
        if path is None:
            return None
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise EvmRailError("SIGNER_STATE_INVALID")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise EvmRailError("SIGNER_STATE_INVALID") from exc
        return value if isinstance(value, dict) else None

    def _write_state(self, request_id: UUID, value: dict[str, Any]) -> None:
        path = self._state_path(request_id)
        if path is None:
            return
        temporary = path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _load_signed(self, request_id: UUID, intent_hash: str) -> SignedEvmTransfer | None:
        value = self._read_state(request_id)
        if value is None:
            return None
        if value.get("intent_hash") != intent_hash:
            raise EvmRailError(HttpCode.REPLAY_APPROVED_REQUEST)
        signed = value.get("signed")
        if not isinstance(signed, dict):
            return None
        material = {key: item for key, item in signed.items() if key != "raw_transaction_hex"}
        return SignedEvmTransfer.model_validate({**material,
            "raw_transaction": bytes.fromhex(str(signed["raw_transaction_hex"]))})

    @property
    def hmac_key(self) -> str:
        return self._hmac_key

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    @property
    def signer_enabled(self) -> bool:
        return self.is_effectively_enabled()

    def is_effectively_enabled(self) -> bool:
        with self._lock:
            enabled = self._enabled
        if not enabled:
            return False
        if self._db_signer_enabled_reader is None:
            return True
        try:
            value = self._db_signer_enabled_reader()
        except Exception:
            return False
        return value if isinstance(value, bool) else False

    def inspect_current_freeze(self) -> Any:
        kw: dict[str, Any] = {}
        if self._db_frozen_reader is not None:
            try:
                kw["db_frozen"] = self._db_frozen_reader()
            except Exception:
                kw["db_frozen"] = None
        return inspect_freeze(self._freeze_path, **kw)

    def _safe(self) -> str | None:
        if self.inspect_current_freeze().frozen:
            return HttpCode.AGENT_FROZEN
        if not self.is_effectively_enabled():
            return HttpCode.SIGNER_DISABLED
        if self._config.network == "base-mainnet":
            gate = inspect_live_spend_gate(self._live_spend_path, operator_intent=self._live_operator_intent)
            if not gate.enabled:
                return HttpCode.LIVE_SPEND_DISABLED
        return None

    def _intent(self, request: SignRequest) -> EvmTransferIntent:
        approved, context = request.approved_request, request.approved_request.evm_context
        if context is None or approved.asset != "USDC" or context.operation != "erc20_transfer":
            raise EvmRailError(ReasonCode.POLICY_TAMPER)
        destination = self._destinations.get(approved.destination)
        if destination is None or destination != to_checksum_address(context.destination):
            raise EvmRailError(ReasonCode.PROHIBITED_DESTINATION)
        base = approved.amount * Decimal(10**context.decimals)
        expected = {"rail": "evm", "network": self._config.network, "chain_id": self._config.chain_id,
                    "operation": "erc20_transfer", "payer": self._config.public_wallet,
                    "token_contract": self._config.token_contract, "destination": destination,
                    "amount_base_units": int(base), "decimals": self._config.token_decimals,
                    "max_gas_limit": self._config.max_gas_limit,
                    "max_fee_per_gas_wei": self._config.max_fee_per_gas_wei,
                    "max_priority_fee_per_gas_wei": self._config.max_priority_fee_per_gas_wei,
                    "max_total_fee_wei": self._config.max_total_fee_wei}
        if base != base.to_integral_value() or context.model_dump(mode="json") != expected:
            raise EvmRailError(ReasonCode.POLICY_TAMPER)
        return EvmTransferIntent(network=context.network, chain_id=context.chain_id, payer=context.payer,
            token_contract=context.token_contract, destination=context.destination, amount=approved.amount,
            amount_base_units=context.amount_base_units, request_id=str(approved.request_id),
            job_id=str(approved.job_id), policy_version=approved.policy_version, policy_hash=approved.policy_hash,
            approval_hash=request.canonical_hash, purpose=approved.purpose,
            max_gas_limit=context.max_gas_limit, max_fee_per_gas_wei=context.max_fee_per_gas_wei,
            max_priority_fee_per_gas_wei=context.max_priority_fee_per_gas_wei,
            max_total_fee_wei=context.max_total_fee_wei)

    async def sign(self, request: SignRequest) -> SignResult:
        approved, request_id = request.approved_request, request.approved_request.request_id
        def fail(code: str) -> SignResult:
            return SignResult(ok=False, code=code, reason_code=code, request_id=request_id,
                              correlation_id=approved.correlation_id)
        if not verify_request_hmac(self._hmac_key, request.request_hmac, approved_request=approved,
                                   canonical_hash=request.canonical_hash, policy_version=request.policy_version):
            return fail(HttpCode.UNAUTHENTICATED)
        canonical = canonical_approved_hash(approved)
        if (request.policy_version != approved.policy_version or approved.policy_version != self._policy_version
                or approved.policy_hash != self._policy_hash or canonical != request.canonical_hash
                or format_amount(approved.amount) != format_amount(approved.approved_amount)):
            return fail(ReasonCode.POLICY_TAMPER)
        try:
            intent = self._intent(request)
        except EvmRailError as exc:
            return fail(exc.code)
        with self._lock:
            if ((request_id in self._hashes and self._hashes[request_id] != canonical)
                    or (request_id in self._intent_hashes and self._intent_hashes[request_id] != intent.intent_hash)):
                return fail(HttpCode.REPLAY_APPROVED_REQUEST)
            if request_id in self._results:
                return self._results[request_id].model_copy(update={"replay": True, "code": HttpCode.IDEMPOTENT_REPLAY})
            if request_id in self._in_flight:
                return fail(HttpCode.CONFLICT)
            self._in_flight.add(request_id)
            self._hashes[request_id], self._intent_hashes[request_id] = canonical, intent.intent_hash
            signed = self._signed.get(request_id)
        try:
            unsafe = self._safe()
            if unsafe:
                return fail(unsafe)
            try:
                await self._rpc.validate(self._config, for_spend=True)
                if signed is None:
                    signed = self._load_signed(request_id, intent.intent_hash)
                if signed is None:
                    signed = await self._rpc.prepare_and_sign(self._config, intent, self._account)
                    with self._lock:
                        self._signed[request_id] = signed
                    self._write_state(request_id, {"intent_hash": intent.intent_hash,
                        "canonical_hash": canonical, "signed": {
                            **signed.model_dump(exclude={"raw_transaction"}, mode="json"),
                            "raw_transaction_hex": signed.raw_transaction.hex()}})
                unsafe = self._safe()
                if unsafe:
                    return fail(unsafe)
                evidence = await self._rpc.lookup(self._config, signed.transaction_hash)
                if evidence.state not in {"confirmed", "accepted"}:
                    await self._rpc.submit(self._config, signed)
                    evidence = await self._rpc.wait_for_settlement(self._config, signed.transaction_hash)
                if evidence.state != "accepted":
                    return fail("TRANSACTION_REVERTED" if evidence.state == "reverted" else HttpCode.TIMEOUT)
                verified = await self._rpc.verify_transfer(self._config, signed.transaction_hash, intent)
            except EvmRailError as exc:
                return fail(exc.code)
            result = SignResult(ok=True, code=HttpCode.OK, request_id=request_id,
                correlation_id=approved.correlation_id, tx_id=signed.transaction_hash,
                canonical_hash=canonical, fee_wei=verified.fee_wei, gas_used=verified.gas_used,
                effective_gas_price_wei=verified.effective_gas_price_wei, rail="evm",
                network=self._config.network, chain_id=self._config.chain_id,
                token_contract=self._config.token_contract, block_number=verified.block_number)
            with self._lock:
                self._results[request_id] = result
            return result
        finally:
            with self._lock:
                self._in_flight.discard(request_id)

    # Intentionally no sign_message, sign_typed_data, sign_bytes, raw calldata, approval, or native-transfer method.
