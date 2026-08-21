"""Inbound supervisor admin DTOs. extra='forbid' including force=true."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from aea.types import AeaBaseModel


class SupervisorMutationRequest(AeaBaseModel):
    reason: str = Field(min_length=3, max_length=500)
    actor: str = Field(default="operator", min_length=1, max_length=128)
    source: str = Field(default="supervisor", min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)


class UnfreezeRequest(SupervisorMutationRequest):
    confirm: Literal["UNFREEZE"]


class EnableSignerRequest(SupervisorMutationRequest):
    confirm: Literal["ENABLE_SIGNER"]


class PermitLoopRequest(SupervisorMutationRequest):
    confirm: Literal["PERMIT_LOOP"]


RELAXING_CONFIRM = {
    "unfreeze": "UNFREEZE",
    "enable-signer": "ENABLE_SIGNER",
    "permit-loop": "PERMIT_LOOP",
}


class IncidentCreateRequest(AeaBaseModel):
    severity: Literal["info", "warn", "critical"]
    kind: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    actor: str = Field(default="operator", min_length=1, max_length=128)
    source: str = Field(default="supervisor", min_length=1, max_length=128)
    reason: str = Field(default="incident", min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128)
    correlation_id: UUID | None = None
