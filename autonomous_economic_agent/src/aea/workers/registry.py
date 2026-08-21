"""Map marketplace external_reference prefixes to in-process workers."""

from __future__ import annotations

from collections.abc import Callable

from aea.workers.mock import (
    WorkerResult,
    fail_after_mark,
    noop_expensive_estimate,
    runaway_loop,
    summarise_canned,
)


WorkerFn = Callable[..., WorkerResult]

_PREFIX_TABLE: tuple[tuple[str, WorkerFn], ...] = (
    ("mock:job:profitable-summary-", summarise_canned),
    ("mock:job:unprofitable-research-", noop_expensive_estimate),
    ("mock:job:high-compute-", runaway_loop),
    ("mock:job:fails-after-spend-", fail_after_mark),
    ("mock:job:fake-payment-", summarise_canned),
    ("mock:job:", summarise_canned),
)


def resolve_worker(external_reference: str) -> WorkerFn:
    for prefix, fn in _PREFIX_TABLE:
        if external_reference.startswith(prefix):
            return fn
    return summarise_canned


def run_worker(external_reference: str) -> WorkerResult:
    """Run the canned worker. No LLM, no network, no exec."""
    fn = resolve_worker(external_reference)
    return fn(external_reference=external_reference)
