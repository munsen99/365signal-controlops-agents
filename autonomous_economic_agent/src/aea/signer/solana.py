"""Phase-B isolated signer for one narrow SPL ``transfer_checked`` intent."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Mapping
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import UUID

from aea.policy.reasons import HttpCode, ReasonCode
from aea.signer.backend import (
    HASH_RE,
    HMAC_MIN_KEY_CHARS,
    SignRequest,
    SignResult,
    canonical_approved_hash,
    verify_request_hmac,
)
from aea.signer.freeze import inspect_freeze
from aea.types import format_amount
from aea.wallet.solana import (
    SolanaBackendError,
    SolanaConfig,
    SolanaRpcPort,
    SolanaTransferIntent,
    SignedTransfer,
)


def load_protected_keypair(path: Path | str) -> Any:
    """Load a Solana 64-byte keypair file, rejecting links and loose modes.

    The function intentionally has no export/diagnostic counterpart.
    """
    key_path = Path(path)
    try:
        info = os.lstat(key_path)
    except OSError as exc:
        raise ValueError("signer key is missing or unreadable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("signer key must be a regular non-symlink file")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("signer key permissions must be owner-only")
    try:
        raw = json.loads(key_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or len(raw) != 64 or any(
            isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 255
            for item in raw
        ):
            raise ValueError
        from solders.keypair import Keypair
        return Keypair.from_bytes(bytes(raw))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, ImportError) as exc:
        raise ValueError("signer key is malformed or Solana support is unavailable") from exc


class SolanaSigner:
    """Validates the PR5 approval then constructs/signs exactly one SPL transfer.

    Unknown outcomes retain the original signed bytes and signature. A retry
    queries chain evidence and may re-submit those exact bytes; it never creates
    a fresh payment or fresh transaction for an uncertain request.
    """

    def __init__(
        self,
        *,
        freeze_path: Path | str | None,
        expected_policy_version: str,
        expected_policy_hash: str,
        hmac_key: str,
        config: SolanaConfig,
        keypair: Any,
        rpc: SolanaRpcPort,
        approved_destinations: Mapping[str, str],
        signer_enabled: bool = True,
        db_frozen_reader: Callable[[], Any] | None = None,
        db_signer_enabled_reader: Callable[[], Any] | None = None,
    ) -> None:
        if not HASH_RE.fullmatch(expected_policy_hash):
            raise ValueError("expected_policy_hash must be 64 lowercase hex characters")
        if len(hmac_key) < HMAC_MIN_KEY_CHARS:
            raise ValueError("hmac_key must be at least 32 characters")
        if str(keypair.pubkey()) != config.public_wallet:
            raise ValueError("configured public wallet does not match signer key")
        if not approved_destinations:
            raise ValueError("at least one approved Phase-B destination is required")
        self._freeze_path = freeze_path
        self._expected_policy_version = expected_policy_version
        self._expected_policy_hash = expected_policy_hash
        self._hmac_key = hmac_key
        self._config = config
        self._keypair = keypair
        self._rpc = rpc
        self._destinations = dict(approved_destinations)
        self._enabled = bool(signer_enabled)
        self._db_frozen_reader = db_frozen_reader
        self._db_signer_enabled_reader = db_signer_enabled_reader
        self._lock = Lock()
        self._results: dict[UUID, SignResult] = {}
        self._hashes: dict[UUID, str] = {}
        self._signed: dict[UUID, SignedTransfer] = {}
        self._intent_hashes: dict[UUID, str] = {}
        self._in_flight: set[UUID] = set()

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
        kwargs: dict[str, Any] = {}
        if self._db_frozen_reader is not None:
            try:
                kwargs["db_frozen"] = self._db_frozen_reader()
            except Exception:
                kwargs["db_frozen"] = None
        return inspect_freeze(self._freeze_path, **kwargs)

    def _safe(self) -> str | None:
        if self.inspect_current_freeze().frozen:
            return HttpCode.AGENT_FROZEN
        if not self.is_effectively_enabled():
            return HttpCode.SIGNER_DISABLED
        return None

    def _intent(self, request: SignRequest) -> SolanaTransferIntent:
        approved = request.approved_request
        context = approved.phase_b_context
        if context is None:
            raise SolanaBackendError(ReasonCode.POLICY_TAMPER)
        destination_owner = self._destinations.get(approved.destination)
        if destination_owner is None:
            raise SolanaBackendError(ReasonCode.PROHIBITED_DESTINATION)
        if approved.asset != "USDC":
            raise SolanaBackendError(ReasonCode.PROHIBITED_TOKEN)
        from solders.pubkey import Pubkey
        from spl.token.instructions import get_associated_token_address
        try:
            owner = Pubkey.from_string(destination_owner)
            mint = Pubkey.from_string(self._config.token_mint)
        except ValueError as exc:
            raise SolanaBackendError(ReasonCode.PROHIBITED_DESTINATION) from exc
        destination_account = str(get_associated_token_address(owner, mint))
        base = approved.amount * (Decimal(10) ** self._config.token_decimals)
        if base != base.to_integral_value() or base <= 0:
            raise SolanaBackendError(HttpCode.VALIDATION_ERROR)
        expected_context = {
            "network": self._config.network, "payer": self._config.public_wallet,
            "source_mint": self._config.token_mint,
            "source_token_account": self._config.source_token_account,
            "destination_owner": destination_owner,
            "destination_token_account": destination_account,
            "amount_base_units": int(base), "decimals": self._config.token_decimals,
        }
        if context.model_dump(mode="json") != expected_context:
            raise SolanaBackendError(ReasonCode.POLICY_TAMPER)
        return SolanaTransferIntent(
            network=self._config.network,
            payer=self._config.public_wallet,
            source_mint=self._config.token_mint,
            source_token_account=self._config.source_token_account,
            destination_owner=destination_owner,
            destination_token_account=destination_account,
            asset="USDC",
            amount=approved.amount,
            amount_base_units=int(base),
            decimals=self._config.token_decimals,
            request_id=str(approved.request_id),
            job_id=str(approved.job_id),
            policy_version=approved.policy_version,
            policy_hash=approved.policy_hash,
            approval_hash=request.canonical_hash,
            idempotency_key=str(approved.request_id),
            purpose=approved.purpose,
        )

    async def sign(self, request: SignRequest) -> SignResult:
        approved = request.approved_request
        request_id = approved.request_id
        correlation_id = approved.correlation_id

        def fail(code: str) -> SignResult:
            return SignResult(ok=False, code=code, request_id=request_id,
                              correlation_id=correlation_id, reason_code=code)

        if not verify_request_hmac(self._hmac_key, request.request_hmac,
            approved_request=approved, canonical_hash=request.canonical_hash,
            policy_version=request.policy_version):
            return fail(HttpCode.UNAUTHENTICATED)
        if request.policy_version != approved.policy_version:
            return fail(ReasonCode.POLICY_TAMPER)
        if approved.policy_version != self._expected_policy_version or approved.policy_hash != self._expected_policy_hash:
            return fail(ReasonCode.POLICY_TAMPER)
        if format_amount(approved.amount) != format_amount(approved.approved_amount):
            return fail(ReasonCode.AMOUNT_MISMATCH)
        canonical = canonical_approved_hash(approved)
        if canonical != request.canonical_hash:
            return fail(HttpCode.REPLAY_APPROVED_REQUEST)
        try:
            intent = self._intent(request)
        except SolanaBackendError as exc:
            return fail(exc.code)

        with self._lock:
            result = self._results.get(request_id)
            old_hash = self._hashes.get(request_id)
            old_intent = self._intent_hashes.get(request_id)
            if (old_hash is not None and old_hash != canonical) or (old_intent is not None and old_intent != intent.intent_hash):
                return fail(HttpCode.REPLAY_APPROVED_REQUEST)
            if result is not None:
                return result.model_copy(update={"replay": True, "code": HttpCode.IDEMPOTENT_REPLAY})
            if request_id in self._in_flight:
                return fail(HttpCode.CONFLICT)
            self._in_flight.add(request_id)
            signed = self._signed.get(request_id)
            self._hashes[request_id] = canonical
            self._intent_hashes[request_id] = intent.intent_hash

        try:
            unsafe = self._safe()
            if unsafe:
                return fail(unsafe)
            if signed is None:
                try:
                    signed = await self._rpc.prepare_and_sign(self._config, intent, self._keypair)
                except SolanaBackendError as exc:
                    return fail(exc.code)
                with self._lock:
                    self._signed[request_id] = signed
            # Required second independent control check immediately before broadcast.
            unsafe = self._safe()
            if unsafe:
                return fail(unsafe)
            try:
                evidence = await self._rpc.lookup(self._config, signed.signature)
                if evidence.state not in {"confirmed", "finalized"}:
                    await self._rpc.submit(self._config, signed)
                    evidence = await self._rpc.wait_for_settlement(self._config, signed.signature)  # type: ignore[attr-defined]
            except SolanaBackendError as exc:
                # Submission may have succeeded. Preserve signature/bytes and fail
                # closed; retry recovers by chain lookup before any resubmission.
                return fail(exc.code)
            required_ok = evidence.state == "finalized" or (
                self._config.commitment == "confirmed" and evidence.state == "confirmed"
            )
            if not required_ok:
                return fail(HttpCode.TIMEOUT if evidence.state in {"timeout", "unknown", "processed"} else HttpCode.NETWORK_FAILURE)
            result = SignResult(ok=True, code=HttpCode.OK, request_id=request_id,
                correlation_id=correlation_id, tx_id=signed.signature,
                canonical_hash=canonical, fee_lamports=evidence.fee_lamports)
            with self._lock:
                self._results[request_id] = result
            return result
        finally:
            with self._lock:
                self._in_flight.discard(request_id)
