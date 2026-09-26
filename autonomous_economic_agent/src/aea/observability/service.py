"""Assemble the observability DTO from ledger, policy, supervisor, and wallet reads.

Does not call the signer. Does not debit. Does not mutate supervisor or policy.
Isolated economic contexts are never summed into one operating wallet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from aea import POLICY_VERSION
from aea.config import LoadedPolicy
from aea.control.freeze import ControlSafety
from aea.ledger.service import LedgerService
from aea.observability.identity import evm_owner_wallet, solana_owner_wallet
from aea.observability.sanitize import RECENT_EVENTS_LIMIT, isoformat, safe_display_text
from aea.observability.schemas import (
    AgentSection,
    AgentState,
    Availability,
    ContextSection,
    CurrentJobSection,
    EconomicsSection,
    Freshness,
    ObservationSection,
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

DEGRADED_BANNER = (
    "OBSERVATION DEGRADED — one or more live control/wallet sources are unavailable. "
    "Some values below are last-known durable state."
)

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


def _recon_for(*, ledger_available: bool, wallet_current: bool, mismatches: list[Any]) -> tuple[ReconciliationHealth, Freshness]:
    """Live wallet read is required for current healthy/mismatch."""
    if wallet_current:
        if mismatches:
            return "mismatch", "current"
        if ledger_available:
            return "healthy", "current"
        return "unknown", "unknown"
    if not ledger_available:
        return "unknown", "unknown"
    if mismatches:
        return "mismatch", "stale"
    return "stale", "stale"


@dataclass
class ContextResult:
    id: str
    purpose: str
    rail: str
    network: str | None
    database: str
    wallet_phase: str | None
    chain_id: int | None = None
    active: bool = True
    ledger_available: bool = False
    economics: dict[str, Any] | None = None
    recon_rows: list[dict[str, str]] = field(default_factory=list)
    recon_mismatches: list[dict[str, str]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    activity: tuple[dict[str, Any] | None, dict[str, Any] | None] = (None, None)
    settlements: dict[str, Any] = field(default_factory=dict)
    configured_wallet: str | None = None
    configured_token: str | None = None
    wallet_probe: dict[str, Any] | None = None
    detail: str | None = None


def load_configured_contexts(policy: LoadedPolicy, probes: list[dict[str, Any]]) -> list[ContextResult]:
    """Snapshot each isolated ledger independently. Failures do not erase others."""
    from aea.observability.contexts import default_descriptors, public_identity
    from aea.observability.readonly import open_readonly_ledger

    by_rail: dict[str, list[dict[str, Any]]] = {"solana": [], "evm": []}
    for probe in probes:
        kind = _classify_probe(probe)
        if kind in by_rail:
            by_rail[kind].append(probe)
    results: list[ContextResult] = []
    for desc in default_descriptors():
        ident = public_identity(desc)
        owner = ident.get("public_wallet")
        token = ident.get("token_mint") or ident.get("token_contract")
        if desc.rail == "solana":
            owner = solana_owner_wallet(public_wallet=owner, token_mint=token)
        elif desc.rail == "evm":
            owner = evm_owner_wallet(public_wallet=owner, token_contract=token)
        ledger = None
        detail = None
        try:
            ledger = open_readonly_ledger(desc.database, policy=policy)
        except Exception as exc:
            detail = f"ledger unavailable ({type(exc).__name__})"
        probe = None
        if desc.rail in by_rail and by_rail[desc.rail]:
            probe = _first_ok_probe(by_rail[desc.rail]) or by_rail[desc.rail][0]
        try:
            ctx = _context_from_ledger(
                ident=desc.id,
                purpose=desc.purpose,
                rail=desc.rail,
                network=ident.get("network") or desc.network,
                database=desc.database,
                wallet_phase=desc.wallet_phase,
                chain_id=ident.get("chain_id") or desc.chain_id,
                ledger=ledger,
                configured_wallet=owner,
                configured_token=token,
                wallet_probe=probe,
            )
        finally:
            if ledger is not None:
                try:
                    ledger._conn.close()
                except Exception:
                    pass
        if detail:
            ctx.detail = detail if not ctx.detail else f"{ctx.detail}; {detail}"
        results.append(ctx)
    return results


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
        context_loader: Callable[[], list[ContextResult]] | None = None,
        discover_contexts: bool = False,
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
        self._context_loader = context_loader
        self._discover_contexts = discover_contexts
        self._secrets = secrets

    def snapshot(self) -> ObservabilityStatus:
        probes = _probe_wallets(self._wallet_status, self._extra_wallet_status)
        extra: list[ContextResult] = []
        if self._context_loader is not None:
            try:
                extra = list(self._context_loader())
            except Exception:
                extra = []
        elif self._discover_contexts:
            try:
                extra = load_configured_contexts(self._policy, probes)
            except Exception:
                extra = []
        return build_status(
            policy=self._policy,
            ledger=self._ledger,
            safety=self._safety,
            wallet_probes=probes,
            supervisor=self._read_supervisor(),
            live_gate=self._live_gate,
            configured_solana=self._configured_solana,
            configured_evm=self._configured_evm,
            extra_contexts=extra,
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


def _first_ok_probe(probes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for probe in probes:
        if probe.get("ok") and isinstance(probe.get("balances"), dict):
            return probe
    return None


def _ledger_economics(ledger: LedgerService | None) -> dict[str, Any] | None:
    if ledger is None:
        return None
    try:
        return ledger.observability_economics()
    except Exception:
        return None


def _ledger_recon(ledger: LedgerService | None) -> tuple[list[dict[str, str]], list[dict[str, str]], bool]:
    if ledger is None:
        return [], [], False
    try:
        recon = ledger.observability_reconciliation()
        return list(recon.get("rows") or []), list(recon.get("mismatches") or []), True
    except Exception:
        return [], [], False


def _context_from_ledger(
    *,
    ident: str,
    purpose: str,
    rail: str,
    network: str | None,
    database: str,
    wallet_phase: str | None,
    ledger: LedgerService | None,
    configured_wallet: str | None = None,
    configured_token: str | None = None,
    chain_id: int | None = None,
    wallet_probe: dict[str, Any] | None = None,
) -> ContextResult:
    econ = _ledger_economics(ledger)
    rows, mismatches, recon_ok = _ledger_recon(ledger)
    events: list[dict[str, Any]] = []
    activity: tuple[dict[str, Any] | None, dict[str, Any] | None] = (None, None)
    settlements: dict[str, Any] = {}
    if ledger is not None:
        try:
            events = ledger.recent_audit_events(limit=RECENT_EVENTS_LIMIT)
        except Exception:
            events = []
        try:
            activity = ledger.current_or_last_activity()
        except Exception:
            activity = (None, None)
        try:
            settlements = ledger.last_settlements()
        except Exception:
            settlements = {}
    return ContextResult(
        id=ident,
        purpose=purpose,
        rail=rail,
        network=network,
        database=database,
        wallet_phase=wallet_phase,
        chain_id=chain_id,
        ledger_available=econ is not None,
        economics=econ,
        recon_rows=rows,
        recon_mismatches=mismatches if recon_ok else [],
        events=events,
        activity=activity,
        settlements=settlements,
        configured_wallet=configured_wallet,
        configured_token=configured_token,
        wallet_probe=wallet_probe,
        detail=None if econ is not None else "ledger unavailable",
    )


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
    extra_contexts: list[ContextResult] | None = None,
    generated_at: datetime | None = None,
) -> ObservabilityStatus:
    generated = generated_at or _now()
    warnings: list[str] = []
    reasons: list[str] = []

    db_flags: dict[str, Any] | None = None
    ledger_ok = ledger is not None
    if ledger is not None:
        try:
            db_flags = ledger.supervisor_flags()
        except Exception:
            db_flags = {"frozen": True, "signer_enabled": False, "loop_enabled": False, "readable": False}

    http_ok = isinstance(supervisor, dict)
    if http_ok:
        readable: YesNoUnknown = "yes"
        frozen_v: YesNoUnknown = "yes" if supervisor.get("frozen") else "no"
        signer_v: YesNoUnknown = "yes" if supervisor.get("signer_enabled") else "no"
        loop_v: YesNoUnknown = "yes" if supervisor.get("loop_enabled") else "no"
        flag_fresh: Freshness = "current"
        flag_source = "supervisor_http"
        flag_as_of = str(supervisor.get("updated_at")) if supervisor.get("updated_at") else generated.isoformat()
    else:
        readable = "unknown"
        reasons.append("supervisor unreadable")
        warnings.append("supervisor HTTP status is unavailable")
        durable_ok = bool(db_flags and db_flags.get("readable"))
        if durable_ok:
            frozen_v = "yes" if db_flags.get("frozen") else "no"
            signer_v = "yes" if db_flags.get("signer_enabled") else "no"
            loop_v = "yes" if db_flags.get("loop_enabled") else "no"
            flag_fresh = "stale"
            flag_source = "durable_ledger"
            flag_as_of = None
        else:
            frozen_v = "unknown"
            signer_v = "unknown"
            loop_v = "unknown"
            flag_fresh = "unknown"
            flag_source = None
            flag_as_of = None
            if db_flags is not None and not db_flags.get("readable", True):
                warnings.append("supervisor state is unreadable")

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
        policy_verified: YesNoUnknown = "unknown" if not ledger_ok else "no"
        policy_detail = "policy row unreadable from ledger"
        warnings.append("policy cannot be verified")
        reasons.append("policy unverifiable")
    elif str(policy_row.get("policy_hash") or "") != expected_hash:
        policy_verified = "no"
        policy_detail = "ledger policy hash does not match loaded policy"
        warnings.append("policy cannot be verified")
        reasons.append("policy unverifiable")
    else:
        policy_verified = "yes"
        policy_detail = None

    probes_by_rail = {"solana": [], "evm": []}
    for probe in wallet_probes:
        kind = _classify_probe(probe)
        if kind in probes_by_rail:
            probes_by_rail[kind].append(probe)

    sol_id = public_identity_solana(configured_solana)
    evm_id = public_identity_evm(configured_evm, policy)

    contexts = list(extra_contexts or [])
    have_ids = {c.id for c in contexts}
    if "m1-default" not in have_ids and ledger is not None:
        contexts.insert(
            0,
            _context_from_ledger(
                ident="m1-default",
                purpose="core/default experiment",
                rail="mock",
                network="phase-a-mock",
                database="controlops",
                wallet_phase=policy.document.wallet_phase,
                ledger=ledger,
            ),
        )
    _attach_probes(contexts, probes_by_rail, sol_id, evm_id)

    if not any(c.rail == "solana" for c in contexts) and (sol_id["configured"] or probes_by_rail["solana"]):
        contexts.append(
            _context_from_ledger(
                ident="solana-configured",
                purpose="Solana rail",
                rail="solana",
                network=sol_id["network"],
                database="unspecified",
                wallet_phase=policy.document.wallet_phase,
                ledger=None,
                configured_wallet=sol_id["owner"],
                configured_token=sol_id["token"],
                wallet_probe=_first_ok_probe(probes_by_rail["solana"]) or (probes_by_rail["solana"][0] if probes_by_rail["solana"] else None),
            )
        )
    if not any(c.rail == "evm" for c in contexts) and (evm_id["configured"] or probes_by_rail["evm"]):
        contexts.append(
            _context_from_ledger(
                ident="evm-configured",
                purpose="EVM rail",
                rail="evm",
                network=evm_id["network"],
                database="unspecified",
                wallet_phase=policy.document.wallet_phase,
                chain_id=evm_id["chain_id"],
                ledger=None,
                configured_wallet=evm_id["owner"],
                configured_token=evm_id["token"],
                wallet_probe=_first_ok_probe(probes_by_rail["evm"]) or (probes_by_rail["evm"][0] if probes_by_rail["evm"] else None),
            )
        )

    context_sections: list[ContextSection] = []
    rails: list[RailSection] = []
    all_events: list[RecentEventSection] = []
    jobs: list[tuple[ContextResult, dict[str, Any] | None, dict[str, Any] | None]] = []

    for ctx in contexts:
        wallet_current = bool(ctx.wallet_probe and ctx.wallet_probe.get("ok") and isinstance(ctx.wallet_probe.get("balances"), dict))
        recon_h, recon_f = _recon_for(
            ledger_available=ctx.ledger_available,
            wallet_current=wallet_current,
            mismatches=ctx.recon_mismatches,
        )
        if ctx.rail in {"solana", "evm"} and not wallet_current:
            reasons.append(f"{ctx.rail} wallet unavailable")
        last_activity = None
        job, opp = ctx.activity
        jobs.append((ctx, job, opp))
        if job and isinstance(job.get("accepted_at"), datetime):
            last_activity = isoformat(job.get("accepted_at"))
        elif opp and isinstance(opp.get("discovered_at"), datetime):
            last_activity = isoformat(opp.get("discovered_at"))
        econ = ctx.economics or {}
        avail_fresh: Freshness = "current" if wallet_current else ("stale" if ctx.ledger_available else "unknown")
        current_usdc = None
        current_native = None
        if wallet_current:
            balances = ctx.wallet_probe.get("balances") or {}
            if balances.get("USDC") is not None:
                current_usdc = format_amount(_dec(balances["USDC"]) or Decimal("0"))
            native_key = "ETH" if ctx.rail == "evm" else "SOL"
            if balances.get(native_key) is not None:
                current_native = format_asset_amount(_dec(balances[native_key]) or Decimal("0"), native_key)
        last_known_usdc = econ.get("available_capital_usdc")
        last_known_native = econ.get("fee_reserve_eth") if ctx.rail == "evm" else econ.get("fee_reserve_sol")
        context_sections.append(
            ContextSection(
                id=ctx.id,
                purpose=ctx.purpose,
                rail=ctx.rail,
                network=ctx.network,
                chain_id=ctx.chain_id,
                database=ctx.database,
                wallet_phase=ctx.wallet_phase,
                active=ctx.active,
                ledger_available=ctx.ledger_available,
                opening_capital_usdc=econ.get("opening_capital_usdc"),
                available_capital_usdc=current_usdc if wallet_current else last_known_usdc,
                available_capital_freshness=avail_fresh,
                verified_revenue_usdc=econ.get("verified_revenue_usdc"),
                attributable_costs_usdc=econ.get("attributable_costs_usdc"),
                realized_pnl_usdc=econ.get("realized_pnl_usdc"),
                last_activity_at=last_activity,
                reconciliation=recon_h,
                reconciliation_freshness=recon_f,
                detail=ctx.detail,
            )
        )
        if ctx.rail in {"solana", "evm"}:
            rails.append(
                _rail_from_context(
                    ctx,
                    wallet_current=wallet_current,
                    current_usdc=current_usdc,
                    current_native=current_native,
                    last_known_usdc=last_known_usdc,
                    last_known_native=last_known_native,
                    recon_h=recon_h,
                    recon_f=recon_f,
                    fallback_owner=sol_id["owner"] if ctx.rail == "solana" else evm_id["owner"],
                    fallback_token=sol_id["token"] if ctx.rail == "solana" else evm_id["token"],
                    fallback_network=sol_id["network"] if ctx.rail == "solana" else evm_id["network"],
                    fallback_chain=evm_id["chain_id"] if ctx.rail == "evm" else None,
                )
            )
        all_events.extend(_events_from_context(ctx))

    if not any(r.rail == "solana" for r in rails) and (sol_id["configured"] or probes_by_rail["solana"]):
        rails.append(_standalone_rail("solana", sol_id, probes_by_rail["solana"]))
    if not any(r.rail == "evm" for r in rails) and (evm_id["configured"] or probes_by_rail["evm"]):
        rails.append(_standalone_rail("evm", evm_id, probes_by_rail["evm"]))

    for rail in rails:
        if rail.wallet_read == "unavailable":
            warnings.append(f"{rail.rail} wallet state is unavailable")
        if rail.reconciliation != "healthy":
            warnings.append(f"{rail.rail} reconciliation is {rail.reconciliation}")

    overall_recon, overall_fresh, last_success = _overall_recon(context_sections, rails)
    if overall_recon != "healthy":
        reasons.append("current reconciliation unavailable")
        warnings.append("reconciliation is not current healthy")

    current_caps = [
        (c.id, c.available_capital_usdc)
        for c in context_sections
        if c.available_capital_freshness == "current" and c.available_capital_usdc
    ]
    rail_caps = [
        (r.context_id or r.rail, r.current_usdc_balance)
        for r in rails
        if r.wallet_read == "current" and r.current_usdc_balance
    ]
    live_caps = current_caps or rail_caps
    if len(live_caps) == 1:
        avail, avail_fresh, avail_ctx, avail_label = live_caps[0][1], "current", live_caps[0][0], f"{live_caps[0][0]} (current wallet)"
    else:
        avail, avail_fresh, avail_ctx = None, "unknown", None
        avail_label = "no current wallet read" if not live_caps else "multiple current contexts; not summed"

    default_ctx = next((c for c in context_sections if c.id == "m1-default"), context_sections[0] if context_sections else None)
    default_result = next((c for c in contexts if c.id == "m1-default"), None)
    de = (default_result.economics if default_result is not None else None) or {}
    econ_source: str = "ledger" if default_ctx and default_ctx.ledger_available else "unavailable"

    observation_degraded = bool(
        readable != "yes"
        or policy_verified != "yes"
        or overall_recon != "healthy"
        or any(r.wallet_read == "unavailable" for r in rails)
    )
    unique_reasons = list(dict.fromkeys(reasons))
    banner = DEGRADED_BANNER if observation_degraded else None

    current_job = CurrentJobSection(
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
    activity_state: AgentState = "idle"
    job_id = None
    marketplace = None
    last_update_dt = generated
    for ctx, job, opp in jobs:
        if job is None and opp is None:
            continue
        current_job = _job_section(job, opp, context_id=ctx.id)
        activity_state = _job_state(job, opp)
        job_id = current_job.job_id
        marketplace = current_job.marketplace
        if job is not None:
            last_update_dt = job.get("submitted_at") or job.get("accepted_at") or last_update_dt
        elif opp is not None:
            last_update_dt = opp.get("discovered_at") or last_update_dt
        if not isinstance(last_update_dt, datetime):
            last_update_dt = generated
        break

    if frozen_v == "yes" and flag_fresh == "current":
        activity_state = "frozen"

    runtime: Availability = "healthy"
    if observation_degraded:
        runtime = "degraded"
    health: Availability = "degraded" if observation_degraded else "healthy"
    if frozen_v == "yes" and flag_fresh == "current":
        health = "degraded"
    if health != "healthy" and activity_state == "idle":
        activity_state = "degraded"

    events = _bound_events(all_events)

    return ObservabilityStatus(
        ok=True,
        code=HttpCode.OK,
        generated_at=generated,
        observation=ObservationSection(
            degraded=observation_degraded,
            banner=banner,
            reasons=unique_reasons,
        ),
        agent=AgentSection(
            state=activity_state,
            health=health,
            last_update=last_update_dt if isinstance(last_update_dt, datetime) else generated,
            runtime_health=runtime,
            current_job_id=job_id if current_job.present and current_job.status in _OPEN_JOB_TO_STATE else None,
            last_job_id=job_id,
            marketplace=marketplace,
            adapter=marketplace,
        ),
        economics=EconomicsSection(
            unit_of_account="USDC",
            opening_capital_usdc=de.get("opening_capital_usdc"),
            available_capital_usdc=avail,
            available_capital_freshness=avail_fresh,  # type: ignore[arg-type]
            available_capital_context_id=avail_ctx,
            available_capital_label=avail_label,
            verified_revenue_usdc=de.get("verified_revenue_usdc"),
            attributable_costs_usdc=de.get("attributable_costs_usdc"),
            realized_pnl_usdc=de.get("realized_pnl_usdc"),
            daily_spend_usdc=de.get("daily_spend_usdc"),
            capital_at_risk_usdc=de.get("capital_at_risk_usdc"),
            fee_reserve_sol=de.get("fee_reserve_sol"),
            fee_reserve_eth=de.get("fee_reserve_eth"),
            source=econ_source,  # type: ignore[arg-type]
            note="Isolated experimental ledgers are listed as separate contexts and are not summed.",
        ),
        supervisor=SupervisorSection(
            readable=readable,
            frozen=frozen_v,
            frozen_freshness=flag_fresh,
            signer_enabled=signer_v,
            signer_enabled_freshness=flag_fresh,
            loop_enabled=loop_v,
            loop_enabled_freshness=flag_fresh,
            live_spend_gate=gate_state,
            live_spend_gate_detail=gate_detail,
            updated_at=flag_as_of if http_ok else None,
            updated_by=None if not http_ok else (str(supervisor.get("updated_by")) if supervisor.get("updated_by") else None),
            detail=None if http_ok else "supervisor HTTP status is unavailable; flags are not current",
            last_known_source=flag_source,
        ),
        policy=PolicySection(
            version=str(policy_row.get("policy_version")) if policy_row and policy_row.get("policy_version") else expected_version,
            hash=str(policy_row.get("policy_hash")) if policy_row and policy_row.get("policy_hash") else expected_hash,
            verified=policy_verified,
            wallet_phase=policy.document.wallet_phase,
            detail=policy_detail,
        ),
        reconciliation=ReconciliationSection(
            health=overall_recon,
            freshness=overall_fresh,
            rows=[],
            mismatches=[],
            last_success_at=last_success,
            detail=None if overall_recon == "healthy" else "current healthy requires a live wallet read with zero delta",
        ),
        contexts=context_sections,
        rails=rails,
        current_job=current_job,
        recent_events=events,
        warnings=list(dict.fromkeys(warnings + unique_reasons)),
    )


def public_identity_solana(configured: dict[str, Any]) -> dict[str, Any]:
    mint = configured.get("token_mint")
    owner = solana_owner_wallet(public_wallet=configured.get("public_wallet"), token_mint=mint)
    return {
        "owner": owner,
        "token": mint,
        "network": configured.get("network"),
        "configured": bool(owner or mint or configured.get("network")),
    }


def public_identity_evm(configured: dict[str, Any], policy: LoadedPolicy) -> dict[str, Any]:
    evm = policy.document.evm
    token = configured.get("token_contract") or (None if evm is None else evm.usdc_contract)
    owner = evm_owner_wallet(public_wallet=configured.get("public_wallet"), token_contract=token)
    network = configured.get("network") or (None if evm is None else evm.network)
    chain_id = configured.get("chain_id") or (None if evm is None else evm.chain_id)
    return {
        "owner": owner,
        "token": token,
        "network": network,
        "chain_id": chain_id,
        "configured": bool(owner or token or network or chain_id),
    }


def _attach_probes(
    contexts: list[ContextResult],
    probes_by_rail: dict[str, list[dict[str, Any]]],
    sol_id: dict[str, Any],
    evm_id: dict[str, Any],
) -> None:
    for ctx in contexts:
        if ctx.wallet_probe is not None:
            continue
        if ctx.rail in probes_by_rail and probes_by_rail[ctx.rail]:
            ok = _first_ok_probe(probes_by_rail[ctx.rail])
            ctx.wallet_probe = ok or probes_by_rail[ctx.rail][0]
        if ctx.rail == "solana":
            ctx.configured_wallet = solana_owner_wallet(
                public_wallet=ctx.configured_wallet or sol_id["owner"],
                token_mint=ctx.configured_token or sol_id["token"],
            )
            ctx.configured_token = ctx.configured_token or sol_id["token"]
            ctx.network = ctx.network or sol_id["network"]
        if ctx.rail == "evm":
            ctx.configured_wallet = evm_owner_wallet(
                public_wallet=ctx.configured_wallet or evm_id["owner"],
                token_contract=ctx.configured_token or evm_id["token"],
            )
            ctx.configured_token = ctx.configured_token or evm_id["token"]
            ctx.network = ctx.network or evm_id["network"]
            ctx.chain_id = ctx.chain_id or evm_id["chain_id"]


def _rail_from_context(
    ctx: ContextResult,
    *,
    wallet_current: bool,
    current_usdc: str | None,
    current_native: str | None,
    last_known_usdc: str | None,
    last_known_native: str | None,
    recon_h: ReconciliationHealth,
    recon_f: Freshness,
    fallback_owner: str | None,
    fallback_token: str | None,
    fallback_network: str | None,
    fallback_chain: int | None,
) -> RailSection:
    native_asset = "ETH" if ctx.rail == "evm" else "SOL"
    owner = ctx.configured_wallet or fallback_owner
    token = ctx.configured_token or fallback_token
    if ctx.rail == "solana":
        owner = solana_owner_wallet(public_wallet=owner, token_mint=token)
    else:
        owner = evm_owner_wallet(public_wallet=owner, token_contract=token)
    probe = ctx.wallet_probe
    if wallet_current and probe is not None:
        probe_owner = probe.get("public_wallet")
        if ctx.rail == "solana":
            probe_owner = solana_owner_wallet(public_wallet=probe_owner, token_mint=token)
        else:
            probe_owner = evm_owner_wallet(public_wallet=probe_owner, token_contract=token)
        owner = probe_owner or owner
    wallet_read = "current" if wallet_current else ("unavailable" if (probe or owner) else "unconfigured")
    health = "healthy" if wallet_current else ("unavailable" if wallet_read == "unavailable" else "unconfigured")
    if recon_h == "mismatch" and health == "healthy":
        health = "degraded"
    settle_key = "evm" if ctx.rail == "evm" else "sol"
    last = (ctx.settlements or {}).get(settle_key) or (ctx.settlements or {}).get(ctx.rail)
    last_ref = None if not last else last.get("ref")
    last_status = None if not last else last.get("status")
    last_as_of = None if not last else last.get("as_of")
    econ = ctx.economics or {}
    known_as_of = econ.get("updated_at") or last_as_of
    detail = None
    if wallet_read == "unavailable":
        detail = f"{ctx.rail} wallet read failed"
    if ctx.configured_wallet is None and fallback_owner is None and token:
        detail = (detail + "; " if detail else "") + "configured owner wallet missing or was a token mint"
    return RailSection(
        rail=ctx.rail,  # type: ignore[arg-type]
        context_id=ctx.id,
        configured=bool(owner or token or ctx.network),
        health=health,  # type: ignore[arg-type]
        configured_network=ctx.network or fallback_network,
        configured_public_wallet=owner,
        network=ctx.network or fallback_network,
        chain_id=ctx.chain_id or fallback_chain,
        public_wallet=owner,
        usdc_balance=current_usdc,
        native_asset=native_asset,  # type: ignore[arg-type]
        native_reserve=current_native,
        canonical_token=token,
        wallet_read=wallet_read,  # type: ignore[arg-type]
        current_usdc_balance=current_usdc,
        current_native_reserve=current_native,
        last_known_usdc_balance=last_known_usdc,
        last_known_native_reserve=last_known_native,
        last_known_as_of=known_as_of if isinstance(known_as_of, str) else None,
        last_known_source="durable_ledger" if last_known_usdc else None,
        last_successful_refresh=generated_refresh(probe) if wallet_current else None,
        reconciliation=recon_h,
        reconciliation_freshness=recon_f,
        last_settlement_ref=None if last_ref is None else str(last_ref),
        last_settlement_status=None if last_status is None else str(last_status),
        last_settlement_freshness="stale" if last_ref else "unknown",
        last_settlement_source="durable_ledger" if last_ref else None,
        detail=detail,
    )


def generated_refresh(probe: dict[str, Any] | None) -> str | None:
    if probe is None:
        return None
    return _now().isoformat()


def _standalone_rail(kind: str, ident: dict[str, Any], probes: list[dict[str, Any]]) -> RailSection:
    probe = _first_ok_probe(probes)
    wallet_current = probe is not None
    owner = ident["owner"]
    token = ident["token"]
    if kind == "solana":
        owner = solana_owner_wallet(public_wallet=owner or (None if probe is None else probe.get("public_wallet")), token_mint=token)
    else:
        owner = evm_owner_wallet(public_wallet=owner or (None if probe is None else probe.get("public_wallet")), token_contract=token)
    usdc = native = None
    if wallet_current:
        balances = probe.get("balances") or {}
        if balances.get("USDC") is not None:
            usdc = format_amount(_dec(balances["USDC"]) or Decimal("0"))
        key = "ETH" if kind == "evm" else "SOL"
        if balances.get(key) is not None:
            native = format_asset_amount(_dec(balances[key]) or Decimal("0"), key)
    wallet_read = "current" if wallet_current else ("unavailable" if ident["configured"] or probes else "unconfigured")
    recon_h, recon_f = _recon_for(ledger_available=False, wallet_current=wallet_current, mismatches=[])
    if not wallet_current and ident["configured"]:
        recon_h, recon_f = "unknown", "unknown"
    return RailSection(
        rail=kind,  # type: ignore[arg-type]
        configured=ident["configured"] or wallet_current,
        health="healthy" if wallet_current else ("unavailable" if wallet_read == "unavailable" else "unconfigured"),
        configured_network=ident.get("network"),
        configured_public_wallet=owner,
        network=ident.get("network") if probe is None else (probe.get("network") or ident.get("network")),
        chain_id=ident.get("chain_id"),
        public_wallet=owner,
        usdc_balance=usdc,
        native_asset="ETH" if kind == "evm" else "SOL",
        native_reserve=native,
        canonical_token=token,
        wallet_read=wallet_read,  # type: ignore[arg-type]
        current_usdc_balance=usdc,
        current_native_reserve=native,
        reconciliation=recon_h,
        reconciliation_freshness=recon_f,
        last_settlement_ref=None,
        last_settlement_status=None,
        detail=None if wallet_current else f"{kind} wallet read failed",
    )


def _overall_recon(
    contexts: list[ContextSection],
    rails: list[RailSection],
) -> tuple[ReconciliationHealth, Freshness, str | None]:
    states = [c.reconciliation for c in contexts] + [r.reconciliation for r in rails]
    if "mismatch" in states:
        fresh = "current" if any(c.reconciliation_freshness == "current" and c.reconciliation == "mismatch" for c in contexts) else "stale"
        return "mismatch", fresh, None
    if "healthy" in states and all(s in {"healthy", "stale"} for s in states if s):
        if all(c.reconciliation == "healthy" and c.reconciliation_freshness == "current" for c in contexts if c.rail in {"solana", "evm"}):
            return "healthy", "current", _now().isoformat()
    if "stale" in states:
        return "stale", "stale", None
    if "healthy" in states:
        # healthy only if every configured rail is current healthy
        rail_ok = [r for r in rails if r.configured]
        if rail_ok and all(r.reconciliation == "healthy" and r.wallet_read == "current" for r in rail_ok):
            return "healthy", "current", _now().isoformat()
        return "stale", "stale", None
    return "unknown", "unknown", None


def _events_from_context(ctx: ContextResult) -> list[RecentEventSection]:
    out: list[RecentEventSection] = []
    for row in ctx.events:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        created = row.get("created_at")
        stamp = isoformat(created) if isinstance(created, datetime) else safe_display_text(created or "", max_len=40)
        if not stamp:
            continue
        event_type = str(row.get("event_type") or "unknown")
        out.append(
            RecentEventSection(
                timestamp=stamp,
                event_type=safe_display_text(event_type, max_len=64),
                display_type=_event_display(event_type),
                identifier=_event_identifier(payload),
                status=safe_display_text(payload.get("status") or payload.get("to") or payload.get("decision") or "recorded", max_len=32),
                context_id=ctx.id,
                rail=ctx.rail,
                network=ctx.network,
            )
        )
    return out


def _bound_events(events: list[RecentEventSection]) -> list[RecentEventSection]:
    dated = [e for e in events if e.timestamp]
    dated.sort(key=lambda e: e.timestamp, reverse=True)
    return dated[:RECENT_EVENTS_LIMIT]


def _job_section(
    job: dict[str, Any] | None,
    opportunity: dict[str, Any] | None,
    *,
    context_id: str | None = None,
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
            context_id=context_id,
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
        context_id=context_id,
    )
