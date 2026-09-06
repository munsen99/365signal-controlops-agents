"""Idempotency key reuse rule for mutating economic actions."""

from __future__ import annotations

from aea.control.idempotency import (
    IDEMPOTENCY_RULE,
    is_uncertain_transport_outcome,
    should_store_idempotent_result,
)
from aea.policy.reasons import HttpCode, ReasonCode


def test_idempotency_rule_is_the_operator_contract() -> None:
    assert IDEMPOTENCY_RULE == (
        "Reuse the same idempotency key only when retrying the exact same logical "
        "operation after an uncertain transport outcome. Use a new key when the "
        "previous result was definitive or when relevant state/inputs have changed "
        "and a new operation is intended."
    )


def test_uncertain_transport_is_not_cached_as_idempotent() -> None:
    for code in (
        HttpCode.NETWORK_FAILURE,
        HttpCode.TIMEOUT,
        HttpCode.MARKETPLACE_UNAVAILABLE,
        HttpCode.SIGNER_UNAVAILABLE,
    ):
        assert is_uncertain_transport_outcome(code) is True
        assert should_store_idempotent_result(code) is False


def test_definitive_results_are_cached() -> None:
    for code in (
        HttpCode.OK,
        HttpCode.POLICY_REJECTED,
        HttpCode.AGENT_RISK_VETO,
        HttpCode.FAKE_PAYMENT,
        ReasonCode.MARGIN_NOT_MET,
        ReasonCode.PROHIBITED_TOKEN,
        HttpCode.DUPLICATE_PAYMENT,
        HttpCode.IDEMPOTENT_REPLAY,
    ):
        assert is_uncertain_transport_outcome(code) is False
        assert should_store_idempotent_result(code) is True
