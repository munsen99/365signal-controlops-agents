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
Freshness = Literal["current", "stale", "unknown"]
ReconciliationHealth = Literal["healthy", "mismatch", "stale", "unknown"]
RailKind = Literal["solana", "evm", "mock"]
RailHealth = Literal["healthy", "degraded", "unavailable", "unconfigured"]
WalletReadStatus = Literal["current", "unavailable", "unconfigured"]


class ObservedFlag(AeaBaseModel):
    value: YesNoUnknown
    freshness: Freshness
    as_of: str | None = None
    source: str | None = None


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
    available_capital_freshness: Freshness
    available_capital_context_id: str | None
    available_capital_label: str
    verified_revenue_usdc: str | None
    attributable_costs_usdc: str | None
    realized_pnl_usdc: str | None
    daily_spend_usdc: str | None
    capital_at_risk_usdc: str | None
    fee_reserve_sol: str | None
    fee_reserve_eth: str | None
    source: Literal["ledger", "unavailable"]
    note: str | None = None


class SupervisorSection(AeaBaseModel):
    readable: YesNoUnknown
    frozen: YesNoUnknown
    frozen_freshness: Freshness
    signer_enabled: YesNoUnknown
    signer_enabled_freshness: Freshness
    loop_enabled: YesNoUnknown
    loop_enabled_freshness: Freshness
    live_spend_gate: PresentAbsentUnknown
    live_spend_gate_detail: str | None
    updated_at: str | None
    updated_by: str | None
    detail: str | None
    last_known_source: str | None = None


class PolicySection(AeaBaseModel):
    version: str | None
    hash: str | None
    verified: YesNoUnknown
    wallet_phase: str | None
    detail: str | None


class ReconciliationSection(AeaBaseModel):
    health: ReconciliationHealth
    freshness: Freshness
    rows: list[dict[str, str]]
    mismatches: list[dict[str, str]]
    last_success_at: str | None = None
    detail: str | None


class RailSection(AeaBaseModel):
    rail: RailKind
    context_id: str | None = None
    configured: bool
    health: RailHealth
    configured_network: str | None = None
    configured_public_wallet: str | None = None
    network: str | None
    chain_id: int | None
    public_wallet: str | None
    usdc_balance: str | None
    native_asset: Literal["SOL", "ETH"]
    native_reserve: str | None
    canonical_token: str | None
    wallet_read: WalletReadStatus = "unconfigured"
    current_usdc_balance: str | None = None
    current_native_reserve: str | None = None
    last_known_usdc_balance: str | None = None
    last_known_native_reserve: str | None = None
    last_known_as_of: str | None = None
    last_known_source: str | None = None
    last_successful_refresh: str | None = None
    reconciliation: ReconciliationHealth
    reconciliation_freshness: Freshness = "unknown"
    last_settlement_ref: str | None
    last_settlement_status: str | None
    last_settlement_freshness: Freshness = "unknown"
    last_settlement_source: str | None = None
    detail: str | None


class ContextSection(AeaBaseModel):
    id: str
    purpose: str
    rail: str
    network: str | None
    chain_id: int | None = None
    database: str
    wallet_phase: str | None
    active: bool
    ledger_available: bool
    opening_capital_usdc: str | None
    available_capital_usdc: str | None
    available_capital_freshness: Freshness
    verified_revenue_usdc: str | None
    attributable_costs_usdc: str | None
    realized_pnl_usdc: str | None
    last_activity_at: str | None
    reconciliation: ReconciliationHealth
    reconciliation_freshness: Freshness
    detail: str | None = None


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
    context_id: str | None = None


class RecentEventSection(AeaBaseModel):
    timestamp: str
    event_type: str
    display_type: str
    identifier: str | None
    status: str | None
    context_id: str | None = None
    rail: str | None = None
    network: str | None = None


class ObservationSection(AeaBaseModel):
    degraded: bool
    banner: str | None
    reasons: list[str]


class ObservabilityStatus(AeaBaseModel):
    ok: bool
    code: str
    generated_at: datetime
    observation: ObservationSection
    agent: AgentSection
    economics: EconomicsSection
    supervisor: SupervisorSection
    policy: PolicySection
    reconciliation: ReconciliationSection
    contexts: list[ContextSection]
    rails: list[RailSection]
    current_job: CurrentJobSection
    recent_events: list[RecentEventSection]
    warnings: list[str]
