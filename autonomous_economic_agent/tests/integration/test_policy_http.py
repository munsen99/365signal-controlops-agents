"""HTTP policy service on :18701 contract. ASGI in-process; no live wallet."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from aea.config import load_policy
from aea.policy.engine import evaluate
from aea.policy.service import create_app
from aea.types import PolicyInput

NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
CONTROL = "control-token-test"
MODEL = "model-token-test"


@pytest.fixture(scope="module")
def loaded():
    return load_policy()


@pytest.fixture
def app(loaded):
    return create_app(
        control_token=CONTROL,
        model_token=MODEL,
        loaded=loaded,
        now=NOW,
    )


def _body(loaded, **overrides) -> dict:
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


def _request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://policy") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def test_health_unauthenticated(app) -> None:
    response = _request(app, "GET", "/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_evaluate_missing_token(app, loaded) -> None:
    response = _request(app, "POST", "/v1/evaluate", json=_body(loaded))
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_evaluate_wrong_token(app, loaded) -> None:
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=_body(loaded),
        headers={"Authorization": "Bearer not-a-known-token"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_evaluate_model_token_forbidden(app, loaded) -> None:
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=_body(loaded),
        headers={"Authorization": f"Bearer {MODEL}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_evaluate_force_true_validation_error(app, loaded) -> None:
    body = _body(loaded)
    body["force"] = True
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=body,
        headers={"Authorization": f"Bearer {CONTROL}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_evaluate_malformed_json(app) -> None:
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        content=b"{not-json",
        headers={
            "Authorization": f"Bearer {CONTROL}",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_http_matches_engine_approve(app, loaded) -> None:
    body = _body(loaded)
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=body,
        headers={"Authorization": f"Bearer {CONTROL}"},
    )
    assert response.status_code == 200
    payload = response.json()
    inp = PolicyInput.model_validate(body)
    direct = evaluate(
        inp,
        loaded.document,
        effective_policy_hash=loaded.policy_hash,
        now=NOW,
        destination=loaded.classify(inp.destination),
    )
    assert payload["ok"] is True
    assert payload["code"] == "OK"
    assert payload["decision"] == direct.decision == "approved"
    assert payload["reason_code"] == direct.reason_code
    assert payload["canonical_request_hash"] == direct.canonical_request_hash
    assert payload["approved_amount"] == "0.050000"


def test_http_matches_engine_over_limit(app, loaded) -> None:
    body = _body(loaded, amount="1.000001")
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=body,
        headers={"Authorization": f"Bearer {CONTROL}"},
    )
    inp = PolicyInput.model_validate(body)
    direct = evaluate(
        inp,
        loaded.document,
        effective_policy_hash=loaded.policy_hash,
        now=NOW,
        destination=loaded.classify(inp.destination),
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] is False
    assert payload["code"] == "POLICY_REJECTED"
    assert payload["reason_code"] == direct.reason_code == "MAX_OUTBOUND_EXCEEDED"


def test_http_policy_hash_mismatch(app, loaded) -> None:
    body = _body(loaded, policy_hash="c" * 64)
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=body,
        headers={"Authorization": f"Bearer {CONTROL}"},
    )
    assert response.json()["reason_code"] == "POLICY_TAMPER"


def test_http_policy_version_mismatch(app, loaded) -> None:
    body = _body(loaded, policy_version="policy/v9.9.9")
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=body,
        headers={"Authorization": f"Bearer {CONTROL}"},
    )
    assert response.json()["reason_code"] == "POLICY_TAMPER"


def test_http_frozen_input(app, loaded) -> None:
    body = _body(loaded, frozen=True)
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=body,
        headers={"Authorization": f"Bearer {CONTROL}"},
    )
    assert response.json()["reason_code"] == "FROZEN"


def test_http_signer_disabled(app, loaded) -> None:
    body = _body(loaded, signer_enabled=False)
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=body,
        headers={"Authorization": f"Bearer {CONTROL}"},
    )
    assert response.json()["reason_code"] == "SIGNER_DISABLED"


def test_http_freeze_file_overrides_unfrozen_body(loaded, tmp_path: Path) -> None:
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    freeze_file = freeze_dir / "FREEZE"
    freeze_file.write_text("1\n", encoding="utf-8")
    app = create_app(
        control_token=CONTROL,
        model_token=MODEL,
        loaded=loaded,
        freeze_path=freeze_file,
        now=NOW,
    )
    body = _body(loaded, frozen=False)
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=body,
        headers={"Authorization": f"Bearer {CONTROL}"},
    )
    assert response.json()["reason_code"] == "FROZEN"


def test_http_unreadable_freeze_dir_fail_closed(loaded, tmp_path: Path) -> None:
    missing = tmp_path / "no-such-dir" / "FREEZE"
    app = create_app(
        control_token=CONTROL,
        model_token=MODEL,
        loaded=loaded,
        freeze_path=missing,
        now=NOW,
    )
    response = _request(
        app,
        "POST",
        "/v1/evaluate",
        json=_body(loaded),
        headers={"Authorization": f"Bearer {CONTROL}"},
    )
    assert response.json()["reason_code"] == "FROZEN"
