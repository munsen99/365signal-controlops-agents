"""Stable read-only observability DTO. extra='forbid'; allow-listed fields only."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from aea.types import AeaBaseModel

AgentState = Literal[
    "offline",
    "idle",
    "discovering",
    "evaluating",
    "accepted",
    "performing",
    "submitted",
    "awaiting_payment",
    "reconciling",
    "frozen",
    "degraded",
]
Availability = Literal["healthy", "degraded", "unknown", "unavailable"]
YesNoUnknown = Literal["yes", "no", "unknown"]
PresentAbsentUnknown = Literal["present", "absent", "unknown"]
ReconciliationHealth = Literal["healthy", "mismatch", "unavailable"]
RailKind = Literal["solana", "evm"]
RailHealth = Literal["healthy", "degraded", "unavailable", "unconfigured"]


class AgentSection(AeaBaseModel):
    state: AgentState
    health: Availability
    last_update: datetime | None
    runtime_health: Availability
    current_job_id: str | None
    last_job_id: str | None
    marketplace: str | None
    adapter: str | None


class EconomicsSection(AeaBaseModel):
    unit_of_account: Literal["USDC"]
    opening_capital_usdc: str | None
    available_capital_usdc: str | None
    verified_revenue_usdc: str | None
    attributable_costs_usdc: str | None
    realized_pnl_usdc: str | None
    daily_spend_usdc: str | None
    capital_at_risk_usdc: str | None
    fee_reserve_sol: str | None
    fee_reserve_eth: str | None
    source: Literal["ledger", "unavailable"]


class SupervisorSection(AeaBaseModel):
    readable: YesNoUnknown
    frozen: YesNoUnknown
    signer_enabled: YesNoUnknown
    loop_enabled: YesNoUnknown
    live_spend_gate: PresentAbsentUnknown
    live_spend_gate_detail: str | None
    updated_at: str | None
    updated_by: str | None
    detail: str | None


class PolicySection(AeaBaseModel):
    version: str | None
    hash: str | None
    verified: YesNoUnknown
    wallet_phase: str | None
    detail: str | None


class ReconciliationSection(AeaBaseModel):
    health: ReconciliationHealth
    rows: list[dict[str, str]]
    mismatches: list[dict[str, str]]
    detail: str | None


class RailSection(AeaBaseModel):
    rail: RailKind
    configured: bool
    health: RailHealth
    network: str | None
    chain_id: int | None
    public_wallet: str | None
    usdc_balance: str | None
    native_asset: Literal["SOL", "ETH"]
    native_reserve: str | None
    canonical_token: str | None
    reconciliation: ReconciliationHealth
    last_settlement_ref: str | None
    last_settlement_status: str | None
    detail: str | None


class CurrentJobSection(AeaBaseModel):
    present: bool
    job_id: str | None
    opportunity_id: str | None
    external_reference: str | None
    title: str | None
    marketplace: str | None
    status: str | None
    expected_reward_usdc: str | None
    expected_cost_usdc: str | None
    expected_margin_usdc: str | None
    accepted_at: str | None
    submitted_at: str | None
    payment_state: str | None
    untrusted: bool


class RecentEventSection(AeaBaseModel):
    timestamp: str
    event_type: str
    display_type: str
    identifier: str | None
    status: str | None


class ObservabilityStatus(AeaBaseModel):
    ok: bool
    code: str
    generated_at: datetime
    agent: AgentSection
    economics: EconomicsSection
    supervisor: SupervisorSection
    policy: PolicySection
    reconciliation: ReconciliationSection
    rails: list[RailSection]
    current_job: CurrentJobSection
    recent_events: list[RecentEventSection]
    warnings: list[str]
