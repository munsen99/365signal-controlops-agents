"""Independent supervisor (M0 PR9). Auth, freeze, signer, loop, races, audit."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from aea.config import load_policy
from aea.control.app import create_app as create_control_app
from aea.ledger.errors import LedgerError
from aea.ledger.models import CostCreate, OpportunityCreate, JobAccept
from aea.ledger.service import LedgerService
from aea.marketplace.mock import MockMarketplace
from aea.policy.service import create_app as create_policy_app
from aea.signer.backend import ApprovedRequest, canonical_approved_hash, compute_request_hmac
from aea.signer.mock import MockSigner
from aea.signer.service import AsgiWalletDebit, create_app as create_signer_app
from aea.supervisor.service import CallableSignerAdmin, create_app
from aea.supervisor.state import MemorySupervisorStore, PostgresSupervisorStore, SupervisorState
from aea.wallet.mock import MockWallet
from aea.wallet.service import create_app as create_wallet_app

NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)

SUPERVISOR = "supervisor-token-pr9"
MODEL = "model-token-pr9"
CONTROL = "control-token-pr9"
SIGNER = "signer-token-pr9"
HMAC_KEY = "signer-request-hmac-key-pr9-0001"
DEBIT = "wallet-debit-token-pr9"
CREDIT = "wallet-credit-token-pr9"
READ = "wallet-read-token-pr9"
MARKET = "marketplace-token-pr9"
PROFITABLE = "mock:job:profitable-summary-001"

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


@pytest.fixture
def freeze_dir(tmp_path: Path) -> Path:
    path = tmp_path / "freeze"
    path.mkdir()
    return path


@pytest.fixture
def loaded():
    return load_policy()


@pytest.fixture
def store() -> MemorySupervisorStore:
    return MemorySupervisorStore()


@pytest.fixture
def wallet() -> MockWallet:
    return MockWallet(phase="A", opening={"USDC": Decimal("20"), "SOL": Decimal("0.05")})


@pytest.fixture
def wallet_app(wallet: MockWallet):
    return create_wallet_app(
        wallet=wallet,
        debit_token=DEBIT,
        credit_token=CREDIT,
        read_token=READ,
        model_token=MODEL,
        control_token=CONTROL,
        allow_faults=True,
    )


@pytest.fixture
def signer_stack(wallet, wallet_app, freeze_dir, loaded, store):
    debit = AsgiWalletDebit(wallet_app, DEBIT)

    def read_db_frozen():
        row = store.load()
        if row is None:
            return None
        return bool(row.frozen)

    def read_db_signer():
        row = store.load()
        if row is None:
            return None
        return bool(row.signer_enabled)

    signer = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=debit,
        hmac_key=HMAC_KEY,
        db_frozen_reader=read_db_frozen,
        db_signer_enabled_reader=read_db_signer,
    )
    signer_app = create_signer_app(
        signer=signer,
        signer_token=SIGNER,
        debit_token=DEBIT,
        model_token=MODEL,
        control_token=CONTROL,
        supervisor_token=SUPERVISOR,
    )
    admin = CallableSignerAdmin(
        disable=lambda: signer.set_enabled(False),
        enable=lambda: signer.set_enabled(True),
    )
    sup = create_app(
        supervisor_token=SUPERVISOR,
        freeze_path=freeze_dir / "FREEZE",
        store=store,
        model_token=MODEL,
        control_token=CONTROL,
        signer_token=SIGNER,
        marketplace_token=MARKET,
        wallet_read_token=READ,
        signer_admin=admin,
    )
    return SimpleNamespace(
        supervisor=sup,
        signer=signer,
        signer_app=signer_app,
        wallet=wallet,
        freeze_dir=freeze_dir,
        loaded=loaded,
        store=store,
    )


@pytest.fixture
def control_app(freeze_dir, wallet, store):
    def state_reader():
        row = store.load()
        if row is None:
            return None
        return {
            "frozen": row.frozen,
            "signer_enabled": row.signer_enabled,
            "loop_enabled": row.loop_enabled,
        }

    return create_control_app(
        model_token=MODEL,
        freeze_path=freeze_dir / "FREEZE",
        marketplace=MockMarketplace(credit_fn=wallet.credit),
        control_token=CONTROL,
        supervisor_token=SUPERVISOR,
        marketplace_token=MARKET,
        wallet_get_tx=wallet.get_tx,
        state_reader=state_reader,
    )


def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://svc") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mut(**overrides) -> dict:
    body = {
        "reason": "operator safety action",
        "actor": "operator",
        "source": "supervisor",
        "idempotency_key": f"sup-{uuid4().hex[:12]}",
    }
    body.update(overrides)
    return body


def _assert_no_secrets(response: httpx.Response) -> None:
    blob = response.text
    for needle in (
        SUPERVISOR,
        MODEL,
        CONTROL,
        SIGNER,
        HMAC_KEY,
        DEBIT,
        CREDIT,
        READ,
        MARKET,
        "AEA_SUPERVISOR_TOKEN",
        "AEA_SIGNER_HMAC_KEY",
        "AEA_WALLET_DEBIT_TOKEN",
        "private_key",
        "seed_phrase",
    ):
        assert needle not in blob


def _approved(loaded, **overrides) -> ApprovedRequest:
    body = {
        "request_id": str(uuid4()),
        "amount": "0.050000",
        "asset": "USDC",
        "destination": "mock:counterparty:mkt-escrow",
        "purpose": "marketplace_acceptance_fee",
        "job_id": str(uuid4()),
        "policy_version": loaded.document.policy_version,
        "policy_hash": loaded.policy_hash,
        "approved_amount": "0.050000",
        "approved_at": NOW.isoformat(),
        "correlation_id": str(uuid4()),
    }
    body.update(overrides)
    return ApprovedRequest.model_validate(body)


def _sign_body(approved: ApprovedRequest) -> dict:
    canonical = canonical_approved_hash(approved)
    return {
        "approved_request": approved.model_dump(mode="json"),
        "canonical_hash": canonical,
        "policy_version": approved.policy_version,
        "request_hmac": compute_request_hmac(
            HMAC_KEY,
            approved_request=approved,
            canonical_hash=canonical,
            policy_version=approved.policy_version,
        ),
    }


def _policy_body(loaded, **overrides) -> dict:
    payload = {
        "amount": "0.050000",
        "asset": "USDC",
        "destination": "mock:counterparty:mkt-escrow",
        "destination_class": "marketplace_escrow",
        "destination_allowed": True,
        "job_id": str(uuid4()),
        "purpose": "marketplace_acceptance_fee",
        "daily_spend_usdc": "0.000000",
        "outstanding_exposure_usdc": "0.000000",
        "wallet_balances": {"USDC": "20.000000", "SOL": "0.050000"},
        "policy_version": loaded.document.policy_version,
        "policy_hash": loaded.policy_hash,
        "frozen": False,
        "signer_enabled": True,
        "wallet_phase": "A",
        "correlation_id": str(uuid4()),
    }
    payload.update(overrides)
    return payload


def _accept_profitable(control_app) -> str:
    found = _request(
        control_app, "POST", "/v1/tools/find_jobs", json={"limit": 20}, headers=_auth(MODEL)
    ).json()
    oid = next(j["opportunity_id"] for j in found["jobs"] if j["external_reference"] == PROFITABLE)
    job = _request(
        control_app,
        "POST",
        "/v1/tools/accept_job",
        json={"opportunity_id": oid, "idempotency_key": f"acc-{uuid4().hex[:10]}"},
        headers=_auth(MODEL),
    ).json()
    assert job["ok"] is True
    return job["job_id"]


# --- health / constructor ---


def test_health_unauthenticated(signer_stack) -> None:
    response = _request(signer_stack.supervisor, "GET", "/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["frozen"] is False
    assert body["signer_enabled"] is True
    assert body["loop_enabled"] is True
    _assert_no_secrets(response)
    status = _request(signer_stack.supervisor, "GET", "/v1/status")
    assert status.status_code == 200
    assert status.json()["frozen"] is False


def test_supervisor_rejects_spend_secrets(freeze_dir) -> None:
    with pytest.raises(ValueError, match="must not hold"):
        create_app(
            supervisor_token=SUPERVISOR,
            freeze_path=freeze_dir / "FREEZE",
            hmac_key=HMAC_KEY,  # type: ignore[call-arg]
        )
    with pytest.raises(ValueError, match="must not hold"):
        create_app(
            supervisor_token=SUPERVISOR,
            freeze_path=freeze_dir / "FREEZE",
            debit_token=DEBIT,  # type: ignore[call-arg]
        )


# --- auth matrix ---


@pytest.mark.parametrize(
    "path",
    [
        "/v1/admin/freeze-spend",
        "/v1/admin/unfreeze",
        "/v1/admin/disable-signer",
        "/v1/admin/enable-signer",
        "/v1/admin/stop-agent",
        "/v1/admin/permit-loop",
        "/v1/admin/incidents",
    ],
)
def test_model_and_foreign_tokens_cannot_mutate(signer_stack, path) -> None:
    body = _mut()
    if path.endswith("unfreeze"):
        body["confirm"] = "UNFREEZE"
    if path.endswith("enable-signer"):
        body["confirm"] = "ENABLE_SIGNER"
    if path.endswith("permit-loop"):
        body["confirm"] = "PERMIT_LOOP"
    if path.endswith("incidents"):
        body = {
            "severity": "warn",
            "kind": "test",
            "message": "nope",
            "idempotency_key": "incident01",
        }
    for token, status in (
        (None, 401),
        (MODEL, 403),
        (CONTROL, 403),
        (SIGNER, 403),
        (MARKET, 403),
        (READ, 403),
        (HMAC_KEY, 401),
        (DEBIT, 401),
        (CREDIT, 401),
        ("wrong-token", 401),
    ):
        headers = {} if token is None else _auth(token)
        response = _request(signer_stack.supervisor, "POST", path, json=body, headers=headers)
        assert response.status_code == status, (path, token, response.status_code, response.text)
        assert response.json()["ok"] is False
        _assert_no_secrets(response)
    health = _request(signer_stack.supervisor, "GET", "/health").json()
    assert health["frozen"] is False
    assert health["signer_enabled"] is True
    assert health["loop_enabled"] is True


def test_force_true_and_extra_fields_rejected(signer_stack) -> None:
    response = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(force=True),
        headers=_auth(SUPERVISOR),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    extra = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(bypass=True),
        headers=_auth(SUPERVISOR),
    )
    assert extra.status_code == 400
    unfreeze = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/unfreeze",
        json=_mut(confirm="unfreeze"),
        headers=_auth(SUPERVISOR),
    )
    assert unfreeze.status_code == 400
    missing = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/unfreeze",
        json=_mut(),
        headers=_auth(SUPERVISOR),
    )
    assert missing.status_code == 400
    freeze_confirm = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(confirm="UNFREEZE"),
        headers=_auth(SUPERVISOR),
    )
    assert freeze_confirm.status_code == 400
    health = _request(signer_stack.supervisor, "GET", "/health").json()
    assert health["frozen"] is False
    assert health["signer_enabled"] is True
    assert health["loop_enabled"] is True


@pytest.mark.parametrize(
    "path,required",
    [
        ("/v1/admin/unfreeze", "UNFREEZE"),
        ("/v1/admin/enable-signer", "ENABLE_SIGNER"),
        ("/v1/admin/permit-loop", "PERMIT_LOOP"),
    ],
)
def test_relaxing_requires_action_specific_confirm(signer_stack, path, required) -> None:
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(reason="restrict freeze"),
        headers=_auth(SUPERVISOR),
    )
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/disable-signer",
        json=_mut(reason="restrict signer"),
        headers=_auth(SUPERVISOR),
    )
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/stop-agent",
        json=_mut(reason="restrict loop"),
        headers=_auth(SUPERVISOR),
    )
    before = _request(signer_stack.supervisor, "GET", "/health").json()
    assert before["frozen"] is True
    assert before["signer_enabled"] is False
    assert before["loop_enabled"] is False

    others = {"UNFREEZE", "ENABLE_SIGNER", "PERMIT_LOOP"} - {required}
    cases = [
        _mut(),
        _mut(confirm=required.lower()),
        _mut(confirm=next(iter(others))),
        _mut(confirm=True),
        _mut(confirm=["UNFREEZE"]),
        _mut(confirm=required, extra="nope"),
        _mut(confirm=required, force=True),
        {**_mut(confirm=required), "confirmation": required},
    ]
    for body in cases:
        response = _request(
            signer_stack.supervisor,
            "POST",
            path,
            json=body,
            headers=_auth(SUPERVISOR),
        )
        assert response.status_code == 400, (path, body, response.text)
        assert response.json()["code"] == "VALIDATION_ERROR"
        after = _request(signer_stack.supervisor, "GET", "/health").json()
        assert after["frozen"] is True
        assert after["signer_enabled"] is False
        assert after["loop_enabled"] is False
        assert (signer_stack.freeze_dir / "FREEZE").is_file()
        assert signer_stack.signer.signer_enabled is False


# --- transitions ---


def test_freeze_unfreeze_idempotent_and_conflict(signer_stack) -> None:
    key = "freeze-idemp-01"
    first = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(idempotency_key=key, reason="halt spend"),
        headers=_auth(SUPERVISOR),
    )
    assert first.status_code == 200
    assert first.json()["frozen"] is True
    assert first.json()["previous"]["frozen"] is False
    assert first.json()["new"]["frozen"] is True
    _assert_no_secrets(first)
    assert (signer_stack.freeze_dir / "FREEZE").is_file()
    replay = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(idempotency_key=key, reason="halt spend"),
        headers=_auth(SUPERVISOR),
    )
    assert replay.json()["code"] == "IDEMPOTENT_REPLAY"
    conflict = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(idempotency_key=key, reason="different reason text"),
        headers=_auth(SUPERVISOR),
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    denied = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/unfreeze",
        json=_mut(confirm="UNFREEZE"),
        headers=_auth(MODEL),
    )
    assert denied.status_code == 403
    assert (signer_stack.freeze_dir / "FREEZE").is_file()
    ok = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/unfreeze",
        json=_mut(confirm="UNFREEZE", reason="resume after review"),
        headers=_auth(SUPERVISOR),
    )
    assert ok.status_code == 200
    assert ok.json()["frozen"] is False
    assert not (signer_stack.freeze_dir / "FREEZE").exists()


def test_signer_disable_enable(signer_stack) -> None:
    off = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/disable-signer",
        json=_mut(reason="disable spend path"),
        headers=_auth(SUPERVISOR),
    )
    assert off.json()["signer_enabled"] is False
    assert signer_stack.signer.signer_enabled is False
    again = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/disable-signer",
        json=_mut(reason="disable spend path", idempotency_key=off.json().get("correlation_id", "xxxxxxxx")[:8] + "replay01"),
        headers=_auth(SUPERVISOR),
    )
    assert again.json()["signer_enabled"] is False
    on = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/enable-signer",
        json=_mut(reason="re-enable after review", confirm="ENABLE_SIGNER"),
        headers=_auth(SUPERVISOR),
    )
    assert on.json()["signer_enabled"] is True
    assert signer_stack.signer.signer_enabled is True


def test_loop_stop_permit(signer_stack) -> None:
    stop = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/stop-agent",
        json=_mut(reason="stop autonomous loop"),
        headers=_auth(SUPERVISOR),
    )
    assert stop.json()["loop_enabled"] is False
    permit = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/permit-loop",
        json=_mut(reason="permit loop after review", confirm="PERMIT_LOOP"),
        headers=_auth(SUPERVISOR),
    )
    assert permit.json()["loop_enabled"] is True


def test_incidents_write(signer_stack) -> None:
    response = _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/incidents",
        json={
            "severity": "warn",
            "kind": "UNUSUAL_DESTINATION",
            "message": "destination not classified",
            "idempotency_key": "incident-01",
            "reason": "operator note",
        },
        headers=_auth(SUPERVISOR),
    )
    assert response.status_code == 200
    assert response.json()["kind"] == "UNUSUAL_DESTINATION"
    assert signer_stack.store._incidents
    _assert_no_secrets(response)


# --- freeze propagation to control ---


def test_freeze_blocks_mutating_tools_observe_remain(signer_stack, control_app) -> None:
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(reason="halt all spend"),
        headers=_auth(SUPERVISOR),
    )
    frozen_eval = _request(
        control_app,
        "POST",
        "/v1/tools/evaluate_job",
        json={"opportunity_id": str(uuid4()), "idempotency_key": "eval-frz-0001"},
        headers=_auth(MODEL),
    ).json()
    assert frozen_eval["code"] == "AGENT_FROZEN"
    state = _request(
        control_app, "POST", "/v1/tools/get_financial_state", json={}, headers=_auth(MODEL)
    ).json()
    assert state["ok"] is True
    assert state["frozen"] is True
    assert state["signer_enabled"] is True
    assert state["loop_enabled"] is True
    found = _request(
        control_app, "POST", "/v1/tools/find_jobs", json={}, headers=_auth(MODEL)
    )
    assert found.status_code == 200
    assert found.json().get("ok") is True or found.json().get("code") == "OK"
    rec = _request(
        control_app,
        "POST",
        "/v1/tools/record_decision",
        json={
            "decision_type": "abort",
            "decision": "abort",
            "reasoning_summary": "frozen",
            "idempotency_key": "dec-frz-0001",
        },
        headers=_auth(MODEL),
    )
    assert rec.status_code == 200


def test_loop_stopped_blocks_mutations_not_observe(signer_stack, control_app) -> None:
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/stop-agent",
        json=_mut(reason="stop loop"),
        headers=_auth(SUPERVISOR),
    )
    stopped = _request(
        control_app,
        "POST",
        "/v1/tools/evaluate_job",
        json={"opportunity_id": str(uuid4()), "idempotency_key": "eval-stop-01"},
        headers=_auth(MODEL),
    ).json()
    assert stopped["code"] == "LOOP_STOPPED"
    state = _request(
        control_app, "POST", "/v1/tools/get_financial_state", json={}, headers=_auth(MODEL)
    ).json()
    assert state["loop_enabled"] is False
    assert state["frozen"] is False
    found = _request(
        control_app, "POST", "/v1/tools/find_jobs", json={}, headers=_auth(MODEL)
    )
    assert found.status_code == 200


def test_signer_disabled_surfaces_on_request_payment(signer_stack, control_app) -> None:
    job_id = _accept_profitable(control_app)
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/disable-signer",
        json=_mut(reason="disable signer"),
        headers=_auth(SUPERVISOR),
    )
    pay = _request(
        control_app,
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job_id,
            "idempotency_key": "pay-dis-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert pay["code"] == "SIGNER_DISABLED"
    state = _request(
        control_app, "POST", "/v1/tools/get_financial_state", json={}, headers=_auth(MODEL)
    ).json()
    assert state["signer_enabled"] is False


def test_unreadable_supervisor_state_fail_closed(freeze_dir, wallet) -> None:
    def boom():
        raise RuntimeError("db down")

    app = create_control_app(
        model_token=MODEL,
        freeze_path=freeze_dir / "FREEZE",
        marketplace=MockMarketplace(credit_fn=wallet.credit),
        state_reader=boom,
    )
    frozen = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={"opportunity_id": str(uuid4()), "idempotency_key": "eval-unr-01"},
        headers=_auth(MODEL),
    ).json()
    assert frozen["code"] == "AGENT_FROZEN"
    state = _request(app, "POST", "/v1/tools/get_financial_state", json={}, headers=_auth(MODEL)).json()
    assert state["frozen"] is True
    assert state["signer_enabled"] is False
    assert state["loop_enabled"] is False


# --- job-progress freeze races ---


def test_freeze_while_job_in_progress(signer_stack, control_app) -> None:
    job_id = _accept_profitable(control_app)
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(reason="mid-job freeze"),
        headers=_auth(SUPERVISOR),
    )
    performed = _request(
        control_app,
        "POST",
        "/v1/tools/perform_job",
        json={"job_id": job_id, "idempotency_key": "perf-frz-0001"},
        headers=_auth(MODEL),
    ).json()
    assert performed["code"] == "AGENT_FROZEN"


def test_freeze_between_perform_and_submit(signer_stack, control_app) -> None:
    job_id = _accept_profitable(control_app)
    performed = _request(
        control_app,
        "POST",
        "/v1/tools/perform_job",
        json={"job_id": job_id, "idempotency_key": "perf-ok-0001"},
        headers=_auth(MODEL),
    ).json()
    assert performed["ok"] is True
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(reason="freeze before submit"),
        headers=_auth(SUPERVISOR),
    )
    submitted = _request(
        control_app,
        "POST",
        "/v1/tools/submit_work",
        json={"job_id": job_id, "idempotency_key": "sub-frz-0001"},
        headers=_auth(MODEL),
    ).json()
    assert submitted["code"] == "AGENT_FROZEN"


def test_freeze_while_payment_verification_pending(signer_stack, control_app) -> None:
    job_id = _accept_profitable(control_app)
    _request(
        control_app,
        "POST",
        "/v1/tools/perform_job",
        json={"job_id": job_id, "idempotency_key": "perf-pay-0001"},
        headers=_auth(MODEL),
    )
    submitted = _request(
        control_app,
        "POST",
        "/v1/tools/submit_work",
        json={"job_id": job_id, "idempotency_key": "sub-pay-0001"},
        headers=_auth(MODEL),
    ).json()
    assert submitted["ok"] is True
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(reason="freeze during verify"),
        headers=_auth(SUPERVISOR),
    )
    check = _request(
        control_app,
        "POST",
        "/v1/tools/check_payment",
        json={"job_id": job_id, "idempotency_key": "chk-frz-0001"},
        headers=_auth(MODEL),
    ).json()
    assert check["code"] == "AGENT_FROZEN"


# --- critical payment race ---


def test_policy_approval_then_freeze_then_signer_rejects(signer_stack, freeze_dir, loaded) -> None:
    policy = create_policy_app(
        control_token=CONTROL,
        model_token=MODEL,
        loaded=loaded,
        freeze_path=freeze_dir / "FREEZE",
        now=NOW,
        db_frozen_reader=lambda: bool(signer_stack.store.load().frozen)
        if signer_stack.store.load() is not None
        else None,
    )
    approved_http = _request(
        policy,
        "POST",
        "/v1/evaluate",
        json=_policy_body(loaded),
        headers=_auth(CONTROL),
    ).json()
    assert approved_http["decision"] == "approved"
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(reason="freeze after policy approval"),
        headers=_auth(SUPERVISOR),
    )
    sign = _request(
        signer_stack.signer_app,
        "POST",
        "/v1/sign",
        json=_sign_body(_approved(loaded)),
        headers=_auth(SIGNER),
    )
    assert sign.json()["code"] == "AGENT_FROZEN"
    assert signer_stack.wallet.get_balances()["USDC"] == Decimal("20")
    _assert_no_secrets(sign)


def test_signer_disabled_after_approval_before_debit(signer_stack, loaded) -> None:
    approved = _approved(loaded)
    body = _sign_body(approved)
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/disable-signer",
        json=_mut(reason="disable after approval"),
        headers=_auth(SUPERVISOR),
    )
    sign = _request(
        signer_stack.signer_app,
        "POST",
        "/v1/sign",
        json=body,
        headers=_auth(SIGNER),
    )
    assert sign.json()["code"] == "SIGNER_DISABLED"
    assert signer_stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_unreadable_freeze_dir_during_sign(signer_stack, loaded) -> None:
    freeze_dir = signer_stack.freeze_dir
    os.chmod(freeze_dir, 0)
    try:
        sign = _request(
            signer_stack.signer_app,
            "POST",
            "/v1/sign",
            json=_sign_body(_approved(loaded)),
            headers=_auth(SIGNER),
        )
        assert sign.json()["code"] == "AGENT_FROZEN"
        assert signer_stack.wallet.get_balances()["USDC"] == Decimal("20")
    finally:
        os.chmod(freeze_dir, 0o700)


def test_file_db_disagreement_fail_closed(signer_stack, loaded) -> None:
    (signer_stack.freeze_dir / "FREEZE").write_text("1\n", encoding="utf-8")
    # DB still unfrozen
    health = _request(signer_stack.supervisor, "GET", "/health").json()
    assert health["frozen"] is True
    sign = _request(
        signer_stack.signer_app,
        "POST",
        "/v1/sign",
        json=_sign_body(_approved(loaded)),
        headers=_auth(SIGNER),
    )
    assert sign.json()["code"] == "AGENT_FROZEN"
    assert signer_stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_db_frozen_without_file_fail_closed(signer_stack, loaded) -> None:
    signer_stack.store.save(
        SupervisorState(frozen=True, signer_enabled=True, loop_enabled=True, updated_by="test"),
        actor="test",
    )
    sign = _request(
        signer_stack.signer_app,
        "POST",
        "/v1/sign",
        json=_sign_body(_approved(loaded)),
        headers=_auth(SIGNER),
    )
    assert sign.json()["code"] == "AGENT_FROZEN"
    assert signer_stack.wallet.get_balances()["USDC"] == Decimal("20")


_RELAXING_ROUTES = (
    ("/v1/admin/unfreeze", "UNFREEZE", "frozen"),
    ("/v1/admin/enable-signer", "ENABLE_SIGNER", "signer_enabled"),
    ("/v1/admin/permit-loop", "PERMIT_LOOP", "loop_enabled"),
)


def test_missing_db_row_fail_closed_on_relaxing(freeze_dir) -> None:
    store = MemorySupervisorStore(missing=True)
    app = create_app(
        supervisor_token=SUPERVISOR,
        freeze_path=freeze_dir / "FREEZE",
        store=store,
    )
    for path, confirm, _flag in _RELAXING_ROUTES:
        response = _request(
            app,
            "POST",
            path,
            json=_mut(confirm=confirm, reason="cannot relax missing state"),
            headers=_auth(SUPERVISOR),
        )
        assert response.json()["ok"] is False, path
        assert response.json()["code"] == "AGENT_FROZEN", path
        assert store.missing is True


def test_unreadable_db_fail_closed_on_relaxing(freeze_dir, signer_stack) -> None:
    class BoomStore(MemorySupervisorStore):
        def load(self):  # type: ignore[override]
            raise RuntimeError("db down")

    store = BoomStore()
    store.save(
        SupervisorState(frozen=True, signer_enabled=False, loop_enabled=False),
        actor="setup",
    )
    app = create_app(
        supervisor_token=SUPERVISOR,
        freeze_path=freeze_dir / "FREEZE",
        store=store,
        signer_admin=CallableSignerAdmin(
            disable=lambda: None,
            enable=lambda: signer_stack.signer.set_enabled(True),
        ),
    )
    signer_stack.signer.set_enabled(False)
    for path, confirm, _flag in _RELAXING_ROUTES:
        response = _request(
            app,
            "POST",
            path,
            json=_mut(confirm=confirm, reason="cannot relax unreadable"),
            headers=_auth(SUPERVISOR),
        )
        assert response.json()["code"] == "AGENT_FROZEN", path
    assert signer_stack.signer.signer_enabled is False


def test_malformed_db_fail_closed_on_relaxing(freeze_dir) -> None:
    class MalformedStore(MemorySupervisorStore):
        def load(self):  # type: ignore[override]
            return SimpleNamespace(
                frozen="yes",
                signer_enabled=True,
                loop_enabled=True,
                updated_at=None,
                updated_by="broken",
            )

    store = MalformedStore()
    app = create_app(
        supervisor_token=SUPERVISOR,
        freeze_path=freeze_dir / "FREEZE",
        store=store,
    )
    for path, confirm, _flag in _RELAXING_ROUTES:
        response = _request(
            app,
            "POST",
            path,
            json=_mut(confirm=confirm, reason="cannot relax malformed"),
            headers=_auth(SUPERVISOR),
        )
        assert response.json()["ok"] is False, path
        assert response.json()["code"] == "AGENT_FROZEN", path
        assert response.json()["detail"] == "malformed_db"


def test_inconsistent_file_db_refuses_relaxing(signer_stack) -> None:
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/disable-signer",
        json=_mut(reason="restrict signer"),
        headers=_auth(SUPERVISOR),
    )
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/stop-agent",
        json=_mut(reason="restrict loop"),
        headers=_auth(SUPERVISOR),
    )
    (signer_stack.freeze_dir / "FREEZE").write_text("1\n", encoding="utf-8")
    before = _request(signer_stack.supervisor, "GET", "/health").json()
    assert before["frozen"] is True
    assert before["signer_enabled"] is False
    assert before["loop_enabled"] is False
    for path, confirm, flag in _RELAXING_ROUTES:
        response = _request(
            signer_stack.supervisor,
            "POST",
            path,
            json=_mut(confirm=confirm, reason="cannot relax inconsistent"),
            headers=_auth(SUPERVISOR),
        )
        assert response.status_code == 200, path
        assert response.json()["ok"] is False, path
        assert response.json()["code"] == "AGENT_FROZEN", path
        assert response.json()["detail"] == "inconsistent", path
    after = _request(signer_stack.supervisor, "GET", "/health").json()
    assert after["frozen"] is True
    assert after["signer_enabled"] is False
    assert after["loop_enabled"] is False
    assert signer_stack.signer.signer_enabled is False
    assert (signer_stack.freeze_dir / "FREEZE").is_file()


def test_unreadable_freeze_dir_refuses_unfreeze(signer_stack) -> None:
    _request(
        signer_stack.supervisor,
        "POST",
        "/v1/admin/freeze-spend",
        json=_mut(reason="freeze then unread"),
        headers=_auth(SUPERVISOR),
    )
    freeze_dir = signer_stack.freeze_dir
    os.chmod(freeze_dir, 0)
    try:
        response = _request(
            signer_stack.supervisor,
            "POST",
            "/v1/admin/unfreeze",
            json=_mut(confirm="UNFREEZE", reason="cannot unfreeze unreadable dir"),
            headers=_auth(SUPERVISOR),
        )
        assert response.json()["ok"] is False
        assert response.json()["code"] == "AGENT_FROZEN"
    finally:
        os.chmod(freeze_dir, 0o700)
    health = _request(signer_stack.supervisor, "GET", "/health").json()
    assert health["frozen"] is True
    assert (freeze_dir / "FREEZE").is_file()
    assert signer_stack.store.load().frozen is True


# --- postgres persistence and privileges ---


@pytest.mark.skipif(not _postgres_up(), reason="controlops Postgres is not reachable")
def test_postgres_supervisor_persistence_privileges_and_costs(freeze_dir, loaded) -> None:
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="controlops",
        user="controlops_admin",
        password=ADMIN_PW.read_text(encoding="utf-8").rstrip("\n"),
    )
    conn.row_factory = dict_row
    try:
        conn.execute("SET ROLE economic_supervisor")
        conn.execute("SET search_path TO economic")
        store = PostgresSupervisorStore(conn)
        app = create_app(
            supervisor_token=SUPERVISOR,
            freeze_path=freeze_dir / "FREEZE",
            store=store,
            model_token=MODEL,
        )
        freeze = _request(
            app,
            "POST",
            "/v1/admin/freeze-spend",
            json=_mut(reason="persist freeze"),
            headers=_auth(SUPERVISOR),
        )
        assert freeze.json()["frozen"] is True
        row = conn.execute(
            "SELECT frozen, signer_enabled, loop_enabled, updated_by FROM supervisor_state WHERE singleton"
        ).fetchone()
        assert row["frozen"] is True
        assert row["updated_by"] == "operator"
        audit = conn.execute(
            """
            SELECT event_type, payload FROM audit_events
             WHERE event_type = 'supervisor.freeze-spend'
             ORDER BY created_at DESC LIMIT 1
            """
        ).fetchone()
        assert audit is not None
        payload = audit["payload"]
        assert payload["previous"]["frozen"] is False
        assert payload["new"]["frozen"] is True
        assert payload["reason"] == "persist freeze"
        assert payload["actor"] == "operator"
        assert "token" not in str(payload).lower() or "idempotency" in str(payload)
        for needle in (SUPERVISOR, MODEL, HMAC_KEY, DEBIT):
            assert needle not in str(payload)

        conn.execute("RESET ROLE")
        app_priv = conn.execute(
            "SELECT has_table_privilege('economic_app', 'economic.supervisor_state', 'UPDATE') AS allowed"
        ).fetchone()
        assert app_priv["allowed"] is False
        sup_jobs = conn.execute(
            "SELECT has_table_privilege('economic_supervisor', 'economic.jobs', 'UPDATE') AS allowed"
        ).fetchone()
        assert sup_jobs["allowed"] is False
        sup_state = conn.execute(
            "SELECT has_table_privilege('economic_supervisor', 'economic.supervisor_state', 'UPDATE') AS allowed"
        ).fetchone()
        assert sup_state["allowed"] is True

        conn.execute("SET ROLE economic_app")
        conn.execute("SET search_path TO economic")
        ledger = LedgerService(conn, policy=loaded)
        flags = ledger.supervisor_flags()
        assert flags["frozen"] is True
        opp = ledger.record_opportunity(
            OpportunityCreate.model_validate(
                {
                    "source": "mock",
                    "external_reference": f"mock:job:pr9-{uuid4().hex}",
                    "description_hash": "a" * 64,
                    "expected_revenue": "0.500000",
                    "expected_cost": "0.050000",
                    "idempotency_key": f"opp-{uuid4().hex[:12]}",
                }
            )
        )
        with pytest.raises(LedgerError) as exc:
            ledger.accept_job(
                JobAccept.model_validate(
                    {
                        "opportunity_id": str(opp["opportunity_id"]),
                        "expected_revenue": "0.500000",
                        "idempotency_key": f"acc-{uuid4().hex[:12]}",
                    }
                )
            )
        assert exc.value.code == "AGENT_FROZEN"

        conn.execute("RESET ROLE")
        conn.execute("SET ROLE economic_supervisor")
        conn.execute("SET search_path TO economic")
        unfreeze = _request(
            app,
            "POST",
            "/v1/admin/unfreeze",
            json=_mut(confirm="UNFREEZE", reason="clear after privilege test"),
            headers=_auth(SUPERVISOR),
        )
        assert unfreeze.json()["frozen"] is False

        conn.execute("RESET ROLE")
        conn.execute("SET ROLE economic_app")
        conn.execute("SET search_path TO economic")
        job = ledger.accept_job(
            JobAccept.model_validate(
                {
                    "opportunity_id": str(opp["opportunity_id"]),
                    "expected_revenue": "0.500000",
                    "idempotency_key": f"acc-{uuid4().hex[:12]}",
                }
            )
        )
        before_costs = conn.execute("SELECT count(*) AS n FROM economic_costs").fetchone()
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
        assert cost["replay"] is False
        after = conn.execute("SELECT frozen FROM supervisor_state WHERE singleton").fetchone()
        frozen_now = after["frozen"] if isinstance(after, dict) else after[0]
        assert frozen_now is False
        after_costs = conn.execute("SELECT count(*) AS n FROM economic_costs").fetchone()
        n_before = before_costs["n"] if isinstance(before_costs, dict) else before_costs[0]
        n_after = after_costs["n"] if isinstance(after_costs, dict) else after_costs[0]
        assert n_after == n_before + 1
        state = ledger.get_financial_state()
        assert state["frozen"] is False
        assert "loop_enabled" in state
    finally:
        conn.rollback()
        conn.execute("RESET ROLE")
        conn.execute(
            """
            UPDATE economic.supervisor_state
               SET frozen = false, signer_enabled = true, loop_enabled = true,
                   updated_by = 'pr9-test-reset'
             WHERE singleton
            """
        )
        conn.commit()
        conn.close()


def test_env_refuse_hmac(monkeypatch: pytest.MonkeyPatch) -> None:
    from aea.supervisor.service import assert_no_spend_secrets

    monkeypatch.setenv("AEA_SIGNER_HMAC_KEY", "should-not-be-here-32-chars-min")
    with pytest.raises(ValueError, match="AEA_SIGNER_HMAC_KEY"):
        assert_no_spend_secrets()
    monkeypatch.delenv("AEA_SIGNER_HMAC_KEY")
    monkeypatch.setenv("AEA_WALLET_DEBIT_TOKEN", "debit")
    with pytest.raises(ValueError, match="AEA_WALLET_DEBIT_TOKEN"):
        assert_no_spend_secrets()
