"""Phase A mock marketplace. Deterministic fixtures. No LLM. No ledger writes."""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any

from aea.hashing import sha256_hex
from aea.marketplace.protocol import (
    AcceptResult,
    Counterparty,
    DiscoveredJob,
    DiscoverPage,
    JobStatus,
    MarketplaceError,
    MarketplaceMoney,
    PaymentClaim,
    PaymentTerms,
    Reputation,
    Requirements,
    SubmitResult,
)
from aea.marketplace.sanitise import sanitise_marketplace_text
from aea.policy.reasons import HttpCode
from aea.wallet.mock import new_tx_id

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "e2e" / "fixtures" / "marketplace_jobs.json"
)

CreditFn = Callable[..., Any]


def _fake_tx_id(external_reference: str) -> str:
    return "mocktx_" + sha256_hex(f"fake:{external_reference}".encode("utf-8"))[:32]


class MockMarketplace:
    """In-process adapter keyed by the M1 fixture pack."""

    name = "mock"

    def __init__(
        self,
        *,
        fixture_path: Path | None = None,
        credit_fn: CreditFn | None = None,
    ) -> None:
        if hasattr(credit_fn, "debit"):
            raise ValueError("marketplace credit rail must not expose debit")
        self._credit_fn = credit_fn
        self._lock = Lock()
        path = fixture_path or DEFAULT_FIXTURE_PATH
        raw = json.loads(path.read_text(encoding="utf-8"))
        jobs = raw.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise ValueError("marketplace fixture pack must contain jobs")
        self._catalog: dict[str, dict[str, Any]] = {}
        for item in jobs:
            ref = str(item["external_reference"])
            self._catalog[ref] = dict(item)
        self._state: dict[str, str] = {ref: "available" for ref in self._catalog}
        self._accept_keys: dict[str, str] = {}
        self._submit_keys: dict[str, tuple[str, str, str]] = {}
        self._txs: dict[str, str] = {}

    def _job(self, external_reference: str) -> dict[str, Any]:
        job = self._catalog.get(external_reference)
        if job is None:
            raise MarketplaceError(HttpCode.NOT_FOUND, "unknown job")
        return job

    def _discovered(self, job: dict[str, Any]) -> DiscoveredJob:
        sanitised = sanitise_marketplace_text(str(job["description"]))
        asset = str(job["payment_asset"])
        revenue = MarketplaceMoney.model_validate(
            {"amount": job["expected_revenue"], "asset": asset}
        )
        cost = MarketplaceMoney.model_validate(
            {"amount": job["estimated_cost"], "asset": "USDC"}
        )
        return DiscoveredJob.model_validate(
            {
                "external_reference": job["external_reference"],
                "title": job["title"],
                "description_hash": sanitised.description_hash,
                "untrusted_description_preview": sanitised.wrapped,
                "expected_revenue": revenue.model_dump(mode="json"),
                "estimated_cost": cost.model_dump(mode="json"),
                "payment_asset": asset,
                "payment_terms": job["payment_terms"],
                "counterparty_id": job["counterparty_id"],
                "counterparty_reputation": job["counterparty_reputation"],
                "worker": job["worker"],
                "flags": list(sanitised.flags),
                "credits_wallet_on_submit": bool(job["credits_wallet_on_submit"]),
            }
        )

    def lookup(self, external_reference: str) -> DiscoveredJob:
        return self._discovered(self._job(external_reference))

    def discover(self, *, limit: int = 10, cursor: str | None = None) -> DiscoverPage:
        if limit < 1 or limit > 20:
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "limit must be 1-20")
        refs = list(self._catalog)
        offset = 0
        if cursor:
            try:
                offset = int(cursor)
            except ValueError as exc:
                raise MarketplaceError(HttpCode.VALIDATION_ERROR, "bad cursor") from exc
            if offset < 0:
                raise MarketplaceError(HttpCode.VALIDATION_ERROR, "bad cursor")
        slice_refs = refs[offset : offset + limit]
        jobs = [self._discovered(self._catalog[r]) for r in slice_refs]
        nxt = str(offset + limit) if offset + limit < len(refs) else None
        return DiscoverPage(adapter="mock", jobs=jobs, next_cursor=nxt)

    def get_requirements(self, external_reference: str) -> Requirements:
        job = self._job(external_reference)
        return Requirements(
            external_reference=external_reference,
            worker=str(job["worker"]),
            summary="Digital deliverable produced by an in-process canned worker.",
            digital_deliverable=True,
        )

    def get_payment_terms(self, external_reference: str) -> PaymentTerms:
        job = self._job(external_reference)
        amount = MarketplaceMoney.model_validate(
            {"amount": job["expected_revenue"], "asset": job["payment_asset"]}
        )
        return PaymentTerms(
            external_reference=external_reference,
            terms=str(job["payment_terms"]),
            amount=amount,
            asset=str(job["payment_asset"]),
        )

    def get_counterparty(self, external_reference: str) -> Counterparty:
        job = self._job(external_reference)
        return Counterparty(
            external_reference=external_reference,
            counterparty_id=str(job["counterparty_id"]),
            reputation=Reputation.model_validate(job["counterparty_reputation"]),
        )

    def get_status(self, external_reference: str) -> JobStatus:
        self._job(external_reference)
        with self._lock:
            self._maybe_network_fail(external_reference)
            status = self._state[external_reference]
        return JobStatus(external_reference=external_reference, status=status)  # type: ignore[arg-type]

    def _maybe_network_fail(self, external_reference: str) -> None:
        job = self._catalog[external_reference]
        if job.get("adapter_fault") != "network_after_accept":
            return
        if self._state[external_reference] in {"accepted", "failed"}:
            self._state[external_reference] = "failed"
            raise MarketplaceError(HttpCode.NETWORK_FAILURE, "adapter transport failed")

    def accept(self, external_reference: str, *, idempotency_key: str) -> AcceptResult:
        self._job(external_reference)
        if not (8 <= len(idempotency_key) <= 128):
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "idempotency_key invalid")
        with self._lock:
            status = self._state[external_reference]
            existing_key = self._accept_keys.get(external_reference)
            if existing_key is not None:
                if existing_key != idempotency_key:
                    raise MarketplaceError(HttpCode.CONFLICT, "job already accepted")
                if status != "accepted":
                    raise MarketplaceError(HttpCode.CONFLICT, f"cannot accept from {status}")
                return AcceptResult(
                    external_reference=external_reference,
                    status="accepted",
                    replay=True,
                    code=HttpCode.IDEMPOTENT_REPLAY,
                )
            if status != "available":
                raise MarketplaceError(HttpCode.CONFLICT, f"cannot accept from {status}")
            self._state[external_reference] = "accepted"
            self._accept_keys[external_reference] = idempotency_key
            return AcceptResult(
                external_reference=external_reference,
                status="accepted",
                replay=False,
            )

    def submit(
        self,
        external_reference: str,
        *,
        artefact_digest: str,
        artefact_uri: str,
        idempotency_key: str,
    ) -> SubmitResult:
        job = self._job(external_reference)
        if not (8 <= len(idempotency_key) <= 128):
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "idempotency_key invalid")
        if not artefact_digest.strip() or not artefact_uri.strip():
            raise MarketplaceError(HttpCode.VALIDATION_ERROR, "artefact required")
        print_key = (idempotency_key, artefact_digest, artefact_uri)
        with self._lock:
            self._maybe_network_fail(external_reference)
            status = self._state[external_reference]
            prior = self._submit_keys.get(external_reference)
            if prior is not None:
                if prior == print_key:
                    tx = self._txs.get(external_reference)
                    return SubmitResult(
                        external_reference=external_reference,
                        status=status,  # type: ignore[arg-type]
                        artefact_digest=artefact_digest,
                        transaction_reference=tx,
                        credited=bool(job["credits_wallet_on_submit"]) and tx is not None,
                        replay=True,
                        code=HttpCode.IDEMPOTENT_REPLAY,
                    )
                if prior[0] == idempotency_key:
                    raise MarketplaceError(HttpCode.IDEMPOTENCY_CONFLICT)
                raise MarketplaceError(HttpCode.CONFLICT, "job already submitted")
            if status != "accepted":
                raise MarketplaceError(HttpCode.CONFLICT, f"cannot submit from {status}")
            credited = False
            if job["credits_wallet_on_submit"]:
                if self._credit_fn is None:
                    raise MarketplaceError(
                        HttpCode.INTERNAL_ERROR, "wallet credit rail is required"
                    )
                if str(job["payment_asset"]) != "USDC":
                    raise MarketplaceError(HttpCode.VALIDATION_ERROR, "mock credit is USDC only")
                tx_id = new_tx_id()
                result = self._credit_fn(
                    asset="USDC",
                    amount=Decimal(str(job["expected_revenue"])),
                    tx_id=tx_id,
                    reason="marketplace_settlement",
                    idempotency_key=f"mkt-settle:{external_reference}",
                )
                if hasattr(result, "tx_id"):
                    tx_id = result.tx_id
                self._txs[external_reference] = tx_id
                credited = True
            elif str(external_reference).startswith("mock:job:fake-payment-"):
                self._txs[external_reference] = _fake_tx_id(external_reference)
            self._state[external_reference] = "submitted"
            self._submit_keys[external_reference] = print_key
            return SubmitResult(
                external_reference=external_reference,
                status="submitted",
                artefact_digest=artefact_digest,
                transaction_reference=self._txs.get(external_reference),
                credited=credited,
                replay=False,
            )

    def verify_payment(self, external_reference: str) -> PaymentClaim:
        job = self._job(external_reference)
        with self._lock:
            self._maybe_network_fail(external_reference)
            status = self._state[external_reference]
            tx = self._txs.get(external_reference)
        if status == "available":
            claim_status = "not_due"
        elif status == "accepted":
            claim_status = "pending"
        elif status == "failed":
            claim_status = "failed"
        elif status == "submitted":
            claim_status = "paid"
        else:
            claim_status = "pending"
        amount = None
        if claim_status == "paid":
            amount = MarketplaceMoney.model_validate(
                {"amount": job["expected_revenue"], "asset": job["payment_asset"]}
            )
        return PaymentClaim(
            external_reference=external_reference,
            status=claim_status,  # type: ignore[arg-type]
            amount=amount,
            transaction_reference=tx if claim_status == "paid" else None,
            verified=False,
        )

    def raw_description(self, external_reference: str) -> str:
        """Original untrusted description. Never executed."""
        return str(self._job(external_reference)["description"])
