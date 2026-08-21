"""Bearer auth for the model-facing control plane.

POST /v1/tools/* accepts AEA_MODEL_TOKEN only. AEA_CONTROL_TOKEN is FORBIDDEN.
"""

from __future__ import annotations

from hmac import compare_digest

from aea.policy.reasons import HttpCode


def bearer_token(headers: dict[str, str]) -> str | None:
    raw = headers.get("authorization")
    if raw is None or not raw.startswith("Bearer "):
        return None
    token = raw[len("Bearer ") :].strip()
    return token or None


def authorize_model_tools(
    token: str | None,
    *,
    model_token: str,
    known_rejected: tuple[str, ...] = (),
) -> HttpCode | None:
    if token is None:
        return HttpCode.UNAUTHENTICATED
    if compare_digest(token, model_token):
        return None
    for other in known_rejected:
        if other and compare_digest(token, other):
            return HttpCode.FORBIDDEN
    return HttpCode.UNAUTHENTICATED


def authorize_control_only(
    token: str | None,
    *,
    control_token: str,
    known_rejected: tuple[str, ...] = (),
) -> HttpCode | None:
    """POST /v1/payment-requests is control-token only. Model is FORBIDDEN."""
    if not control_token:
        return HttpCode.UNAUTHENTICATED
    if token is None:
        return HttpCode.UNAUTHENTICATED
    if compare_digest(token, control_token):
        return None
    for other in known_rejected:
        if other and compare_digest(token, other):
            return HttpCode.FORBIDDEN
    return HttpCode.UNAUTHENTICATED
