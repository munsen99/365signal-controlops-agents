"""Phase A mock signer. Verifies an approved request and calls wallet debit.

Does not evaluate economic policy. Does not credit the wallet. Does not
load Solana, LLM, marketplace, or live-wallet backends.
"""

from __future__ import annotations

from collections.abc import Callable
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
    WalletDebitError,
    WalletDebitPort,
    canonical_approved_hash,
    verify_request_hmac,
)
from aea.signer.freeze import inspect_freeze
from aea.types import format_amount


class MockSigner:
    """Deterministic isolated signer. request_id is the replay key."""

    def __init__(
        self,
        *,
        freeze_path: Path | str | None,
        expected_policy_version: str,
        expected_policy_hash: str,
        debit: WalletDebitPort,
        hmac_key: str,
        signer_enabled: bool = True,
        db_frozen_reader: Callable[[], Any] | None = None,
    ) -> None:
        if not expected_policy_version:
            raise ValueError("expected_policy_version is required")
        if not HASH_RE.fullmatch(expected_policy_hash):
            raise ValueError("expected_policy_hash must be 64 lowercase hex characters")
        if debit is None:
            raise ValueError("wallet debit port is required")
        if hasattr(debit, "credit"):
            raise ValueError("signer debit port must not expose credit")
        if not hmac_key or len(hmac_key) < HMAC_MIN_KEY_CHARS:
            raise ValueError("hmac_key must be at least 32 characters")
        self._freeze_path = freeze_path
        self._expected_policy_version = expected_policy_version
        self._expected_policy_hash = expected_policy_hash
        self._debit = debit
        self._hmac_key = hmac_key
        self._enabled = bool(signer_enabled)
        self._db_frozen_reader = db_frozen_reader
        self._lock = Lock()
        self._results: dict[UUID, SignResult] = {}
        self._hashes: dict[UUID, str] = {}
        self._in_flight: set[UUID] = set()

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    @property
    def signer_enabled(self) -> bool:
        return self._enabled

    @property
    def hmac_key(self) -> str:
        return self._hmac_key

    def inspect_current_freeze(self) -> Any:
        db_kw: dict[str, Any] = {}
        if self._db_frozen_reader is not None:
            try:
                db_kw["db_frozen"] = self._db_frozen_reader()
            except Exception:
                db_kw["db_frozen"] = None
        return inspect_freeze(self._freeze_path, **db_kw)

    async def sign(self, request: SignRequest) -> SignResult:
        approved = request.approved_request
        request_id = approved.request_id
        correlation_id = approved.correlation_id

        def fail(code: str, *, reason: str | None = None) -> SignResult:
            return SignResult(
                ok=False,
                code=code,
                request_id=request_id,
                correlation_id=correlation_id,
                reason_code=reason or code,
                tx_id=None,
                canonical_hash=None,
                replay=False,
            )

        if not verify_request_hmac(
            self._hmac_key,
            request.request_hmac,
            approved_request=approved,
            canonical_hash=request.canonical_hash,
            policy_version=request.policy_version,
        ):
            return fail(HttpCode.UNAUTHENTICATED)

        if request.policy_version != approved.policy_version:
            return fail(HttpCode.VALIDATION_ERROR, reason=ReasonCode.POLICY_TAMPER)
        if (
            approved.policy_version != self._expected_policy_version
            or approved.policy_hash != self._expected_policy_hash
        ):
            return fail(ReasonCode.POLICY_TAMPER)

        if format_amount(approved.amount) != format_amount(approved.approved_amount):
            return fail(ReasonCode.AMOUNT_MISMATCH)

        recomputed = canonical_approved_hash(approved)
        if recomputed != request.canonical_hash:
            return fail(HttpCode.REPLAY_APPROVED_REQUEST)

        with self._lock:
            previous = self._results.get(request_id)
            previous_hash = self._hashes.get(request_id)
            enabled = self._enabled
            if previous is None and request_id in self._in_flight:
                return fail(HttpCode.CONFLICT)
            if previous is None:
                self._in_flight.add(request_id)
                claimed = True
            else:
                claimed = False
        if previous is not None:
            if previous_hash != recomputed:
                return fail(HttpCode.REPLAY_APPROVED_REQUEST)
            return previous.model_copy(update={"replay": True, "code": HttpCode.IDEMPOTENT_REPLAY})

        try:
            if not enabled:
                return fail(HttpCode.SIGNER_DISABLED)

            inspection = self.inspect_current_freeze()
            if inspection.frozen:
                return fail(HttpCode.AGENT_FROZEN)

            try:
                tx_id = await self._debit.debit(
                    asset=approved.asset,
                    amount=approved.amount,
                    destination=approved.destination,
                    reason=approved.purpose,
                    idempotency_key=str(request_id),
                )
            except WalletDebitError as exc:
                return fail(exc.code)

            result = SignResult(
                ok=True,
                code=HttpCode.OK,
                request_id=request_id,
                correlation_id=correlation_id,
                reason_code=None,
                tx_id=tx_id,
                canonical_hash=recomputed,
                replay=False,
            )
            with self._lock:
                self._results[request_id] = result
                self._hashes[request_id] = recomputed
            return result
        finally:
            if claimed:
                with self._lock:
                    self._in_flight.discard(request_id)
