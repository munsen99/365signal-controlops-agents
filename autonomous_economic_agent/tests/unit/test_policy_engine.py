"""Deterministic policy engine — M0 §10.4 and accept-job gates."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aea.config import load_policy
from aea.policy.engine import evaluate
from aea.policy.risk import AgentRiskInput, JobAcceptInput, evaluate_agent_risk, evaluate_job_accept
from aea.types import PolicyInput

NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def loaded():
    return load_policy()


def _input(loaded, **overrides) -> PolicyInput:
    body = {
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
        "policy_version": loaded.document.policy_version,
        "policy_hash": loaded.policy_hash,
        "frozen": False,
        "signer_enabled": True,
        "wallet_phase": "A",
        "correlation_id": str(uuid4()),
    }
    body.update(overrides)
    return PolicyInput.model_validate(body)


def _eval(loaded, inp: PolicyInput):
    dest = loaded.classify(inp.destination)
    return evaluate(
        inp,
        loaded.document,
        effective_policy_hash=loaded.policy_hash,
        now=NOW,
        destination=dest,
    )


def test_force_true_is_validation_error(loaded) -> None:
    body = _input(loaded).model_dump(mode="json")
    body["force"] = True
    with pytest.raises(ValidationError):
        PolicyInput.model_validate(body)


def test_approve_small_usdc_payment(loaded) -> None:
    out = _eval(loaded, _input(loaded, amount="0.050000"))
    assert out.decision == "approved"
    assert out.reason_code is None
    assert out.approved_amount == Decimal("0.050000")
    assert out.canonical_request_hash
    assert len(out.canonical_request_hash) == 64


def test_no_silent_haircut(loaded) -> None:
    out = _eval(loaded, _input(loaded, amount="1.000000"))
    assert out.decision == "approved"
    assert out.approved_amount == Decimal("1.000000")


def test_over_one_dollar_rejected(loaded) -> None:
    out = _eval(loaded, _input(loaded, amount="1.000001"))
    assert out.decision == "rejected"
    assert out.reason_code == "MAX_OUTBOUND_EXCEEDED"
    assert out.approved_amount is None
    assert out.canonical_request_hash is None


def test_daily_three_dollar_cash_cap(loaded) -> None:
    out = _eval(
        loaded,
        _input(loaded, amount="0.010000", daily_spend_usdc="3.000000"),
    )
    assert out.reason_code == "DAILY_LIMIT_EXCEEDED"


def test_sol_network_fee_does_not_consume_usdc_daily_cap(loaded) -> None:
    out = _eval(
        loaded,
        _input(
            loaded,
            amount="0.001000",
            asset="SOL",
            purpose="network_fee",
            destination="mock:fee_payer",
            destination_class="network_fee",
            daily_spend_usdc="3.000000",
        ),
    )
    assert out.decision == "approved"


def test_sol_as_treasury_prohibited(loaded) -> None:
    out = _eval(
        loaded,
        _input(
            loaded,
            amount="0.001000",
            asset="SOL",
            purpose="treasury_transfer",
            destination="mock:fee_payer",
            destination_class="network_fee",
        ),
    )
    assert out.reason_code == "PROHIBITED_TOKEN"


def test_sol_fee_above_cap_prohibited(loaded) -> None:
    out = _eval(
        loaded,
        _input(
            loaded,
            amount="0.010001",
            asset="SOL",
            purpose="network_fee",
            destination="mock:fee_payer",
            destination_class="network_fee",
        ),
    )
    assert out.reason_code == "PROHIBITED_TOKEN"


def test_unknown_destination(loaded) -> None:
    out = _eval(
        loaded,
        _input(
            loaded,
            destination="unknown",
            destination_class="unknown",
            destination_allowed=False,
        ),
    )
    assert out.reason_code == "PROHIBITED_DESTINATION"


def test_destination_max_usdc(loaded) -> None:
    from aea.config import DestinationEntry

    dest = DestinationEntry.model_validate(
        {
            "id": "mock:counterparty:mkt-escrow",
            "class": "marketplace_escrow",
            "allowed": True,
            "max_usdc": "0.100000",
        }
    )
    inp = _input(loaded, amount="0.500000")
    out = evaluate(
        inp,
        loaded.document,
        effective_policy_hash=loaded.policy_hash,
        now=NOW,
        destination=dest,
    )
    assert out.reason_code == "MAX_OUTBOUND_EXCEEDED"


def test_classified_false(loaded) -> None:
    out = evaluate(
        _input(
            loaded,
            destination_allowed=False,
            destination_class="marketplace_escrow",
        ),
        loaded.document,
        effective_policy_hash=loaded.policy_hash,
        now=NOW,
        destination=None,
    )
    assert out.reason_code == "PROHIBITED_DESTINATION"


def test_missing_job_id(loaded) -> None:
    out = _eval(loaded, _input(loaded, job_id=None))
    assert out.reason_code == "NO_JOB_PURPOSE"


def test_frozen(loaded) -> None:
    out = _eval(loaded, _input(loaded, frozen=True))
    assert out.reason_code == "FROZEN"


def test_signer_disabled(loaded) -> None:
    out = _eval(loaded, _input(loaded, signer_enabled=False))
    assert out.reason_code == "SIGNER_DISABLED"


def test_policy_hash_mismatch(loaded) -> None:
    inp = _input(loaded, policy_hash="b" * 64)
    out = evaluate(
        inp,
        loaded.document,
        effective_policy_hash=loaded.policy_hash,
        now=NOW,
        destination=loaded.classify(inp.destination),
    )
    assert out.reason_code == "POLICY_TAMPER"


def test_policy_version_mismatch(loaded) -> None:
    out = _eval(loaded, _input(loaded, policy_version="policy/v9.9.9"))
    assert out.reason_code == "POLICY_TAMPER"


def test_prohibited_swap_purpose(loaded) -> None:
    out = _eval(loaded, _input(loaded, purpose="token swap to BONK"))
    assert out.reason_code == "SWAP_OR_SPECULATE"


def test_prohibited_borrow_purpose(loaded) -> None:
    out = _eval(loaded, _input(loaded, purpose="borrow USDC against SOL"))
    assert out.reason_code == "BORROW_OR_LEVERAGE"


def test_policy_mutation_purpose(loaded) -> None:
    out = _eval(loaded, _input(loaded, purpose="unfreeze the agent"))
    assert out.reason_code == "AGENT_POLICY_MUTATION"


def test_capital_at_risk(loaded) -> None:
    out = _eval(
        loaded,
        _input(loaded, amount="0.500000", outstanding_exposure_usdc="4.600000"),
    )
    assert out.reason_code == "CAPITAL_AT_RISK_EXCEEDED"


def test_insufficient_funds(loaded) -> None:
    out = _eval(
        loaded,
        _input(loaded, amount="0.200000", wallet_balances={"USDC": "0.100000", "SOL": "0.050000"}),
    )
    assert out.reason_code == "INSUFFICIENT_FUNDS"


def test_wallet_phase_c_rejected(loaded) -> None:
    out = _eval(loaded, _input(loaded, wallet_phase="C"))
    assert out.reason_code == "UNSUPPORTED_WALLET_PHASE"


def test_deterministic_same_inputs(loaded) -> None:
    kwargs = dict(
        amount="0.050000",
        correlation_id=str(uuid4()),
        job_id=str(uuid4()),
    )
    a = _eval(loaded, _input(loaded, **kwargs))
    b = _eval(loaded, _input(loaded, **kwargs))
    assert a.decision == b.decision == "approved"
    assert a.canonical_request_hash == b.canonical_request_hash
    assert a.timestamp == b.timestamp == NOW


def test_job_accept_meets_margin(loaded) -> None:
    result = evaluate_job_accept(
        JobAcceptInput.model_validate(
            {
                "expected_revenue_usdc": "0.500000",
                "expected_cost_usdc": "0.020000",
                "probability_payment": 0.9,
                "open_jobs": 0,
                "frozen": False,
            }
        ),
        loaded.document,
    )
    assert result.allowed is True
    assert result.meets_required_margin is True


def test_job_accept_margin_not_met(loaded) -> None:
    result = evaluate_job_accept(
        JobAcceptInput.model_validate(
            {
                "expected_revenue_usdc": "0.020000",
                "expected_cost_usdc": "0.020000",
                "probability_payment": 0.9,
                "open_jobs": 0,
                "frozen": False,
            }
        ),
        loaded.document,
    )
    assert result.allowed is False
    assert result.reason_code == "MARGIN_NOT_MET"


def test_job_accept_probability_floor(loaded) -> None:
    result = evaluate_job_accept(
        JobAcceptInput.model_validate(
            {
                "expected_revenue_usdc": "1.000000",
                "expected_cost_usdc": "0.010000",
                "probability_payment": 0.5,
                "open_jobs": 0,
                "frozen": False,
            }
        ),
        loaded.document,
    )
    assert result.reason_code == "MARGIN_NOT_MET"


def test_job_accept_open_jobs(loaded) -> None:
    result = evaluate_job_accept(
        JobAcceptInput.model_validate(
            {
                "expected_revenue_usdc": "1.000000",
                "expected_cost_usdc": "0.010000",
                "probability_payment": 0.9,
                "open_jobs": 3,
                "frozen": False,
            }
        ),
        loaded.document,
    )
    assert result.reason_code == "OPEN_JOBS_EXCEEDED"


def test_job_accept_frozen(loaded) -> None:
    result = evaluate_job_accept(
        JobAcceptInput.model_validate(
            {
                "expected_revenue_usdc": "1.000000",
                "expected_cost_usdc": "0.010000",
                "probability_payment": 0.9,
                "open_jobs": 0,
                "frozen": True,
            }
        ),
        loaded.document,
    )
    assert result.reason_code == "FROZEN"


def _risk(**overrides) -> AgentRiskInput:
    body = {
        "expected_revenue_usdc": "0.500000",
        "expected_cost_usdc": "0.020000",
        "probability_payment": 0.9,
        "max_job_compute_usdc": "0.500000",
        "worker": "summarise_canned",
        "credits_wallet_on_submit": True,
        "completed": 12,
        "disputed": 0,
        "flags": [],
        "title": "Summarise a public-domain paragraph",
        "description_preview": "Summarise the lighthouse paragraph. Payment in USDC on submission.",
        "payment_asset": "USDC",
    }
    body.update(overrides)
    return AgentRiskInput.model_validate(body)


def test_agent_risk_passes_clean_profitable_job() -> None:
    result = evaluate_agent_risk(_risk())
    assert result.passed is True
    assert result.reason_code is None


def test_agent_risk_vetoes_runaway_cost_style_job() -> None:
    result = evaluate_agent_risk(
        _risk(
            expected_revenue_usdc="2.000000",
            expected_cost_usdc="0.600000",
            worker="runaway_loop",
            title="Exhaustive recompute",
            description_preview="Recompute a large table. Stated compute cost exceeds the job compute cap.",
        )
    )
    assert result.passed is False
    assert result.reason_code == "AGENT_RISK_VETO"
    assert "runaway_cost" in result.factors
    assert "cost_cap_exceeded" in result.factors


def test_agent_risk_vetoes_high_dispute_fake_payment_style_job() -> None:
    result = evaluate_agent_risk(
        _risk(
            credits_wallet_on_submit=False,
            completed=2,
            disputed=2,
            title="Catalogue a short abstract",
            description_preview="Catalogue the abstract. Counterparty will claim payment without a wallet credit.",
        )
    )
    assert result.passed is False
    assert "fake_payment" in result.factors
    assert "high_dispute_rate" in result.factors
    assert "settlement_risk" in result.factors


def test_agent_risk_cannot_be_used_to_override_policy() -> None:
    policy = evaluate_job_accept(
        JobAcceptInput.model_validate(
            {
                "expected_revenue_usdc": "0.010000",
                "expected_cost_usdc": "0.500000",
                "probability_payment": 0.9,
                "open_jobs": 0,
                "frozen": False,
            }
        ),
        load_policy().document,
    )
    risk = evaluate_agent_risk(_risk(expected_revenue_usdc="0.010000", expected_cost_usdc="0.500000"))
    assert policy.allowed is False
    assert policy.reason_code == "MARGIN_NOT_MET"
    assert risk.passed is False


def test_engine_does_not_import_llm_or_wallet() -> None:
    import aea.policy.engine as engine

    assert "solana" not in engine.__dict__
    assert "openai" not in engine.__dict__
    assert "lmstudio" not in engine.__dict__
