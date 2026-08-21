"""In-process canned workers for M1. No LLM."""

from aea.workers.mock import WorkerResult
from aea.workers.registry import run_worker

__all__ = ["WorkerResult", "run_worker"]
