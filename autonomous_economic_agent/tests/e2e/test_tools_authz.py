"""Model-scope /v1/tools/* authz, freeze, and thin tool semantics."""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from aea import CALLABLE_MODEL_TOOLS, DECLARED_UNIMPLEMENTED_TOOLS, IMPLEMENTED_ECONOMIC_TOOLS, NINE_TOOLS
from aea.config import load_policy
from aea.control.app import create_app
from aea.control.schemas import GetFinancialStateRequest, RequestPaymentRequest
from aea.ledger.service import LedgerService
from aea.marketplace.mock import MockMarketplace
from aea.marketplace.engagement import EconomicEngagementService
from aea.marketplace.intelligence import MarketObservation
from aea.research.readonly import ReadOnlyWebService
from aea.tools_client.http import ToolClient
from aea.wallet.mock import MockWallet
from tests.dbutil import isolate_economic_ledger

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

MODEL = "model-token-pr8"
CONTROL = "control-token-pr8"
SUPERVISOR = "supervisor-token-pr8"
CREDIT = "credit-token-pr8"
MARKET = "marketplace-token-pr8"
PROFITABLE = "mock:job:profitable-summary-001"
UNPROFITABLE = "mock:job:unprofitable-research-001"
INJECTION = "mock:job:prompt-injection-001"
FAKE = "mock:job:fake-payment-001"
HIGH_COMPUTE = "mock:job:high-compute-001"
PROHIBITED = "mock:job:prohibited-token-001"
NETWORK = "mock:job:network-fail-001"


@pytest.fixture
def freeze_dir(tmp_path: Path) -> Path:
    path = tmp_path / "freeze"
    path.mkdir()
    return path


@pytest.fixture
def wallet() -> MockWallet:
    return MockWallet(phase="A", opening={"USDC": Decimal("20"), "SOL": Decimal("0.05")})


@pytest.fixture
def market(wallet: MockWallet) -> MockMarketplace:
    return MockMarketplace(credit_fn=wallet.credit)


@pytest.fixture
def conn():
    if not _postgres_up():
        pytest.skip("controlops Postgres is not reachable")
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
def engagement() -> EconomicEngagementService:
    class Transport:
        source = "the402"

        def send_non_binding_message(self, **_kwargs):  # type: ignore[no-untyped-def]
            return {"message_id": "msg-control-auth-1"}

    def research():
        return {
            "the402": [
                MarketObservation(
                    marketplace="the402",
                    observed_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
                    source="GET /v1/postings",
                    external_id="posting-auth-1",
                    poster_id="buyer-auth-1",
                    title="Bounded public research",
                    reward_usd="2.000000",
                    asset="USDC",
                    chain="base",
                    funded=True,
                    status="open",
                )
            ]
        }

    return EconomicEngagementService(research_fn=research, transports={"the402": Transport()})


@pytest.fixture
def web_research() -> ReadOnlyWebService:
    class Client:
        def request(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
            assert method == "GET"
            body = (
                b'<a class="result__a" href="https://example.com/jobs">Public jobs</a>'
                b'<a class="result__snippet">Bounded research work.</a>'
                if "duckduckgo" in str(url)
                else b"<html><body><p>Public listing of agent work.</p></body></html>"
            )
            return SimpleNamespace(
                status_code=200,
                content=body,
                headers={"content-type": "text/html"},
                url=str(url),
            )

    return ReadOnlyWebService(client=Client(), resolver=lambda host: ["8.8.8.8"], now=lambda: 1000.0)


@pytest.fixture
def app(freeze_dir: Path, market: MockMarketplace, wallet: MockWallet, conn, engagement, web_research):
    return create_app(
        model_token=MODEL,
        freeze_path=freeze_dir / "FREEZE",
        marketplace=market,
        control_token=CONTROL,
        supervisor_token=SUPERVISOR,
        credit_token=CREDIT,
        marketplace_token=MARKET,
        wallet_get_tx=wallet.get_tx,
        wallet_balances=wallet.get_balances,
        ledger=LedgerService(conn, policy=load_policy()),
        engagement=engagement,
        web_research=web_research,
        auto_commit=False,
    )


def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://control") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _client(app) -> ToolClient:
    # Drive tools through ASGI via a tiny httpx wrapper by patching call.
    class AsgiToolClient(ToolClient):
        def call(self, name, body=None, **kwargs):  # type: ignore[no-untyped-def]
            headers = _auth(MODEL)
            payload = body or {}
            if payload.get("idempotency_key"):
                headers["X-AEA-Idempotency-Key"] = payload["idempotency_key"]
            response = _request(app, "POST", f"/v1/tools/{name}", json=payload, headers=headers)
            return response.json()

    return AsgiToolClient(model_token=MODEL)


def test_health(app) -> None:
    assert _request(app, "GET", "/health").status_code == 200


def test_nine_tools_exist_and_unknown_is_404(app) -> None:
    for name in NINE_TOOLS:
        if name == "get_financial_state":
            body: dict = {}
        elif name == "find_jobs":
            body = {}
        else:
            continue
        response = _request(app, "POST", f"/v1/tools/{name}", json=body, headers=_auth(MODEL))
        assert response.status_code in {200, 400}
    tenth = _request(
        app,
        "POST",
        "/v1/tools/call_api",
        json={"url": "http://evil", "force": True},
        headers=_auth(MODEL),
    )
    assert tenth.status_code == 404
    alias = _request(app, "POST", "/v1/tools/find-jobs", json={}, headers=_auth(MODEL))
    assert alias.status_code == 404


def test_new_bounded_tools_require_model_auth_and_observation_tools_work(app) -> None:
    new_tools = (
        "research_opportunities",
        "discover_counterparties",
        "send_message",
        "get_counterparty_profile",
        "post_service_offer",
        "read_messages",
        "follow_up_message",
        "propose_collaboration",
        "get_market_status",
        "list_active_conversations",
    )
    for name in new_tools:
        missing = _request(app, "POST", f"/v1/tools/{name}", json={})
        assert missing.status_code == 401, name
        assert missing.json()["code"] == "UNAUTHENTICATED", name
    research = _request(
        app,
        "POST",
        "/v1/tools/research_opportunities",
        json={"query": "legitimate agent research work", "limit": 2},
        headers=_auth(MODEL),
    )
    counterparties = _request(
        app,
        "POST",
        "/v1/tools/discover_counterparties",
        json={"query": "legitimate research buyers", "limit": 2},
        headers=_auth(MODEL),
    )
    assert research.status_code == 200 and research.json()["code"] == "OK"
    assert counterparties.status_code == 200 and counterparties.json()["code"] == "OK"
    profile = _request(
        app,
        "POST",
        "/v1/tools/get_counterparty_profile",
        json={"counterparty_id": "the402:buyer-auth-1"},
        headers=_auth(MODEL),
    )
    status = _request(app, "POST", "/v1/tools/get_market_status", json={}, headers=_auth(MODEL))
    offer = _request(
        app,
        "POST",
        "/v1/tools/post_service_offer",
        json={"idempotency_key": "control-offer-auth-1"},
        headers=_auth(MODEL),
    )
    sent = _request(
        app,
        "POST",
        "/v1/tools/send_message",
        json={
            "counterparty_id": "the402:buyer-auth-1",
            "channel": "marketplace_api",
            "intent": "ask_work_available",
            "message": "Is legitimate bounded research work currently available?",
            "idempotency_key": "control-message-auth-1",
        },
        headers=_auth(MODEL),
    )
    collab = _request(
        app,
        "POST",
        "/v1/tools/propose_collaboration",
        json={
            "counterparty_id": "the402:buyer-auth-1",
            "proposal": "I can handle the research comparison portion as a non-binding subtask.",
            "idempotency_key": "control-collab-auth-1",
        },
        headers=_auth(MODEL),
    )
    listed = _request(
        app, "POST", "/v1/tools/list_active_conversations", json={}, headers=_auth(MODEL)
    )
    inbox = _request(
        app,
        "POST",
        "/v1/tools/read_messages",
        json={"counterparty_id": "the402:buyer-auth-1"},
        headers=_auth(MODEL),
    )
    assert profile.status_code == 200 and profile.json()["code"] == "OK"
    assert status.status_code == 200 and status.json()["code"] == "OK"
    assert offer.status_code == 200 and offer.json()["canonical_profile"] is True
    assert sent.status_code == 200 and sent.json()["code"] == "OK"
    assert sent.json()["non_binding"] is True
    assert collab.status_code == 200 and collab.json()["paid_subcontracting"] is False
    assert listed.status_code == 200 and listed.json()["conversations"]
    assert inbox.status_code == 200 and inbox.json()["code"] == "OK"
    follow = _request(
        app,
        "POST",
        "/v1/tools/follow_up_message",
        json={
            "conversation_id": sent.json()["conversation_id"],
            "message": "Checking whether this research task is still open.",
            "idempotency_key": "control-follow-auth-1",
        },
        headers=_auth(MODEL),
    )
    assert follow.status_code == 403
    assert follow.json()["code"] == "FORBIDDEN"
    injected = _request(
        app,
        "POST",
        "/v1/tools/research_opportunities",
        json={"query": "legitimate work", "url": "https://evil.example/jobs", "limit": 1},
        headers=_auth(MODEL),
    )
    assert injected.status_code == 400
    assert set(IMPLEMENTED_ECONOMIC_TOOLS) == set(NINE_TOOLS) | set(new_tools)
    assert len(IMPLEMENTED_ECONOMIC_TOOLS) == 19
    assert set(CALLABLE_MODEL_TOOLS) == set(IMPLEMENTED_ECONOMIC_TOOLS) | {"web_search", "web_extract"}


def test_readonly_web_tools_are_authenticated_get_only_and_ssrf_closed(app) -> None:
    for name in ("web_search", "web_extract"):
        missing = _request(app, "POST", f"/v1/tools/{name}", json={})
        assert missing.status_code == 401, name
    search = _request(
        app,
        "POST",
        "/v1/tools/web_search",
        json={"query": "autonomous agent bounty boards", "limit": 3},
        headers=_auth(MODEL),
    )
    extract = _request(
        app,
        "POST",
        "/v1/tools/web_extract",
        json={"url": "https://example.com/jobs"},
        headers=_auth(MODEL),
    )
    assert search.status_code == 200 and search.json()["read_only"] is True
    assert extract.status_code == 200 and extract.json()["untrusted"] is True
    local = _request(
        app,
        "POST",
        "/v1/tools/web_extract",
        json={"url": "http://127.0.0.1:18700/health"},
        headers=_auth(MODEL),
    )
    assert local.status_code == 403
    smuggled = _request(
        app,
        "POST",
        "/v1/tools/web_extract",
        json={"url": "https://example.com/jobs", "method": "POST"},
        headers=_auth(MODEL),
    )
    assert smuggled.status_code == 400
    for name in ("browser_automation", "computer_use", "terminal", "email", "external_messaging"):
        denied = _request(app, "POST", f"/v1/tools/{name}", json={}, headers=_auth(MODEL))
        assert denied.status_code == 404, name


def test_declared_unimplemented_capabilities_have_no_control_route(app) -> None:
    for name in DECLARED_UNIMPLEMENTED_TOOLS:
        response = _request(
            app,
            "POST",
            f"/v1/tools/{name}",
            json={},
            headers=_auth(MODEL),
        )
        assert response.status_code == 404, name
        assert response.json()["code"] == "NOT_FOUND", name


def test_control_and_other_tokens_forbidden_on_tools(app) -> None:
    for token in (CONTROL, SUPERVISOR, CREDIT, MARKET):
        response = _request(
            app,
            "POST",
            "/v1/tools/get_financial_state",
            json={},
            headers=_auth(token),
        )
        assert response.status_code == 403, token
        assert response.json()["code"] == "FORBIDDEN"
    missing = _request(app, "POST", "/v1/tools/get_financial_state", json={})
    assert missing.status_code == 401


def test_force_true_rejected(app) -> None:
    response = _request(
        app,
        "POST",
        "/v1/tools/get_financial_state",
        json={"force": True},
        headers=_auth(MODEL),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    with pytest.raises(ValidationError):
        GetFinancialStateRequest.model_validate({"force": True})
    with pytest.raises(ValidationError):
        RequestPaymentRequest.model_validate(
            {
                "amount": "0.050000",
                "asset": "USDC",
                "destination": "mock:counterparty:mkt-escrow",
                "purpose": "marketplace_acceptance_fee",
                "job_id": str(uuid4()),
                "idempotency_key": "pay-force-01",
                "url": "http://evil",
            }
        )


def test_find_jobs_marks_untrusted_and_flags_injection(app) -> None:
    response = _request(
        app,
        "POST",
        "/v1/tools/find_jobs",
        json={"limit": 20},
        headers=_auth(MODEL),
    )
    assert response.status_code == 200
    jobs = {j["external_reference"]: j for j in response.json()["jobs"]}
    assert PROFITABLE in jobs
    preview = jobs[INJECTION]["untrusted_description_preview"]
    assert preview.startswith("[UNTRUSTED_MARKETPLACE_DATA]")
    assert "prompt_injection" in jobs[INJECTION]["flags"]
    blob = response.text
    assert MODEL not in blob
    assert CONTROL not in blob


def test_evaluate_and_accept_reject_unprofitable_and_injection(app) -> None:
    found = _request(app, "POST", "/v1/tools/find_jobs", json={"limit": 20}, headers=_auth(MODEL)).json()
    by_ref = {j["external_reference"]: j for j in found["jobs"]}
    unprof = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={
            "opportunity_id": by_ref[UNPROFITABLE]["opportunity_id"],
            "idempotency_key": "eval-unprof-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert unprof["recommendation"] == "decline"
    assert unprof["meets_required_margin"] is False
    denied = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[UNPROFITABLE]["opportunity_id"],
            "idempotency_key": "acc-unprof-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert denied["ok"] is False
    inj = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[INJECTION]["opportunity_id"],
            "idempotency_key": "acc-inj-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert inj["code"] == "PROMPT_INJECTION_DETECTED"
    prohibited = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[PROHIBITED]["opportunity_id"],
            "idempotency_key": "acc-bonk-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert prohibited["ok"] is False
    assert prohibited["code"] in {"PROHIBITED_TOKEN", "PROMPT_INJECTION_DETECTED"}


def test_profitable_perform_submit_and_fake_payment(app, wallet: MockWallet) -> None:
    found = _request(app, "POST", "/v1/tools/find_jobs", json={"limit": 20}, headers=_auth(MODEL)).json()
    by_ref = {j["external_reference"]: j for j in found["jobs"]}
    accepted = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[PROFITABLE]["opportunity_id"],
            "idempotency_key": "acc-prof-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert accepted["ok"] is True
    job_id = accepted["job_id"]
    performed = _request(
        app,
        "POST",
        "/v1/tools/perform_job",
        json={"job_id": job_id, "idempotency_key": "perf-prof-0001"},
        headers=_auth(MODEL),
    ).json()
    assert performed["ok"] is True, performed
    assert performed["deliverable_digest"]
    submitted = _request(
        app,
        "POST",
        "/v1/tools/submit_work",
        json={"job_id": job_id, "idempotency_key": "sub-prof-0001"},
        headers=_auth(MODEL),
    ).json()
    assert submitted["ok"] is True
    assert wallet.get_balances()["USDC"] == Decimal("20.5")
    settled = _request(
        app,
        "POST",
        "/v1/tools/check_payment",
        json={"job_id": job_id, "idempotency_key": "chk-prof-0001"},
        headers=_auth(MODEL),
    ).json()
    assert settled["status"] == "settled"
    assert settled["verified"] is True

    fake_eval = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={
            "opportunity_id": by_ref[FAKE]["opportunity_id"],
            "idempotency_key": "eval-fake-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert fake_eval["accept_allowed"] is True
    assert fake_eval["recommendation"] == "decline"
    assert fake_eval["risk_veto"] is True
    fake_acc = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[FAKE]["opportunity_id"],
            "idempotency_key": "acc-fake-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert fake_acc["ok"] is False
    assert fake_acc["code"] == "AGENT_RISK_VETO"
    assert "fake_payment" in fake_acc["risk_factors"]
    runaway_eval = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={
            "opportunity_id": by_ref[HIGH_COMPUTE]["opportunity_id"],
            "idempotency_key": "eval-runaway-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert runaway_eval["accept_allowed"] is True
    assert runaway_eval["risk_veto"] is True
    runaway_acc = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[HIGH_COMPUTE]["opportunity_id"],
            "idempotency_key": "acc-runaway-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert runaway_acc["ok"] is False
    assert runaway_acc["code"] == "AGENT_RISK_VETO"
    assert "runaway_cost" in runaway_acc["risk_factors"]
    assert wallet.get_balances()["USDC"] == Decimal("20.5")


def test_request_payment_does_not_debit(app, wallet: MockWallet) -> None:
    found = _request(app, "POST", "/v1/tools/find_jobs", json={"limit": 20}, headers=_auth(MODEL)).json()
    oid = next(j["opportunity_id"] for j in found["jobs"] if j["external_reference"] == PROFITABLE)
    job = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={"opportunity_id": oid, "idempotency_key": "acc-pay-0001"},
        headers=_auth(MODEL),
    ).json()
    before = wallet.get_balances()["USDC"]
    response = _request(
        app,
        "POST",
        "/v1/tools/request_payment",
        json={
            "amount": "0.050000",
            "asset": "USDC",
            "destination": "mock:counterparty:mkt-escrow",
            "purpose": "marketplace_acceptance_fee",
            "job_id": job["job_id"],
            "idempotency_key": "req-pay-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert response["code"] == "SIGNER_UNAVAILABLE"
    assert response["transaction_reference"] is None
    assert wallet.get_balances()["USDC"] == before


def test_freeze_blocks_mutating_not_observe(app, freeze_dir: Path) -> None:
    (freeze_dir / "FREEZE").write_text("1\n", encoding="utf-8")
    frozen_eval = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={"opportunity_id": str(uuid4()), "idempotency_key": "eval-frz-0001"},
        headers=_auth(MODEL),
    ).json()
    assert frozen_eval["code"] == "AGENT_FROZEN"
    state = _request(
        app,
        "POST",
        "/v1/tools/get_financial_state",
        json={},
        headers=_auth(MODEL),
    ).json()
    assert state["ok"] is True
    assert state["frozen"] is True
    found = _request(
        app,
        "POST",
        "/v1/tools/find_jobs",
        json={},
        headers=_auth(MODEL),
    )
    assert found.status_code == 200


def test_idempotency_conflict(app) -> None:
    found = _request(app, "POST", "/v1/tools/find_jobs", json={"limit": 20}, headers=_auth(MODEL)).json()
    oid = found["jobs"][0]["opportunity_id"]
    key = "eval-idem-0001"
    first = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={"opportunity_id": oid, "idempotency_key": key},
        headers=_auth(MODEL),
    )
    replay = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={"opportunity_id": oid, "idempotency_key": key},
        headers=_auth(MODEL),
    )
    assert replay.json()["code"] == "IDEMPOTENT_REPLAY"
    other = str(uuid4())
    conflict = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={"opportunity_id": other, "idempotency_key": key},
        headers=_auth(MODEL),
    )
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert first.json()["opportunity_id"] == replay.json()["opportunity_id"]


def test_idempotency_semantics_for_mutating_economic_actions(app) -> None:
    found = _request(app, "POST", "/v1/tools/find_jobs", json={"limit": 20}, headers=_auth(MODEL)).json()
    by_ref = {j["external_reference"]: j for j in found["jobs"]}

    denied = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[UNPROFITABLE]["opportunity_id"],
            "idempotency_key": "idem-def-reject-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert denied["ok"] is False
    replay_denied = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[UNPROFITABLE]["opportunity_id"],
            "idempotency_key": "idem-def-reject-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert replay_denied["code"] == "IDEMPOTENT_REPLAY"
    later = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[PROFITABLE]["opportunity_id"],
            "idempotency_key": "idem-new-valid-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert later["ok"] is True, later

    eval_key = "idem-changed-state-0001"
    first_eval = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={"opportunity_id": by_ref[PROFITABLE]["opportunity_id"], "idempotency_key": eval_key},
        headers=_auth(MODEL),
    )
    assert first_eval.status_code == 200
    conflict = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={"opportunity_id": by_ref[UNPROFITABLE]["opportunity_id"], "idempotency_key": eval_key},
        headers=_auth(MODEL),
    ).json()
    assert conflict["code"] == "IDEMPOTENCY_CONFLICT"
    new_state = _request(
        app,
        "POST",
        "/v1/tools/evaluate_job",
        json={
            "opportunity_id": by_ref[UNPROFITABLE]["opportunity_id"],
            "idempotency_key": "idem-changed-state-0002",
        },
        headers=_auth(MODEL),
    ).json()
    assert new_state["code"] == "OK"

    first_bypass = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[PROHIBITED]["opportunity_id"],
            "idempotency_key": "idem-bypass-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert first_bypass["ok"] is False
    second_bypass = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[PROHIBITED]["opportunity_id"],
            "idempotency_key": "idem-bypass-0002",
        },
        headers=_auth(MODEL),
    ).json()
    assert second_bypass["ok"] is False
    assert second_bypass["code"] in {"PROHIBITED_TOKEN", "PROMPT_INJECTION_DETECTED"}

    network = _request(
        app,
        "POST",
        "/v1/tools/accept_job",
        json={
            "opportunity_id": by_ref[NETWORK]["opportunity_id"],
            "idempotency_key": "idem-net-accept-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert network["ok"] is True, network
    performed = _request(
        app,
        "POST",
        "/v1/tools/perform_job",
        json={"job_id": network["job_id"], "idempotency_key": "idem-net-perf-0001"},
        headers=_auth(MODEL),
    ).json()
    assert performed["ok"] is True
    first_submit = _request(
        app,
        "POST",
        "/v1/tools/submit_work",
        json={"job_id": network["job_id"], "idempotency_key": "idem-net-submit-0001"},
        headers=_auth(MODEL),
    ).json()
    assert first_submit["code"] == "NETWORK_FAILURE"
    retry_submit = _request(
        app,
        "POST",
        "/v1/tools/submit_work",
        json={"job_id": network["job_id"], "idempotency_key": "idem-net-submit-0001"},
        headers=_auth(MODEL),
    ).json()
    assert retry_submit["code"] == "NETWORK_FAILURE"
    assert retry_submit.get("code") != "IDEMPOTENCY_CONFLICT"


def test_record_decision_does_not_apply_control_change(app) -> None:
    response = _request(
        app,
        "POST",
        "/v1/tools/record_decision",
        json={
            "decision_type": "recommend_control_change",
            "decision": "recommend",
            "reasoning_summary": "raise limits",
            "idempotency_key": "dec-rec-0001",
        },
        headers=_auth(MODEL),
    ).json()
    assert response["ok"] is True
    assert response["applied"] is False


def test_no_privileged_routes_on_control(app) -> None:
    for path in ("/v1/sign", "/v1/evaluate", "/v1/wallet/debit", "/v1/admin/unfreeze"):
        response = _request(app, "POST", path, json={}, headers=_auth(MODEL))
        assert response.status_code == 404


def test_tool_client_has_no_control_constructor() -> None:
    params = inspect.signature(ToolClient.__init__).parameters
    assert "control_token" not in params
    assert "signer_token" not in params
    assert "debit_token" not in params
    client = ToolClient(model_token=MODEL)
    assert client._model_token == MODEL


def test_pre_tool_call_blocks_aliases_and_tenth_tool() -> None:
    import importlib.util

    plugin = Path(__file__).resolve().parents[2] / "hermes_plugin" / "__init__.py"
    spec = importlib.util.spec_from_file_location("economic_hermes_plugin", plugin)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.on_pre_tool_call(tool_name="terminal")["action"] == "block"
    assert mod.on_pre_tool_call(tool_name="find-jobs")["action"] == "block"
    assert mod.on_pre_tool_call(tool_name="FindJobs")["action"] == "block"
    assert mod.on_pre_tool_call(tool_name="request_payment_admin")["action"] == "block"
    assert mod.on_pre_tool_call(tool_name="find_jobs") is None
    src = plugin.read_text(encoding="utf-8")
    assert "AEA_CONTROL_TOKEN" not in src
    assert "AEA_SIGNER" not in src
    assert "AEA_WALLET_DEBIT" not in src


def test_plugin_handlers_accept_hermes_positional_argument_dict(monkeypatch) -> None:
    import importlib.util

    plugin = Path(__file__).resolve().parents[2] / "hermes_plugin" / "__init__.py"
    spec = importlib.util.spec_from_file_location("economic_hermes_plugin_handler", plugin)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    captured = {}
    monkeypatch.setattr(mod, "_post_tool", lambda name, body: captured.update(name=name, body=body) or {"ok": True})
    result = mod._handler_for("find_jobs")({"limit": 8, "url": "http://forbidden"})
    assert json.loads(result) == {"ok": True}
    assert captured == {"name": "find_jobs", "body": {"limit": 8}}


def test_plugin_preserves_control_plane_http_error_body(monkeypatch) -> None:
    import importlib.util
    from io import BytesIO
    from urllib.error import HTTPError

    plugin = Path(__file__).resolve().parents[2] / "hermes_plugin" / "__init__.py"
    spec = importlib.util.spec_from_file_location("economic_hermes_plugin_http", plugin)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    body = json.dumps(
        {"ok": False, "code": "POLICY_REJECTED", "detail": "workpnp: no bounded non-binding message path"}
    ).encode()

    def boom(_req, timeout=None):  # type: ignore[no-untyped-def]
        raise HTTPError(
            "http://127.0.0.1:18700/v1/tools/send_message",
            403,
            "Forbidden",
            None,
            BytesIO(body),
        )

    monkeypatch.setattr(mod, "urlopen", boom)
    monkeypatch.setattr(mod, "_model_token", lambda: "model-token")
    result = mod._post_tool("send_message", {"idempotency_key": "plugin-http-0001"})
    assert result["code"] == "POLICY_REJECTED"
    assert "workpnp" in result["detail"]


def test_lmstudio_wire_messages_have_valid_content(monkeypatch) -> None:
    import sys

    workspace = Path(__file__).resolve().parents[3]
    if str(workspace) not in sys.path:
        sys.path.insert(0, str(workspace))
    from autonomous_economic_agent.tests.e2e.lmstudio_preflight import (
        request_body,
        validate_messages,
    )

    tool_result = json.dumps({"ok": True, "code": "OK"})
    messages = request_body(with_tools=True)["messages"] + [
        {
            "role": "assistant",
            "content": "Calling an observation tool.",
            "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "get_financial_state", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call-1", "name": "get_financial_state", "content": tool_result},
    ]
    validate_messages(messages)
    with pytest.raises(ValueError, match="invalid content type dict"):
        validate_messages([{"role": "tool", "content": {"ok": True}}])


def test_create_app_rejects_debit_and_hmac(freeze_dir: Path) -> None:
    with pytest.raises(ValueError):
        from aea.control.app import ControlService
        from aea.marketplace.mock import MockMarketplace

        ControlService(
            model_token=MODEL,
            freeze_path=freeze_dir / "FREEZE",
            marketplace=MockMarketplace(),
            policy=__import__("aea.config", fromlist=["load_policy"]).load_policy(),
            debit_token="debit",
        )
