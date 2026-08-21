"""Deterministic M1 workers. No LM Studio, no network, no subprocess."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from aea.hashing import sha256_hex
from aea.policy.reasons import HttpCode


@dataclass(frozen=True)
class WorkerResult:
    worker: str
    external_reference: str
    text: str
    digest: str
    tokens_in: int
    tokens_out: int
    wall_seconds: Decimal
    ok: bool
    reason_code: str | None

CANNED_SOURCE = (
    "The lighthouse stood on the granite headland and swept the fog "
    "with a steady beam. Mariners used it as a mark, not a harbour."
)
CANNED_SUMMARY = (
    "CANNED_SUMMARY: A granite-headland lighthouse swept fog with a steady "
    "beam and served mariners as a mark rather than a harbour."
)


def summarise_canned(*, external_reference: str) -> WorkerResult:
    digest = sha256_hex(CANNED_SUMMARY.encode("utf-8"))
    return WorkerResult(
        worker="summarise_canned",
        external_reference=external_reference,
        text=CANNED_SUMMARY,
        digest=digest,
        tokens_in=48,
        tokens_out=36,
        wall_seconds=Decimal("0.050000"),
        ok=True,
        reason_code=None,
    )


def noop_expensive_estimate(*, external_reference: str) -> WorkerResult:
    text = "EXPENSIVE_NOOP"
    return WorkerResult(
        worker="noop_expensive_estimate",
        external_reference=external_reference,
        text=text,
        digest=sha256_hex(text.encode("utf-8")),
        tokens_in=8000,
        tokens_out=8000,
        wall_seconds=Decimal("30.000000"),
        ok=True,
        reason_code=None,
    )


def runaway_loop(*, external_reference: str) -> WorkerResult:
    text = "RUNAWAY_ABORTED"
    return WorkerResult(
        worker="runaway_loop",
        external_reference=external_reference,
        text=text,
        digest=sha256_hex(text.encode("utf-8")),
        tokens_in=1,
        tokens_out=1,
        wall_seconds=Decimal("120.000000"),
        ok=False,
        reason_code=HttpCode.RUNAWAY_COST,
    )


def fail_after_mark(*, external_reference: str) -> WorkerResult:
    text = "PARTIAL_THEN_FAIL"
    return WorkerResult(
        worker="fail_after_mark",
        external_reference=external_reference,
        text=text,
        digest=sha256_hex(text.encode("utf-8")),
        tokens_in=20,
        tokens_out=5,
        wall_seconds=Decimal("0.200000"),
        ok=False,
        reason_code=HttpCode.JOB_FAILED,
    )
