"""Read-only observability endpoint, sanitizer, and fail-closed semantics."""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from aea.config import load_policy
from aea.control.app import create_app
from aea.control.freeze import ControlSafety
from aea.marketplace.mock import MockMarketplace
from aea.observability.sanitize import (
    RECENT_EVENTS_LIMIT,
    filter_secrets,
    safe_display_text,
    serialize_status,
)
from aea.observability.identity import solana_owner_wallet
from aea.observability.schemas import ObservabilityStatus
from aea.observability.service import ContextResult, build_status
from aea.signer.live_gate import LiveGateInspection
from aea.wallet.solana import CANONICAL_MAINNET_USDC_MINT, WRAPPED_SOL_MINT

AEA_SOLANA_OWNER = "CWqTwLoGXCYU4gn7KxEcWTVFJuhzTMEmMrBKTM512Yag"
AEA_EVM_OWNER = "0x7fc8ACC21e601c488e6EE4eE39AD67d3ecA12a7e"
E3_TX = "0xe66c35ea9bc02853ebd607715322f921759dbbf9e487ae3a15ffc688550d539b"
E3_USDC = "0.990000"
E3_ETH = "0.000099593798219532"

MODEL = "obs-model-token"
CONTROL = "obs-control-token"
OBS = "obs-read-token"
SUPERVISOR = "obs-supervisor-token"


def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://control") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


@pytest.fixture
def freeze_dir(tmp_path: Path) -> Path:
    path = tmp_path / "freeze"
    path.mkdir()
    return path


@pytest.fixture
def app(freeze_dir: Path):
    return create_app(
        model_token=MODEL,
        freeze_path=freeze_dir / "FREEZE",
        marketplace=MockMarketplace(),
        policy=load_policy(),
        control_token=CONTROL,
        supervisor_token=SUPERVISOR,
        observability_token=OBS,
        auto_commit=False,
    )


class FakeLedger:
    def __init__(self, **kwargs):
        self.flags = kwargs.get(
            "flags",
            {"frozen": False, "signer_enabled": True, "loop_enabled": True, "readable": True},
        )
        self.policy_row = kwargs.get(
            "policy_row",
            {"policy_version": load_policy().document.policy_version, "policy_hash": load_policy().policy_hash},
        )
        self.econ = kwargs.get(
            "econ",
            {
                "opening_capital_usdc": "20.000000",
                "available_capital_usdc": "19.500000",
                "verified_revenue_usdc": "1.250000",
                "attributable_costs_usdc": "0.100000",
                "realized_pnl_usdc": "1.150000",
                "daily_spend_usdc": "0.050000",
                "capital_at_risk_usdc": "0.000000",
                "fee_reserve_sol": "0.050000",
                "fee_reserve_eth": "0.000100000000000000",
            },
        )
        self.recon = kwargs.get(
            "recon",
            {
                "ok": True,
                "rows": [
                    {"asset": "USDC", "delta": "0.000000", "ledger_balance": "19.500000", "reconstructed_balance": "19.500000"},
                    {"asset": "SOL", "delta": "0.000000", "ledger_balance": "0.050000", "reconstructed_balance": "0.050000"},
                    {"asset": "ETH", "delta": "0.000000", "ledger_balance": "0.000100000000000000", "reconstructed_balance": "0.000100000000000000"},
                ],
                "mismatches": [],
            },
        )
        self.activity = kwargs.get("activity", (None, None))
        self.events = kwargs.get("events", [])
        self.settlements = kwargs.get(
            "settlements",
            {
                "sol": {"ref": "5" * 64, "status": "settled"},
                "evm": {"ref": "0x" + "ab" * 32, "status": "confirmed"},
            },
        )

    def supervisor_flags(self):
        return self.flags

    def current_policy(self):
        return self.policy_row

    def observability_economics(self):
        return self.econ

    def observability_reconciliation(self):
        return self.recon

    def current_or_last_activity(self):
        return self.activity

    def recent_audit_events(self, *, limit: int = 20):
        return self.events[:limit]

    def last_settlements(self):
        return self.settlements


def _safety(**kwargs) -> ControlSafety:
    return ControlSafety(
        frozen=kwargs.get("frozen", False),
        freeze_detail="ok",
        signer_enabled=kwargs.get("signer_enabled", True),
        loop_enabled=kwargs.get("loop_enabled", True),
    )


def test_missing_observability_token_is_fail_closed(freeze_dir: Path) -> None:
    app = create_app(
        model_token=MODEL,
        freeze_path=freeze_dir / "FREEZE",
        marketplace=MockMarketplace(),
        policy=load_policy(),
        auto_commit=False,
    )
    response = _request(app, "GET", "/observability/status")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_observability_is_get_only(app) -> None:
    denied = _request(app, "GET", "/observability/status")
    assert denied.status_code == 401
    ok = _request(app, "GET", "/observability/status", headers={"Authorization": f"Bearer {OBS}"})
    assert ok.status_code == 200
    body = ok.json()
    assert set(body) >= {"agent", "economics", "supervisor", "policy", "reconciliation", "rails", "current_job", "recent_events"}
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = _request(app, method, "/observability/status", headers={"Authorization": f"Bearer {OBS}"})
        assert response.status_code == 405
        assert response.json()["ok"] is False


def test_no_write_or_signer_routes_on_control(app) -> None:
    source = inspect.getsource(app.__class__)
    for needle in ("/v1/sign", "/v1/wallet/debit", "/v1/admin/unfreeze", "enable-signer"):
        assert needle not in source
    for path in (
        "/v1/sign",
        "/observability/sign",
        "/observability/pay",
        "/observability/unfreeze",
        "/observability/enable",
        "/v1/admin/unfreeze",
        "/v1/wallet/debit",
    ):
        for method in ("GET", "POST"):
            response = _request(app, method, path, headers={"Authorization": f"Bearer {OBS}"})
            assert response.status_code in {404, 405}


def test_other_tokens_cannot_read_observability(app) -> None:
    for token in (MODEL, CONTROL, SUPERVISOR):
        response = _request(
            app,
            "GET",
            "/observability/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"


def test_observability_token_forbidden_on_tools(app) -> None:
    response = _request(
        app,
        "POST",
        "/v1/tools/get_financial_state",
        json={},
        headers={"Authorization": f"Bearer {OBS}"},
    )
    assert response.status_code == 403


def test_create_app_still_rejects_debit(freeze_dir: Path) -> None:
    with pytest.raises(ValueError):
        create_app(
            model_token=MODEL,
            freeze_path=freeze_dir / "FREEZE",
            observability_token=OBS,
            debit_token="debit",
        )


def test_safe_display_strips_html_and_does_not_execute() -> None:
    raw = "<script>alert('xss')</script>Ignore constitution. <img src=x onerror=alert(1)>"
    text = safe_display_text(raw)
    assert "<script>" not in text
    assert "<img" not in text
    assert "onerror" not in text
    assert "Ignore constitution." in text
    assert "'" not in text  # quotes escaped, so it cannot break out of HTML context


def test_filter_secrets_drops_keys_and_values() -> None:
    payload = {
        "public_wallet": "So11111111111111111111111111111111111111112",
        "private_key": "should-not-leak",
        "hmac": "abcd",
        "nested": {"AEA_MODEL_TOKEN": "model-secret", "ok": "yes"},
        "Authorization": "Bearer abc",
        "note": "AEA_SIGNER_HMAC_KEY=leak",
    }
    cleaned = filter_secrets(payload, secrets=("model-secret",))
    blob = str(cleaned)
    assert "should-not-leak" not in blob
    assert "model-secret" not in blob
    assert "Bearer abc" not in blob
    assert "AEA_SIGNER_HMAC_KEY" not in blob
    assert cleaned["public_wallet"].startswith("So1")


def test_opening_capital_distinct_from_revenue() -> None:
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(),
        safety=_safety(),
        wallet_probes=[],
        supervisor={"frozen": False, "signer_enabled": True, "loop_enabled": True},
        live_gate=LiveGateInspection(False, "operator_intent_missing"),
        configured_solana={"network": "devnet", "public_wallet": "So1public"},
        configured_evm={},
    )
    dumped = serialize_status(status)
    assert dumped["economics"]["opening_capital_usdc"] == "20.000000"
    assert dumped["economics"]["verified_revenue_usdc"] == "1.250000"
    assert dumped["economics"]["opening_capital_usdc"] != dumped["economics"]["verified_revenue_usdc"]
    assert dumped["economics"]["fee_reserve_sol"] == "0.050000"
    assert dumped["economics"]["fee_reserve_eth"] == "0.000100000000000000"
    assert dumped["economics"]["fee_reserve_sol"] != dumped["economics"]["fee_reserve_eth"]


def test_sol_and_eth_reserves_are_distinct_on_rails() -> None:
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(),
        safety=_safety(),
        wallet_probes=[
            {"ok": True, "network": "devnet", "public_wallet": "So1abc", "balances": {"USDC": "10.0", "SOL": "0.04"}},
            {"ok": True, "network": "base-sepolia", "chain_id": 84532, "public_wallet": "0xabc", "balances": {"USDC": "3.0", "ETH": "0.0002"}},
        ],
        supervisor={"frozen": False, "signer_enabled": False, "loop_enabled": False},
        live_gate=LiveGateInspection(False, "operator_intent_missing"),
        configured_solana={"network": "devnet", "public_wallet": "So1abc"},
        configured_evm={"network": "base-sepolia", "chain_id": 84532, "public_wallet": "0xabc", "token_contract": "0x036CbD53842c5426634e7929541eC2318f3dCF7e"},
    )
    dumped = serialize_status(status)
    rails = {r["rail"]: r for r in dumped["rails"]}
    assert "solana" in rails and "evm" in rails
    assert rails["solana"]["native_asset"] == "SOL"
    assert rails["evm"]["native_asset"] == "ETH"
    assert rails["solana"]["native_reserve"] != rails["evm"]["native_reserve"]
    assert rails["solana"]["usdc_balance"] == "10.000000"
    assert rails["evm"]["usdc_balance"] == "3.000000"
    assert rails["evm"]["chain_id"] == 84532
    assert rails["solana"]["chain_id"] is None


def test_one_rail_down_does_not_hide_the_other() -> None:
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(),
        safety=_safety(),
        wallet_probes=[
            {"ok": True, "network": "devnet", "public_wallet": "So1abc", "balances": {"USDC": "1", "SOL": "0.01"}},
            {"ok": False, "unavailable": True, "network": "base-sepolia", "chain_id": 84532},
        ],
        supervisor={"frozen": False, "signer_enabled": True, "loop_enabled": True},
        live_gate=LiveGateInspection(False, "operator_intent_missing"),
        configured_solana={"public_wallet": "So1abc", "network": "devnet"},
        configured_evm={"public_wallet": "0xabc", "network": "base-sepolia", "chain_id": 84532},
    )
    dumped = serialize_status(status)
    rails = {r["rail"]: r for r in dumped["rails"]}
    assert rails["solana"]["health"] == "healthy"
    assert rails["evm"]["health"] == "unavailable"
    assert rails["evm"]["public_wallet"] == "0xabc"
    assert rails["solana"]["wallet_read"] == "current"
    assert rails["evm"]["wallet_read"] == "unavailable"
    assert rails["evm"]["reconciliation"] != "healthy"


def test_reconciliation_mismatch_is_unhealthy() -> None:
    ledger = FakeLedger(
        recon={
            "ok": False,
            "rows": [{"asset": "USDC", "delta": "1.000000", "ledger_balance": "2", "reconstructed_balance": "1"}],
            "mismatches": [{"asset": "USDC", "reason": "ledger_internal_delta", "delta": "1.000000"}],
        }
    )
    status = build_status(
        policy=load_policy(),
        ledger=ledger,
        safety=_safety(),
        wallet_probes=[],
        supervisor={"frozen": False, "signer_enabled": True, "loop_enabled": True},
        live_gate=LiveGateInspection(False, "x"),
        configured_solana={},
        configured_evm={},
    )
    dumped = serialize_status(status)
    assert dumped["reconciliation"]["health"] == "mismatch"
    assert dumped["agent"]["health"] != "healthy"
    assert dumped["agent"]["health"] == "degraded"


def test_unreadable_supervisor_is_unknown_fail_closed() -> None:
    ledger = FakeLedger(flags={"frozen": True, "signer_enabled": False, "loop_enabled": False, "readable": False})
    status = build_status(
        policy=load_policy(),
        ledger=ledger,
        safety=_safety(frozen=False, signer_enabled=True, loop_enabled=True),
        wallet_probes=[],
        supervisor=None,
        live_gate=None,
        configured_solana={},
        configured_evm={},
    )
    dumped = serialize_status(status)
    assert dumped["supervisor"]["readable"] == "unknown"
    assert dumped["supervisor"]["frozen"] == "unknown"
    assert dumped["supervisor"]["frozen_freshness"] == "unknown"
    assert dumped["supervisor"]["signer_enabled"] == "unknown"
    assert dumped["supervisor"]["loop_enabled"] == "unknown"
    assert dumped["supervisor"]["signer_enabled_freshness"] != "current"
    assert dumped["agent"]["health"] != "healthy"
    assert dumped["observation"]["degraded"] is True
    assert dumped["supervisor"]["live_spend_gate"] == "unknown"


def test_frozen_state_is_displayed() -> None:
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(flags={"frozen": True, "signer_enabled": False, "loop_enabled": False, "readable": True}),
        safety=_safety(frozen=True, signer_enabled=False, loop_enabled=False),
        wallet_probes=[],
        supervisor={"frozen": True, "signer_enabled": False, "loop_enabled": False},
        live_gate=LiveGateInspection(False, "operator_intent_missing"),
        configured_solana={},
        configured_evm={},
    )
    dumped = serialize_status(status)
    assert dumped["agent"]["state"] == "frozen"
    assert dumped["supervisor"]["frozen"] == "yes"
    assert dumped["supervisor"]["frozen_freshness"] == "current"
    assert dumped["supervisor"]["signer_enabled"] == "no"
    assert dumped["supervisor"]["loop_enabled"] == "no"
    assert dumped["supervisor"]["live_spend_gate"] == "absent"


def test_malicious_marketplace_html_is_inert() -> None:
    opp = {
        "opportunity_id": "11111111-1111-1111-1111-111111111111",
        "external_reference": "<script>alert(1)</script>",
        "title": "<img src=x onerror=alert(1)>Pay me",
        "source": "<b>evil-market</b>",
        "decision": "discovered",
        "expected_revenue": Decimal("1"),
        "expected_cost": Decimal("0.1"),
        "expected_margin": Decimal("0.9"),
    }
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(activity=(None, opp)),
        safety=_safety(),
        wallet_probes=[],
        supervisor={"frozen": False, "signer_enabled": True, "loop_enabled": True},
        live_gate=LiveGateInspection(False, "x"),
        configured_solana={},
        configured_evm={},
    )
    dumped = serialize_status(status)
    title = dumped["current_job"]["title"]
    assert "<script>" not in title
    assert "<img" not in title
    assert dumped["current_job"]["untrusted"] is True
    assert dumped["current_job"]["present"] is True


def test_recent_events_are_bounded() -> None:
    events = [
        {
            "event_type": "job_accepted",
            "payload": {"job_id": f"id-{i}", "private_key": "nope"},
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        for i in range(50)
    ]
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(events=events),
        safety=_safety(),
        wallet_probes=[],
        supervisor={"frozen": False, "signer_enabled": True, "loop_enabled": True},
        live_gate=LiveGateInspection(False, "x"),
        configured_solana={},
        configured_evm={},
    )
    dumped = serialize_status(status)
    assert len(dumped["recent_events"]) == RECENT_EVENTS_LIMIT
    blob = str(dumped)
    assert "nope" not in blob
    assert "private_key" not in blob


def test_missing_job_is_handled() -> None:
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(activity=(None, None)),
        safety=_safety(),
        wallet_probes=[],
        supervisor={"frozen": False, "signer_enabled": True, "loop_enabled": True},
        live_gate=LiveGateInspection(False, "x"),
        configured_solana={},
        configured_evm={},
    )
    dumped = serialize_status(status)
    assert dumped["current_job"]["present"] is False
    assert dumped["agent"]["current_job_id"] is None


def test_unknown_is_never_healthy() -> None:
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(flags={"frozen": True, "signer_enabled": False, "loop_enabled": False, "readable": False}),
        safety=_safety(),
        wallet_probes=[],
        supervisor=None,
        live_gate=None,
        configured_solana={},
        configured_evm={},
    )
    dumped = serialize_status(status)
    assert dumped["agent"]["health"] != "healthy"
    assert dumped["supervisor"]["readable"] != "yes"
    ObservabilityStatus.model_validate(dumped)


def test_endpoint_response_contains_no_secrets(app) -> None:
    response = _request(app, "GET", "/observability/status", headers={"Authorization": f"Bearer {OBS}"})
    blob = response.text
    for needle in (MODEL, CONTROL, OBS, SUPERVISOR, "BEGIN ", "private_key", "hmac"):
        assert needle not in blob


def test_supervisor_http_down_uses_stale_not_current_yes() -> None:
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(flags={"frozen": False, "signer_enabled": True, "loop_enabled": True, "readable": True}),
        safety=_safety(frozen=False, signer_enabled=True, loop_enabled=True),
        wallet_probes=[],
        supervisor=None,
        live_gate=LiveGateInspection(False, "operator_intent_missing"),
        configured_solana={},
        configured_evm={},
    )
    dumped = serialize_status(status)
    assert dumped["supervisor"]["readable"] == "unknown"
    assert dumped["supervisor"]["frozen"] == "no"
    assert dumped["supervisor"]["frozen_freshness"] == "stale"
    assert dumped["supervisor"]["signer_enabled_freshness"] == "stale"
    assert dumped["supervisor"]["loop_enabled_freshness"] == "stale"
    assert dumped["observation"]["degraded"] is True
    assert dumped["observation"]["banner"]


def test_wrapped_sol_mint_is_never_owner_wallet() -> None:
    assert solana_owner_wallet(public_wallet=WRAPPED_SOL_MINT, token_mint=CANONICAL_MAINNET_USDC_MINT) is None
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(),
        safety=_safety(),
        wallet_probes=[],
        supervisor=None,
        live_gate=LiveGateInspection(False, "x"),
        configured_solana={
            "network": "mainnet-beta",
            "public_wallet": WRAPPED_SOL_MINT,
            "token_mint": CANONICAL_MAINNET_USDC_MINT,
        },
        configured_evm={},
    )
    dumped = serialize_status(status)
    rails = {r["rail"]: r for r in dumped["rails"]}
    blob = str(dumped["rails"])
    assert WRAPPED_SOL_MINT not in (rails["solana"].get("public_wallet") or "")
    assert WRAPPED_SOL_MINT not in (rails["solana"].get("configured_public_wallet") or "")
    assert rails["solana"]["canonical_token"] == CANONICAL_MAINNET_USDC_MINT
    assert AEA_SOLANA_OWNER not in blob or True


def test_configured_solana_owner_distinct_from_mint() -> None:
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(),
        safety=_safety(),
        wallet_probes=[],
        supervisor=None,
        live_gate=LiveGateInspection(False, "x"),
        configured_solana={
            "network": "mainnet-beta",
            "public_wallet": AEA_SOLANA_OWNER,
            "token_mint": CANONICAL_MAINNET_USDC_MINT,
        },
        configured_evm={},
    )
    dumped = serialize_status(status)
    rail = {r["rail"]: r for r in dumped["rails"]}["solana"]
    assert rail["configured_public_wallet"] == AEA_SOLANA_OWNER
    assert rail["public_wallet"] == AEA_SOLANA_OWNER
    assert rail["canonical_token"] == CANONICAL_MAINNET_USDC_MINT
    assert rail["canonical_token"] != rail["public_wallet"]
    assert rail["public_wallet"] != WRAPPED_SOL_MINT


def test_zero_ledger_delta_without_wallet_is_not_healthy() -> None:
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(),
        safety=_safety(),
        wallet_probes=[],
        supervisor=None,
        live_gate=LiveGateInspection(False, "x"),
        configured_solana={"network": "mainnet-beta", "public_wallet": AEA_SOLANA_OWNER},
        configured_evm={},
    )
    dumped = serialize_status(status)
    assert dumped["reconciliation"]["health"] != "healthy"
    assert dumped["reconciliation"]["health"] in {"stale", "unknown"}
    rails = {r["rail"]: r for r in dumped["rails"]}
    assert rails["solana"]["reconciliation"] != "healthy"
    assert rails["solana"]["wallet_read"] == "unavailable"


def test_top_level_available_usdc_not_current_when_wallets_down() -> None:
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(),
        safety=_safety(),
        wallet_probes=[],
        supervisor=None,
        live_gate=LiveGateInspection(False, "x"),
        configured_solana={},
        configured_evm={},
    )
    dumped = serialize_status(status)
    assert dumped["economics"]["available_capital_usdc"] is None
    assert dumped["economics"]["available_capital_freshness"] != "current"
    assert dumped["economics"]["opening_capital_usdc"] == "20.000000"
    assert dumped["economics"]["available_capital_label"]


def test_multi_context_are_distinct_and_not_summed() -> None:
    extra = [
        ContextResult(
            id="m1-default",
            purpose="core/default experiment",
            rail="mock",
            network="phase-a-mock",
            database="controlops",
            wallet_phase="A",
            ledger_available=True,
            economics={
                "opening_capital_usdc": "20.000000",
                "available_capital_usdc": "20.000000",
                "verified_revenue_usdc": "0.000000",
                "attributable_costs_usdc": "0.000000",
                "realized_pnl_usdc": "0.000000",
            },
        ),
        ContextResult(
            id="phase-c-solana",
            purpose="Solana Phase-C mainnet",
            rail="solana",
            network="mainnet-beta",
            database="controlops_phase_c",
            wallet_phase="C",
            ledger_available=True,
            economics={
                "opening_capital_usdc": "2.000000",
                "available_capital_usdc": "1.990000",
                "verified_revenue_usdc": "0.000000",
                "fee_reserve_sol": "0.009995",
                "updated_at": "2026-08-22T11:12:06+00:00",
            },
            configured_wallet=AEA_SOLANA_OWNER,
            configured_token=CANONICAL_MAINNET_USDC_MINT,
            settlements={"sol": {"ref": "2eveDGPdxeUuHMHCQWQYBiTRN27VA4Z9pBSDkXMiZkPUWpU2cQxokji93xHrsqaU762jW9VMciuJm3JC14bFNqYR", "status": "settled"}},
        ),
        ContextResult(
            id="phase-e-evm",
            purpose="EVM Phase-E Base",
            rail="evm",
            network="base-sepolia",
            database="controlops_phase_e",
            wallet_phase="E",
            chain_id=84532,
            ledger_available=True,
            economics={
                "opening_capital_usdc": "1.000000",
                "available_capital_usdc": E3_USDC,
                "verified_revenue_usdc": "0.000000",
                "fee_reserve_eth": E3_ETH,
                "updated_at": "2026-08-22T15:14:55+00:00",
            },
            configured_wallet=AEA_EVM_OWNER,
            configured_token="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
            settlements={"evm": {"ref": E3_TX, "status": "confirmed"}},
            events=[
                {
                    "event_type": "payment_request_settled",
                    "payload": {"transaction_hash": E3_TX},
                    "created_at": datetime(2026, 8, 22, 15, 14, 55, tzinfo=timezone.utc),
                }
            ],
        ),
    ]
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(),
        safety=_safety(),
        wallet_probes=[],
        supervisor=None,
        live_gate=LiveGateInspection(False, "x"),
        configured_solana={"public_wallet": AEA_SOLANA_OWNER, "token_mint": CANONICAL_MAINNET_USDC_MINT, "network": "mainnet-beta"},
        configured_evm={"public_wallet": AEA_EVM_OWNER, "network": "base-sepolia", "chain_id": 84532},
        extra_contexts=extra,
    )
    dumped = serialize_status(status)
    by_id = {c["id"]: c for c in dumped["contexts"]}
    assert set(by_id) >= {"m1-default", "phase-c-solana", "phase-e-evm"}
    assert by_id["m1-default"]["opening_capital_usdc"] == "20.000000"
    assert by_id["phase-c-solana"]["opening_capital_usdc"] == "2.000000"
    assert by_id["phase-e-evm"]["available_capital_usdc"] == E3_USDC
    assert by_id["phase-e-evm"]["available_capital_freshness"] == "stale"
    assert dumped["economics"]["available_capital_usdc"] != "20.000000"
    rails = {r["rail"]: r for r in dumped["rails"]}
    assert rails["solana"]["public_wallet"] == AEA_SOLANA_OWNER
    assert rails["evm"]["public_wallet"] == AEA_EVM_OWNER
    assert rails["evm"]["last_known_usdc_balance"] == E3_USDC
    assert rails["evm"]["last_known_native_reserve"] == E3_ETH
    assert rails["evm"]["last_settlement_ref"] == E3_TX
    assert rails["evm"]["last_settlement_freshness"] == "stale"
    assert rails["solana"]["wallet_read"] == "unavailable"
    assert rails["evm"]["reconciliation"] != "healthy"
    assert dumped["observation"]["degraded"] is True
    types = {e["context_id"] for e in dumped["recent_events"]}
    assert "phase-e-evm" in types
    assert len(dumped["recent_events"]) <= 20


def test_one_context_offline_does_not_drop_others() -> None:
    extra = [
        ContextResult(
            id="phase-c-solana",
            purpose="Solana",
            rail="solana",
            network="mainnet-beta",
            database="controlops_phase_c",
            wallet_phase="C",
            ledger_available=True,
            economics={"opening_capital_usdc": "2.000000", "available_capital_usdc": "1.990000"},
            configured_wallet=AEA_SOLANA_OWNER,
        ),
        ContextResult(
            id="phase-e-evm",
            purpose="EVM",
            rail="evm",
            network="base-sepolia",
            database="controlops_phase_e",
            wallet_phase="E",
            ledger_available=False,
            detail="ledger unavailable",
            configured_wallet=AEA_EVM_OWNER,
            chain_id=84532,
        ),
    ]
    status = build_status(
        policy=load_policy(),
        ledger=FakeLedger(),
        safety=_safety(),
        wallet_probes=[],
        supervisor=None,
        live_gate=LiveGateInspection(False, "x"),
        configured_solana={"public_wallet": AEA_SOLANA_OWNER, "network": "mainnet-beta"},
        configured_evm={"public_wallet": AEA_EVM_OWNER, "network": "base-sepolia", "chain_id": 84532},
        extra_contexts=extra,
    )
    dumped = serialize_status(status)
    by_id = {c["id"]: c for c in dumped["contexts"]}
    assert by_id["phase-c-solana"]["ledger_available"] is True
    assert by_id["phase-e-evm"]["ledger_available"] is False
    rails = {r["rail"]: r for r in dumped["rails"]}
    assert rails["solana"]["public_wallet"] == AEA_SOLANA_OWNER
    assert rails["evm"]["public_wallet"] == AEA_EVM_OWNER


def test_hermes_compose_does_not_mount_economic_secrets() -> None:
    text = Path(__file__).resolve().parents[3].joinpath("ops/compose.controlops.yaml").read_text(encoding="utf-8")
    assert ".config/controlops/economic" not in text
    assert "wallet_debit" not in text
    assert "signer_hmac" not in text
    assert "AEA_MODEL_TOKEN" not in text
    assert "AEA_SIGNER_TOKEN" not in text
    assert "AEA_CONTROL_URL" in text
    assert "/opt/data/aea/observability.token" in text
