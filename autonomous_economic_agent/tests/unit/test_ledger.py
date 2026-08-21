"""Ledger state machines, money snapshot, and inbound DTO fail-closed."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aea.ledger.errors import LedgerError
from aea.ledger.models import CostCreate, RevenueCreate, TransferCreate
from aea.ledger.service import usdc_equivalent
from aea.ledger.transitions import ensure_transition


def test_job_cannot_leave_completed() -> None:
    with pytest.raises(LedgerError) as exc:
        ensure_transition("job", "completed", "submitted")
    assert exc.value.code == "CONFLICT"


def test_payment_cannot_revert_approved_to_pending() -> None:
    with pytest.raises(LedgerError) as exc:
        ensure_transition("payment", "approved", "pending")
    assert exc.value.code == "CONFLICT"


def test_rejected_payment_is_terminal() -> None:
    with pytest.raises(LedgerError) as exc:
        ensure_transition("payment", "rejected", "approved")
    assert exc.value.code == "CONFLICT"


def test_opportunity_declined_is_terminal() -> None:
    with pytest.raises(LedgerError) as exc:
        ensure_transition("opportunity", "declined", "accepted")
    assert exc.value.code == "CONFLICT"


def test_legal_job_path() -> None:
    ensure_transition("job", "accepted", "performing")
    ensure_transition("job", "performing", "performed")
    ensure_transition("job", "performed", "submitted")
    ensure_transition("job", "submitted", "completed")


def test_usdc_equivalent_usdc_is_identity() -> None:
    assert usdc_equivalent(
        amount=Decimal("0.050000"),
        asset="USDC",
        snapshot=Decimal("150"),
        ceiling=Decimal("500"),
    ) == Decimal("0.050000")


def test_sol_fee_uses_snapshot_not_oracle() -> None:
    assert usdc_equivalent(
        amount=Decimal("0.010000"),
        asset="SOL",
        snapshot=Decimal("150"),
        ceiling=Decimal("500"),
    ) == Decimal("1.500000")


def test_sol_fee_missing_snapshot_uses_ceiling() -> None:
    assert usdc_equivalent(
        amount=Decimal("0.010000"),
        asset="SOL",
        snapshot=None,
        ceiling=Decimal("500"),
    ) == Decimal("5.000000")


def test_cost_rejects_force_and_float() -> None:
    with pytest.raises(ValidationError):
        CostCreate.model_validate(
            {
                "category": "compute",
                "amount": "0.001000",
                "asset": "USDC",
                "idempotency_key": "cost-force-01",
                "force": True,
            }
        )
    with pytest.raises(ValidationError):
        CostCreate.model_validate(
            {
                "category": "compute",
                "amount": 0.001,
                "asset": "USDC",
                "idempotency_key": "cost-float-01",
            }
        )


def test_unverified_revenue_flag_is_on_dto_but_service_must_reject() -> None:
    req = RevenueCreate.model_validate(
        {
            "job_id": str(uuid4()),
            "amount": "0.500000",
            "transaction_reference": "mocktx_" + "aa" * 16,
            "verified": False,
            "idempotency_key": "rev-unverified-01",
        }
    )
    assert req.verified is False


def test_seed_transfer_classification_rejected_by_dto() -> None:
    with pytest.raises(ValidationError):
        TransferCreate.model_validate(
            {
                "asset": "USDC",
                "amount": "20.000000",
                "direction": "in",
                "classification": "opening_capital",
                "idempotency_key": "xfer-seed-01",
            }
        )
