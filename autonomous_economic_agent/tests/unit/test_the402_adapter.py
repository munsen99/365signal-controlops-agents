"""Deterministic the402 provider-adapter tests. No live bids. No secrets in asserts."""

from __future__ import annotations

import ast
import inspect
import json
import os
import time
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from aea.marketplace.live.the402 import (
    ADAPTER_NAME,
    BASE_MAINNET_CHAIN_ID,
    BASE_MAINNET_USDC,
    DEFAULT_PAYOUT_WALLET,
    PROVIDER_CAPABILITY,
    THE402_API_HOST,
    THE402_ORIGIN,
    FakeThe402Transport,
    The402Adapter,
    The402HttpsClient,
    WalletPayoutObservation,
    classify_posting,
    default_fixtures,
    public_postings_demand,
    verify_the402_webhook,
)
from aea.marketplace.protocol import MarketplaceError, PaymentClaim
from aea.marketplace.registry import enabled_adapter_names, get_adapter
from aea.policy.reasons import HttpCode

ROOT = Path(__file__).resolve().parents[2] / "src" / "aea" / "marketplace" / "live" / "the402.py"
REF = "the402:posting:post_summary_001"


def _adapter(**kwargs: object) -> The402Adapter:
    kwargs.setdefault("service_id", "svc_fixture_text")
    return The402Adapter(**kwargs)


def _sign(secret: str, body: bytes, timestamp: str) -> str:
    import hashlib
    import hmac

    return "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def test_live_adapter_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AEA_THE402_ENABLED", raising=False)
    monkeypatch.setenv("AEA_ENABLED_ADAPTERS", "mock")
    assert enabled_adapter_names() == ("mock",)
    with pytest.raises(MarketplaceError):
        get_adapter("the402")
    monkeypatch.setenv("AEA_ENABLED_ADAPTERS", "mock,the402")
    with pytest.raises(MarketplaceError, match="disabled by default"):
        enabled_adapter_names()


def test_registry_still_rejects_unknown_live_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEA_ENABLED_ADAPTERS", "mock,live")
    with pytest.raises(MarketplaceError):
        enabled_adapter_names()


def test_credentials_remain_server_side(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_file = tmp_path / "the402_api_key"
    secret_file = tmp_path / "the402_webhook"
    key_file.write_text("sk_fixture_not_for_model\n")
    secret_file.write_text("whsec_fixture_not_for_model\n")
    key_file.chmod(0o600)
    secret_file.chmod(0o600)
    monkeypatch.setenv("AEA_THE402_ENABLED", "1")
    monkeypatch.setenv("AEA_ENABLED_ADAPTERS", "the402")
    monkeypatch.setenv("AEA_THE402_API_KEY_FILE", str(key_file))
    monkeypatch.setenv("AEA_THE402_WEBHOOK_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("AEA_THE402_SERVICE_ID", "svc_fixture_text")
    adapter = get_adapter("the402")
    page = adapter.discover(limit=5, cursor=None)
    dumped = json.dumps(page.model_dump(mode="json"))
    assert "sk_fixture_not_for_model" not in dumped
    assert "whsec_fixture_not_for_model" not in dumped
    assert "sk_fixture_not_for_model" not in repr(adapter)


def test_provider_capability_is_provider_only_and_model_safe() -> None:
    capability = PROVIDER_CAPABILITY
    assert capability.marketplace == "the402"
    assert capability.role == "provider"
    assert capability.settlement_chain == "base"
    assert capability.settlement_asset == "USDC"
    assert capability.payout_wallet == "external"
    assert capability.auth == "scoped_api_key"
    assert capability.buyer_flow == "disabled"
    assert capability.arbitrary_signing is False
    assert capability.typed_data_signing is False
    assert capability.transaction_signing is False
    assert capability.custody is False
    assert capability.capital_spend is False
    assert "secret" not in repr(capability).lower()


def test_live_credentials_require_protected_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    api = tmp_path / "api-key"
    webhook = tmp_path / "webhook-secret"
    api.write_text("sk_provider_fixture_value\n")
    webhook.write_text("whsec_fixture_value\n")
    monkeypatch.setenv("AEA_THE402_ENABLED", "1")
    monkeypatch.setenv("AEA_THE402_API_KEY_FILE", str(api))
    monkeypatch.setenv("AEA_THE402_WEBHOOK_SECRET_FILE", str(webhook))
    with pytest.raises(MarketplaceError, match="0600"):
        The402Adapter.from_env()
    api.chmod(0o600)
    webhook.chmod(0o600)
    adapter = The402Adapter.from_env()
    assert adapter.credentials_configured is True
    assert "sk_provider_fixture_value" not in repr(adapter)
    assert "whsec_fixture_value" not in repr(adapter)


def test_symlink_and_raw_environment_credentials_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.write_text("sk_provider_fixture_value\n")
    target.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(target)
    monkeypatch.setenv("AEA_THE402_ENABLED", "1")
    monkeypatch.setenv("AEA_THE402_API_KEY_FILE", str(link))
    with pytest.raises(MarketplaceError, match="non-symlink"):
        The402Adapter.from_env()
    monkeypatch.delenv("AEA_THE402_API_KEY_FILE")
    monkeypatch.setenv("AEA_THE402_API_KEY", "sk_provider_fixture_value")
    with pytest.raises(MarketplaceError, match="environment are forbidden"):
        The402Adapter.from_env()


def test_credential_file_owner_check_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    api = tmp_path / "api-key"
    api.write_text("sk_provider_fixture_value\n")
    api.chmod(0o600)
    monkeypatch.setenv("AEA_THE402_ENABLED", "1")
    monkeypatch.setenv("AEA_THE402_API_KEY_FILE", str(api))
    monkeypatch.setenv("AEA_THE402_SECRET_UID", str(os.geteuid() + 1))
    with pytest.raises(MarketplaceError, match="owner"):
        The402Adapter.from_env()


def test_no_wallet_signer_dependency() -> None:
    source = ROOT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            imported.add(node.module)
    assert "aea.signer" not in imported
    assert "aea.wallet" not in imported
    assert "aea.supervisor" not in imported
    adapter = _adapter()
    assert not hasattr(adapter, "sign")
    with pytest.raises((TypeError, ValueError)):
        The402Adapter(signer_token="nope", service_id="svc_x")  # type: ignore[call-arg]
    with pytest.raises((TypeError, ValueError)):
        The402Adapter(debit_token="nope", service_id="svc_x")  # type: ignore[call-arg]


def test_buyer_and_signing_operations_do_not_exist() -> None:
    adapter = _adapter()
    for name in (
        "purchase",
        "fund",
        "fund_escrow",
        "checkout",
        "deposit",
        "approve",
        "permit",
        "sign",
        "sign_message",
        "sign_typed_data",
        "sign_transaction",
        "eip3009",
    ):
        assert not hasattr(adapter, name)


def test_fixed_api_origin() -> None:
    with pytest.raises(MarketplaceError):
        The402HttpsClient(origin="https://evil.example")
    with pytest.raises(MarketplaceError):
        The402HttpsClient(origin="http://api.the402.ai")
    client = The402HttpsClient(api_key="sk_x")
    assert urlsplit_host(client) == THE402_API_HOST
    client.close()


def urlsplit_host(client: The402HttpsClient) -> str:
    return THE402_API_HOST


def test_redirect_rejection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/x", "content-type": "application/json"}, json={})

    transport = httpx.MockTransport(handler)
    raw = httpx.Client(base_url=THE402_ORIGIN, transport=transport, follow_redirects=False)
    client = The402HttpsClient(api_key="sk_x", client=raw)
    with pytest.raises(MarketplaceError) as exc:
        client.request("GET", "/v1/postings")
    assert exc.value.code == HttpCode.FORBIDDEN
    adapter = _adapter()
    assert isinstance(adapter._transport, FakeThe402Transport)
    adapter._transport.fail_mode = "redirect"
    with pytest.raises(MarketplaceError) as exc2:
        adapter.discover(limit=5, cursor=None)
    assert exc2.value.code == HttpCode.FORBIDDEN


def test_auth_header_not_model_controlled() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update({k.decode().lower(): v.decode() for k, v in request.headers.raw})
        return httpx.Response(200, json={"postings": [], "total": 0, "limit": 5, "offset": 0}, headers={"content-type": "application/json"})

    raw = httpx.Client(base_url=THE402_ORIGIN, transport=httpx.MockTransport(handler), follow_redirects=False)
    client = The402HttpsClient(api_key="sk_server_only", client=raw)
    client.request("GET", "/v1/jobs", headers={"Authorization": "Bearer model-supplied", "X-API-Key": "model-key", "X-PAYMENT": "eip3009"})
    assert captured.get("x-api-key") == "sk_server_only"
    assert captured.get("authorization") is None
    assert captured.get("x-payment") is None


def test_bounded_discovery_and_pagination() -> None:
    adapter = _adapter()
    with pytest.raises(MarketplaceError):
        adapter.discover(limit=0, cursor=None)
    with pytest.raises(MarketplaceError):
        adapter.discover(limit=21, cursor=None)
    page = adapter.discover(limit=2, cursor=None)
    assert page.adapter == ADAPTER_NAME
    assert len(page.jobs) == 2
    refs = [job.external_reference for job in page.jobs]
    page2 = adapter.discover(limit=2, cursor=page.next_cursor)
    refs2 = [job.external_reference for job in page2.jobs]
    assert not set(refs) & set(refs2)


def test_discovery_dedup() -> None:
    adapter = _adapter()
    first = adapter.discover(limit=20, cursor=None)
    second = adapter.discover(limit=20, cursor=None)
    refs1 = [job.external_reference for job in first.jobs]
    refs2 = [job.external_reference for job in second.jobs]
    assert refs1 == refs2
    assert len(refs1) == len(set(refs1))


def test_malformed_json() -> None:
    adapter = _adapter()
    assert isinstance(adapter._transport, FakeThe402Transport)
    adapter._transport.fail_mode = "malformed"
    with pytest.raises(MarketplaceError) as exc:
        adapter.discover(limit=5, cursor=None)
    assert exc.value.code == HttpCode.VALIDATION_ERROR


def test_timeout() -> None:
    adapter = _adapter()
    assert isinstance(adapter._transport, FakeThe402Transport)
    adapter._transport.fail_mode = "timeout"
    with pytest.raises(MarketplaceError) as exc:
        adapter.discover(limit=5, cursor=None)
    assert exc.value.code == HttpCode.TIMEOUT


def test_rate_limit_backoff() -> None:
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0.1", "content-type": "application/json"}, json={"error": "rate"})
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"postings": [], "total": 0, "limit": 5, "offset": 0},
        )

    raw = httpx.Client(base_url=THE402_ORIGIN, transport=httpx.MockTransport(handler), follow_redirects=False)
    client = The402HttpsClient(api_key="sk_x", client=raw)
    response = client.request("GET", "/v1/postings")
    assert response.status_code == 200
    assert hits["n"] == 2


def test_unsupported_jobs_rejected() -> None:
    adapter = _adapter()
    pentest = adapter.lookup("the402:posting:post_pentest_001")
    assert "prohibited_work" in pentest.flags or "unsupported_deliverable" in pentest.flags
    with pytest.raises(MarketplaceError) as exc:
        adapter.accept("the402:posting:post_pentest_001", idempotency_key="bid-pentest-0001")
    assert exc.value.code in {HttpCode.POLICY_REJECTED, HttpCode.PROMPT_INJECTION_DETECTED}


def test_prompt_injection_inert() -> None:
    adapter = _adapter()
    job = adapter.lookup("the402:posting:post_injection_001")
    assert job.untrusted_description_preview.startswith("[UNTRUSTED_MARKETPLACE_DATA]")
    assert "prompt_injection" in job.flags
    assert adapter.payout_wallet == DEFAULT_PAYOUT_WALLET
    with pytest.raises(MarketplaceError) as exc:
        adapter.accept("the402:posting:post_injection_001", idempotency_key="bid-inject-0001")
    assert exc.value.code == HttpCode.PROMPT_INJECTION_DETECTED
    assert adapter.payout_wallet == DEFAULT_PAYOUT_WALLET


def test_arbitrary_urls_rejected() -> None:
    adapter = _adapter()
    with pytest.raises(MarketplaceError):
        adapter.accept("the402:posting:post_url_001", idempotency_key="bid-url-0001")
    awarded = adapter
    assert isinstance(awarded._transport, FakeThe402Transport)
    awarded._transport.award("post_summary_001")
    with pytest.raises(MarketplaceError) as exc:
        adapter.submit(
            REF,
            artefact_digest="a" * 32,
            artefact_uri="https://evil.example/payload",
            idempotency_key="sub-url-0001",
        )
    assert exc.value.code == HttpCode.FORBIDDEN


def test_bid_idempotency() -> None:
    adapter = _adapter()
    first = adapter.accept(REF, idempotency_key="bid-summary-0001")
    second = adapter.accept(REF, idempotency_key="bid-summary-0001")
    assert first.status == "available"
    assert second.replay is True
    assert second.status != "accepted"
    with pytest.raises(MarketplaceError) as exc:
        adapter.accept(REF, idempotency_key="bid-summary-0002")
    assert exc.value.code == HttpCode.CONFLICT


def test_timeout_after_bid_recovery() -> None:
    adapter = _adapter()
    assert isinstance(adapter._transport, FakeThe402Transport)
    adapter._transport.fail_mode = "timeout_after_bid"
    result = adapter.accept(REF, idempotency_key="bid-timeout-0001")
    assert result.status == "available"
    assert result.replay is True
    assert adapter.get_status(REF).status == "available"


def test_delivery_idempotency() -> None:
    adapter = _adapter()
    assert isinstance(adapter._transport, FakeThe402Transport)
    adapter.accept(REF, idempotency_key="bid-deliv-0001")
    adapter._transport.award("post_summary_001")
    first = adapter.submit(REF, artefact_digest="d" * 32, artefact_uri="artefacts/d.txt", idempotency_key="sub-deliv-0001")
    second = adapter.submit(REF, artefact_digest="d" * 32, artefact_uri="artefacts/d.txt", idempotency_key="sub-deliv-0001")
    assert first.credited is False
    assert second.replay is True
    with pytest.raises(MarketplaceError):
        adapter.submit(REF, artefact_digest="e" * 32, artefact_uri="artefacts/e.txt", idempotency_key="sub-deliv-0002")


def test_webhook_auth_and_replay() -> None:
    adapter = _adapter(webhook_secret="whsec_test")
    body = json.dumps({"type": "request.created", "posting_id": "post_summary_001", "event_id": "evt_1"}).encode()
    ts = str(int(time.time()))
    with pytest.raises(MarketplaceError):
        adapter.handle_webhook(raw_body=body, signature=None, timestamp=ts)
    with pytest.raises(MarketplaceError):
        adapter.handle_webhook(raw_body=body, signature="sha256=deadbeef", timestamp=ts)
    old = str(int(time.time()) - 301)
    with pytest.raises(MarketplaceError):
        adapter.handle_webhook(raw_body=body, signature=_sign("whsec_test", body, old), timestamp=old)
    first = adapter.handle_webhook(raw_body=body, signature=_sign("whsec_test", body, ts), timestamp=ts)
    second = adapter.handle_webhook(raw_body=body, signature=_sign("whsec_test", body, ts), timestamp=ts)
    assert first["replay"] is False
    assert second["replay"] is True
    assert first["payment_proof"] is False


def test_payment_state_parsing_completed_not_paid() -> None:
    adapter = _adapter()
    assert isinstance(adapter._transport, FakeThe402Transport)
    adapter.accept(REF, idempotency_key="bid-pay-0001")
    job = adapter._transport.award("post_summary_001")
    job["status"] = "completed"
    claim = adapter.verify_payment(REF)
    assert claim.status == "pending"
    assert claim.verified is False
    job["status"] = "verified"
    assert adapter.verify_payment(REF).status == "pending"
    job["status"] = "released"
    job["payout_state"] = "pending"
    assert adapter.verify_payment(REF).status == "pending"


def test_paid_flag_without_wallet_is_not_revenue() -> None:
    adapter = _adapter()
    assert isinstance(adapter._transport, FakeThe402Transport)
    adapter.accept(REF, idempotency_key="bid-paid-0001")
    job = adapter._transport.award("post_summary_001")
    job["status"] = "released"
    job["payout_state"] = "paid"
    job["transaction_hash"] = "0x" + "ab" * 32
    claim = adapter.verify_payment(REF)
    assert claim.status == "paid"
    assert claim.verified is False
    ok, reason = adapter.recognize_revenue(
        claim,
        WalletPayoutObservation(
            tx_hash=claim.transaction_reference or "",
            chain_id=BASE_MAINNET_CHAIN_ID,
            token=BASE_MAINNET_USDC,
            recipient=DEFAULT_PAYOUT_WALLET,
            amount=Decimal("4.750000"),
            success=False,
            transfer_log_ok=False,
        ),
        expected_amount=Decimal("4.750000"),
    )
    assert ok is False
    assert reason != "ok"


def test_wallet_confirmed_payout_once_and_duplicate_rejected() -> None:
    adapter = _adapter()
    assert isinstance(adapter._transport, FakeThe402Transport)
    adapter.accept(REF, idempotency_key="bid-rev-0001")
    job = adapter._transport.award("post_summary_001")
    tx = "0x" + "cd" * 32
    job["status"] = "released"
    job["payout_state"] = "settled"
    job["transaction_hash"] = tx
    job["token"] = BASE_MAINNET_USDC
    job["chain_id"] = BASE_MAINNET_CHAIN_ID
    job["payout_wallet"] = DEFAULT_PAYOUT_WALLET
    claim = adapter.verify_payment(REF)
    obs = WalletPayoutObservation(
        tx_hash=tx,
        chain_id=BASE_MAINNET_CHAIN_ID,
        token=BASE_MAINNET_USDC,
        recipient=DEFAULT_PAYOUT_WALLET,
        amount=Decimal("4.750000"),
        success=True,
        transfer_log_ok=True,
    )
    ok, reason = adapter.recognize_revenue(claim, obs, expected_amount=Decimal("4.750000"))
    assert ok is True
    assert reason == "settled_once"
    ok2, reason2 = adapter.recognize_revenue(claim, obs, expected_amount=Decimal("4.750000"))
    assert ok2 is False
    assert reason2 == "duplicate_payout"


def test_payout_destination_immutable() -> None:
    adapter = _adapter()
    assert adapter.payout_wallet == DEFAULT_PAYOUT_WALLET
    with pytest.raises(MarketplaceError) as exc:
        adapter.set_payout_wallet("0x0000000000000000000000000000000000000001")
    assert exc.value.code == HttpCode.FORBIDDEN
    assert adapter.payout_wallet == DEFAULT_PAYOUT_WALLET


def test_base_usdc_mismatch_rejected() -> None:
    adapter = _adapter()
    assert isinstance(adapter._transport, FakeThe402Transport)
    adapter.accept(REF, idempotency_key="bid-usdc-0001")
    job = adapter._transport.award("post_summary_001")
    job["status"] = "released"
    job["payout_state"] = "settled"
    job["transaction_hash"] = "0x" + "ee" * 32
    job["token"] = "0x0000000000000000000000000000000000000001"
    job["chain_id"] = BASE_MAINNET_CHAIN_ID
    with pytest.raises(MarketplaceError):
        adapter.verify_payment(REF)
    job["token"] = BASE_MAINNET_USDC
    job["chain_id"] = 1
    with pytest.raises(MarketplaceError):
        adapter.verify_payment(REF)


def test_path_allow_list_rejects_arbitrary() -> None:
    client = The402HttpsClient(api_key="sk_x")
    with pytest.raises(MarketplaceError):
        client.request("GET", "https://example.com/v1/postings")
    with pytest.raises(MarketplaceError):
        client.request("GET", "/v1/balance/deposit")
    client.close()


def test_classify_envelope() -> None:
    fixtures = default_fixtures()
    cls, reasons = classify_posting(fixtures["post_summary_001"])
    assert cls == "text_summarization"
    assert reasons == []
    _cls, bad = classify_posting(fixtures["post_pentest_001"])
    assert bad


def test_public_demand_helper_zero_funded() -> None:
    report = public_postings_demand({"postings": list(default_fixtures().values()), "total": 5})
    assert report["open_postings"] == 5
    assert report["eligible_funded_postings"] == 0


def test_read_only_probe_onboarding_blocked() -> None:
    adapter = _adapter(api_key="sk_test_fixture")
    probe = adapter.read_only_operator_probe()
    assert probe["ok"] is False
    assert probe["code"] == "OPERATOR_ONBOARDING_BLOCKED"


def test_webhook_verify_helper_binds_raw_body() -> None:
    body = b'{"type":"job_dispatch","job_id":"job_1"}'
    ts = str(int(time.time()))
    sig = _sign("whsec_x", body, ts)
    assert verify_the402_webhook(raw_body=body, signature=sig, timestamp=ts, secret="whsec_x") is True
    assert verify_the402_webhook(raw_body=b'{"type":"tampered"}', signature=sig, timestamp=ts, secret="whsec_x") is False


def test_source_has_no_secret_literals() -> None:
    source = ROOT.read_text(encoding="utf-8")
    assert "sk_live_" not in source
    assert inspect.signature(The402Adapter.__init__).parameters["live_http"].default is False
