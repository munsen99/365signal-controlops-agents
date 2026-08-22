"""Spend-limit checks. Pure; first failure is a reason code."""

from __future__ import annotations

from decimal import Decimal

from aea.config import DestinationEntry, PolicyDocument
from aea.policy.reasons import ReasonCode
from aea.types import PolicyInput


def check_wallet_phase(inp: PolicyInput, policy: PolicyDocument) -> str | None:
    if inp.wallet_phase != policy.wallet_phase:
        return ReasonCode.UNSUPPORTED_WALLET_PHASE
    if inp.wallet_phase not in {"A", "B", "C", "E"}:
        return ReasonCode.UNSUPPORTED_WALLET_PHASE
    return None


def check_asset(inp: PolicyInput, policy: PolicyDocument) -> str | None:
    if inp.asset == "USDC":
        if inp.asset not in policy.assets.permitted_treasury:
            return ReasonCode.PROHIBITED_TOKEN
        return None
    if inp.asset == "SOL":
        if inp.purpose != "network_fee":
            return ReasonCode.PROHIBITED_TOKEN
        if inp.amount > policy.assets.sol_max_fee_per_tx:
            return ReasonCode.PROHIBITED_TOKEN
        return None
    return ReasonCode.PROHIBITED_TOKEN


def effective_outbound_cap(
    policy: PolicyDocument,
    *,
    destination: DestinationEntry | None,
) -> Decimal:
    cap = policy.limits.max_outbound_usdc
    if destination is not None and destination.max_usdc is not None:
        cap = min(cap, destination.max_usdc)
    return cap


def check_outbound(
    inp: PolicyInput,
    policy: PolicyDocument,
    *,
    destination: DestinationEntry | None = None,
) -> str | None:
    if inp.asset != "USDC":
        return None
    cap = effective_outbound_cap(policy, destination=destination)
    if inp.amount > cap:
        return ReasonCode.MAX_OUTBOUND_EXCEEDED
    return None


def check_daily(inp: PolicyInput, policy: PolicyDocument) -> str | None:
    if inp.asset != "USDC":
        return None
    if inp.daily_spend_usdc + inp.amount > policy.limits.max_daily_discretionary_usdc:
        return ReasonCode.DAILY_LIMIT_EXCEEDED
    return None


def check_capital_at_risk(inp: PolicyInput, policy: PolicyDocument) -> str | None:
    if inp.asset != "USDC":
        return None
    if inp.outstanding_exposure_usdc + inp.amount > policy.limits.max_capital_at_risk_usdc:
        return ReasonCode.CAPITAL_AT_RISK_EXCEEDED
    return None


def check_funds(inp: PolicyInput) -> str | None:
    available = inp.wallet_balances.get(inp.asset, Decimal("0"))
    if inp.amount > available:
        return ReasonCode.INSUFFICIENT_FUNDS
    return None
