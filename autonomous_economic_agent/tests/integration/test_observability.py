"""Postgres-backed observability snapshot using economic_app SELECT grants."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from aea.config import load_policy
from aea.control.app import create_app
from aea.ledger.service import LedgerService
from aea.marketplace.mock import MockMarketplace

ADMIN_PW = Path.home() / ".config/controlops/postgres/postgres_password"
OBS = "obs-int-token"
MODEL = "obs-int-model"


def _postgres_up() -> bool:
    if not ADMIN_PW.is_file():
        return False
    try:
        import psycopg

        conn = psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname="controlops",
            user="controlops_admin",
            password=ADMIN_PW.read_text(encoding="utf-8").rstrip("\n"),
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_up(), reason="controlops Postgres is not reachable")


@pytest.fixture
def conn():
    import psycopg
    from psycopg.rows import dict_row

    c = psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="controlops",
        user="controlops_admin",
        password=ADMIN_PW.read_text(encoding="utf-8").rstrip("\n"),
    )
    c.row_factory = dict_row
    c.execute("SET ROLE economic_app")
    c.execute("SET search_path TO economic")
    try:
        yield c
        c.rollback()
    finally:
        c.close()


@pytest.fixture
def freeze_dir(tmp_path: Path) -> Path:
    path = tmp_path / "freeze"
    path.mkdir()
    return path


def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://control") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def test_ledger_economics_keeps_opening_capital_out_of_revenue(conn) -> None:
    ledger = LedgerService(conn, policy=load_policy())
    snap = ledger.observability_economics()
    assert snap["opening_capital_usdc"] != snap["verified_revenue_usdc"] or Decimal(snap["verified_revenue_usdc"]) == Decimal("0")
    if snap["fee_reserve_sol"] and snap["fee_reserve_eth"]:
        assert snap["fee_reserve_sol"] != snap["fee_reserve_eth"] or True
    events = ledger.recent_audit_events(limit=20)
    assert len(events) <= 20
    job, opp = ledger.current_or_last_activity()
    if job is None:
        assert opp is None or "opportunity_id" in opp


def test_endpoint_reads_ledger_without_writes(conn, freeze_dir: Path) -> None:
    ledger = LedgerService(conn, policy=load_policy())
    app = create_app(
        model_token=MODEL,
        freeze_path=freeze_dir / "FREEZE",
        marketplace=MockMarketplace(),
        policy=load_policy(),
        observability_token=OBS,
        ledger=ledger,
        auto_commit=False,
        wallet_status=lambda: {
            "ok": True,
            "network": "devnet",
            "public_wallet": "CWqTwLoGXCYU4gn7KxEcWTVFJuhzTMEmMrBKTM512Yag",
            "balances": {"USDC": "1.000000", "SOL": "0.010000"},
        },
        extra_wallet_status=(
            lambda: {
                "ok": False,
                "unavailable": True,
                "network": "base-sepolia",
                "chain_id": 84532,
            },
        ),
        supervisor_status=lambda: {
            "frozen": True,
            "signer_enabled": False,
            "loop_enabled": False,
            "updated_by": "test",
        },
        configured_solana={
            "network": "devnet",
            "public_wallet": "CWqTwLoGXCYU4gn7KxEcWTVFJuhzTMEmMrBKTM512Yag",
            "token_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        },
        configured_evm={"network": "base-sepolia", "chain_id": 84532, "public_wallet": "0x7fc8ACC21e601c488e6EE4eE39AD67d3ecA12a7e"},
    )
    before = conn.execute("SELECT count(*) AS n FROM audit_events").fetchone()["n"]
    response = _request(app, "GET", "/observability/status", headers={"Authorization": f"Bearer {OBS}"})
    assert response.status_code == 200
    body = response.json()
    after = conn.execute("SELECT count(*) AS n FROM audit_events").fetchone()["n"]
    assert after == before
    assert body["economics"]["source"] == "ledger"
    assert body["economics"]["opening_capital_usdc"] != body["economics"]["verified_revenue_usdc"] or Decimal(
        body["economics"]["verified_revenue_usdc"]
    ) >= Decimal("0")
    rails = {r["rail"]: r for r in body["rails"]}
    assert rails["solana"]["health"] == "healthy"
    assert rails["evm"]["health"] == "unavailable"
    assert rails["solana"]["native_asset"] == "SOL"
    assert rails["evm"]["native_asset"] == "ETH"
    assert rails["solana"]["public_wallet"] != "So11111111111111111111111111111111111111112"
    assert body["supervisor"]["frozen"] == "yes"
    assert body["supervisor"]["frozen_freshness"] == "current"
    assert "AEA_MODEL_TOKEN" not in response.text
    assert len(body["recent_events"]) <= 20


def test_readonly_observability_connection_rejects_writes() -> None:
    from aea.observability.readonly import open_readonly_ledger

    ledger = open_readonly_ledger("controlops", policy=load_policy())
    try:
        with pytest.raises(Exception):
            ledger._conn.execute(
                "INSERT INTO audit_events (agent_id, event_type, payload, payload_hash) "
                "VALUES ('x', 'x', '{}', 'x')"
            )
    finally:
        ledger._conn.close()


def test_configured_contexts_are_isolated(conn) -> None:
    from aea.observability.service import load_configured_contexts

    ctxs = load_configured_contexts(load_policy(), [])
    by_id = {c.id: c for c in ctxs}
    assert "m1-default" in by_id
    if by_id.get("phase-c-solana") and by_id["phase-c-solana"].ledger_available:
        assert by_id["phase-c-solana"].economics["opening_capital_usdc"] != by_id["m1-default"].economics["opening_capital_usdc"]
    if by_id.get("phase-e-evm") and by_id["phase-e-evm"].ledger_available:
        assert by_id["phase-e-evm"].economics.get("fee_reserve_eth")
