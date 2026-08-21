"""Mock signer hash binding, amount equality, and replay without HTTP."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aea.config import load_policy
from aea.signer.backend import (
    ApprovedRequest,
    SignRequest,
    WalletDebitError,
    canonical_approved_hash,
    compute_request_hmac,
)
from aea.signer.mock import MockSigner

NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
HMAC_KEY = "signer-request-hmac-key-test-0001"
WRONG_HMAC_KEY = "signer-request-hmac-key-WRONG-0001"


class _Debit:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def debit(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return "mocktx_" + "ab" * 16


@pytest.fixture(scope="module")
def loaded():
    return load_policy()


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


def _hmac(approved: ApprovedRequest, *, canonical_hash: str, policy_version: str, key: str = HMAC_KEY) -> str:
    return compute_request_hmac(
        key,
        approved_request=approved,
        canonical_hash=canonical_hash,
        policy_version=policy_version,
    )


def _sign_req(approved: ApprovedRequest, **overrides) -> SignRequest:
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
        body["request_hmac"] = _hmac(
            ar,
            canonical_hash=body["canonical_hash"],
            policy_version=body["policy_version"],
        )
    return SignRequest.model_validate(body)


def _signer(loaded, tmp_path: Path, debit: _Debit | None = None) -> tuple[MockSigner, _Debit]:
    port = debit or _Debit()
    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    signer = MockSigner(
        freeze_path=freeze_dir / "FREEZE",
        expected_policy_version=loaded.document.policy_version,
        expected_policy_hash=loaded.policy_hash,
        debit=port,
        hmac_key=HMAC_KEY,
    )
    return signer, port


def test_canonical_hash_stable_and_includes_policy_hash(loaded) -> None:
    req = _approved(loaded)
    a = canonical_approved_hash(req)
    b = canonical_approved_hash(req)
    assert a == b
    assert len(a) == 64
    other = _approved(loaded, policy_hash="b" * 64)
    assert canonical_approved_hash(other) != a


def test_force_true_rejected(loaded) -> None:
    body = _approved(loaded).model_dump(mode="json")
    body["force"] = True
    with pytest.raises(ValidationError):
        ApprovedRequest.model_validate(body)


def test_exact_request_debits_once(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    req = _sign_req(_approved(loaded))
    result = asyncio.run(signer.sign(req))
    assert result.ok is True
    assert result.tx_id.startswith("mocktx_")
    assert len(port.calls) == 1
    assert port.calls[0]["amount"] == Decimal("0.050000")
    assert port.calls[0]["destination"] == "mock:counterparty:mkt-escrow"


def test_replay_same_hash_does_not_second_debit(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    req = _sign_req(_approved(loaded))
    first = asyncio.run(signer.sign(req))
    second = asyncio.run(signer.sign(req))
    assert first.ok and second.ok
    assert first.tx_id == second.tx_id
    assert second.replay is True
    assert second.code == "IDEMPOTENT_REPLAY"
    assert len(port.calls) == 1


def test_replay_changed_body_fails(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    approved = _approved(loaded)
    first = asyncio.run(signer.sign(_sign_req(approved)))
    assert first.ok
    mutated = approved.model_copy(update={"amount": Decimal("0.060000"), "approved_amount": Decimal("0.060000")})
    mutated_req = _sign_req(mutated)
    second = asyncio.run(signer.sign(mutated_req))
    assert second.ok is False
    assert second.code == "REPLAY_APPROVED_REQUEST"
    assert len(port.calls) == 1


def test_hash_mismatch_fails(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    approved = _approved(loaded)
    req = _sign_req(approved, canonical_hash="a" * 64)
    result = asyncio.run(signer.sign(req))
    assert result.code == "REPLAY_APPROVED_REQUEST"
    assert port.calls == []


def test_amount_must_equal_approved_amount(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    approved = _approved(loaded, amount="0.050000", approved_amount="0.040000")
    result = asyncio.run(signer.sign(_sign_req(approved)))
    assert result.code == "AMOUNT_MISMATCH"
    assert port.calls == []


def test_policy_version_hash_pin(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    bad_ver = _approved(loaded, policy_version="policy/v9.9.9")
    r1 = asyncio.run(signer.sign(_sign_req(bad_ver, policy_version="policy/v9.9.9")))
    assert r1.code == "POLICY_TAMPER"
    bad_hash = _approved(loaded, policy_hash="c" * 64)
    r2 = asyncio.run(signer.sign(_sign_req(bad_hash)))
    assert r2.code == "POLICY_TAMPER"
    assert port.calls == []


def test_signer_disabled(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    signer.set_enabled(False)
    result = asyncio.run(signer.sign(_sign_req(_approved(loaded))))
    assert result.code == "SIGNER_DISABLED"
    assert port.calls == []


def test_freeze_file_blocks_debit(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    Path(signer._freeze_path).write_text("1\n", encoding="utf-8")
    result = asyncio.run(signer.sign(_sign_req(_approved(loaded))))
    assert result.code == "AGENT_FROZEN"
    assert port.calls == []


def test_wallet_failure_does_not_record_success(loaded, tmp_path: Path) -> None:
    import asyncio

    class Boom(_Debit):
        async def debit(self, **kwargs) -> str:
            raise WalletDebitError("NETWORK_FAILURE")

    signer, _ = _signer(loaded, tmp_path, debit=Boom())
    req = _sign_req(_approved(loaded))
    result = asyncio.run(signer.sign(req))
    assert result.code == "NETWORK_FAILURE"
    retry_port = _Debit()
    signer._debit = retry_port
    second = asyncio.run(signer.sign(req))
    assert second.ok is True
    assert len(retry_port.calls) == 1


def test_debit_port_must_not_expose_credit(loaded, tmp_path: Path) -> None:
    class Both(_Debit):
        async def credit(self, **kwargs) -> str:
            return "nope"

    freeze_dir = tmp_path / "freeze"
    freeze_dir.mkdir()
    with pytest.raises(ValueError, match="credit"):
        MockSigner(
            freeze_path=freeze_dir / "FREEZE",
            expected_policy_version=loaded.document.policy_version,
            expected_policy_hash=loaded.policy_hash,
            debit=Both(),
            hmac_key=HMAC_KEY,
        )


def test_missing_hmac_rejected_by_schema(loaded) -> None:
    approved = _approved(loaded)
    with pytest.raises(ValidationError):
        SignRequest.model_validate(
            {
                "approved_request": approved.model_dump(mode="json"),
                "canonical_hash": canonical_approved_hash(approved),
                "policy_version": approved.policy_version,
            }
        )


def test_wrong_hmac_fails_before_debit(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    result = asyncio.run(signer.sign(_sign_req(_approved(loaded), request_hmac="ab" * 32)))
    assert result.code == "UNAUTHENTICATED"
    assert port.calls == []


def test_hmac_from_wrong_key_fails(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    approved = _approved(loaded)
    digest = canonical_approved_hash(approved)
    req = _sign_req(
        approved,
        request_hmac=_hmac(
            approved,
            canonical_hash=digest,
            policy_version=approved.policy_version,
            key=WRONG_HMAC_KEY,
        ),
    )
    result = asyncio.run(signer.sign(req))
    assert result.code == "UNAUTHENTICATED"
    assert port.calls == []


def test_mutation_invalidates_hmac(loaded, tmp_path: Path) -> None:
    import asyncio

    signer, port = _signer(loaded, tmp_path)
    approved = _approved(loaded)
    original = _sign_req(approved)
    dumped = approved.model_dump(mode="json")
    dumped["amount"] = "0.060000"
    dumped["approved_amount"] = "0.060000"
    mutated = ApprovedRequest.model_validate(dumped)
    replay_mac = SignRequest.model_validate(
        {
            "approved_request": mutated.model_dump(mode="json"),
            "canonical_hash": canonical_approved_hash(mutated),
            "policy_version": mutated.policy_version,
            "request_hmac": original.request_hmac,
        }
    )
    result = asyncio.run(signer.sign(replay_mac))
    assert result.code == "UNAUTHENTICATED"
    assert port.calls == []


def test_hmac_artifact_includes_policy_hash_and_signer_hash(loaded) -> None:
    from aea.signer.backend import signer_approval_artifact

    approved = _approved(loaded)
    digest = canonical_approved_hash(approved)
    artifact = signer_approval_artifact(
        approved_request=approved,
        canonical_hash=digest,
        policy_version=approved.policy_version,
    )
    assert artifact["canonical_hash"] == digest
    assert artifact["policy_hash"] == approved.policy_hash
    assert artifact["policy_version"] == approved.policy_version
    assert artifact["approved_request"]["request_id"] == str(approved.request_id)
    a = compute_request_hmac(
        HMAC_KEY,
        approved_request=approved,
        canonical_hash=digest,
        policy_version=approved.policy_version,
    )
    b = compute_request_hmac(
        HMAC_KEY,
        approved_request=approved,
        canonical_hash=digest,
        policy_version=approved.policy_version,
    )
    assert a == b
    assert len(a) == 64


def test_no_solana_or_llm_imports() -> None:
    import aea.signer.backend as backend
    import aea.signer.mock as mock
    import aea.signer.service as service

    for module in (backend, mock, service):
        assert "solana" not in module.__dict__
        assert "solders" not in module.__dict__
        assert "openai" not in module.__dict__
