"""Postgres-backed ledger services. Uses economic_app grants via SET ROLE."""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aea.config import load_policy
from aea.ledger.errors import LedgerError
from aea.ledger.models import (
    ChainEvidenceCreate,
    CostCreate,
    DecisionCreate,
    JobAccept,
    JobTransition,
    OpportunityCreate,
    PaymentCreate,
    PaymentDecisionWrite,
    PaymentSettle,
    RevenueCreate,
    TransferCreate,
)
from aea.ledger.service import LedgerService
from aea.wallet.mock import MockWallet, new_tx_id

ADMIN_PW = Path.home() / ".config/controlops/postgres/postgres_password"


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
    from tests.dbutil import isolate_economic_ledger

    isolate_economic_ledger(c)
    c.execute("SET ROLE economic_app")
    c.execute("SET search_path TO economic")
    try:
        yield c
        c.rollback()
    finally:
        c.close()


@pytest.fixture
def ledger(conn) -> LedgerService:
    return LedgerService(conn, policy=load_policy())


def _opp(ledger: LedgerService, **overrides) -> dict:
    body = {
        "source": "mock",
        "external_reference": f"mock:job:pr6-{uuid4().hex}",
        "description_hash": "a" * 64,
        "expected_revenue": "0.500000",
        "expected_cost": "0.050000",
        "idempotency_key": f"opp-{uuid4().hex[:12]}",
    }
    body.update(overrides)
    return ledger.record_opportunity(OpportunityCreate.model_validate(body))


def _accept(ledger: LedgerService, opportunity_id, revenue: str = "0.500000") -> dict:
    return ledger.accept_job(
        JobAccept.model_validate(
            {
                "opportunity_id": str(opportunity_id),
                "expected_revenue": revenue,
                "idempotency_key": f"accept-{uuid4().hex[:12]}",
            }
        )
    )


def _to_submitted(ledger: LedgerService, job_id) -> None:
    for status in ("performing", "performed", "submitted"):
        ledger.transition_job(
            JobTransition.model_validate(
                {
                    "job_id": str(job_id),
                    "status": status,
                    "deliverable_hash": "b" * 64,
                    "idempotency_key": f"job-{status}-{uuid4().hex[:10]}",
                }
            )
        )


def test_financial_state_reads_seed(ledger: LedgerService) -> None:
    state = ledger.get_financial_state()
    assert state["agent_id"] == "economic-agent"
    assert state["balances"]["USDC"] == "20.000000"
    assert state["balances"]["SOL"] == "0.050000"
    assert state["opening_usdc"] == "20.000000"
    assert state["unit_of_account"] == "USDC"
    assert "AEA_WALLET" not in str(state)
    assert "AEA_SIGNER" not in str(state)


def test_job_lifecycle_and_compute_mark(ledger: LedgerService, conn) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    assert job["status"] == "accepted"
    before = ledger.get_accounts()["USDC"]["current_balance"]
    cost = ledger.record_cost(
        CostCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "category": "compute",
                "amount": "0.001000",
                "asset": "USDC",
                "idempotency_key": f"compute-{uuid4().hex[:12]}",
            }
        )
    )
    assert cost["payment_request_id"] is None
    assert ledger.get_accounts()["USDC"]["current_balance"] == before
    recon = ledger.ledger_reconciliation()
    usdc = next(r for r in recon if r["asset"] == "USDC")
    assert usdc["delta"] == "0.000000"
    _to_submitted(ledger, job["job_id"])
    assert ledger.get_job(job["job_id"])["status"] == "submitted"


def test_cash_cost_decrements_balance_compute_does_not(ledger: LedgerService) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    pay = ledger.create_payment_request(
        PaymentCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "amount": "0.050000",
                "asset": "USDC",
                "destination": "mock:counterparty:mkt-escrow",
                "purpose": "marketplace_acceptance_fee",
                "correlation_id": str(uuid4()),
                "idempotency_key": f"pay-{uuid4().hex[:12]}",
            }
        )
    )
    ledger.decide_payment_request(
        PaymentDecisionWrite.model_validate(
            {
                "request_id": str(pay["request_id"]),
                "decision": "approved",
                "approved_amount": "0.050000",
                "idempotency_key": f"dec-{uuid4().hex[:12]}",
            }
        )
    )
    ledger.settle_payment_request(
        PaymentSettle.model_validate(
            {
                "request_id": str(pay["request_id"]),
                "transaction_reference": new_tx_id(),
                "idempotency_key": f"set-{uuid4().hex[:12]}",
            }
        )
    )
    before = Decimal(ledger.get_accounts()["USDC"]["current_balance"])
    ledger.record_cost(
        CostCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "category": "purchased_service",
                "amount": "0.050000",
                "asset": "USDC",
                "payment_request_id": str(pay["request_id"]),
                "idempotency_key": f"cash-{uuid4().hex[:12]}",
            }
        )
    )
    after = Decimal(ledger.get_accounts()["USDC"]["current_balance"])
    assert after == before - Decimal("0.050000")
    usdc = next(r for r in ledger.ledger_reconciliation() if r["asset"] == "USDC")
    assert usdc["delta"] == "0.000000"


def test_verified_revenue_and_pnl(ledger: LedgerService) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    ledger.record_cost(
        CostCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "category": "compute",
                "amount": "0.001000",
                "asset": "USDC",
                "idempotency_key": f"cmark-{uuid4().hex[:12]}",
            }
        )
    )
    _to_submitted(ledger, job["job_id"])
    tx = new_tx_id()
    ledger.record_verified_revenue(
        RevenueCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "amount": "0.500000",
                "transaction_reference": tx,
                "idempotency_key": f"rev-{uuid4().hex[:12]}",
            }
        )
    )
    pnl = ledger.realised_pnl_by_job(job["job_id"])
    assert pnl["realised_revenue_usdc"] == "0.500000"
    assert pnl["realised_cost_usdc"] == "0.001000"
    assert pnl["realised_pnl_usdc"] == "0.499000"
    assert ledger.get_job(job["job_id"])["status"] == "completed"
    assert Decimal(ledger.get_accounts()["USDC"]["current_balance"]) == Decimal("20.500000")


def test_unverified_and_fake_revenue_rejected(ledger: LedgerService) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    _to_submitted(ledger, job["job_id"])
    with pytest.raises(LedgerError) as exc:
        ledger.record_verified_revenue(
            RevenueCreate.model_validate(
                {
                    "job_id": str(job["job_id"]),
                    "amount": "0.500000",
                    "transaction_reference": new_tx_id(),
                    "verified": False,
                    "idempotency_key": f"fake-{uuid4().hex[:12]}",
                }
            )
        )
    assert exc.value.code == "FAKE_PAYMENT"
    pnl = ledger.realised_pnl_by_job(job["job_id"])
    assert pnl["realised_revenue_usdc"] == "0.000000"


def test_duplicate_transaction_reference(ledger: LedgerService) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    _to_submitted(ledger, job["job_id"])
    tx = new_tx_id()
    first = ledger.record_verified_revenue(
        RevenueCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "amount": "0.500000",
                "transaction_reference": tx,
                "idempotency_key": f"r1-{uuid4().hex[:12]}",
            }
        )
    )
    replay = ledger.record_verified_revenue(
        RevenueCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "amount": "0.500000",
                "transaction_reference": tx,
                "idempotency_key": f"r2-{uuid4().hex[:12]}",
            }
        )
    )
    assert replay["replay"] is True
    assert first["revenue_id"] == replay["revenue_id"]
    opp2 = _opp(ledger)
    job2 = _accept(ledger, opp2["opportunity_id"])
    _to_submitted(ledger, job2["job_id"])
    with pytest.raises(LedgerError) as exc:
        ledger.record_verified_revenue(
            RevenueCreate.model_validate(
                {
                    "job_id": str(job2["job_id"]),
                    "amount": "0.400000",
                    "transaction_reference": tx,
                    "idempotency_key": f"r3-{uuid4().hex[:12]}",
                }
            )
        )
    assert exc.value.code == "CONFLICT"
    assert Decimal(ledger.get_accounts()["USDC"]["current_balance"]) == Decimal("20.500000")


def test_payment_request_lifecycle_and_duplicate_intent(ledger: LedgerService) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    key = f"pay-{uuid4().hex[:12]}"
    body = {
        "job_id": str(job["job_id"]),
        "amount": "0.050000",
        "asset": "USDC",
        "destination": "mock:counterparty:mkt-escrow",
        "purpose": "marketplace_acceptance_fee",
        "correlation_id": str(uuid4()),
        "idempotency_key": key,
    }
    first = ledger.create_payment_request(PaymentCreate.model_validate(body))
    second = ledger.create_payment_request(PaymentCreate.model_validate(body))
    assert second["replay"] is True
    assert first["request_id"] == second["request_id"]
    conflict = dict(body)
    conflict["amount"] = "0.060000"
    with pytest.raises(LedgerError) as exc:
        ledger.create_payment_request(PaymentCreate.model_validate(conflict))
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    other = dict(body)
    other["idempotency_key"] = f"pay-{uuid4().hex[:12]}"
    other["correlation_id"] = str(uuid4())
    with pytest.raises(LedgerError) as exc2:
        ledger.create_payment_request(PaymentCreate.model_validate(other))
    assert exc2.value.code == "DUPLICATE_PAYMENT"


def test_rejected_payment_stays_rejected(ledger: LedgerService) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    pay = ledger.create_payment_request(
        PaymentCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "amount": "0.050000",
                "asset": "USDC",
                "destination": "mock:counterparty:mkt-escrow",
                "purpose": "marketplace_acceptance_fee",
                "correlation_id": str(uuid4()),
                "idempotency_key": f"rej-{uuid4().hex[:12]}",
            }
        )
    )
    ledger.decide_payment_request(
        PaymentDecisionWrite.model_validate(
            {
                "request_id": str(pay["request_id"]),
                "decision": "rejected",
                "reason_code": "POLICY_REJECTED",
                "rejection_reason": "test",
                "idempotency_key": f"rejdec-{uuid4().hex[:12]}",
            }
        )
    )
    with pytest.raises(LedgerError) as exc:
        ledger.decide_payment_request(
            PaymentDecisionWrite.model_validate(
                {
                    "request_id": str(pay["request_id"]),
                    "decision": "approved",
                    "approved_amount": "0.050000",
                    "idempotency_key": f"rejappr-{uuid4().hex[:12]}",
                }
            )
        )
    assert exc.value.code == "CONFLICT"
    row = ledger.get_payment_request(pay["request_id"])
    assert row["policy_decision"] == "rejected"
    with pytest.raises(LedgerError):
        ledger.settle_payment_request(
            PaymentSettle.model_validate(
                {
                    "request_id": str(pay["request_id"]),
                    "transaction_reference": new_tx_id(),
                    "idempotency_key": f"rejs-{uuid4().hex[:12]}",
                }
            )
        )


def test_settled_payment_cannot_change_reference(ledger: LedgerService) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    pay = ledger.create_payment_request(
        PaymentCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "amount": "0.050000",
                "asset": "USDC",
                "destination": "mock:counterparty:mkt-escrow",
                "purpose": "marketplace_acceptance_fee",
                "correlation_id": str(uuid4()),
                "idempotency_key": f"st-{uuid4().hex[:12]}",
            }
        )
    )
    ledger.decide_payment_request(
        PaymentDecisionWrite.model_validate(
            {
                "request_id": str(pay["request_id"]),
                "decision": "approved",
                "approved_amount": "0.050000",
                "idempotency_key": f"stdec-{uuid4().hex[:12]}",
            }
        )
    )
    tx = new_tx_id()
    ledger.settle_payment_request(
        PaymentSettle.model_validate(
            {
                "request_id": str(pay["request_id"]),
                "transaction_reference": tx,
                "idempotency_key": f"st1-{uuid4().hex[:12]}",
            }
        )
    )
    with pytest.raises(LedgerError) as exc:
        ledger.settle_payment_request(
            PaymentSettle.model_validate(
                {
                    "request_id": str(pay["request_id"]),
                    "transaction_reference": new_tx_id(),
                    "idempotency_key": f"st2-{uuid4().hex[:12]}",
                }
            )
        )
    assert exc.value.code == "CONFLICT"


def test_transfer_top_up_is_not_revenue(ledger: LedgerService) -> None:
    before_pnl = ledger.get_financial_state()["revenue_usdc"]
    ledger.record_transfer(
        TransferCreate.model_validate(
            {
                "asset": "USDC",
                "amount": "1.000000",
                "direction": "in",
                "classification": "operator_top_up",
                "idempotency_key": f"top-{uuid4().hex[:12]}",
            }
        )
    )
    assert Decimal(ledger.get_accounts()["USDC"]["current_balance"]) == Decimal("21.000000")
    assert ledger.get_financial_state()["revenue_usdc"] == before_pnl
    usdc = next(r for r in ledger.ledger_reconciliation() if r["asset"] == "USDC")
    assert usdc["delta"] == "0.000000"


def test_opening_capital_insert_blocked(ledger: LedgerService) -> None:
    with pytest.raises(ValidationError):
        TransferCreate.model_validate(
            {
                "asset": "USDC",
                "amount": "1.000000",
                "direction": "in",
                "classification": "opening_capital",
                "idempotency_key": "seed-blocked-01",
            }
        )


def test_idempotent_cost_replay_and_conflict(ledger: LedgerService) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    key = f"cost-{uuid4().hex[:12]}"
    body = {
        "job_id": str(job["job_id"]),
        "category": "compute",
        "amount": "0.001000",
        "asset": "USDC",
        "idempotency_key": key,
    }
    a = ledger.record_cost(CostCreate.model_validate(body))
    b = ledger.record_cost(CostCreate.model_validate(body))
    assert a["cost_id"] == b["cost_id"]
    body2 = dict(body)
    body2["amount"] = "0.002000"
    with pytest.raises(LedgerError) as exc:
        ledger.record_cost(CostCreate.model_validate(body2))
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_invalid_job_transition(ledger: LedgerService) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    _to_submitted(ledger, job["job_id"])
    ledger.transition_job(
        JobTransition.model_validate(
            {
                "job_id": str(job["job_id"]),
                "status": "completed",
                "idempotency_key": f"done-{uuid4().hex[:12]}",
            }
        )
    )
    with pytest.raises(LedgerError) as exc:
        ledger.transition_job(
            JobTransition.model_validate(
                {
                    "job_id": str(job["job_id"]),
                    "status": "accepted",
                    "idempotency_key": f"back-{uuid4().hex[:12]}",
                }
            )
        )
    assert exc.value.code == "CONFLICT"


def test_atomic_rollback_on_missing_payment_request(ledger: LedgerService) -> None:
    before = ledger.get_accounts()["USDC"]["current_balance"]
    with pytest.raises(LedgerError):
        ledger.record_cost(
            CostCreate.model_validate(
                {
                    "job_id": str(uuid4()),
                    "category": "purchased_service",
                    "amount": "0.050000",
                    "asset": "USDC",
                    "payment_request_id": str(uuid4()),
                    "idempotency_key": f"badfk-{uuid4().hex[:12]}",
                }
            )
        )
    assert ledger.get_accounts()["USDC"]["current_balance"] == before
    state = ledger.get_financial_state()
    assert state["balances"]["USDC"] == before


def test_accept_wrong_revenue_rolls_back_opportunity(ledger: LedgerService, conn) -> None:
    opp = _opp(ledger)
    with pytest.raises(LedgerError) as exc:
        _accept(ledger, opp["opportunity_id"], revenue="0.400000")
    assert exc.value.code == "CONFLICT"
    row = conn.execute(
        "SELECT decision FROM opportunities WHERE opportunity_id = %s",
        (opp["opportunity_id"],),
    ).fetchone()
    assert row["decision"] == "discovered"


def test_wallet_ledger_recon_and_mismatch(ledger: LedgerService) -> None:
    wallet = MockWallet(
        phase="A",
        opening={"USDC": Decimal("20"), "SOL": Decimal("0.05")},
    )
    report = ledger.reconcile_with_wallet(wallet.get_balances())
    assert report["ok"] is True
    assert report["code"] == "OK"
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    pay = ledger.create_payment_request(
        PaymentCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "amount": "0.050000",
                "asset": "USDC",
                "destination": "mock:counterparty:mkt-escrow",
                "purpose": "marketplace_acceptance_fee",
                "correlation_id": str(uuid4()),
                "idempotency_key": f"wpay-{uuid4().hex[:12]}",
            }
        )
    )
    ledger.decide_payment_request(
        PaymentDecisionWrite.model_validate(
            {
                "request_id": str(pay["request_id"]),
                "decision": "approved",
                "approved_amount": "0.050000",
                "idempotency_key": f"wdec-{uuid4().hex[:12]}",
            }
        )
    )
    tx = new_tx_id()
    ledger.settle_payment_request(
        PaymentSettle.model_validate(
            {
                "request_id": str(pay["request_id"]),
                "transaction_reference": tx,
                "idempotency_key": f"wset-{uuid4().hex[:12]}",
            }
        )
    )
    ledger.record_cost(
        CostCreate.model_validate(
            {
                "job_id": str(job["job_id"]),
                "category": "purchased_service",
                "amount": "0.050000",
                "asset": "USDC",
                "payment_request_id": str(pay["request_id"]),
                "idempotency_key": f"wcash-{uuid4().hex[:12]}",
            }
        )
    )
    mismatched = ledger.reconcile_with_wallet(wallet.get_balances())
    assert mismatched["ok"] is False
    assert mismatched["code"] == "WALLET_LEDGER_MISMATCH"
    assert Decimal(ledger.get_accounts()["USDC"]["current_balance"]) == Decimal("19.950000")
    assert wallet.get_balances()["USDC"] == Decimal("20")
    wallet.debit(
        asset="USDC",
        amount=Decimal("0.050000"),
        destination="mock:counterparty:mkt-escrow",
        tx_id=tx,
        reason="marketplace_acceptance_fee",
        idempotency_key="wallet-match-pr6",
    )
    matched = ledger.reconcile_with_wallet(wallet.get_balances())
    assert matched["ok"] is True


def test_evm_chain_evidence_is_exact_and_idempotent(ledger: LedgerService) -> None:
    opp = _opp(ledger)
    job = _accept(ledger, opp["opportunity_id"])
    pay = ledger.create_payment_request(PaymentCreate.model_validate({
        "job_id": str(job["job_id"]), "amount": "0.010000", "asset": "USDC",
        "destination": "base:approved:test", "purpose": "evm fixture",
        "correlation_id": str(uuid4()), "idempotency_key": f"evm-pay-{uuid4().hex[:12]}"}))
    body = ChainEvidenceCreate.model_validate({"payment_request_id": str(pay["request_id"]),
        "rail": "evm", "network": "base-local", "chain_id": 31337,
        "transaction_hash": "0x" + "ab" * 32, "block_number": 7,
        "token_contract": "0x" + "22" * 20, "gas_used": 55123,
        "effective_gas_price_wei": 123456789, "fee_wei": 6805308570747,
        "fee_usdc_snapshot": "2500.000000", "fee_rate_source": "test fixture",
        "fee_rate_observed_at": "2026-08-22T00:00:00Z"})
    first = ledger.record_chain_evidence(body)
    replay = ledger.record_chain_evidence(body)
    assert not first["replay"] and replay["replay"]
    changed = body.model_copy(update={"fee_wei": body.fee_wei + 1})
    with pytest.raises(LedgerError, match="IDEMPOTENCY_CONFLICT"):
        ledger.record_chain_evidence(changed)


def test_decision_and_audit_scrub_secrets(ledger: LedgerService) -> None:
    from aea.ledger.models import AuditWrite

    ledger.write_audit(
        AuditWrite.model_validate(
            {
                "event_type": "test_event",
                "payload": {
                    "note": "ok",
                    "AEA_WALLET_DEBIT_TOKEN": "should-not-store",
                    "request_hmac": "deadbeef",
                },
            }
        )
    )
    row = ledger._conn.execute(
        "SELECT payload FROM audit_events WHERE event_type = 'test_event' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert "note" in row["payload"]
    assert "AEA_WALLET_DEBIT_TOKEN" not in row["payload"]
    assert "request_hmac" not in row["payload"]
    ledger.record_decision(
        DecisionCreate.model_validate(
            {
                "decision_type": "evaluate",
                "decision": "record",
                "reasoning_summary": "margin ok",
                "idempotency_key": f"decn-{uuid4().hex[:12]}",
            }
        )
    )


def test_economic_app_cannot_mutate_controls(conn) -> None:
    def as_app() -> None:
        conn.rollback()
        conn.execute("SET ROLE economic_app")
        conn.execute("SET search_path TO economic")

    as_app()
    with pytest.raises(Exception):
        conn.execute("UPDATE supervisor_state SET frozen = true WHERE singleton")
    as_app()
    with pytest.raises(Exception):
        conn.execute("UPDATE policy_versions SET is_current = false WHERE is_current")
    as_app()
    with pytest.raises(Exception):
        conn.execute("UPDATE constitution_versions SET constitution_hash = 'tamper'")
    as_app()
    with pytest.raises(Exception):
        conn.execute("UPDATE agent_accounts SET opening_balance = 99 WHERE asset = 'USDC'")
    as_app()
    with pytest.raises(Exception):
        conn.execute(
            """
            INSERT INTO transfers (account_id, direction, amount, asset, classification)
            SELECT account_id, 'in', 1, 'USDC', 'opening_capital'
              FROM agent_accounts WHERE asset = 'USDC' LIMIT 1
            """
        )


def test_service_has_no_wallet_or_signer_secrets() -> None:
    src = inspect.getsource(LedgerService)
    assert "AEA_WALLET_DEBIT_TOKEN" not in src
    assert "AEA_SIGNER_TOKEN" not in src
    assert "AEA_SIGNER_HMAC_KEY" not in src
    assert "solders" not in src
    assert "solana" not in src
    assert not hasattr(LedgerService, "debit")
    assert not hasattr(LedgerService, "credit")
    assert not hasattr(LedgerService, "unfreeze")
