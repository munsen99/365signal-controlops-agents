"""Mock wallet HTTP authz, idempotency, and ledger recon inputs."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
import httpx
import pytest

from aea.types import format_amount
from aea.wallet.mock import MockWallet, new_tx_id
from aea.wallet.service import create_app

DEBIT = "debit-token"
CREDIT = "credit-token"
READ = "read-token"
MODEL = "model-token"
CONTROL = "control-token"

ADMIN_PW = Path.home() / ".config/controlops/postgres/postgres_password"


@pytest.fixture
def wallet() -> MockWallet:
    return MockWallet(
        phase="A",
        opening={"USDC": Decimal("20"), "SOL": Decimal("0.05")},
    )


@pytest.fixture
def app(wallet: MockWallet):
    return create_app(
        wallet=wallet,
        debit_token=DEBIT,
        credit_token=CREDIT,
        read_token=READ,
        model_token=MODEL,
        control_token=CONTROL,
        allow_faults=True,
    )


def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wallet") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def test_health(app) -> None:
    response = _request(app, "GET", "/health")
    assert response.status_code == 200


def test_balances_require_read_token(app) -> None:
    assert _request(app, "GET", "/v1/wallet/balances").status_code == 401
    model = _request(
        app,
        "GET",
        "/v1/wallet/balances",
        headers={"Authorization": f"Bearer {MODEL}"},
    )
    assert model.status_code == 403
    debit = _request(
        app,
        "GET",
        "/v1/wallet/balances",
        headers={"Authorization": f"Bearer {DEBIT}"},
    )
    assert debit.status_code == 403
    ok = _request(
        app,
        "GET",
        "/v1/wallet/balances",
        headers={"Authorization": f"Bearer {READ}"},
    )
    assert ok.status_code == 200
    assert ok.json()["balances"]["USDC"] == "20.000000"
    assert ok.json()["balances"]["SOL"] == "0.050000"


def test_model_and_control_cannot_debit(app) -> None:
    body = {
        "asset": "USDC",
        "amount": "0.010000",
        "destination": "mock:counterparty:mkt-escrow",
        "reason": "fee",
        "idempotency_key": "debit-forbidden-01",
    }
    for token in (MODEL, CONTROL, READ, CREDIT):
        response = _request(
            app,
            "POST",
            "/v1/wallet/debit",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403, token
        assert response.json()["code"] == "FORBIDDEN"


def test_model_and_control_cannot_credit(app) -> None:
    body = {
        "asset": "USDC",
        "amount": "1.000000",
        "reason": "marketplace_settlement",
        "idempotency_key": "credit-forbidden-model-control",
    }
    for token in (MODEL, CONTROL, READ):
        response = _request(
            app,
            "POST",
            "/v1/wallet/credit",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403, token
        assert response.json()["code"] == "FORBIDDEN"


def test_create_app_requires_distinct_tokens(wallet: MockWallet) -> None:
    with pytest.raises(ValueError, match="distinct"):
        create_app(
            wallet=wallet,
            debit_token="same",
            credit_token="same",
            read_token="read-token",
        )


def test_fault_header_ignored_fail_closed_in_runtime(wallet: MockWallet) -> None:
    runtime = create_app(
        wallet=wallet,
        debit_token=DEBIT,
        credit_token=CREDIT,
        read_token=READ,
        model_token=MODEL,
        control_token=CONTROL,
        allow_faults=False,
    )
    before = wallet.get_balances()["USDC"]
    response = _request(
        runtime,
        "POST",
        "/v1/wallet/debit",
        json={
            "asset": "USDC",
            "amount": "0.010000",
            "destination": "mock:fee_payer",
            "reason": "fee",
            "idempotency_key": "pay:fault-runtime-blocked",
        },
        headers={
            "Authorization": f"Bearer {DEBIT}",
            "X-AEA-Fault": "timeout",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert wallet.get_balances()["USDC"] == before


def test_create_app_from_env_never_enables_faults() -> None:
    from aea.wallet.service import create_app_from_env

    assert create_app_from_env.__defaults__ is None
    import inspect

    src = inspect.getsource(create_app_from_env)
    assert "allow_faults=False" in src
    assert "AEA_ALLOW_FAULTS" not in src


def test_tx_and_balance_payloads_have_no_key_material(app) -> None:
    body = {
        "asset": "USDC",
        "amount": "0.010000",
        "destination": "mock:fee_payer",
        "reason": "fee",
        "idempotency_key": "pay:no-secrets",
    }
    debit = _request(
        app,
        "POST",
        "/v1/wallet/debit",
        json=body,
        headers={"Authorization": f"Bearer {DEBIT}"},
    )
    balances = _request(
        app,
        "GET",
        "/v1/wallet/balances",
        headers={"Authorization": f"Bearer {READ}"},
    )
    blob = debit.text + balances.text
    for needle in ("private_key", "seed phrase", "seed_phrase", "mnemonic", DEBIT, CREDIT):
        assert needle not in blob


def test_no_set_balance_or_admin_mutate_route(app) -> None:
    for path in (
        "/v1/wallet/set_balance",
        "/v1/wallet/balances",
        "/v1/wallet/admin",
        "/v1/wallet/fault",
    ):
        response = _request(
            app,
            "POST",
            path,
            json={"USDC": "999", "force": True},
            headers={"Authorization": f"Bearer {DEBIT}"},
        )
        assert response.status_code == 404


def test_debit_token_cannot_credit(app) -> None:
    response = _request(
        app,
        "POST",
        "/v1/wallet/credit",
        json={
            "asset": "USDC",
            "amount": "1.000000",
            "reason": "marketplace_settlement",
            "idempotency_key": "credit-forbidden-01",
        },
        headers={"Authorization": f"Bearer {DEBIT}"},
    )
    assert response.status_code == 403


def test_debit_and_get_tx(app, wallet: MockWallet) -> None:
    body = {
        "asset": "USDC",
        "amount": "0.050000",
        "destination": "mock:counterparty:mkt-escrow",
        "reason": "marketplace_acceptance_fee",
        "idempotency_key": "pay:job-http-1",
        "tx_id": new_tx_id(),
    }
    response = _request(
        app,
        "POST",
        "/v1/wallet/debit",
        json=body,
        headers={"Authorization": f"Bearer {DEBIT}"},
    )
    assert response.status_code == 200
    tx = response.json()["tx"]
    assert tx["tx_id"].startswith("mocktx_")
    fetched = _request(
        app,
        "GET",
        f"/v1/wallet/tx/{tx['tx_id']}",
        headers={"Authorization": f"Bearer {READ}"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["tx"]["amount"] == "0.050000"
    assert wallet.get_balances()["USDC"] == Decimal("19.95")


def test_credit_settlement_idempotent(app, wallet: MockWallet) -> None:
    body = {
        "asset": "USDC",
        "amount": "0.500000",
        "reason": "marketplace_settlement",
        "idempotency_key": "mkt-settle:job-abc",
    }
    first = _request(
        app,
        "POST",
        "/v1/wallet/credit",
        json=body,
        headers={"Authorization": f"Bearer {CREDIT}"},
    )
    second = _request(
        app,
        "POST",
        "/v1/wallet/credit",
        json=body,
        headers={"Authorization": f"Bearer {CREDIT}"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["tx"]["tx_id"] == second.json()["tx"]["tx_id"]
    assert wallet.get_balances()["USDC"] == Decimal("20.5")


def test_idempotency_conflict_http(app) -> None:
    _request(
        app,
        "POST",
        "/v1/wallet/credit",
        json={
            "asset": "USDC",
            "amount": "1.000000",
            "reason": "opening_capital",
            "idempotency_key": "seed:conflict",
        },
        headers={"Authorization": f"Bearer {CREDIT}"},
    )
    conflict = _request(
        app,
        "POST",
        "/v1/wallet/credit",
        json={
            "asset": "USDC",
            "amount": "2.000000",
            "reason": "opening_capital",
            "idempotency_key": "seed:conflict",
        },
        headers={"Authorization": f"Bearer {CREDIT}"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_force_true_rejected(app) -> None:
    response = _request(
        app,
        "POST",
        "/v1/wallet/credit",
        json={
            "asset": "USDC",
            "amount": "1.000000",
            "reason": "opening_capital",
            "idempotency_key": "seed:force",
            "force": True,
        },
        headers={"Authorization": f"Bearer {CREDIT}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unknown_asset_http(app) -> None:
    response = _request(
        app,
        "POST",
        "/v1/wallet/credit",
        json={
            "asset": "BONK",
            "amount": "1.000000",
            "reason": "x",
            "idempotency_key": "seed:bonk",
        },
        headers={"Authorization": f"Bearer {CREDIT}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_insufficient_funds_http(app, wallet: MockWallet) -> None:
    before = wallet.get_balances()["USDC"]
    response = _request(
        app,
        "POST",
        "/v1/wallet/debit",
        json={
            "asset": "USDC",
            "amount": "99.000000",
            "destination": "mock:counterparty:mkt-escrow",
            "reason": "fee",
            "idempotency_key": "pay:too-big-http",
        },
        headers={"Authorization": f"Bearer {DEBIT}"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["code"] == "INSUFFICIENT_FUNDS"
    assert wallet.get_balances()["USDC"] == before


def test_fault_header_timeout(app) -> None:
    response = _request(
        app,
        "POST",
        "/v1/wallet/debit",
        json={
            "asset": "USDC",
            "amount": "0.010000",
            "destination": "mock:fee_payer",
            "reason": "fee",
            "idempotency_key": "pay:fault-timeout",
        },
        headers={
            "Authorization": f"Bearer {DEBIT}",
            "X-AEA-Fault": "timeout",
        },
    )
    assert response.status_code == 503
    assert response.json()["code"] == "NETWORK_FAILURE"


def test_no_export_key(app) -> None:
    response = _request(
        app,
        "POST",
        "/v1/wallet/export_key",
        headers={"Authorization": f"Bearer {DEBIT}"},
    )
    assert response.status_code == 404


def test_missing_tx(app) -> None:
    response = _request(
        app,
        "GET",
        f"/v1/wallet/tx/mocktx_{'ab' * 16}",
        headers={"Authorization": f"Bearer {READ}"},
    )
    assert response.status_code == 404


def _postgres_up() -> bool:
    if not ADMIN_PW.is_file():
        return False
    try:
        import psycopg
    except ImportError:
        return False
    try:
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


@pytest.mark.skipif(not _postgres_up(), reason="controlops Postgres is not reachable")
def test_wallet_matches_ledger_current_balance_after_seed_credit() -> None:
    import psycopg

    conn = psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="controlops",
        user="controlops_admin",
        password=ADMIN_PW.read_text(encoding="utf-8").rstrip("\n"),
    )
    rows = conn.execute(
        """
        SELECT asset, ledger_balance, delta
          FROM economic.v_balance_reconciliation
         WHERE agent_id = 'economic-agent'
        """
    ).fetchall()
    ledger = {r[0]: r[1] for r in rows}
    deltas = {r[0]: r[2] for r in rows}
    conn.close()
    assert abs(deltas["USDC"]) < Decimal("0.000001")
    assert abs(deltas["SOL"]) < Decimal("0.000001")

    wallet = MockWallet(phase="A")
    app = create_app(
        wallet=wallet,
        debit_token=DEBIT,
        credit_token=CREDIT,
        read_token=READ,
        allow_faults=False,
    )
    for asset, amount in ledger.items():
        reason = "opening_capital" if asset == "USDC" else "fee_reserve"
        response = _request(
            app,
            "POST",
            "/v1/wallet/credit",
            json={
                "asset": asset,
                "amount": format_amount(amount),
                "reason": reason,
                "idempotency_key": f"seed:{asset.lower()}",
            },
            headers={"Authorization": f"Bearer {CREDIT}"},
        )
        assert response.status_code == 200, response.text
    balances = wallet.get_balances()
    assert balances["USDC"] == ledger["USDC"]
    assert balances["SOL"] == ledger["SOL"]
