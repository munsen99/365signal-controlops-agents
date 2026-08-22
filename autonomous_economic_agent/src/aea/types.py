"""Shared pydantic v2 models. Every inbound DTO forbids extra fields."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

MONEY_AMOUNT_RE = re.compile(r"^[0-9]+(\.[0-9]{1,8})?$")
SIGNED_MONEY_AMOUNT_RE = re.compile(r"^[+-]?[0-9]+(\.[0-9]{1,8})?$")
NATIVE_AMOUNT_RE = re.compile(r"^[0-9]+(\.[0-9]{1,18})?$")

WalletPhase = Literal["A", "B", "C", "E"]
TreasuryAsset = Literal["USDC", "SOL", "ETH"]


class AeaBaseModel(BaseModel):
    """Inbound DTOs reject unknown keys including ``force=true``."""

    model_config = ConfigDict(extra="forbid")


def parse_unsigned_amount(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("money amounts must be decimal strings, not float/bool")
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise ValueError("money amounts must be decimal strings")
    if not MONEY_AMOUNT_RE.fullmatch(text):
        raise ValueError("money amount does not match unsigned decimal pattern")
    return Decimal(text)


def parse_signed_amount(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("money amounts must be decimal strings, not float/bool")
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise ValueError("money amounts must be decimal strings")
    if not SIGNED_MONEY_AMOUNT_RE.fullmatch(text):
        raise ValueError("money amount does not match signed decimal pattern")
    return Decimal(text)


def format_amount(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.000001"))
    return format(quantized, "f")


def parse_unsigned_native_amount(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("native amounts must be decimal strings, not float/bool")
    text = str(value) if isinstance(value, (str, int)) else ""
    if not NATIVE_AMOUNT_RE.fullmatch(text):
        raise ValueError("native amount must have at most 18 decimal places")
    return Decimal(text)


def format_asset_amount(value: Decimal, asset: str) -> str:
    # The accepted ledger stores monetary mirrors to 8 decimal places. Exact
    # EVM wei remains in chain_transaction_evidence and is never discarded.
    places = Decimal("0.00000001") if asset == "ETH" else Decimal("0.000001")
    return format(value.quantize(places), "f")


class Money(AeaBaseModel):
    amount: Decimal
    asset: TreasuryAsset

    @field_validator("amount", mode="before")
    @classmethod
    def _amount_unsigned(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_serializer("amount")
    def _dump_amount(self, value: Decimal) -> str:
        return format_amount(value)


class PolicyInput(AeaBaseModel):
    amount: Decimal
    asset: TreasuryAsset
    destination: str
    destination_class: str
    destination_allowed: bool
    job_id: UUID | None
    purpose: str
    daily_spend_usdc: Decimal
    outstanding_exposure_usdc: Decimal
    wallet_balances: dict[str, Decimal]
    policy_version: str
    policy_hash: str
    frozen: bool
    signer_enabled: bool
    wallet_phase: WalletPhase
    correlation_id: UUID
    expected_return_usdc: Decimal | None = None

    @field_validator("amount", "daily_spend_usdc", "outstanding_exposure_usdc", mode="before")
    @classmethod
    def _unsigned(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("expected_return_usdc", mode="before")
    @classmethod
    def _optional_unsigned(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_unsigned_amount(value)

    @field_validator("wallet_balances", mode="before")
    @classmethod
    def _balances(cls, value: object) -> dict[str, Decimal]:
        if not isinstance(value, dict):
            raise ValueError("wallet_balances must be an object")
        return {str(k): parse_unsigned_amount(v) for k, v in value.items()}

    @field_serializer("amount", "daily_spend_usdc", "outstanding_exposure_usdc")
    def _dump_unsigned(self, value: Decimal) -> str:
        return format_amount(value)

    @field_serializer("expected_return_usdc")
    def _dump_optional(self, value: Decimal | None) -> str | None:
        return None if value is None else format_amount(value)

    @field_serializer("wallet_balances")
    def _dump_balances(self, value: dict[str, Decimal]) -> dict[str, str]:
        return {k: format_amount(v) for k, v in value.items()}


class PolicyOutput(AeaBaseModel):
    decision: Literal["approved", "rejected"]
    reason_code: str | None
    approved_amount: Decimal | None
    policy_version: str
    policy_hash: str
    timestamp: datetime
    correlation_id: UUID
    canonical_request_hash: str | None

    @field_validator("approved_amount", mode="before")
    @classmethod
    def _optional_unsigned(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_unsigned_amount(value)

    @field_serializer("approved_amount")
    def _dump_approved(self, value: Decimal | None) -> str | None:
        return None if value is None else format_amount(value)


class PaymentRequest(AeaBaseModel):
    amount: Decimal
    asset: TreasuryAsset
    destination: str
    purpose: str
    job_id: UUID
    expected_return: Money
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("amount", mode="before")
    @classmethod
    def _unsigned(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_serializer("amount")
    def _dump_amount(self, value: Decimal) -> str:
        return format_amount(value)
