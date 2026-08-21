"""Isolated signer HTTP + freeze + wallet debit boundary (M0 PR5)."""

from __future__ import annotations

import asyncio
import inspect
import os
import stat
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import uvicorn

from aea.config import load_policy
from aea.signer.backend import ApprovedRequest, canonical_approved_hash, compute_request_hmac
from aea.signer.mock import MockSigner
from aea.signer.service import (
    SIGNER_SOCKET_MODE,
    AsgiWalletDebit,
    create_app,
    create_app_from_env,
    prepare_unix_socket,
    socket_mode,
)
from aea.wallet.mock import MockWallet
from aea.wallet.service import create_app as create_wallet_app

NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)

SIGNER = "signer-token-test"
HMAC_KEY = "signer-request-hmac-key-test-0001"
WRONG_HMAC_KEY = "signer-request-hmac-key-WRONG-0001"
DEBIT = "wallet-debit-token-test"
CREDIT = "wallet-credit-token-test"
READ = "wallet-read-token-test"
MODEL = "model-token-test"
CONTROL = "control-token-test"
SUPERVISOR = "supervisor-token-test"
POLICY = "policy-token-test"

ADMIN_PW = Path.home() / ".config/controlops/postgres/postgres_password"


@pytest.fixture(scope="module")
def loaded():
    return load_policy()


@pytest.fixture
def wallet() -> MockWallet:
    return MockWallet(
        phase="A",
        opening={"USDC": Decimal("20"), "SOL": Decimal("0.05")},
    )


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
def freeze_dir(tmp_path: Path) -> Path:
    path = tmp_path / "freeze"
    path.mkdir()
    return path


@pytest.fixture
def stack(wallet, wallet_app, freeze_dir, loaded):
    debit = AsgiWalletDebit(wallet_app, DEBIT)
    signer = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=debit,
        hmac_key=HMAC_KEY,
    )
    app = create_app(
        signer=signer,
        signer_token=SIGNER,
        debit_token=DEBIT,
        model_token=MODEL,
        control_token=CONTROL,
        supervisor_token=SUPERVISOR,
        policy_token=POLICY,
        read_token=READ,
        credit_token=CREDIT,
    )
    return SimpleNamespace(
        app=app,
        signer=signer,
        wallet=wallet,
        wallet_app=wallet_app,
        freeze_dir=freeze_dir,
        loaded=loaded,
        debit=debit,
    )


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


def _sign_body(approved: ApprovedRequest, **overrides) -> dict:
    body = {
        "approved_request": approved.model_dump(mode="json"),
        "canonical_hash": canonical_approved_hash(approved),
        "policy_version": approved.policy_version,
    }
    body.update(overrides)
    if "request_hmac" not in overrides:
        ar = body["approved_request"]
        if isinstance(ar, dict):
            ar = ApprovedRequest.model_validate(ar)
        body["request_hmac"] = compute_request_hmac(
            HMAC_KEY,
            approved_request=ar,
            canonical_hash=body["canonical_hash"],
            policy_version=body["policy_version"],
        )
    return body


def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://signer") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def _wallet_request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wallet") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_no_secrets(response: httpx.Response) -> None:
    blob = response.text
    for needle in (
        SIGNER,
        HMAC_KEY,
        WRONG_HMAC_KEY,
        DEBIT,
        CREDIT,
        READ,
        MODEL,
        CONTROL,
        SUPERVISOR,
        POLICY,
        "private_key",
        "seed_phrase",
        "mnemonic",
        "AEA_WALLET_DEBIT_TOKEN",
        "AEA_SIGNER_TOKEN",
        "AEA_SIGNER_HMAC_KEY",
    ):
        assert needle not in blob


def test_health_unauthenticated(stack) -> None:
    response = _request(stack.app, "GET", "/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["signer_enabled"] is True
    assert response.json()["frozen"] is False
    _assert_no_secrets(response)


def test_sign_requires_signer_token(stack, loaded) -> None:
    body = _sign_body(_approved(loaded))
    missing = _request(stack.app, "POST", "/v1/sign", json=body)
    assert missing.status_code == 401
    assert missing.json()["code"] == "UNAUTHENTICATED"
    unknown = _request(
        stack.app,
        "POST",
        "/v1/sign",
        json=body,
        headers=_auth("not-a-known-token"),
    )
    assert unknown.status_code == 401


def test_model_control_and_other_tokens_cannot_sign(stack, loaded) -> None:
    body = _sign_body(_approved(loaded))
    for token in (MODEL, CONTROL, SUPERVISOR, POLICY, READ, CREDIT, DEBIT):
        response = _request(
            stack.app, "POST", "/v1/sign", json=body, headers=_auth(token)
        )
        assert response.status_code == 403, token
        assert response.json()["code"] == "FORBIDDEN"
        _assert_no_secrets(response)
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_valid_token_and_hmac_succeeds(stack, loaded) -> None:
    response = _request(
        stack.app,
        "POST",
        "/v1/sign",
        json=_sign_body(_approved(loaded)),
        headers=_auth(SIGNER),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["tx_id"].startswith("mocktx_")
    _assert_no_secrets(response)


def test_valid_token_missing_hmac_fails(stack, loaded) -> None:
    body = _sign_body(_approved(loaded))
    del body["request_hmac"]
    response = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")
    _assert_no_secrets(response)


def test_valid_token_malformed_hmac_fails(stack, loaded) -> None:
    body = _sign_body(_approved(loaded), request_hmac="not-a-mac")
    response = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_valid_token_wrong_hmac_fails(stack, loaded) -> None:
    body = _sign_body(_approved(loaded), request_hmac="ab" * 32)
    response = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")
    _assert_no_secrets(response)


def test_valid_hmac_wrong_token_fails(stack, loaded) -> None:
    body = _sign_body(_approved(loaded))
    for token in (MODEL, CONTROL, DEBIT, CREDIT, READ, SUPERVISOR, POLICY, HMAC_KEY):
        response = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(token))
        assert response.status_code in {401, 403}, token
        assert response.json()["code"] in {"UNAUTHENTICATED", "FORBIDDEN"}
        _assert_no_secrets(response)
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_hmac_signed_with_wallet_or_bearer_secret_fails(stack, loaded) -> None:
    approved = _approved(loaded)
    digest = canonical_approved_hash(approved)
    for key in (SIGNER, DEBIT, CREDIT, READ, MODEL, CONTROL):
        padded = (key + "x" * 32)[:32]
        mac = compute_request_hmac(
            padded,
            approved_request=approved,
            canonical_hash=digest,
            policy_version=approved.policy_version,
        )
        body = _sign_body(approved, request_hmac=mac)
        response = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
        assert response.json()["code"] == "UNAUTHENTICATED", key
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_field_mutation_invalidates_hmac(stack, loaded) -> None:
    approved = _approved(loaded)
    original = _sign_body(approved)
    dumped = approved.model_dump(mode="json")
    dumped["destination"] = "mock:fee_payer"
    mutated = ApprovedRequest.model_validate(dumped)
    body = {
        "approved_request": mutated.model_dump(mode="json"),
        "canonical_hash": canonical_approved_hash(mutated),
        "policy_version": mutated.policy_version,
        "request_hmac": original["request_hmac"],
    }
    response = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_hmac_key_cannot_equal_signer_or_debit_token(
    wallet_app, loaded, freeze_dir
) -> None:
    long_signer = "signer-token-test-padded-to-32ok"
    assert len(long_signer) >= 32
    signer = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=long_signer,
    )
    with pytest.raises(ValueError, match="distinct"):
        create_app(signer=signer, signer_token=long_signer, debit_token=DEBIT)


def test_control_policy_model_cannot_debit_wallet_directly(stack) -> None:
    body = {
        "asset": "USDC",
        "amount": "0.010000",
        "destination": "mock:counterparty:mkt-escrow",
        "reason": "marketplace_acceptance_fee",
        "idempotency_key": "direct-debit-forbidden",
    }
    for token in (MODEL, CONTROL, READ, CREDIT):
        response = _wallet_request(
            stack.wallet_app,
            "POST",
            "/v1/wallet/debit",
            json=body,
            headers=_auth(token),
        )
        assert response.status_code == 403, token
    for token in (SIGNER, SUPERVISOR, POLICY):
        response = _wallet_request(
            stack.wallet_app,
            "POST",
            "/v1/wallet/debit",
            json=body,
            headers=_auth(token),
        )
        assert response.status_code == 401, token
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_signer_debit_token_cannot_credit(stack) -> None:
    response = _wallet_request(
        stack.wallet_app,
        "POST",
        "/v1/wallet/credit",
        json={
            "asset": "USDC",
            "amount": "1.000000",
            "reason": "marketplace_settlement",
            "idempotency_key": "signer-cannot-credit",
        },
        headers=_auth(DEBIT),
    )
    assert response.status_code == 403
    missing = _request(
        stack.app,
        "POST",
        "/v1/wallet/credit",
        json={"asset": "USDC", "amount": "1.000000", "reason": "x", "idempotency_key": "nope-credit"},
        headers=_auth(SIGNER),
    )
    assert missing.status_code == 404
    assert not hasattr(stack.debit, "credit")
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_exact_approved_request_debits(stack, loaded) -> None:
    before = stack.wallet.get_balances()["USDC"]
    approved = _approved(loaded)
    response = _request(
        stack.app, "POST", "/v1/sign", json=_sign_body(approved), headers=_auth(SIGNER)
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["code"] == "OK"
    assert payload["tx_id"].startswith("mocktx_")
    assert stack.wallet.get_balances()["USDC"] == before - Decimal("0.050000")
    _assert_no_secrets(response)


def test_replay_same_request_no_double_debit(stack, loaded) -> None:
    approved = _approved(loaded)
    body = _sign_body(approved)
    first = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
    second = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
    assert first.json()["tx_id"] == second.json()["tx_id"]
    assert second.json()["code"] == "IDEMPOTENT_REPLAY"
    assert second.json()["replay"] is True
    assert stack.wallet.get_balances()["USDC"] == Decimal("19.950000")


def test_same_request_id_changed_fields_fail(stack, loaded) -> None:
    approved = _approved(loaded, amount="0.050000", approved_amount="0.050000")
    first = _request(
        stack.app, "POST", "/v1/sign", json=_sign_body(approved), headers=_auth(SIGNER)
    )
    assert first.json()["ok"] is True
    before = stack.wallet.get_balances()["USDC"]
    for field, value in (
        ("amount", "0.060000"),
        ("destination", "mock:fee_payer"),
        ("asset", "SOL"),
        ("job_id", str(uuid4())),
        ("purpose", "network_fee"),
    ):
        dumped = approved.model_dump(mode="json")
        dumped[field] = value
        if field == "amount":
            dumped["approved_amount"] = value
        if field == "asset":
            dumped["amount"] = "0.010000"
            dumped["approved_amount"] = "0.010000"
            dumped["purpose"] = "network_fee"
        mutated = ApprovedRequest.model_validate(dumped)
        body = _sign_body(mutated)
        response = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
        assert response.json()["code"] == "REPLAY_APPROVED_REQUEST", field
        assert stack.wallet.get_balances()["USDC"] == before


def test_approval_hash_mismatch(stack, loaded) -> None:
    approved = _approved(loaded)
    body = _sign_body(approved, canonical_hash="d" * 64)
    response = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
    assert response.json()["code"] == "REPLAY_APPROVED_REQUEST"
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_policy_version_and_hash_mismatch(stack, loaded) -> None:
    bad_version = _approved(loaded, policy_version="policy/v9.9.9")
    r1 = _request(
        stack.app,
        "POST",
        "/v1/sign",
        json=_sign_body(bad_version, policy_version="policy/v9.9.9"),
        headers=_auth(SIGNER),
    )
    assert r1.json()["code"] == "POLICY_TAMPER"
    bad_hash = _approved(loaded, policy_hash="e" * 64)
    r2 = _request(
        stack.app, "POST", "/v1/sign", json=_sign_body(bad_hash), headers=_auth(SIGNER)
    )
    assert r2.json()["code"] == "POLICY_TAMPER"
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_amount_expansion_rejected(stack, loaded) -> None:
    approved = _approved(loaded, amount="1.000000", approved_amount="0.050000")
    response = _request(
        stack.app, "POST", "/v1/sign", json=_sign_body(approved), headers=_auth(SIGNER)
    )
    assert response.json()["code"] == "AMOUNT_MISMATCH"
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_force_true_validation_error(stack, loaded) -> None:
    body = _sign_body(_approved(loaded))
    body["force"] = True
    response = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_agent_frozen_file(stack, loaded) -> None:
    (stack.freeze_dir / "FREEZE").write_text("1\n", encoding="utf-8")
    response = _request(
        stack.app,
        "POST",
        "/v1/sign",
        json=_sign_body(_approved(loaded)),
        headers=_auth(SIGNER),
    )
    assert response.json()["ok"] is False
    assert response.json()["code"] == "AGENT_FROZEN"
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_signer_disabled_via_supervisor(stack, loaded) -> None:
    denied = _request(stack.app, "POST", "/v1/disable", headers=_auth(MODEL))
    assert denied.status_code == 403
    control = _request(stack.app, "POST", "/v1/disable", headers=_auth(CONTROL))
    assert control.status_code == 403
    ok = _request(stack.app, "POST", "/v1/disable", headers=_auth(SUPERVISOR))
    assert ok.status_code == 200
    assert ok.json()["signer_enabled"] is False
    response = _request(
        stack.app,
        "POST",
        "/v1/sign",
        json=_sign_body(_approved(loaded)),
        headers=_auth(SIGNER),
    )
    assert response.json()["code"] == "SIGNER_DISABLED"
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def test_freeze_after_approval_before_debit(stack, loaded) -> None:
    approved = _approved(loaded)
    body = _sign_body(approved)
    assert inspect_source_unfrozen(stack)
    (stack.freeze_dir / "FREEZE").write_text("frozen\n", encoding="utf-8")
    response = _request(stack.app, "POST", "/v1/sign", json=body, headers=_auth(SIGNER))
    assert response.json()["code"] == "AGENT_FROZEN"
    assert stack.wallet.get_balances()["USDC"] == Decimal("20")


def inspect_source_unfrozen(stack) -> bool:
    return not (stack.freeze_dir / "FREEZE").exists()


def test_missing_freeze_state_fail_closed(wallet_app, loaded, tmp_path: Path) -> None:
    signer = MockSigner(
        freeze_path=None,
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=HMAC_KEY,
    )
    app = create_app(signer=signer, signer_token=SIGNER, debit_token=DEBIT)
    response = _request(
        app, "POST", "/v1/sign", json=_sign_body(_approved(loaded)), headers=_auth(SIGNER)
    )
    assert response.json()["code"] == "AGENT_FROZEN"
    missing_dir = tmp_path / "absent" / "FREEZE"
    signer2 = MockSigner(
        freeze_path=missing_dir,
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=HMAC_KEY,
    )
    app2 = create_app(signer=signer2, signer_token=SIGNER, debit_token=DEBIT)
    response2 = _request(
        app2, "POST", "/v1/sign", json=_sign_body(_approved(loaded)), headers=_auth(SIGNER)
    )
    assert response2.json()["code"] == "AGENT_FROZEN"


def test_unreadable_freeze_state(wallet_app, loaded, tmp_path: Path, wallet: MockWallet) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    signer = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=HMAC_KEY,
    )
    app = create_app(signer=signer, signer_token=SIGNER, debit_token=DEBIT)
    os.chmod(freeze_dir, 0)
    try:
        response = _request(
            app, "POST", "/v1/sign", json=_sign_body(_approved(loaded)), headers=_auth(SIGNER)
        )
        assert response.json()["code"] == "AGENT_FROZEN"
        assert wallet.get_balances()["USDC"] == Decimal("20")
    finally:
        os.chmod(freeze_dir, 0o700)


def test_malformed_freeze_state(wallet_app, loaded, tmp_path: Path, wallet: MockWallet) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    (freeze_dir / "FREEZE").mkdir()
    signer = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=HMAC_KEY,
    )
    app = create_app(signer=signer, signer_token=SIGNER, debit_token=DEBIT)
    response = _request(
        app, "POST", "/v1/sign", json=_sign_body(_approved(loaded)), headers=_auth(SIGNER)
    )
    assert response.json()["code"] == "AGENT_FROZEN"
    assert wallet.get_balances()["USDC"] == Decimal("20")


def test_freeze_path_symlink(wallet_app, loaded, tmp_path: Path, wallet: MockWallet) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    signer = MockSigner(
        freeze_path=link / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=HMAC_KEY,
    )
    app = create_app(signer=signer, signer_token=SIGNER, debit_token=DEBIT)
    response = _request(
        app, "POST", "/v1/sign", json=_sign_body(_approved(loaded)), headers=_auth(SIGNER)
    )
    assert response.json()["code"] == "AGENT_FROZEN"
    assert wallet.get_balances()["USDC"] == Decimal("20")


def test_inconsistent_db_file_freeze(wallet_app, loaded, freeze_dir, wallet: MockWallet) -> None:
    signer = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=HMAC_KEY,
        db_frozen_reader=lambda: True,
    )
    app = create_app(signer=signer, signer_token=SIGNER, debit_token=DEBIT)
    response = _request(
        app, "POST", "/v1/sign", json=_sign_body(_approved(loaded)), headers=_auth(SIGNER)
    )
    assert response.json()["code"] == "AGENT_FROZEN"
    (freeze_dir / "FREEZE").write_text("1\n", encoding="utf-8")
    signer2 = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=HMAC_KEY,
        db_frozen_reader=lambda: False,
    )
    app2 = create_app(signer=signer2, signer_token=SIGNER, debit_token=DEBIT)
    stale = _request(
        app2, "POST", "/v1/sign", json=_sign_body(_approved(loaded)), headers=_auth(SIGNER)
    )
    assert stale.json()["code"] == "AGENT_FROZEN"
    unread = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=HMAC_KEY,
        db_frozen_reader=lambda: None,
    )
    app3 = create_app(signer=unread, signer_token=SIGNER, debit_token=DEBIT)
    r3 = _request(
        app3, "POST", "/v1/sign", json=_sign_body(_approved(loaded)), headers=_auth(SIGNER)
    )
    assert r3.json()["code"] == "AGENT_FROZEN"
    assert wallet.get_balances()["USDC"] == Decimal("20")


def test_wallet_network_failure_after_valid_request(stack, loaded) -> None:
    before = stack.wallet.get_balances()["USDC"]
    stack.wallet.enable_faults()
    stack.wallet.set_fault("network")
    response = _request(
        stack.app,
        "POST",
        "/v1/sign",
        json=_sign_body(_approved(loaded)),
        headers=_auth(SIGNER),
    )
    assert response.json()["code"] == "NETWORK_FAILURE"
    assert response.status_code == 503
    assert stack.wallet.get_balances()["USDC"] == before
    stack.wallet.set_fault("none")
    retry = _request(
        stack.app,
        "POST",
        "/v1/sign",
        json=_sign_body(_approved(loaded)),
        headers=_auth(SIGNER),
    )
    assert retry.json()["ok"] is True
    assert stack.wallet.get_balances()["USDC"] == before - Decimal("0.050000")


def test_no_export_or_key_routes(stack) -> None:
    for path in ("/v1/export_key", "/v1/sign_message", "/v1/wallet/debit", "/secrets"):
        response = _request(stack.app, "POST", path, json={}, headers=_auth(SIGNER))
        assert response.status_code == 404
        _assert_no_secrets(response)


def test_create_app_from_env_does_not_load_credit_token() -> None:
    src = inspect.getsource(create_app_from_env)
    assert "credit_token=None" in src
    assert "AEA_WALLET_CREDIT_TOKEN" not in src
    assert "allow_faults" not in src
    assert "AEA_SIGNER_HMAC_KEY" in src
    assert "AEA_SIGNER_HMAC_KEY_FILE" in src


def test_unix_socket_mode_and_sign(tmp_path: Path, loaded, wallet, wallet_app) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    signer = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=AsgiWalletDebit(wallet_app, DEBIT),
        hmac_key=HMAC_KEY,
    )
    app = create_app(
        signer=signer,
        signer_token=SIGNER,
        debit_token=DEBIT,
        model_token=MODEL,
        control_token=CONTROL,
    )
    sock_path = tmp_path / "signer.sock"
    sock = prepare_unix_socket(sock_path)
    assert socket_mode(sock_path) == SIGNER_SOCKET_MODE
    assert stat.S_IMODE(os.stat(sock_path).st_mode) == 0o660
    config = uvicorn.Config(app, fd=sock.fileno(), log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        transport = httpx.HTTPTransport(uds=str(sock_path))
        with httpx.Client(transport=transport, base_url="http://signer") as client:
            health = client.get("/health")
            assert health.status_code == 200
            forbidden = client.post(
                "/v1/sign",
                json=_sign_body(_approved(loaded)),
                headers=_auth(MODEL),
            )
            assert forbidden.status_code == 403
            ok = client.post(
                "/v1/sign",
                json=_sign_body(_approved(loaded)),
                headers=_auth(SIGNER),
            )
            assert ok.status_code == 200
            assert ok.json()["ok"] is True
            assert "mocktx_" in ok.json()["tx_id"]
            assert SIGNER not in ok.text
            assert DEBIT not in ok.text
        assert wallet.get_balances()["USDC"] == Decimal("19.950000")
    finally:
        server.should_exit = True
        thread.join(timeout=5)


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
def test_live_supervisor_state_inconsistent_with_file(
    wallet_app, loaded, freeze_dir, wallet: MockWallet
) -> None:
    import psycopg

    conn = psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="controlops",
        user="controlops_admin",
        password=ADMIN_PW.read_text(encoding="utf-8").rstrip("\n"),
    )
    try:
        conn.execute(
            "UPDATE economic.supervisor_state SET frozen = true, updated_by = %s WHERE singleton",
            ("pr5-signer-test",),
        )
        conn.commit()

        def read_db() -> bool:
            row = conn.execute(
                "SELECT frozen FROM economic.supervisor_state WHERE singleton"
            ).fetchone()
            if row is None:
                return None  # type: ignore[return-value]
            return bool(row[0])

        signer = MockSigner(
            freeze_path=freeze_dir / "FREEZE",
            expected_policy_version=loaded.document.policy_version,
            expected_policy_hash=loaded.policy_hash,
            debit=AsgiWalletDebit(wallet_app, DEBIT),
            hmac_key=HMAC_KEY,
            db_frozen_reader=read_db,
        )
        app = create_app(signer=signer, signer_token=SIGNER, debit_token=DEBIT)
        response = _request(
            app, "POST", "/v1/sign", json=_sign_body(_approved(loaded)), headers=_auth(SIGNER)
        )
        assert response.json()["code"] == "AGENT_FROZEN"
        assert wallet.get_balances()["USDC"] == Decimal("20")
    finally:
        conn.execute(
            "UPDATE economic.supervisor_state SET frozen = false, updated_by = %s WHERE singleton",
            ("pr5-signer-test-reset",),
        )
        conn.commit()
        conn.close()
