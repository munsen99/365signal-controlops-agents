"""Freeze, prohibited behaviours, job-id rule, and accept-job margin/risk."""

from __future__ import annotations

import re
from decimal import Decimal

from aea.config import PolicyDocument
from aea.policy.reasons import ReasonCode
from aea.types import AeaBaseModel, PolicyInput, parse_unsigned_amount
from pydantic import field_validator

_PURPOSE_RULES: tuple[tuple[str, ReasonCode, re.Pattern[str]], ...] = (
    ("borrow", ReasonCode.BORROW_OR_LEVERAGE, re.compile(r"\b(borrow|borrowing|loan|credit-line)\b", re.I)),
    ("leverage", ReasonCode.BORROW_OR_LEVERAGE, re.compile(r"\b(leverage|levered|gearing)\b", re.I)),
    ("lend", ReasonCode.BORROW_OR_LEVERAGE, re.compile(r"\b(lend|lending|yield.?farm)\b", re.I)),
    ("speculate", ReasonCode.SWAP_OR_SPECULATE, re.compile(r"\b(speculat|gambl|wager|bet)\b", re.I)),
    ("arbitrary_swaps", ReasonCode.SWAP_OR_SPECULATE, re.compile(r"\b(swap|token.?exchange)\b", re.I)),
    (
        "agent_policy_mutation",
        ReasonCode.AGENT_POLICY_MUTATION,
        re.compile(
            r"\b(set_policy|unfreeze|disable_supervisor|replace.?policy|bypass.?policy)\b",
            re.I,
        ),
    ),
)


def check_freeze(inp: PolicyInput) -> str | None:
    if inp.frozen:
        return ReasonCode.FROZEN
    if not inp.signer_enabled:
        return ReasonCode.SIGNER_DISABLED
    return None


def check_integrity(
    inp: PolicyInput,
    policy: PolicyDocument,
    *,
    effective_policy_hash: str,
) -> str | None:
    if not effective_policy_hash or inp.policy_hash != effective_policy_hash:
        return ReasonCode.POLICY_TAMPER
    if inp.policy_version != policy.policy_version:
        return ReasonCode.POLICY_TAMPER
    return None


def check_job_purpose(inp: PolicyInput, policy: PolicyDocument) -> str | None:
    if not inp.purpose.strip():
        return ReasonCode.NO_JOB_PURPOSE
    if policy.prohibited.wallet_transfer_without_job and inp.job_id is None:
        return ReasonCode.NO_JOB_PURPOSE
    if inp.asset == "SOL" and policy.assets.sol_spend_requires_job and inp.job_id is None:
        return ReasonCode.NO_JOB_PURPOSE
    return None


def check_prohibited_purpose(inp: PolicyInput, policy: PolicyDocument) -> str | None:
    flags = policy.prohibited
    text = inp.purpose
    for attr, code, pattern in _PURPOSE_RULES:
        if getattr(flags, attr) and pattern.search(text):
            return code
    return None


class JobAcceptInput(AeaBaseModel):
    expected_revenue_usdc: Decimal
    expected_cost_usdc: Decimal
    probability_payment: float
    open_jobs: int
    frozen: bool
    asset: str = "USDC"

    @field_validator("expected_revenue_usdc", "expected_cost_usdc", mode="before")
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)


class JobAcceptResult(AeaBaseModel):
    allowed: bool
    reason_code: str | None
    meets_required_margin: bool


def evaluate_job_accept(inp: JobAcceptInput, policy: PolicyDocument) -> JobAcceptResult:
    """Accept-job gates. Not payable through PolicyInput. Fail closed."""
    if inp.frozen:
        return JobAcceptResult(
            allowed=False, reason_code=ReasonCode.FROZEN, meets_required_margin=False
        )
    if inp.asset != "USDC":
        return JobAcceptResult(
            allowed=False,
            reason_code=ReasonCode.PROHIBITED_TOKEN,
            meets_required_margin=False,
        )
    revenue = inp.expected_revenue_usdc
    cost = inp.expected_cost_usdc
    required = cost * (Decimal(1) + Decimal(policy.limits.required_margin_bps) / Decimal(10000))
    meets_margin = revenue >= required
    if not meets_margin:
        return JobAcceptResult(
            allowed=False,
            reason_code=ReasonCode.MARGIN_NOT_MET,
            meets_required_margin=False,
        )
    if inp.probability_payment < policy.limits.min_payment_probability:
        return JobAcceptResult(
            allowed=False,
            reason_code=ReasonCode.MARGIN_NOT_MET,
            meets_required_margin=True,
        )
    if inp.open_jobs >= policy.limits.max_open_jobs:
        return JobAcceptResult(
            allowed=False,
            reason_code=ReasonCode.OPEN_JOBS_EXCEEDED,
            meets_required_margin=True,
        )
    return JobAcceptResult(
        allowed=True, reason_code=None, meets_required_margin=True
    )
