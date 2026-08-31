"""Assemble the observability DTO from ledger, policy, supervisor, and wallet reads.

Does not call the signer. Does not debit. Does not mutate supervisor or policy.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from aea import POLICY_VERSION
from aea.config import LoadedPolicy
from aea.control.freeze import ControlSafety
from aea.ledger.service import LedgerService
from aea.observability.sanitize import RECENT_EVENTS_LIMIT, isoformat, safe_display_text
from aea.observability.schemas import (
    AgentSection,
    AgentState,
    Availability,
    CurrentJobSection,
    EconomicsSection,
    ObservabilityStatus,
    PolicySection,
    PresentAbsentUnknown,
    RailSection,
    RecentEventSection,
    ReconciliationHealth,
    ReconciliationSection,
    SupervisorSection,
    YesNoUnknown,
)
from aea.policy.reasons import HttpCode
from aea.signer.live_gate import LiveGateInspection
from aea.types import format_amount, format_asset_amount

WalletStatusFn = Callable[[], dict[str, Any]]
SupervisorStatusFn = Callable[[], dict[str, Any] | None]

_EVENT_DISPLAY = {
    "opportunity_recorded": "job discovered",
    "opportunity_decision": "job evaluated",
    "job_accepted": "job accepted",
    "job_transition": "job transitioned",
    "cost_recorded": "cost booked",
    "payment_request_created": "payment requested",
    "payment_request_decided": "payment decided",
    "payment_request_settled": "settlement confirmed",
    "transfer_recorded": "transfer broadcast",
    "revenue_verified": "revenue verified",
    "wallet_ledger_mismatch": "reconciliation performed",
    "evm_fee_precision_reconciled": "reconciliation performed",
    "decision_recorded": "decision recorded",
}

_OPEN_JOB_TO_STATE: dict[str, AgentState] = {
    "accepted": "accepted",
    "performing": "performing",
    "performed": "submitted",
    "submitted": "submitted",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dec(value: object | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _yn(value: bool | None) -> YesNoUnknown:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _gate_state(inspection: LiveGateInspection | None) -> tuple[PresentAbsentUnknown, str | None]:
    if inspection is None:
        return "unknown", "live spend gate not inspectable from this process"
    if inspection.enabled:
        return "present", inspection.reason
    return "absent", inspection.reason


def _event_display(event_type: str) -> str:
    if event_type.startswith("supervisor."):
        return "freeze/supervisor event"
    return _EVENT_DISPLAY.get(event_type, safe_display_text(event_type, max_len=64))


def _event_identifier(payload: dict[str, Any]) -> str | None:
    for key in (
        "job_id",
        "opportunity_id",
        "request_id",
        "revenue_id",
        "cost_id",
        "transfer_id",
        "decision_id",
        "transaction_reference",
        "transaction_hash",
        "external_reference",
    ):
        value = payload.get(key)
        if value:
            return safe_display_text(value, max_len=80)
    return None


def _job_state(job: dict[str, Any] | None, opportunity: dict[str, Any] | None) -> AgentState:
    if job is not None:
        status = str(job.get("status") or "")
        payment = str(job.get("payment_state") or "")
        if status == "submitted" and payment in {"pending", "approved"}:
            return "awaiting_payment"
        if status in _OPEN_JOB_TO_STATE:
            return _OPEN_JOB_TO_STATE[status]
        if status == "completed":
            return "idle"
    if opportunity is not None:
        decision = str(opportunity.get("decision") or "")
        if decision == "discovered":
            return "discovering"
        if decision == "evaluated":
            return "evaluating"
        if decision == "accepted":
            return "accepted"
    return "idle"


def _recon_health(mismatches: list[Any] | None, available: bool) -> ReconciliationHealth:
    if not available:
        return "unavailable"
    if mismatches:
        return "mismatch"
    return "healthy"


class ObservabilityCollector:
    """Trusted-side collector. Browser never talks to this object."""

    def __init__(
        self,
        *,
        policy: LoadedPolicy,
        ledger: LedgerService | None = None,
        safety: ControlSafety | None = None,
        wallet_status: WalletStatusFn | None = None,
        extra_wallet_status: tuple[WalletStatusFn, ...] = (),
        supervisor_status: SupervisorStatusFn | None = None,
        live_gate: LiveGateInspection | None = None,
        configured_solana: dict[str, Any] | None = None,
        configured_evm: dict[str, Any] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self._policy = policy
        self._ledger = ledger
        self._safety = safety
        self._wallet_status = wallet_status
        self._extra_wallet_status = extra_wallet_status
        self._supervisor_status = supervisor_status
        self._live_gate = live_gate
        self._configured_solana = configured_solana or {}
        self._configured_evm = configured_evm or {}
        self._secrets = secrets

    def snapshot(self) -> ObservabilityStatus:
        return build_status(
            policy=self._policy,
            ledger=self._ledger,
            safety=self._safety,
            wallet_probes=_probe_wallets(self._wallet_status, self._extra_wallet_status),
            supervisor=self._read_supervisor(),
            live_gate=self._live_gate,
            configured_solana=self._configured_solana,
            configured_evm=self._configured_evm,
        )

    def _read_supervisor(self) -> dict[str, Any] | None:
        if self._supervisor_status is None:
            return None
        try:
            snap = self._supervisor_status()
        except Exception:
            return None
        return snap if isinstance(snap, dict) else None


def _probe_wallets(
    primary: WalletStatusFn | None,
    extra: tuple[WalletStatusFn, ...],
) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    for fn in (primary, *extra):
        if fn is None:
            continue
        try:
            body = fn()
            if isinstance(body, dict):
                probes.append(body)
            else:
                probes.append({"ok": False, "unavailable": True})
        except Exception as exc:
            probes.append({"ok": False, "unavailable": True, "error": type(exc).__name__})
    return probes


def _classify_probe(probe: dict[str, Any]) -> str | None:
    balances = probe.get("balances") if isinstance(probe.get("balances"), dict) else {}
    if "ETH" in balances or probe.get("chain_id") is not None:
        return "evm"
    if "SOL" in balances:
        return "solana"
    network = str(probe.get("network") or "").lower()
    if network.startswith("base") or network.startswith("evm"):
        return "evm"
    if network in {"devnet", "testnet", "localnet", "mainnet-beta", "solana"}:
        return "solana"
    return None


def build_status(
    *,
    policy: LoadedPolicy,
    ledger: LedgerService | None,
    safety: ControlSafety | None,
    wallet_probes: list[dict[str, Any]],
    supervisor: dict[str, Any] | None,
    live_gate: LiveGateInspection | None,
    configured_solana: dict[str, Any],
    configured_evm: dict[str, Any],
    generated_at: datetime | None = None,
) -> ObservabilityStatus:
    generated = generated_at or _now()
    warnings: list[str] = []

    supervisor_readable: YesNoUnknown = "yes" if supervisor is not None else "unknown"
    db_flags: dict[str, Any] | None = None
    ledger_ok = ledger is not None
    if ledger is not None:
        try:
            db_flags = ledger.supervisor_flags()
        except Exception:
            db_flags = {"frozen": True, "signer_enabled": False, "loop_enabled": False, "readable": False}

    if db_flags is not None and not db_flags.get("readable", True):
        supervisor_readable = "unknown"
        warnings.append("supervisor state is unreadable")
    if supervisor is None and supervisor_readable != "yes":
        warnings.append("supervisor HTTP status is unavailable")
        supervisor_readable = "unknown"

    frozen_file = bool(safety.frozen) if safety is not None else None
    frozen_db = None if db_flags is None else bool(db_flags.get("frozen"))
    frozen_http = None if supervisor is None else bool(supervisor.get("frozen"))
    if True in {frozen_file, frozen_db, frozen_http}:
        frozen: YesNoUnknown = "yes"
    elif False in {frozen_file, frozen_db, frozen_http} and supervisor_readable == "yes":
        frozen = "no"
    elif frozen_file is False and frozen_db is False:
        frozen = "no"
    else:
        frozen = "unknown"

    signer_db = None if db_flags is None else db_flags.get("signer_enabled")
    signer_http = None if supervisor is None else supervisor.get("signer_enabled")
    signer_safety = None if safety is None else safety.signer_enabled
    if supervisor_readable == "unknown" and signer_db is None and signer_http is None:
        signer_enabled: YesNoUnknown = "unknown"
    else:
        enabled = True
        for flag in (signer_db, signer_http, signer_safety):
            if flag is False:
                enabled = False
        if signer_db is None and signer_http is None and signer_safety is None:
            signer_enabled = "unknown"
        else:
            signer_enabled = "yes" if enabled else "no"

    loop_db = None if db_flags is None else db_flags.get("loop_enabled")
    loop_http = None if supervisor is None else supervisor.get("loop_enabled")
    loop_safety = None if safety is None else safety.loop_enabled
    if loop_db is None and loop_http is None and loop_safety is None:
        loop_enabled: YesNoUnknown = "unknown"
    else:
        looping = True
        for flag in (loop_db, loop_http, loop_safety):
            if flag is False:
                looping = False
        loop_enabled = "yes" if looping else "no"

    gate_state, gate_detail = _gate_state(live_gate)

    policy_row: dict[str, Any] | None = None
    if ledger is not None:
        try:
            policy_row = ledger.current_policy()
        except Exception:
            policy_row = None
    expected_hash = policy.policy_hash
    expected_version = policy.document.policy_version or POLICY_VERSION
    if policy_row is None:
        policy_verified: YesNoUnknown = "unknown" if ledger_ok is False else "no"
        policy_detail = "policy row unreadable from ledger"
        warnings.append("policy cannot be verified")
    elif str(policy_row.get("policy_hash") or "") != expected_hash:
        policy_verified = "no"
        policy_detail = "ledger policy hash does not match loaded policy"
        warnings.append("policy cannot be verified")
    else:
        policy_verified = "yes"
        policy_detail = None

    economics, econ_source = _economics(ledger)
    recon_rows: list[dict[str, str]] = []
    recon_mismatches: list[dict[str, str]] = []
    recon_available = False
    if ledger is not None:
        try:
            recon = ledger.observability_reconciliation()
            recon_rows = list(recon.get("rows") or [])
            recon_mismatches = list(recon.get("mismatches") or [])
            recon_available = True
        except Exception:
            recon_available = False
    recon_health = _recon_health(recon_mismatches, recon_available)
    if recon_health == "mismatch":
        warnings.append("reconciliation is non-zero")
    if recon_health == "unavailable":
        warnings.append("reconciliation is unavailable")

    probes_by_rail = {"solana": [], "evm": []}
    for probe in wallet_probes:
        kind = _classify_probe(probe)
        if kind in probes_by_rail:
            probes_by_rail[kind].append(probe)

    phase = policy.document.wallet_phase
    want_solana = bool(configured_solana) or phase in {"A", "B", "C"}
    want_evm = bool(configured_evm) or phase == "E" or policy.document.evm is not None
    last_settlements = {"sol": None, "evm": None}
    if ledger is not None:
        try:
            last_settlements = ledger.last_settlements()
        except Exception:
            last_settlements = {"sol": None, "evm": None}

    rails: list[RailSection] = []
    if want_solana:
        rails.append(
            _solana_rail(
                configured=configured_solana,
                probes=probes_by_rail["solana"],
                recon_rows=recon_rows,
                last=last_settlements.get("sol") or last_settlements.get("solana"),
            )
        )
    if want_evm:
        rails.append(
            _evm_rail(
                configured=configured_evm,
                probes=probes_by_rail["evm"],
                policy=policy,
                recon_rows=recon_rows,
                last=last_settlements.get("evm"),
            )
        )
    for rail in rails:
        if rail.health == "unavailable":
            warnings.append(f"{rail.rail} wallet state is unavailable")
        elif rail.health == "degraded":
            warnings.append(f"{rail.rail} rail is degraded")

    current_job, opportunity = _current_activity(ledger)
    job_state = _job_state(current_job, opportunity)
    activity_state: AgentState = job_state
    if frozen == "yes":
        activity_state = "frozen"

    runtime: Availability = "healthy"
    if not ledger_ok:
        runtime = "degraded"
        warnings.append("ledger is unavailable")
    if any(r.health == "unavailable" for r in rails):
        runtime = "degraded"
    if supervisor_readable != "yes":
        runtime = "degraded"

    health: Availability = "healthy"
    if frozen == "yes":
        health = "degraded"
    if recon_health != "healthy":
        health = "degraded"
    if policy_verified != "yes":
        health = "degraded"
    if supervisor_readable != "yes":
        health = "degraded"
    if runtime != "healthy":
        health = "degraded"
    if health != "healthy" and activity_state not in {"frozen"}:
        # Fail-closed overall state: never call unknown healthy. Degraded is explicit.
        if activity_state == "idle":
            activity_state = "degraded"

    marketplace = None
    adapter = None
    job_id = None
    if current_job is not None:
        job_id = str(current_job.get("job_id") or "") or None
        marketplace = safe_display_text(current_job.get("source") or "mock", max_len=64)
        adapter = marketplace
    elif opportunity is not None:
        marketplace = safe_display_text(opportunity.get("source") or "mock", max_len=64)
        adapter = marketplace

    last_update = None
    if current_job is not None:
        last_update = current_job.get("submitted_at") or current_job.get("accepted_at")
    if last_update is None and opportunity is not None:
        last_update = opportunity.get("discovered_at")
    if isinstance(last_update, datetime):
        last_update_dt = last_update
    else:
        last_update_dt = generated

    events = _recent_events(ledger)

    return ObservabilityStatus(
        ok=True,
        code=HttpCode.OK,
        generated_at=generated,
        agent=AgentSection(
            state=activity_state,
            health=health,
            last_update=last_update_dt,
            runtime_health=runtime,
            current_job_id=job_id if current_job and str(current_job.get("status")) in _OPEN_JOB_TO_STATE else None,
            last_job_id=job_id,
            marketplace=marketplace,
            adapter=adapter,
        ),
        economics=economics,
        supervisor=SupervisorSection(
            readable=supervisor_readable,
            frozen=frozen,
            signer_enabled=signer_enabled,
            loop_enabled=loop_enabled,
            live_spend_gate=gate_state,
            live_spend_gate_detail=gate_detail,
            updated_at=None if supervisor is None else (str(supervisor.get("updated_at")) if supervisor.get("updated_at") else None),
            updated_by=None if supervisor is None else (str(supervisor.get("updated_by")) if supervisor.get("updated_by") else None),
            detail=None if supervisor is None else (str(supervisor.get("detail")) if supervisor.get("detail") else None),
        ),
        policy=PolicySection(
            version=str(policy_row.get("policy_version")) if policy_row and policy_row.get("policy_version") else expected_version,
            hash=str(policy_row.get("policy_hash")) if policy_row and policy_row.get("policy_hash") else expected_hash,
            verified=policy_verified,
            wallet_phase=policy.document.wallet_phase,
            detail=policy_detail,
        ),
        reconciliation=ReconciliationSection(
            health=recon_health,
            rows=recon_rows,
            mismatches=recon_mismatches,
            detail=None if recon_available else "ledger reconciliation view unavailable",
        ),
        rails=rails,
        current_job=_job_section(current_job, opportunity),
        recent_events=events,
        warnings=list(dict.fromkeys(warnings)),
    )


def _economics(ledger: LedgerService | None) -> tuple[EconomicsSection, str]:
    empty = EconomicsSection(
        unit_of_account="USDC",
        opening_capital_usdc=None,
        available_capital_usdc=None,
        verified_revenue_usdc=None,
        attributable_costs_usdc=None,
        realized_pnl_usdc=None,
        daily_spend_usdc=None,
        capital_at_risk_usdc=None,
        fee_reserve_sol=None,
        fee_reserve_eth=None,
        source="unavailable",
    )
    if ledger is None:
        return empty, "unavailable"
    try:
        snap = ledger.observability_economics()
    except Exception:
        return empty, "unavailable"
    return (
        EconomicsSection(
            unit_of_account="USDC",
            opening_capital_usdc=snap.get("opening_capital_usdc"),
            available_capital_usdc=snap.get("available_capital_usdc"),
            verified_revenue_usdc=snap.get("verified_revenue_usdc"),
            attributable_costs_usdc=snap.get("attributable_costs_usdc"),
            realized_pnl_usdc=snap.get("realized_pnl_usdc"),
            daily_spend_usdc=snap.get("daily_spend_usdc"),
            capital_at_risk_usdc=snap.get("capital_at_risk_usdc"),
            fee_reserve_sol=snap.get("fee_reserve_sol"),
            fee_reserve_eth=snap.get("fee_reserve_eth"),
            source="ledger",
        ),
        "ledger",
    )


def _asset_recon(rows: list[dict[str, str]], asset: str) -> ReconciliationHealth:
    found = False
    for row in rows:
        if row.get("asset") != asset:
            continue
        found = True
        try:
            if Decimal(str(row.get("delta") or "0")) != Decimal("0"):
                return "mismatch"
        except Exception:
            return "unavailable"
    if not found:
        return "unavailable"
    return "healthy"


def _first_ok_probe(probes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for probe in probes:
        if probe.get("ok") and isinstance(probe.get("balances"), dict):
            return probe
    return None


def _solana_rail(
    *,
    configured: dict[str, Any],
    probes: list[dict[str, Any]],
    recon_rows: list[dict[str, str]],
    last: dict[str, Any] | None,
) -> RailSection:
    probe = _first_ok_probe(probes)
    unavailable = bool(probes) and probe is None
    configured_flag = bool(configured.get("public_wallet") or configured.get("network") or probes)
    public_wallet = None
    network = None
    usdc = None
    native = None
    if probe is not None:
        public_wallet = probe.get("public_wallet") or configured.get("public_wallet")
        network = probe.get("network") or configured.get("network")
        balances = probe.get("balances") or {}
        usdc = None if balances.get("USDC") is None else format_amount(_dec(balances["USDC"]) or Decimal("0"))
        native = None if balances.get("SOL") is None else format_amount(_dec(balances["SOL"]) or Decimal("0"))
    else:
        public_wallet = configured.get("public_wallet")
        network = configured.get("network")
    health: str
    if probe is not None:
        health = "healthy"
    elif unavailable or (configured_flag and probes):
        health = "unavailable"
    elif configured_flag:
        health = "unavailable"
    else:
        health = "unconfigured"
    recon = _asset_recon(recon_rows, "SOL")
    if recon == "mismatch" and health == "healthy":
        health = "degraded"
    last_ref = None if last is None else last.get("ref")
    last_status = None if last is None else last.get("status")
    detail = None
    if health == "unavailable":
        detail = "solana wallet read failed"
    return RailSection(
        rail="solana",
        configured=configured_flag or probe is not None,
        health=health,  # type: ignore[arg-type]
        network=None if network is None else str(network),
        chain_id=None,
        public_wallet=None if public_wallet is None else str(public_wallet),
        usdc_balance=usdc,
        native_asset="SOL",
        native_reserve=native,
        canonical_token=configured.get("token_mint"),
        reconciliation=recon,
        last_settlement_ref=None if last_ref is None else str(last_ref),
        last_settlement_status=None if last_status is None else str(last_status),
        detail=detail,
    )


def _evm_rail(
    *,
    configured: dict[str, Any],
    probes: list[dict[str, Any]],
    policy: LoadedPolicy,
    recon_rows: list[dict[str, str]],
    last: dict[str, Any] | None,
) -> RailSection:
    probe = _first_ok_probe(probes)
    unavailable = bool(probes) and probe is None
    evm = policy.document.evm
    public_wallet = configured.get("public_wallet")
    network = configured.get("network") or (None if evm is None else evm.network)
    chain_id = configured.get("chain_id") or (None if evm is None else evm.chain_id)
    token = configured.get("token_contract") or (None if evm is None else evm.usdc_contract)
    usdc = None
    native = None
    if probe is not None:
        public_wallet = probe.get("public_wallet") or public_wallet
        network = probe.get("network") or network
        if probe.get("chain_id") is not None:
            try:
                chain_id = int(probe["chain_id"])
            except (TypeError, ValueError):
                pass
        token = probe.get("token_contract") or token
        balances = probe.get("balances") or {}
        usdc = None if balances.get("USDC") is None else format_amount(_dec(balances["USDC"]) or Decimal("0"))
        native = None if balances.get("ETH") is None else format_asset_amount(_dec(balances["ETH"]) or Decimal("0"), "ETH")
    configured_flag = bool(public_wallet or network or chain_id or evm is not None or probes)
    if probe is not None:
        health = "healthy"
    elif unavailable or configured_flag:
        health = "unavailable"
    else:
        health = "unconfigured"
    recon = _asset_recon(recon_rows, "ETH")
    if recon == "mismatch" and health == "healthy":
        health = "degraded"
    last_ref = None if last is None else last.get("ref")
    last_status = None if last is None else last.get("status")
    detail = None
    if health == "unavailable":
        detail = "evm wallet read failed"
    return RailSection(
        rail="evm",
        configured=configured_flag,
        health=health,  # type: ignore[arg-type]
        network=None if network is None else str(network),
        chain_id=None if chain_id is None else int(chain_id),
        public_wallet=None if public_wallet is None else str(public_wallet),
        usdc_balance=usdc,
        native_asset="ETH",
        native_reserve=native,
        canonical_token=None if token is None else str(token),
        reconciliation=recon,
        last_settlement_ref=None if last_ref is None else str(last_ref),
        last_settlement_status=None if last_status is None else str(last_status),
        detail=detail,
    )


def _current_activity(
    ledger: LedgerService | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if ledger is None:
        return None, None
    try:
        return ledger.current_or_last_activity()
    except Exception:
        return None, None


def _job_section(
    job: dict[str, Any] | None,
    opportunity: dict[str, Any] | None,
) -> CurrentJobSection:
    if job is None and opportunity is None:
        return CurrentJobSection(
            present=False,
            job_id=None,
            opportunity_id=None,
            external_reference=None,
            title=None,
            marketplace=None,
            status=None,
            expected_reward_usdc=None,
            expected_cost_usdc=None,
            expected_margin_usdc=None,
            accepted_at=None,
            submitted_at=None,
            payment_state=None,
            untrusted=True,
        )
    src = job or {}
    opp = opportunity or {}
    external = opp.get("external_reference") or src.get("external_reference")
    title_src = opp.get("title") or src.get("title") or external
    expected_rev = src.get("expected_revenue", opp.get("expected_revenue"))
    expected_cost = src.get("expected_cost", opp.get("expected_cost") or opp.get("opp_cost"))
    expected_margin = opp.get("expected_margin")
    if expected_margin is None and expected_rev is not None and expected_cost is not None:
        try:
            expected_margin = _dec(expected_rev) - _dec(expected_cost)  # type: ignore[operator]
        except Exception:
            expected_margin = None
    return CurrentJobSection(
        present=True,
        job_id=None if src.get("job_id") is None else str(src["job_id"]),
        opportunity_id=None if opp.get("opportunity_id") is None and src.get("opportunity_id") is None else str(opp.get("opportunity_id") or src.get("opportunity_id")),
        external_reference=None if external is None else safe_display_text(external, max_len=128),
        title=None if title_src is None else safe_display_text(title_src, max_len=120),
        marketplace=safe_display_text(opp.get("source") or src.get("source") or "mock", max_len=64),
        status=safe_display_text(src.get("status") or opp.get("decision") or "unknown", max_len=32),
        expected_reward_usdc=None if expected_rev is None else format_amount(_dec(expected_rev) or Decimal("0")),
        expected_cost_usdc=None if expected_cost is None else format_amount(_dec(expected_cost) or Decimal("0")),
        expected_margin_usdc=None if expected_margin is None else format_amount(_dec(expected_margin) or Decimal("0")),
        accepted_at=isoformat(src.get("accepted_at") if isinstance(src.get("accepted_at"), datetime) else None),
        submitted_at=isoformat(src.get("submitted_at") if isinstance(src.get("submitted_at"), datetime) else None),
        payment_state=None if src.get("payment_state") is None else safe_display_text(src.get("payment_state"), max_len=32),
        untrusted=True,
    )


def _recent_events(ledger: LedgerService | None) -> list[RecentEventSection]:
    if ledger is None:
        return []
    try:
        rows = ledger.recent_audit_events(limit=RECENT_EVENTS_LIMIT)
    except Exception:
        return []
    out: list[RecentEventSection] = []
    for row in rows[:RECENT_EVENTS_LIMIT]:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        created = row.get("created_at")
        stamp = isoformat(created) if isinstance(created, datetime) else safe_display_text(created or "", max_len=40)
        event_type = str(row.get("event_type") or "unknown")
        out.append(
            RecentEventSection(
                timestamp=stamp or "",
                event_type=safe_display_text(event_type, max_len=64),
                display_type=_event_display(event_type),
                identifier=_event_identifier(payload),
                status=safe_display_text(payload.get("status") or payload.get("to") or payload.get("decision") or "recorded", max_len=32),
            )
        )
    return out
