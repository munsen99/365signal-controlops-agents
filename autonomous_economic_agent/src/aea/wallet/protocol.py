"""Phase A wallet protocol and inbound DTOs. extra='forbid'."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import Field, field_serializer, field_validator

from aea.policy.reasons import HttpCode, ReasonCode
from aea.types import AeaBaseModel, TreasuryAsset, format_amount, parse_unsigned_amount

TX_ID_RE = re.compile(r"^mocktx_[0-9a-f]{32}$")
FaultName = Literal["none", "insufficient_funds", "network", "timeout", "reject"]

WALLET_PORT = 18704
WALLET_HOST = "127.0.0.1"


class WalletError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class WalletTx(AeaBaseModel):
    tx_id: str
    asset: TreasuryAsset
    amount: Decimal
    direction: Literal["credit", "debit"]
    reason: str
    idempotency_key: str = Field(min_length=8, max_length=128)
    destination: str | None = None
    status: Literal["settled"] = "settled"
    created_at: datetime

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("tx_id")
    @classmethod
    def _tx_id(cls, value: str) -> str:
        if not TX_ID_RE.fullmatch(value):
            raise ValueError("tx_id must be mocktx_ plus 128-bit hex")
        return value

    @field_serializer("amount")
    def _dump_amount(self, value: Decimal) -> str:
        return format_amount(value)


class CreditRequest(AeaBaseModel):
    asset: TreasuryAsset
    amount: Decimal
    reason: str
    idempotency_key: str = Field(min_length=8, max_length=128)
    tx_id: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("tx_id")
    @classmethod
    def _tx_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not TX_ID_RE.fullmatch(value):
            raise ValueError("tx_id must be mocktx_ plus 128-bit hex")
        return value


class DebitRequest(AeaBaseModel):
    asset: TreasuryAsset
    amount: Decimal
    destination: str
    reason: str
    idempotency_key: str = Field(min_length=8, max_length=128)
    tx_id: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_validator("destination")
    @classmethod
    def _destination(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("destination is required")
        return value

    @field_validator("tx_id")
    @classmethod
    def _tx_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not TX_ID_RE.fullmatch(value):
            raise ValueError("tx_id must be mocktx_ plus 128-bit hex")
        return value


class WalletBackend(Protocol):
    def get_balances(self) -> dict[str, Decimal]: ...

    def credit(
        self,
        *,
        asset: str,
        amount: Decimal,
        tx_id: str,
        reason: str,
        idempotency_key: str,
    ) -> WalletTx: ...

    def debit(
        self,
        *,
        asset: str,
        amount: Decimal,
        destination: str,
        tx_id: str,
        reason: str,
        idempotency_key: str,
    ) -> WalletTx: ...

    def get_tx(self, tx_id: str) -> WalletTx | None: ...

    def set_fault(self, fault: FaultName) -> None: ...


def fingerprint(
    *,
    direction: str,
    asset: str,
    amount: Decimal,
    reason: str,
    destination: str | None,
) -> tuple[str, str, str, str, str]:
    return (
        direction,
        asset,
        format_amount(amount),
        reason,
        destination or "",
    )


# Re-export codes used at the HTTP boundary.
INSUFFICIENT_FUNDS = ReasonCode.INSUFFICIENT_FUNDS
VALIDATION_ERROR = HttpCode.VALIDATION_ERROR
UNAUTHENTICATED = HttpCode.UNAUTHENTICATED
FORBIDDEN = HttpCode.FORBIDDEN
NOT_FOUND = HttpCode.NOT_FOUND
IDEMPOTENCY_CONFLICT = HttpCode.IDEMPOTENCY_CONFLICT
CONFLICT = HttpCode.CONFLICT
NETWORK_FAILURE = HttpCode.NETWORK_FAILURE
UNSUPPORTED_WALLET_PHASE = ReasonCode.UNSUPPORTED_WALLET_PHASE
PROHIBITED_TOKEN = ReasonCode.PROHIBITED_TOKEN
