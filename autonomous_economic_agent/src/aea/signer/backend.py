"""Signer protocol, inbound DTOs, canonical hashing, and request HMAC.

The signer does not decide economic policy. It verifies an already-approved
request, binds that approval to a canonical hash plus HMAC-SHA256, enforces
freeze/signer controls, and is the only caller of wallet debit.

Signer canonical hash vs PR3 policy hash
----------------------------------------
``canonical_approved_hash`` (this module) covers the M0 §9 payment fields
**plus** ``request_id`` and ``policy_hash``. That is the hash the signer
stores and the HMAC binds.

``PolicyOutput.canonical_request_hash`` (PR3 ``engine.py``) covers the
policy snapshot only: it **omits** ``request_id`` and ``policy_hash``.
The two hashes are intentionally distinct. Later PR10 wiring must
construct the signer approval artifact with ``canonical_approved_hash``
and ``compute_request_hmac``; it must not reuse the policy-engine hash
as ``canonical_hash`` on ``POST /v1/sign``.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from pydantic import Field, field_serializer, field_validator

from aea.hashing import canonical_json_bytes, canonical_json_hash
from aea.policy.reasons import HttpCode, ReasonCode
from aea.types import AeaBaseModel, TreasuryAsset, format_amount, parse_unsigned_amount

HMAC_MIN_KEY_CHARS = 32

HASH_RE = re.compile(r"^[0-9a-f]{64}$")

CANONICAL_APPROVED_KEYS = (
    "amount",
    "approved_amount",
    "approved_at",
    "asset",
    "correlation_id",
    "destination",
    "job_id",
    "policy_hash",
    "policy_version",
    "purpose",
    "request_id",
)


class SignerError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class PhaseBApprovalContext(AeaBaseModel):
    """Public Solana intent fields MAC-bound by Policy before signer execution."""

    network: str
    payer: str
    source_mint: str
    source_token_account: str
    destination_owner: str
    destination_token_account: str
    amount_base_units: int = Field(gt=0)
    decimals: int = Field(ge=0, le=18)


class ApprovedRequest(AeaBaseModel):
    """Canonical approved payment request (M0 §9) plus policy_hash binding."""

    request_id: UUID
    amount: Decimal
    asset: TreasuryAsset
    destination: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    job_id: UUID
    policy_version: str = Field(min_length=1)
    policy_hash: str
    approved_amount: Decimal
    approved_at: datetime
    correlation_id: UUID
    phase_b_context: PhaseBApprovalContext | None = None

    @field_validator("amount", "approved_amount", mode="before")
    @classmethod
    def _amount(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("policy_hash")
    @classmethod
    def _hash(cls, value: str) -> str:
        if not HASH_RE.fullmatch(value):
            raise ValueError("policy_hash must be 64 lowercase hex characters")
        return value

    @field_validator("approved_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("approved_at must be timezone-aware RFC3339")
        return value

    @field_validator("destination", "purpose")
    @classmethod
    def _strip_nonempty(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must be non-empty")
        return text

    @field_serializer("amount", "approved_amount")
    def _dump_amount(self, value: Decimal) -> str:
        return format_amount(value)

    @field_serializer("approved_at")
    def _dump_at(self, value: datetime) -> str:
        return value.isoformat()


class SignRequest(AeaBaseModel):
    approved_request: ApprovedRequest
    canonical_hash: str
    policy_version: str = Field(min_length=1)
    request_hmac: str

    @field_validator("canonical_hash", "request_hmac")
    @classmethod
    def _hash(cls, value: str) -> str:
        if not HASH_RE.fullmatch(value):
            raise ValueError("must be 64 lowercase hex characters")
        return value


class SignResult(AeaBaseModel):
    ok: bool
    code: str
    request_id: UUID
    correlation_id: UUID
    reason_code: str | None = None
    tx_id: str | None = None
    canonical_hash: str | None = None
    replay: bool = False
    fee_lamports: int | None = Field(default=None, ge=0)


class WalletDebitError(Exception):
    """Transport or business error from the wallet debit call."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class WalletDebitPort(Protocol):
    """Sole outbound spend port. No credit method."""

    async def debit(
        self,
        *,
        asset: str,
        amount: Decimal,
        destination: str,
        reason: str,
        idempotency_key: str,
    ) -> str: ...


class SignerBackend(Protocol):
    async def sign(self, request: SignRequest) -> SignResult: ...

    def set_enabled(self, enabled: bool) -> None: ...


def approved_canonical_dict(req: ApprovedRequest) -> dict[str, object]:
    """Exact key set hashed by the signer. policy_hash is an additive binding."""
    out: dict[str, object] = {
        "amount": format_amount(req.amount),
        "approved_amount": format_amount(req.approved_amount),
        "approved_at": req.approved_at.isoformat(),
        "asset": req.asset,
        "correlation_id": str(req.correlation_id),
        "destination": req.destination,
        "job_id": str(req.job_id),
        "policy_hash": req.policy_hash,
        "policy_version": req.policy_version,
        "purpose": req.purpose,
        "request_id": str(req.request_id),
    }
    if req.phase_b_context is not None:
        out["phase_b_context"] = req.phase_b_context.model_dump(mode="json")
    return out


def canonical_approved_hash(req: ApprovedRequest) -> str:
    """Signer canonical hash. Not ``PolicyOutput.canonical_request_hash``."""
    return canonical_json_hash(approved_canonical_dict(req))


def signer_approval_artifact(
    *,
    approved_request: ApprovedRequest,
    canonical_hash: str,
    policy_version: str,
) -> dict[str, object]:
    """Canonical bytes the policy caller HMACs and the signer verifies.

    Includes the approved request, signer canonical hash, policy version,
    and policy hash. ``request_hmac`` itself is excluded (not circular).
    """
    return {
        "approved_request": approved_canonical_dict(approved_request),
        "canonical_hash": canonical_hash,
        "policy_hash": approved_request.policy_hash,
        "policy_version": policy_version,
    }


def compute_request_hmac(
    hmac_key: str,
    *,
    approved_request: ApprovedRequest,
    canonical_hash: str,
    policy_version: str,
) -> str:
    """HMAC-SHA256 (hex) over the canonical signer approval artifact.

    Held by the policy-side caller. Hermes, the model, and control must
    never receive ``hmac_key``. Distinct from ``AEA_SIGNER_TOKEN``.
    """
    if not hmac_key or len(hmac_key) < HMAC_MIN_KEY_CHARS:
        raise ValueError("hmac_key must be at least 32 characters")
    payload = canonical_json_bytes(
        signer_approval_artifact(
            approved_request=approved_request,
            canonical_hash=canonical_hash,
            policy_version=policy_version,
        )
    )
    return hmac.new(hmac_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_request_hmac(
    hmac_key: str,
    presented: str,
    *,
    approved_request: ApprovedRequest,
    canonical_hash: str,
    policy_version: str,
) -> bool:
    """Constant-time HMAC-SHA256 check. Missing/malformed ``presented`` is False."""
    if not isinstance(presented, str) or not HASH_RE.fullmatch(presented):
        return False
    try:
        expected = compute_request_hmac(
            hmac_key,
            approved_request=approved_request,
            canonical_hash=canonical_hash,
            policy_version=policy_version,
        )
    except ValueError:
        return False
    return hmac.compare_digest(presented, expected)


# Re-export codes used at the signer boundary.
AGENT_FROZEN = HttpCode.AGENT_FROZEN
SIGNER_DISABLED = HttpCode.SIGNER_DISABLED
REPLAY_APPROVED_REQUEST = HttpCode.REPLAY_APPROVED_REQUEST
IDEMPOTENT_REPLAY = HttpCode.IDEMPOTENT_REPLAY
POLICY_TAMPER = ReasonCode.POLICY_TAMPER
AMOUNT_MISMATCH = ReasonCode.AMOUNT_MISMATCH
INSUFFICIENT_FUNDS = ReasonCode.INSUFFICIENT_FUNDS
NETWORK_FAILURE = HttpCode.NETWORK_FAILURE
VALIDATION_ERROR = HttpCode.VALIDATION_ERROR
OK = HttpCode.OK
