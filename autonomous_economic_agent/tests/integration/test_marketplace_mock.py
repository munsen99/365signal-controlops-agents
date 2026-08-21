"""Mock marketplace adapter, HTTP authz, settlement rail, and fixtures."""

from __future__ import annotations

import asyncio
import inspect
from decimal import Decimal
import httpx
import pytest
from pydantic import ValidationError

from aea.hashing import sha256_hex
from aea.marketplace.mock import MockMarketplace, _fake_tx_id
from aea.marketplace.protocol import AcceptRequest, MarketplaceError, SubmitRequest
from aea.marketplace.registry import enabled_adapter_names, get_adapter
from aea.marketplace.service import create_app, create_app_from_env
from aea.wallet.mock import MockWallet
from aea.wallet.service import create_app as create_wallet_app
from aea.workers.registry import run_worker

MARKET = "marketplace-token-test"
MODEL = "model-token-test"
CONTROL = "control-token-test"
CREDIT = "wallet-credit-token-test"
DEBIT = "wallet-debit-token-test"
READ = "wallet-read-token-test"

PROFITABLE = "mock:job:profitable-summary-001"
UNPROFITABLE = "mock:job:unprofitable-research-001"
PROHIBITED = "mock:job:prohibited-token-001"
INJECTION = "mock:job:prompt-injection-001"
FAKE = "mock:job:fake-payment-001"
HIGH_COMPUTE = "mock:job:high-compute-001"
NETWORK = "mock:job:network-fail-001"
FAIL_SPEND = "mock:job:fails-after-spend-001"


@pytest.fixture
def wallet() -> MockWallet:
    return MockWallet(phase="A", opening={"USDC": Decimal("20"), "SOL": Decimal("0.05")})


@pytest.fixture
def market(wallet: MockWallet) -> MockMarketplace:
    return MockMarketplace(credit_fn=wallet.credit)


@pytest.fixture
def wallet_app(wallet: MockWallet):
    return create_wallet_app(
        wallet=wallet,
        debit_token=DEBIT,
        credit_token=CREDIT,
        read_token=READ,
        model_token=MODEL,
        control_token=CONTROL,
        allow_faults=False,
    )


@pytest.fixture
def app(market: MockMarketplace):
    return create_app(
        adapter=market,
        marketplace_token=MARKET,
        model_token=MODEL,
        control_token=CONTROL,
        credit_token=CREDIT,
    )


def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://mkt") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _digest(text: str = "deliverable") -> str:
    return sha256_hex(text.encode("utf-8"))


def test_discover_is_deterministic(market: MockMarketplace) -> None:
    a = market.discover(limit=20)
    b = market.discover(limit=20)
    refs_a = [j.external_reference for j in a.jobs]
    refs_b = [j.external_reference for j in b.jobs]
    assert refs_a == refs_b
    assert PROFITABLE in refs_a
    assert UNPROFITABLE in refs_a
    assert PROHIBITED in refs_a
    assert INJECTION in refs_a
    assert FAKE in refs_a
    assert HIGH_COMPUTE in refs_a
    assert NETWORK in refs_a
    assert FAIL_SPEND in refs_a


def test_fixtures_distinguishable_without_policy_labels(market: MockMarketplace) -> None:
    by_ref = {j.external_reference: j for j in market.discover(limit=20).jobs}
    assert by_ref[PROFITABLE].payment_asset == "USDC"
    assert Decimal(by_ref[PROFITABLE].expected_revenue.amount) > Decimal(
        by_ref[PROFITABLE].estimated_cost.amount
    )
    assert Decimal(by_ref[UNPROFITABLE].expected_revenue.amount) < Decimal(
        by_ref[UNPROFITABLE].estimated_cost.amount
    )
    assert by_ref[PROHIBITED].payment_asset != "USDC"
    assert "prompt_injection" in by_ref[INJECTION].flags
    assert by_ref[FAKE].credits_wallet_on_submit is False
    assert Decimal(by_ref[HIGH_COMPUTE].estimated_cost.amount) >= Decimal("0.500000")
    assert by_ref[FAIL_SPEND].worker == "fail_after_mark"
    for job in by_ref.values():
        dumped = job.model_dump()
        assert "policy" not in dumped
        assert "reject" not in dumped.get("title", "").lower() or job.external_reference == INJECTION


def test_accept_and_submit_lifecycle(market: MockMarketplace, wallet: MockWallet) -> None:
    accepted = market.accept(PROFITABLE, idempotency_key="accept-prof-0001")
    assert accepted.status == "accepted"
    submitted = market.submit(
        PROFITABLE,
        artefact_digest=_digest(),
        artefact_uri="artefacts/abc",
        idempotency_key="submit-prof-0001",
    )
    assert submitted.status == "submitted"
    assert submitted.credited is True
    assert submitted.transaction_reference
    assert wallet.get_tx(submitted.transaction_reference) is not None
    assert wallet.get_balances()["USDC"] == Decimal("20.5")
    claim = market.verify_payment(PROFITABLE)
    assert claim.status == "paid"
    assert claim.verified is False
    assert claim.transaction_reference == submitted.transaction_reference


def test_duplicate_accept_replay_and_conflict(market: MockMarketplace) -> None:
    first = market.accept(PROFITABLE, idempotency_key="accept-dup-0001")
    replay = market.accept(PROFITABLE, idempotency_key="accept-dup-0001")
    assert first.replay is False
    assert replay.replay is True
    with pytest.raises(MarketplaceError) as exc:
        market.accept(PROFITABLE, idempotency_key="accept-dup-other")
    assert exc.value.code == "CONFLICT"


def test_submit_idempotent_and_conflict(market: MockMarketplace, wallet: MockWallet) -> None:
    market.accept(PROFITABLE, idempotency_key="accept-sub-0001")
    body = {
        "artefact_digest": _digest("one"),
        "artefact_uri": "artefacts/one",
        "idempotency_key": "submit-idem-0001",
    }
    a = market.submit(PROFITABLE, **body)
    b = market.submit(PROFITABLE, **body)
    assert a.transaction_reference == b.transaction_reference
    assert b.replay is True
    assert wallet.get_balances()["USDC"] == Decimal("20.5")
    with pytest.raises(MarketplaceError) as exc:
        market.submit(
            PROFITABLE,
            artefact_digest=_digest("two"),
            artefact_uri="artefacts/two",
            idempotency_key="submit-idem-0001",
        )
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(MarketplaceError) as exc2:
        market.submit(
            PROFITABLE,
            artefact_digest=_digest("two"),
            artefact_uri="artefacts/two",
            idempotency_key="submit-idem-other",
        )
    assert exc2.value.code == "CONFLICT"


def test_fake_payment_claims_paid_without_wallet_credit(
    market: MockMarketplace, wallet: MockWallet
) -> None:
    market.accept(FAKE, idempotency_key="accept-fake-0001")
    submitted = market.submit(
        FAKE,
        artefact_digest=_digest("fake"),
        artefact_uri="artefacts/fake",
        idempotency_key="submit-fake-0001",
    )
    assert submitted.credited is False
    claim = market.verify_payment(FAKE)
    assert claim.status == "paid"
    assert claim.verified is False
    assert claim.transaction_reference == _fake_tx_id(FAKE)
    assert wallet.get_tx(claim.transaction_reference) is None
    assert wallet.get_balances()["USDC"] == Decimal("20")


def test_network_failure_after_accept(market: MockMarketplace) -> None:
    accepted = market.accept(NETWORK, idempotency_key="accept-net-0001")
    assert accepted.status == "accepted"
    with pytest.raises(MarketplaceError) as exc:
        market.submit(
            NETWORK,
            artefact_digest=_digest(),
            artefact_uri="artefacts/net",
            idempotency_key="submit-net-0001",
        )
    assert exc.value.code == "NETWORK_FAILURE"
    with pytest.raises(MarketplaceError) as exc2:
        market.get_status(NETWORK)
    assert exc2.value.code == "NETWORK_FAILURE"


def test_cannot_submit_before_accept(market: MockMarketplace) -> None:
    with pytest.raises(MarketplaceError) as exc:
        market.submit(
            PROFITABLE,
            artefact_digest=_digest(),
            artefact_uri="artefacts/early",
            idempotency_key="submit-early-01",
        )
    assert exc.value.code == "CONFLICT"


def test_cannot_revert_submitted(market: MockMarketplace) -> None:
    market.accept(PROFITABLE, idempotency_key="accept-term-0001")
    market.submit(
        PROFITABLE,
        artefact_digest=_digest(),
        artefact_uri="artefacts/term",
        idempotency_key="submit-term-0001",
    )
    with pytest.raises(MarketplaceError) as exc:
        market.accept(PROFITABLE, idempotency_key="accept-term-0001")
    assert exc.value.code == "CONFLICT"
    status = market.get_status(PROFITABLE)
    assert status.status == "submitted"


def test_prompt_injection_is_inert_data(market: MockMarketplace) -> None:
    job = next(j for j in market.discover(limit=20).jobs if j.external_reference == INJECTION)
    assert "prompt_injection" in job.flags
    raw = market.raw_description(INJECTION)
    assert "Ignore constitution" in raw
    assert "AEA_SIGNER_TOKEN" in raw
    assert job.untrusted_description_preview.startswith("[UNTRUSTED_MARKETPLACE_DATA]")
    market.accept(INJECTION, idempotency_key="accept-inj-0001")
    assert market.get_status(INJECTION).status == "accepted"


def test_malformed_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AcceptRequest.model_validate({"idempotency_key": "accept-xx-0001", "force": True})
    with pytest.raises(ValidationError):
        SubmitRequest.model_validate(
            {
                "artefact_digest": _digest(),
                "artefact_uri": "artefacts/x",
                "idempotency_key": "submit-xx-0001",
                "force": True,
            }
        )


def test_workers_are_deterministic_and_have_no_llm() -> None:
    a = run_worker(PROFITABLE)
    b = run_worker(PROFITABLE)
    assert a.digest == b.digest
    assert a.ok is True
    fail = run_worker(FAIL_SPEND)
    assert fail.ok is False
    assert fail.reason_code == "JOB_FAILED"
    runaway = run_worker(HIGH_COMPUTE)
    assert runaway.ok is False
    assert runaway.reason_code == "RUNAWAY_COST"
    import aea.workers.mock as mock_mod
    import aea.workers.registry as reg

    for module in (mock_mod, reg):
        assert "openai" not in module.__dict__
        assert "solana" not in module.__dict__


def test_registry_rejects_live_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEA_ENABLED_ADAPTERS", "mock,live")
    with pytest.raises(MarketplaceError):
        enabled_adapter_names()
    monkeypatch.setenv("AEA_ENABLED_ADAPTERS", "mock")
    adapter = get_adapter("mock")
    assert adapter.name == "mock"


def test_http_authz_and_discover(app) -> None:
    assert _request(app, "GET", "/health").status_code == 200
    missing = _request(app, "GET", "/v1/marketplace/jobs")
    assert missing.status_code == 401
    model = _request(app, "GET", "/v1/marketplace/jobs", headers=_auth(MODEL))
    assert model.status_code == 403
    control = _request(app, "GET", "/v1/marketplace/jobs", headers=_auth(CONTROL))
    assert control.status_code == 403
    ok = _request(app, "GET", "/v1/marketplace/jobs?limit=20", headers=_auth(MARKET))
    assert ok.status_code == 200
    refs = [j["external_reference"] for j in ok.json()["jobs"]]
    assert PROFITABLE in refs
    assert MODEL not in ok.text
    assert MARKET not in ok.text
    assert CREDIT not in ok.text


def test_http_accept_submit_and_force_rejected(app, wallet: MockWallet) -> None:
    force = _request(
        app,
        "POST",
        f"/v1/marketplace/jobs/{PROFITABLE}/accept",
        json={"idempotency_key": "http-acc-0001", "force": True},
        headers=_auth(MARKET),
    )
    assert force.status_code == 400
    acc = _request(
        app,
        "POST",
        f"/v1/marketplace/jobs/{PROFITABLE}/accept",
        json={"idempotency_key": "http-acc-0001"},
        headers=_auth(MARKET),
    )
    assert acc.status_code == 200
    sub = _request(
        app,
        "POST",
        f"/v1/marketplace/jobs/{PROFITABLE}/submit",
        json={
            "artefact_digest": _digest("http"),
            "artefact_uri": "artefacts/http",
            "idempotency_key": "http-sub-0001",
        },
        headers=_auth(MARKET),
    )
    assert sub.status_code == 200
    assert sub.json()["credited"] is True
    assert wallet.get_balances()["USDC"] == Decimal("20.5")
    pay = _request(
        app,
        "GET",
        f"/v1/marketplace/jobs/{FAKE}/payment",
        headers=_auth(MARKET),
    )
    assert pay.status_code == 200
    # FAKE not submitted yet
    assert pay.json()["status"] == "not_due"
    assert pay.json()["verified"] is False


def test_http_no_debit_or_ledger_routes(app) -> None:
    for path in (
        "/v1/wallet/debit",
        "/v1/wallet/credit",
        "/v1/sign",
        "/v1/evaluate",
        "/v1/admin/unfreeze",
    ):
        response = _request(app, "POST", path, json={}, headers=_auth(MARKET))
        assert response.status_code == 404


def test_create_app_rejects_debit_token(market: MockMarketplace) -> None:
    with pytest.raises(ValueError, match="debit"):
        from aea.marketplace.service import MarketplaceService

        MarketplaceService(
            adapter=market,
            marketplace_token=MARKET,
            debit_token=DEBIT,
        )


def test_source_has_no_privileged_secrets() -> None:
    from aea.marketplace import mock as mmod
    from aea.marketplace import service as smod

    assert "AEA_SIGNER_HMAC_KEY" not in inspect.getsource(mmod)
    assert "AEA_WALLET_DEBIT_TOKEN" not in inspect.getsource(create_app_from_env)
    assert "solders" not in mmod.__dict__
    assert "openai" not in mmod.__dict__
    env_src = inspect.getsource(create_app_from_env)
    assert "credit_token=credit" in env_src


def test_marketplace_does_not_book_ledger_revenue(market: MockMarketplace) -> None:
    import aea.marketplace.mock as mock_mod

    assert "LedgerService" not in mock_mod.__dict__
    market.accept(PROFITABLE, idempotency_key="accept-norev-0001")
    market.submit(
        PROFITABLE,
        artefact_digest=_digest("nr"),
        artefact_uri="artefacts/nr",
        idempotency_key="submit-norev-0001",
    )
    claim = market.verify_payment(PROFITABLE)
    assert claim.verified is False
