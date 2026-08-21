"""Inbound DTOs forbid extra fields including force=true."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aea.types import Money, PaymentRequest, PolicyInput, PolicyOutput


def _policy_input_kwargs() -> dict:
    return {
        "amount": "0.050000",
        "asset": "USDC",
        "destination": "mock:counterparty:mkt-escrow",
        "destination_class": "marketplace_escrow",
        "destination_allowed": True,
        "job_id": str(uuid4()),
        "purpose": "marketplace_acceptance_fee",
        "daily_spend_usdc": "0.000000",
        "outstanding_exposure_usdc": "0.000000",
        "wallet_balances": {"USDC": "20.000000", "SOL": "0.050000"},
        "policy_version": "policy/v0.1.0",
        "policy_hash": "a" * 64,
        "frozen": False,
        "signer_enabled": True,
        "wallet_phase": "A",
        "correlation_id": str(uuid4()),
    }


def test_policy_input_accepts_canonical_body() -> None:
    model = PolicyInput.model_validate(_policy_input_kwargs())
    assert model.amount == Decimal("0.050000")
    dumped = model.model_dump(mode="json")
    assert dumped["amount"] == "0.050000"
    assert "force" not in dumped


def test_policy_input_rejects_force_true() -> None:
    body = _policy_input_kwargs()
    body["force"] = True
    with pytest.raises(ValidationError):
        PolicyInput.model_validate(body)


def test_policy_input_rejects_float_amount() -> None:
    body = _policy_input_kwargs()
    body["amount"] = 0.05
    with pytest.raises(ValidationError):
        PolicyInput.model_validate(body)


def test_payment_request_requires_job_id_and_money() -> None:
    req = PaymentRequest.model_validate(
        {
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": str(uuid4()),
            "expected_return": {"amount": "0.500000", "asset": "USDC"},
            "idempotency_key": "idem-key-01",
        }
    )
    assert req.expected_return.asset == "USDC"
    extra = req.model_dump(mode="json")
    extra["force"] = True
    with pytest.raises(ValidationError):
        PaymentRequest.model_validate(extra)


def test_money_rejects_scientific_notation() -> None:
    with pytest.raises(ValidationError):
        Money.model_validate({"amount": "1e-2", "asset": "USDC"})


def test_policy_output_forbids_extra() -> None:
    body = {
        "decision": "rejected",
        "reason_code": "MAX_OUTBOUND_EXCEEDED",
        "approved_amount": None,
        "policy_version": "policy/v0.1.0",
        "policy_hash": "b" * 64,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": str(uuid4()),
        "canonical_request_hash": None,
        "force": True,
    }
    with pytest.raises(ValidationError):
        PolicyOutput.model_validate(body)
