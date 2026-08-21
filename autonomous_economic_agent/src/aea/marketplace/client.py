"""HTTP marketplace client for the control plane. Token: marketplace only."""

from __future__ import annotations

from typing import Any

import httpx

from aea.marketplace.protocol import (
    AcceptResult,
    Counterparty,
    DiscoveredJob,
    DiscoverPage,
    JobStatus,
    MarketplaceError,
    PaymentClaim,
    PaymentTerms,
    Requirements,
    SubmitResult,
)
from aea.policy.reasons import HttpCode


class HttpMarketplace:
    name = "mock"

    def __init__(self, base_url: str, token: str) -> None:
        if not token:
            raise ValueError("marketplace token is required")
        self._base = base_url.rstrip("/")
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path: str) -> dict[str, Any]:
        try:
            response = httpx.get(self._base + path, headers=self._headers(), timeout=15.0)
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketplaceError(HttpCode.NETWORK_FAILURE) from exc
        if not isinstance(body, dict):
            raise MarketplaceError(HttpCode.NETWORK_FAILURE)
        if body.get("ok") is False:
            raise MarketplaceError(str(body.get("code") or HttpCode.MARKETPLACE_UNAVAILABLE))
        return {key: value for key, value in body.items() if key not in {"ok", "code"}}

    def _post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                self._base + path, json=json, headers=self._headers(), timeout=15.0
            )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketplaceError(HttpCode.NETWORK_FAILURE) from exc
        if not isinstance(body, dict):
            raise MarketplaceError(HttpCode.NETWORK_FAILURE)
        if body.get("ok") is False:
            raise MarketplaceError(str(body.get("code") or HttpCode.MARKETPLACE_UNAVAILABLE))
        return {key: value for key, value in body.items() if key not in {"ok", "code"}}

    def discover(self, *, limit: int, cursor: str | None) -> DiscoverPage:
        q = f"/v1/marketplace/jobs?limit={limit}"
        if cursor:
            q += f"&cursor={cursor}"
        return DiscoverPage.model_validate(self._get(q))

    def lookup(self, external_reference: str) -> DiscoveredJob:
        body = self._get(f"/v1/marketplace/jobs/{external_reference}")
        job = body.get("job") or body
        return DiscoveredJob.model_validate(job)

    def get_requirements(self, external_reference: str) -> Requirements:
        return Requirements.model_validate(self._get(f"/v1/marketplace/jobs/{external_reference}/requirements"))

    def get_payment_terms(self, external_reference: str) -> PaymentTerms:
        return PaymentTerms.model_validate(self._get(f"/v1/marketplace/jobs/{external_reference}/payment-terms"))

    def accept(self, external_reference: str, *, idempotency_key: str) -> AcceptResult:
        return AcceptResult.model_validate(
            self._post(f"/v1/marketplace/jobs/{external_reference}/accept", {"idempotency_key": idempotency_key})
        )

    def submit(
        self,
        external_reference: str,
        *,
        artefact_digest: str,
        artefact_uri: str,
        idempotency_key: str,
    ) -> SubmitResult:
        return SubmitResult.model_validate(
            self._post(
                f"/v1/marketplace/jobs/{external_reference}/submit",
                {
                    "artefact_digest": artefact_digest,
                    "artefact_uri": artefact_uri,
                    "idempotency_key": idempotency_key,
                },
            )
        )

    def get_status(self, external_reference: str) -> JobStatus:
        return JobStatus.model_validate(self._get(f"/v1/marketplace/jobs/{external_reference}/status"))

    def verify_payment(self, external_reference: str) -> PaymentClaim:
        return PaymentClaim.model_validate(self._get(f"/v1/marketplace/jobs/{external_reference}/payment"))

    def get_counterparty(self, external_reference: str) -> Counterparty:
        return Counterparty.model_validate(self._get(f"/v1/marketplace/jobs/{external_reference}/counterparty"))
