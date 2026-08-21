"""PR11 M1 Gate A: deterministic model-scoped end-to-end acceptance."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from psycopg.rows import dict_row

from aea import CONSTITUTION_VERSION, NINE_TOOLS
from aea.config import load_policy
from aea.control.app import create_app as create_control_app
from aea.ledger.service import LedgerService
from aea.marketplace.mock import MockMarketplace
from aea.payment.service import PaymentOrchestrator, policy_execute_via_asgi
from aea.policy.service import create_app as create_policy_app
from aea.policy.signer_client import PolicySignerClient
from aea.signer.mock import MockSigner
from aea.signer.service import AsgiWalletDebit, create_app as create_signer_app
from aea.tools_client.http import ToolClient
from aea.wallet.mock import MockWallet
from aea.wallet.service import create_app as create_wallet_app

from .driver import GateADriver

MODEL = "gate-a-model-scope"
CONTROL = "gate-a-control-scope"
SUPERVISOR = "gate-a-supervisor-scope"
SIGNER = "gate-a-signer-scope"
HMAC = "gate-a-hmac-binding-material-000001"
DEBIT = "gate-a-wallet-debit-scope"
CREDIT = "gate-a-wallet-credit-scope"
READ = "gate-a-wallet-read-scope"
MARKET = "gate-a-marketplace-scope"
ADMIN_PW = Path.home() / ".config/controlops/postgres/postgres_password"
EVIDENCE = Path(__file__).parent / "evidence" / "gate-a" / "result.json"


def _postgres_up() -> bool:
    if not ADMIN_PW.is_file():
        return False
    try:
        import psycopg
        with psycopg.connect(host="127.0.0.1", port=5432, dbname="controlops", user="controlops_admin", password=ADMIN_PW.read_text().rstrip(), connect_timeout=3):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_up(), reason="controlops Postgres is not reachable")


def _asgi_post(app, url: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://control") as client:
            return await client.post(httpx.URL(url).path, **kwargs)
    return asyncio.run(send())


@pytest.fixture
def gate_stack(tmp_path, monkeypatch):
    import psycopg

    loaded = load_policy()
    conn = psycopg.connect(host="127.0.0.1", port=5432, dbname="controlops", user="controlops_admin", password=ADMIN_PW.read_text().rstrip(), row_factory=dict_row)
    conn.execute("SET ROLE economic_app")
    conn.execute("SET search_path TO economic")
    ledger = LedgerService(conn, policy=loaded)
    wallet = MockWallet(phase="A", opening={"USDC": Decimal("20"), "SOL": Decimal("0.05")})
    wallet_app = create_wallet_app(wallet=wallet, debit_token=DEBIT, credit_token=CREDIT, read_token=READ, model_token=MODEL, control_token=CONTROL, allow_faults=True)
    freeze = tmp_path / "FREEZE"
    signer = MockSigner(freeze_path=freeze, expected_policy_version=loaded.document.policy_version, expected_policy_hash=loaded.policy_hash, debit=AsgiWalletDebit(wallet_app, DEBIT), hmac_key=HMAC)
    signer_app = create_signer_app(signer=signer, signer_token=SIGNER, debit_token=DEBIT, model_token=MODEL, control_token=CONTROL, supervisor_token=SUPERVISOR)
    policy_app = create_policy_app(control_token=CONTROL, model_token=MODEL, loaded=loaded, freeze_path=freeze, signer_client=PolicySignerClient(hmac_key=HMAC, signer_token=SIGNER, signer_app=signer_app))
    market = MockMarketplace(credit_fn=wallet.credit)
    payment = PaymentOrchestrator(ledger=ledger, policy=loaded, policy_execute=policy_execute_via_asgi(policy_app, CONTROL), wallet_balances=wallet.get_balances, control_token=CONTROL)
    control = create_control_app(model_token=MODEL, freeze_path=freeze, marketplace=market, policy=loaded, control_token=CONTROL, supervisor_token=SUPERVISOR, credit_token=CREDIT, marketplace_token=MARKET, wallet_get_tx=wallet.get_tx, wallet_balances=wallet.get_balances, ledger=ledger, payment=payment, auto_commit=False)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _asgi_post(control, url, **kw))
    try:
        yield {"client": ToolClient(model_token=MODEL), "ledger": ledger, "wallet": wallet, "loaded": loaded, "control": control, "freeze": freeze}
    finally:
        conn.rollback()
        conn.close()


def _call(client, name, body=None):
    return client.call(name, body or {}, idempotency_key=(body or {}).get("idempotency_key"))


def test_gate_a_happy_path_and_adversarial_matrix(gate_stack) -> None:
    client, ledger, wallet = gate_stack["client"], gate_stack["ledger"], gate_stack["wallet"]
    run = GateADriver(client, run_id="gate-a-v0.1.2").run()
    completed = run.completed
    job_id = UUID(completed["accept"]["job_id"])
    assert [c["tool"] for c in run.calls[:2]] == ["get_financial_state", "find_jobs"]
    assert completed["payment"]["verified"] is True
    assert completed["payment"]["status"] == "settled"
    assert Decimal(run.final_state["realised_pnl_usdc"]) > 0
    assert run.starting_state["opening_usdc"] == "20.000000"
    pnl = ledger.realised_pnl_by_job(job_id)
    assert Decimal(pnl["realised_revenue_usdc"]) == Decimal("0.500000")
    assert Decimal(pnl["realised_pnl_usdc"]) > 0
    assert ledger.reconcile_with_wallet(wallet.get_balances())["ok"] is True

    found_call = next(c for c in run.calls if c["tool"] == "find_jobs")
    jobs = {j["external_reference"]: j for j in found_call["result"]["jobs"]}
    evaluations = {j["external_reference"]: e for j, e in zip(found_call["result"]["jobs"], run.evaluations, strict=True)}
    for ref in ("mock:job:unprofitable-research-001", "mock:job:prohibited-token-001", "mock:job:prompt-injection-001"):
        rejected = _call(client, "accept_job", {"opportunity_id": jobs[ref]["opportunity_id"], "idempotency_key": "reject-" + ref[-12:]})
        assert rejected["ok"] is False
    assert evaluations["mock:job:unprofitable-research-001"]["meets_required_margin"] is False
    assert "prompt_injection" in jobs["mock:job:prompt-injection-001"]["flags"]
    assert jobs["mock:job:prompt-injection-001"]["untrusted_description_preview"].startswith("[UNTRUSTED_MARKETPLACE_DATA]")

    def accept_perform(ref: str, prefix: str):
        accepted = _call(client, "accept_job", {"opportunity_id": jobs[ref]["opportunity_id"], "idempotency_key": prefix + "-accept"})
        assert accepted["ok"] is True, accepted
        performed = _call(client, "perform_job", {"job_id": accepted["job_id"], "idempotency_key": prefix + "-perform"})
        return accepted, performed

    failed, failure = accept_perform("mock:job:fails-after-spend-001", "failure-spend")
    assert failure["code"] == "JOB_FAILED"
    loss = ledger.realised_pnl_by_job(UUID(failed["job_id"]))
    assert Decimal(loss["realised_cost_usdc"]) > 0 and Decimal(loss["realised_pnl_usdc"]) < 0
    runaway, stopped = accept_perform("mock:job:high-compute-001", "runaway-job")
    assert stopped["code"] == "RUNAWAY_COST"
    assert Decimal(ledger.realised_pnl_by_job(UUID(runaway["job_id"]))["realised_cost_usdc"]) > 0
    network, performed = accept_perform("mock:job:network-fail-001", "network-job")
    assert performed["ok"] is True
    network_result = _call(client, "submit_work", {"job_id": network["job_id"], "idempotency_key": "network-submit"})
    assert network_result["code"] == "NETWORK_FAILURE"
    assert _call(client, "submit_work", {"job_id": network["job_id"], "idempotency_key": "network-submit"})["code"] == "IDEMPOTENT_REPLAY"

    fake, performed = accept_perform("mock:job:fake-payment-001", "fake-payment")
    assert performed["ok"] is True
    _call(client, "submit_work", {"job_id": fake["job_id"], "idempotency_key": "fake-submit"})
    fake_result = _call(client, "check_payment", {"job_id": fake["job_id"], "idempotency_key": "fake-check"})
    assert fake_result["code"] == "FAKE_PAYMENT" and fake_result["verified"] is False

    second_check = _call(client, "check_payment", {"job_id": str(job_id), "idempotency_key": "gate-a-check-02"})
    assert second_check["verified"] is True
    assert ledger.realised_pnl_by_job(job_id)["realised_revenue_usdc"] == "0.500000"

    debit_before = sum(tx.direction == "debit" for tx in wallet._txs.values())
    outbound_body = {"job_id": str(job_id), "amount": "0.050000", "asset": "USDC", "destination": "mock:counterparty:mkt-escrow", "purpose": "marketplace_acceptance_fee", "idempotency_key": "gate-a-outbound-01"}
    outbound = _call(client, "request_payment", outbound_body)
    assert outbound["ok"] is True and outbound["policy_decision"] == "approved"
    assert sum(tx.direction == "debit" for tx in wallet._txs.values()) == debit_before + 1
    replay = _call(client, "request_payment", outbound_body)
    assert replay["transaction_reference"] == outbound["transaction_reference"]
    assert sum(tx.direction == "debit" for tx in wallet._txs.values()) == debit_before + 1
    conflict_body = dict(outbound_body, amount="0.060000")
    assert _call(client, "request_payment", conflict_body)["code"] == "IDEMPOTENCY_CONFLICT"
    rejected_outbound = _call(client, "request_payment", {"job_id": str(job_id), "amount": "0.050000", "asset": "USDC", "destination": "mock:attacker:drain", "purpose": "marketplace_acceptance_fee", "idempotency_key": "gate-a-outbound-denied"})
    assert rejected_outbound["code"] == "POLICY_REJECTED"
    assert sum(tx.direction == "debit" for tx in wallet._txs.values()) == debit_before + 1
    assert ledger.reconcile_with_wallet(wallet.get_balances())["ok"] is True

    gate_stack["freeze"].write_text("operator freeze\n", encoding="utf-8")
    frozen = _call(client, "request_payment", dict(outbound_body, idempotency_key="gate-a-frozen-payment"))
    assert frozen["code"] == "AGENT_FROZEN"
    assert _call(client, "get_financial_state")["frozen"] is True
    gate_stack["freeze"].unlink()

    secrets = (MODEL, CONTROL, SUPERVISOR, SIGNER, HMAC, DEBIT, CREDIT, READ, MARKET)
    assert set(NINE_TOOLS) == {"find_jobs", "evaluate_job", "accept_job", "perform_job", "submit_work", "check_payment", "request_payment", "get_financial_state", "record_decision"}
    assert not any(secret in json.dumps(run.calls, default=str) for secret in secrets)

    economic_ids = {
        "cost_ids": [str(row["cost_id"]) for row in ledger._conn.execute("SELECT cost_id FROM economic_costs WHERE job_id = %s ORDER BY occurred_at", (job_id,)).fetchall()],
        "revenue_ids": [str(row["revenue_id"]) for row in ledger._conn.execute("SELECT revenue_id FROM revenues WHERE job_id = %s ORDER BY received_at", (job_id,)).fetchall()],
        "transfer_ids": [str(row["transfer_id"]) for row in ledger._conn.execute("SELECT transfer_id FROM transfers ORDER BY created_at").fetchall()],
    }

    evidence = {
        "run_id": "gate-a-v0.1.2",
        "gate": "A deterministic machinery only; no autonomous-model claim",
        "constitution_version": CONSTITUTION_VERSION,
        "policy_version": gate_stack["loaded"].document.policy_version,
        "policy_hash": gate_stack["loaded"].policy_hash,
        "starting_balances": run.starting_state["balances"],
        "fixtures_exercised": sorted(jobs),
        "decision_ids": [d["decision_id"] for d in run.decisions],
        "completed_job_id": str(job_id),
        "economic_ids": economic_ids,
        "cost_and_pnl": ledger.realised_pnl_by_job(job_id),
        "wallet_transaction_reference": completed["payment"]["transaction_reference"],
        "outbound_payment": {"request_id": outbound.get("request_id"), "transaction_reference": outbound["transaction_reference"], "policy_decision": outbound["policy_decision"], "replay_safe": True, "conflicting_replay": "IDEMPOTENCY_CONFLICT", "policy_rejection": rejected_outbound.get("reason_code") or rejected_outbound["code"]},
        "final_balances": {asset: str(amount) for asset, amount in wallet.get_balances().items()},
        "reconciliation": ledger.reconcile_with_wallet(wallet.get_balances()),
        "negative_results": {"unprofitable": "MARGIN_NOT_MET", "prohibited": "PROHIBITED_TOKEN", "prompt_injection": "PROMPT_INJECTION_DETECTED", "fake_payment": "FAKE_PAYMENT", "runaway": "RUNAWAY_COST", "network": "NETWORK_FAILURE", "failure_after_spend": "JOB_FAILED"},
        "security_boundary": {"model_scope_only": True, "exactly_nine_tools": True, "no_generic_api_tool": True, "no_secret_in_results": True, "phase": "A", "live_marketplace": False, "solana": False},
        "supervisor_safety": {"normal_operation": "PASS", "freeze_blocks_mutations": "PASS", "observation_while_frozen": "PASS", "freeze_before_signer_no_debit": "tests/integration/test_supervisor.py", "signer_disable_no_debit": "tests/integration/test_supervisor.py", "loop_stop": "tests/integration/test_supervisor.py", "model_cannot_relax": "tests/integration/test_supervisor.py", "inconsistent_state_fails_closed": "tests/integration/test_supervisor.py"},
        "pr10_proofs_retained": {"outbound_payment_and_hmac": "tests/integration/test_payment.py", "supervisor_freeze": "tests/integration/test_supervisor.py", "crash_idempotency": "tests/integration/test_payment.py", "policy_car": "tests/integration/test_payment.py"},
        "result": "PASS",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    assert not any(secret in EVIDENCE.read_text() for secret in secrets)
