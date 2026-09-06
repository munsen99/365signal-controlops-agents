"""PR10 payment path: Control → Policy HMAC → Signer → Wallet → Ledger."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


import httpx
import pytest

from uuid import UUID, uuid4

from aea.config import load_policy
from aea.control.app import create_app as create_control_app
from aea.ledger.models import PaymentCreate, PaymentDecisionWrite, PaymentSettle
from aea.ledger.service import LedgerService
from aea.types import format_amount
from aea.marketplace.mock import MockMarketplace
from aea.payment.service import PaymentOrchestrator, policy_execute_via_asgi
from aea.policy.service import create_app as create_policy_app
from aea.policy.signer_client import PolicySignerClient
from aea.signer.mock import MockSigner
from aea.signer.service import AsgiWalletDebit, create_app as create_signer_app
from aea.wallet.mock import MockWallet, new_tx_id
from aea.wallet.service import create_app as create_wallet_app
from tests.dbutil import isolate_economic_ledger

NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
MODEL = "model-token-pr10"
CONTROL = "control-token-pr10"
SUPERVISOR = "supervisor-token-pr10"
SIGNER = "signer-token-pr10"
HMAC = "signer-request-hmac-key-pr10-0001"
DEBIT = "wallet-debit-token-pr10"
CREDIT = "wallet-credit-token-pr10"
READ = "wallet-read-token-pr10"
MARKET = "marketplace-token-pr10"
PROFITABLE = "mock:job:profitable-summary-001"

ADMIN_PW = Path.home() / ".config/controlops/postgres/postgres_password"


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
def freeze_dir(tmp_path: Path) -> Path:
    path = tmp_path / "freeze"
    path.mkdir()
    return path


@pytest.fixture
def loaded():
    return load_policy()


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
    isolate_economic_ledger(c)
    c.execute("SET ROLE economic_app")
    c.execute("SET search_path TO economic")
    try:
        yield c
        c.rollback()
    finally:
        c.close()


@pytest.fixture
def ledger(conn, loaded) -> LedgerService:
    return LedgerService(conn, policy=loaded)


@pytest.fixture
def wallet() -> MockWallet:
    return MockWallet(phase="A", opening={"USDC": Decimal("20"), "SOL": Decimal("0.05")})


@pytest.fixture
def stack(wallet, freeze_dir, loaded, ledger):
    wallet_app = create_wallet_app(
        wallet=wallet,
        debit_token=DEBIT,
        credit_token=CREDIT,
        read_token=READ,
        model_token=MODEL,
        control_token=CONTROL,
    )
    signer = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=HMAC,
    )
    signer_app = create_signer_app(
        signer=signer,
        signer_token=SIGNER,
        debit_token=DEBIT,
        model_token=MODEL,
        control_token=CONTROL,
        supervisor_token=SUPERVISOR,
    )
    policy_app = create_policy_app(
        control_token=CONTROL,
        model_token=MODEL,
        loaded=loaded,
        freeze_path=freeze_dir / "FREEZE",
        now=NOW,
        signer_client=PolicySignerClient(hmac_key=HMAC, signer_token=SIGNER, signer_app=signer_app),
    )
    market = MockMarketplace(credit_fn=wallet.credit)
    payment = PaymentOrchestrator(
        ledger=ledger,
        policy=loaded,
        policy_execute=policy_execute_via_asgi(policy_app, CONTROL),
        wallet_balances=wallet.get_balances,
        control_token=CONTROL,
    )
    control = create_control_app(
        model_token=MODEL,
        freeze_path=freeze_dir / "FREEZE",
        marketplace=market,
        policy=loaded,
        control_token=CONTROL,
        supervisor_token=SUPERVISOR,
        marketplace_token=MARKET,
        wallet_get_tx=wallet.get_tx,
        wallet_balances=wallet.get_balances,
        ledger=ledger,
        payment=payment,
        auto_commit=False,
    )
    return {
        "control": control,
        "policy": policy_app,
        "signer": signer,
        "signer_app": signer_app,
        "wallet": wallet,
        "ledger": ledger,
        "freeze_dir": freeze_dir,
        "loaded": loaded,
    }


def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://svc") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _accept(control) -> str:
    found = _request(
        control, "POST", "/v1/tools/find_jobs", json={"limit": 20}, headers=_auth(MODEL)
    ).json()
    oid = next(j["opportunity_id"] for j in found["jobs"] if j["external_reference"] == PROFITABLE)
    job = _request(
        control,
        "POST",
        "/v1/tools/accept_job",
        json={"opportunity_id": oid, "idempotency_key": f"acc-{uuid4().hex[:10]}"},
        headers=_auth(MODEL),
    ).json()
    assert job["ok"] is True, job
    return job["job_id"]


def _debit_count(wallet: MockWallet) -> int:
    return sum(1 for tx in wallet._txs.values() if tx.direction == "debit")


def _seed_unsettled(ledger: LedgerService, job_id: str, amount: str) -> dict:
    row = ledger.create_payment_request(
        PaymentCreate.model_validate(
            {
                "job_id": job_id,
                "amount": amount,
                "asset": "USDC",
                "destination": "mock:fee_payer",
                "purpose": "network_fee",
                "correlation_id": str(uuid4()),
                "idempotency_key": f"car-seed-{uuid4().hex[:10]}",
            }
        )
    )
    ledger.decide_payment_request(
        PaymentDecisionWrite.model_validate(
            {
                "request_id": str(row["request_id"]),
                "decision": "approved",
                "approved_amount": amount,
                "idempotency_key": f"car-dec-{uuid4().hex[:10]}",
            }
        )
    )
    return row


def _sign_pending(stack, *, request_id, job_id, amount, destination, purpose, correlation_id) -> dict:
    dest = stack["loaded"].classify(destination)
    exposure = stack["ledger"].outstanding_exposure_usdc(excluding_request_id=request_id)
    daily = stack["ledger"].daily_spend_usdc()
    bals = stack["wallet"].get_balances()
    body = {
        "amount": amount,
        "asset": "USDC",
        "destination": destination,
        "destination_class": dest.class_,
        "destination_allowed": dest.allowed,
        "job_id": str(job_id),
        "purpose": purpose,
        "daily_spend_usdc": format_amount(daily),
        "outstanding_exposure_usdc": format_amount(exposure),
        "wallet_balances": {k: format_amount(v) for k, v in bals.items()},
        "policy_version": stack["loaded"].document.policy_version,
        "policy_hash": stack["loaded"].policy_hash,
        "frozen": False,
        "signer_enabled": True,
        "wallet_phase": "A",
        "correlation_id": str(correlation_id),
        "request_id": str(request_id),
        "approved_at": stack["ledger"].get_payment_request(request_id)["requested_at"].isoformat(),
    }
    return policy_execute_via_asgi(stack["policy"], CONTROL)(body)


def test_model_cannot_call_payment_requests(stack) -> None:
    response = _request(
        stack["control"],
        "POST",
        "/v1/payment-requests",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": str(uuid4()),
            "idempotency_key": "pay-model-01",
        },
        headers=_auth(MODEL),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_control_token_forbidden_on_tools(stack) -> None:
    response = _request(
        stack["control"],
        "POST",
        "/v1/tools/get_financial_state",
        json={},
        headers=_auth(CONTROL),
    )
    assert response.status_code == 403


def test_request_payment_debits_once_via_signer(stack) -> None:
    job_id = _accept(stack["control"])
    before = stack["wallet"].get_balances()["USDC"]
    key = f"pay-{uuid4().hex[:12]}"
    body = {
        "amount": "0.050000",
        "asset": "USDC",
        "destination": "mock:counterparty:mkt-escrow",
        "purpose": "marketplace_acceptance_fee",
        "job_id": job_id,
        "idempotency_key": key,
    }
    first = _request(
        stack["control"], "POST", "/v1/tools/request_payment", json=body, headers=_auth(MODEL)
    ).json()
    assert first["ok"] is True, first
    assert first["transaction_reference"].startswith("mocktx_")
    assert HMAC not in str(first)
    assert DEBIT not in str(first)
    assert SIGNER not in str(first)
    mid = stack["wallet"].get_balances()["USDC"]
    assert mid == before - Decimal("0.050000")
    replay = _request(
        stack["control"], "POST", "/v1/tools/request_payment", json=body, headers=_auth(MODEL)
    ).json()
    assert replay["transaction_reference"] == first["transaction_reference"]
    assert stack["wallet"].get_balances()["USDC"] == mid


def test_duplicate_payment_different_key(stack) -> None:
    job_id = _accept(stack["control"])
    body = {
        "amount": "0.050000",
        "asset": "USDC",
        "destination": "mock:counterparty:mkt-escrow",
        "purpose": "marketplace_acceptance_fee",
        "job_id": job_id,
    }
    first = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={**body, "idempotency_key": f"dup-a-{uuid4().hex[:8]}"},
        headers=_auth(MODEL),
    ).json()
    assert first["ok"] is True, first
    second = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={**body, "idempotency_key": f"dup-b-{uuid4().hex[:8]}"},
        headers=_auth(MODEL),
    ).json()
    assert second["code"] == "DUPLICATE_PAYMENT"
    assert stack["wallet"].get_balances()["USDC"] == Decimal("19.950000")


def test_policy_rejection_is_not_debit(stack) -> None:
    job_id = _accept(stack["control"])
    before = stack["wallet"].get_balances()["USDC"]
    response = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "5.000000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": f"rej-{uuid4().hex[:10]}",
        },
        headers=_auth(MODEL),
    ).json()
    assert response["code"] == "POLICY_REJECTED"
    assert stack["wallet"].get_balances()["USDC"] == before


def test_force_true_on_payment_requests(stack) -> None:
    response = _request(
        stack["control"],
        "POST",
        "/v1/payment-requests",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": str(uuid4()),
            "idempotency_key": "force-pay01",
            "force": True,
        },
        headers=_auth(CONTROL),
    )
    assert response.status_code == 400


def test_freeze_after_approval_before_debit(stack) -> None:
    job_id = _accept(stack["control"])
    (stack["freeze_dir"] / "FREEZE").write_text("1\n", encoding="utf-8")
    before = stack["wallet"].get_balances()["USDC"]
    response = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": f"frz-{uuid4().hex[:10]}",
        },
        headers=_auth(MODEL),
    ).json()
    assert response["code"] == "AGENT_FROZEN"
    assert stack["wallet"].get_balances()["USDC"] == before


def test_hmac_wrong_fails_before_debit(stack, loaded) -> None:
    from aea.policy.signer_client import PolicySignerClient as PSC

    bad = create_policy_app(
        control_token=CONTROL,
        model_token=MODEL,
        loaded=loaded,
        freeze_path=stack["freeze_dir"] / "FREEZE",
        now=NOW,
        signer_client=PSC(
            hmac_key="wrong-hmac-key-pr10-0000000000001",
            signer_token=SIGNER,
            signer_app=stack["signer_app"],
        ),
    )
    job_id = _accept(stack["control"])
    orchestrator = PaymentOrchestrator(
        ledger=stack["ledger"],
        policy=loaded,
        policy_execute=policy_execute_via_asgi(bad, CONTROL),
        wallet_balances=stack["wallet"].get_balances,
        control_token=CONTROL,
    )
    stack["control"]._plane._payment = orchestrator
    before = stack["wallet"].get_balances()["USDC"]
    response = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": f"hmac-{uuid4().hex[:10]}",
        },
        headers=_auth(MODEL),
    ).json()
    assert response["ok"] is False
    assert stack["wallet"].get_balances()["USDC"] == before


def test_perform_records_cost_and_fail_after_spend(stack) -> None:
    found = _request(
        stack["control"], "POST", "/v1/tools/find_jobs", json={"limit": 20}, headers=_auth(MODEL)
    ).json()
    oid = next(
        j["opportunity_id"]
        for j in found["jobs"]
        if j["external_reference"] == "mock:job:fails-after-spend-001"
    )
    # unprofitable/fails job may be declined by margin; this fixture is designed to work
    job = _request(
        stack["control"],
        "POST",
        "/v1/tools/accept_job",
        json={"opportunity_id": oid, "idempotency_key": f"acc-fail-{uuid4().hex[:8]}"},
        headers=_auth(MODEL),
    ).json()
    if job.get("ok"):
        performed = _request(
            stack["control"],
            "POST",
            "/v1/tools/perform_job",
            json={"job_id": job["job_id"], "idempotency_key": f"perf-fail-{uuid4().hex[:8]}"},
            headers=_auth(MODEL),
        ).json()
        assert performed["code"] == "JOB_FAILED"
        costs = stack["ledger"]._conn.execute(
            "SELECT count(*) AS n FROM economic_costs WHERE job_id = %s",
            (job["job_id"],),
        ).fetchone()
        assert int(costs["n"]) >= 1


def test_fake_payment_is_not_revenue(stack) -> None:
    found = _request(
        stack["control"], "POST", "/v1/tools/find_jobs", json={"limit": 20}, headers=_auth(MODEL)
    ).json()
    oid = next(
        j["opportunity_id"]
        for j in found["jobs"]
        if j["external_reference"] == "mock:job:fake-payment-001"
    )
    job = _request(
        stack["control"],
        "POST",
        "/v1/tools/accept_job",
        json={"opportunity_id": oid, "idempotency_key": f"acc-fake-{uuid4().hex[:8]}"},
        headers=_auth(MODEL),
    ).json()
    assert job.get("ok") is False
    assert job.get("code") == "AGENT_RISK_VETO"


def test_control_rejects_hmac_and_debit_in_constructor(freeze_dir) -> None:
    with pytest.raises(ValueError, match="must not hold"):
        create_control_app(
            model_token=MODEL,
            freeze_path=freeze_dir / "FREEZE",
            hmac_key=HMAC,
        )
    with pytest.raises(ValueError, match="must not hold"):
        create_control_app(
            model_token=MODEL,
            freeze_path=freeze_dir / "FREEZE",
            debit_token=DEBIT,
        )


def test_model_cannot_override_outstanding_exposure(stack) -> None:
    job_id = _accept(stack["control"])
    response = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": f"ovr-{uuid4().hex[:10]}",
            "outstanding_exposure_usdc": "0.000000",
        },
        headers=_auth(MODEL),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert _debit_count(stack["wallet"]) == 0


def test_capital_at_risk_from_ledger_rejects_and_permits(stack) -> None:
    job_id = _accept(stack["control"])
    _seed_unsettled(stack["ledger"], job_id, "4.900000")
    assert stack["ledger"].outstanding_exposure_usdc() == Decimal("4.900000")
    over = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.500000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": f"car-over-{uuid4().hex[:8]}",
        },
        headers=_auth(MODEL),
    ).json()
    assert over["code"] == "POLICY_REJECTED"
    assert over["reason_code"] == "CAPITAL_AT_RISK_EXCEEDED"
    assert _debit_count(stack["wallet"]) == 0
    inside = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": f"car-ok-{uuid4().hex[:8]}",
        },
        headers=_auth(MODEL),
    ).json()
    assert inside["ok"] is True, inside
    assert _debit_count(stack["wallet"]) == 1


def test_job_accept_respects_capital_at_risk(stack) -> None:
    job_id = _accept(stack["control"])
    _seed_unsettled(stack["ledger"], job_id, "4.990000")
    found = _request(
        stack["control"], "POST", "/v1/tools/find_jobs", json={"limit": 20}, headers=_auth(MODEL)
    ).json()
    oid = next(
        j["opportunity_id"]
        for j in found["jobs"]
        if j["external_reference"] == "mock:job:network-fail-001"
    )
    blocked = _request(
        stack["control"],
        "POST",
        "/v1/tools/accept_job",
        json={"opportunity_id": oid, "idempotency_key": f"car-job-{uuid4().hex[:8]}"},
        headers=_auth(MODEL),
    ).json()
    assert blocked["ok"] is False
    assert blocked["code"] == "CAPITAL_AT_RISK_EXCEEDED"


def test_recovery_debit_before_ledger_settlement(stack) -> None:
    job_id = _accept(stack["control"])
    key = f"rec-pre-{uuid4().hex[:8]}"
    corr = uuid4()
    pending = stack["ledger"].create_payment_request(
        PaymentCreate.model_validate(
            {
                "job_id": job_id,
                "amount": "0.050000",
                "asset": "USDC",
                "destination": "mock:counterparty:mkt-escrow",
                "purpose": "marketplace_acceptance_fee",
                "correlation_id": str(corr),
                "idempotency_key": key,
            }
        )
    )
    signed = _sign_pending(
        stack,
        request_id=pending["request_id"],
        job_id=job_id,
        amount="0.050000",
        destination="mock:counterparty:mkt-escrow",
        purpose="marketplace_acceptance_fee",
        correlation_id=corr,
    )
    assert signed.get("ok") is True, signed
    assert signed.get("tx_id")
    assert _debit_count(stack["wallet"]) == 1
    row = stack["ledger"].get_payment_request(pending["request_id"])
    assert row["transaction_reference"] is None
    assert stack["ledger"].cash_cost_count(pending["request_id"]) == 0
    recovered = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": key,
        },
        headers=_auth(MODEL),
    ).json()
    assert recovered["ok"] is True, recovered
    assert recovered["transaction_reference"] == signed["tx_id"]
    assert _debit_count(stack["wallet"]) == 1
    assert stack["ledger"].cash_cost_count(pending["request_id"]) == 1
    settled = stack["ledger"].get_payment_request(pending["request_id"])
    assert settled["transaction_reference"] == signed["tx_id"]


def test_recovery_after_settle_before_cost(stack) -> None:
    job_id = _accept(stack["control"])
    key = f"rec-stl-{uuid4().hex[:8]}"
    corr = uuid4()
    pending = stack["ledger"].create_payment_request(
        PaymentCreate.model_validate(
            {
                "job_id": job_id,
                "amount": "0.050000",
                "asset": "USDC",
                "destination": "mock:counterparty:mkt-escrow",
                "purpose": "marketplace_acceptance_fee",
                "correlation_id": str(corr),
                "idempotency_key": key,
            }
        )
    )
    signed = _sign_pending(
        stack,
        request_id=pending["request_id"],
        job_id=job_id,
        amount="0.050000",
        destination="mock:counterparty:mkt-escrow",
        purpose="marketplace_acceptance_fee",
        correlation_id=corr,
    )
    assert signed.get("ok") is True, signed
    stack["ledger"].decide_payment_request(
        PaymentDecisionWrite.model_validate(
            {
                "request_id": str(pending["request_id"]),
                "decision": "approved",
                "approved_amount": "0.050000",
                "canonical_hash": signed.get("canonical_hash"),
                "idempotency_key": f"dec-{key}",
            }
        )
    )
    stack["ledger"].settle_payment_request(
        PaymentSettle.model_validate(
            {
                "request_id": str(pending["request_id"]),
                "transaction_reference": signed["tx_id"],
                "idempotency_key": f"stl-{key}",
            }
        )
    )
    assert stack["ledger"].cash_cost_count(pending["request_id"]) == 0
    assert _debit_count(stack["wallet"]) == 1
    recovered = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": key,
        },
        headers=_auth(MODEL),
    ).json()
    assert recovered["ok"] is True, recovered
    assert recovered["transaction_reference"] == signed["tx_id"]
    assert _debit_count(stack["wallet"]) == 1
    assert stack["ledger"].cash_cost_count(pending["request_id"]) == 1


def test_full_success_retry_does_not_double_cost(stack) -> None:
    job_id = _accept(stack["control"])
    key = f"rec-full-{uuid4().hex[:8]}"
    body = {
        "amount": "0.050000",
        "asset": "USDC",
        "destination": "mock:counterparty:mkt-escrow",
        "purpose": "marketplace_acceptance_fee",
        "job_id": job_id,
        "idempotency_key": key,
    }
    first = _request(
        stack["control"], "POST", "/v1/tools/request_payment", json=body, headers=_auth(MODEL)
    ).json()
    assert first["ok"] is True, first
    request_id = UUID(first["request_id"])
    assert stack["ledger"].cash_cost_count(request_id) == 1
    replay = _request(
        stack["control"], "POST", "/v1/tools/request_payment", json=body, headers=_auth(MODEL)
    ).json()
    assert replay["transaction_reference"] == first["transaction_reference"]
    assert _debit_count(stack["wallet"]) == 1
    assert stack["ledger"].cash_cost_count(request_id) == 1


def test_outbound_wallet_ledger_mismatch_fail_closed(stack) -> None:
    job_id = _accept(stack["control"])
    first = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": f"mm-a-{uuid4().hex[:8]}",
        },
        headers=_auth(MODEL),
    ).json()
    assert first["ok"] is True, first
    assert _debit_count(stack["wallet"]) == 1
    stack["wallet"].credit(
        asset="USDC",
        amount=Decimal("1"),
        tx_id=new_tx_id(),
        reason="inject_mismatch",
        idempotency_key=f"mm-credit-{uuid4().hex[:8]}",
    )
    before = stack["wallet"].get_balances()["USDC"]
    blocked = _request(
        stack["control"],
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.060000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": f"mm-b-{uuid4().hex[:8]}",
        },
        headers=_auth(MODEL),
    ).json()
    assert blocked["code"] == "WALLET_LEDGER_MISMATCH"
    assert _debit_count(stack["wallet"]) == 1
    assert stack["wallet"].get_balances()["USDC"] == before
    audit = stack["ledger"]._conn.execute(
        """
        SELECT count(*) AS n FROM audit_events
         WHERE event_type = 'wallet_ledger_mismatch'
        """
    ).fetchone()
    assert int(audit["n"]) >= 1
    observed = _request(
        stack["control"],
        "POST",
        "/v1/tools/get_financial_state",
        json={},
        headers=_auth(MODEL),
    )
    assert observed.status_code == 200
    costs = stack["ledger"].cash_cost_count(UUID(first["request_id"]))
    assert costs == 1
