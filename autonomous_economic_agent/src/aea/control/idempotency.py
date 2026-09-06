"""Idempotency key semantics for mutating economic actions."""

from __future__ import annotations

from aea.policy.reasons import HttpCode

IDEMPOTENCY_RULE = (
    "Reuse the same idempotency key only when retrying the exact same logical "
    "operation after an uncertain transport outcome. Use a new key when the "
    "previous result was definitive or when relevant state/inputs have changed "
    "and a new operation is intended."
)

UNCERTAIN_TRANSPORT_CODES = frozenset(
    {
        HttpCode.NETWORK_FAILURE,
        HttpCode.TIMEOUT,
        HttpCode.MARKETPLACE_UNAVAILABLE,
        HttpCode.SIGNER_UNAVAILABLE,
    }
)


def is_uncertain_transport_outcome(code: object) -> bool:
    """True when the result is not a committed success or definitive rejection."""
    return str(code or "") in UNCERTAIN_TRANSPORT_CODES


def should_store_idempotent_result(code: object) -> bool:
    """Cache only definitive outcomes. Uncertain transport must remain retryable."""
    return not is_uncertain_transport_outcome(code)
