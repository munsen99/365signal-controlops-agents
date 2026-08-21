"""Pure payment-policy evaluator. No I/O, no LLM, no wall clock."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from aea.config import DestinationEntry, PolicyDocument
from aea.hashing import canonical_json_hash
from aea.types import PolicyInput, PolicyOutput, format_amount

from . import destinations as dest_mod
from . import limits as limits_mod
from . import risk as risk_mod

Check = Callable[[], str | None]


def _canonical_hash(inp: PolicyInput, *, approved_amount: str, approved_at: datetime) -> str:
    # Policy-engine hash only. Distinct from the signer canonical hash:
    # this omits request_id and policy_hash. PR10 must not reuse this value
    # as POST /v1/sign canonical_hash; use aea.signer.canonical_approved_hash.
    body = {
        "amount": format_amount(inp.amount),
        "approved_amount": approved_amount,
        "approved_at": approved_at.isoformat(),
        "asset": inp.asset,
        "correlation_id": str(inp.correlation_id),
        "destination": inp.destination,
        "job_id": str(inp.job_id) if inp.job_id is not None else None,
        "policy_version": inp.policy_version,
        "purpose": inp.purpose,
    }
    return canonical_json_hash(body)


def evaluate(
    inp: PolicyInput,
    policy: PolicyDocument,
    *,
    effective_policy_hash: str,
    now: datetime,
    destination: DestinationEntry | None = None,
) -> PolicyOutput:
    """Fail closed, first matching reason rejects. No silent amount haircut."""
    checks: tuple[Check, ...] = (
        lambda: risk_mod.check_freeze(inp),
        lambda: risk_mod.check_integrity(
            inp, policy, effective_policy_hash=effective_policy_hash
        ),
        lambda: limits_mod.check_wallet_phase(inp, policy),
        lambda: limits_mod.check_asset(inp, policy),
        lambda: dest_mod.check_destination(inp, policy, destination=destination),
        lambda: risk_mod.check_job_purpose(inp, policy),
        lambda: risk_mod.check_prohibited_purpose(inp, policy),
        lambda: limits_mod.check_outbound(inp, policy, destination=destination),
        lambda: limits_mod.check_daily(inp, policy),
        lambda: limits_mod.check_capital_at_risk(inp, policy),
        lambda: limits_mod.check_funds(inp),
    )
    for check in checks:
        reason = check()
        if reason is not None:
            return PolicyOutput(
                decision="rejected",
                reason_code=reason,
                approved_amount=None,
                policy_version=policy.policy_version,
                policy_hash=effective_policy_hash,
                timestamp=now,
                correlation_id=inp.correlation_id,
                canonical_request_hash=None,
            )
    approved = format_amount(inp.amount)
    return PolicyOutput(
        decision="approved",
        reason_code=None,
        approved_amount=inp.amount,
        policy_version=policy.policy_version,
        policy_hash=effective_policy_hash,
        timestamp=now,
        correlation_id=inp.correlation_id,
        canonical_request_hash=_canonical_hash(
            inp, approved_amount=approved, approved_at=now
        ),
    )
