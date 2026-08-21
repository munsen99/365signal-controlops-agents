"""Autonomous Economic Agent control-plane package.

Import root is ``aea``. No Hermes Python dependency. No Solana imports
in this package at process start (wallet phase A).
"""

from __future__ import annotations

__version__ = "0.1.0"
CONSTITUTION_VERSION = "constitution/v0.1.0"
POLICY_VERSION = "policy/v0.1.0"
AGENT_ID = "economic-agent"

NINE_TOOLS: tuple[str, ...] = (
    "find_jobs",
    "evaluate_job",
    "accept_job",
    "perform_job",
    "submit_work",
    "check_payment",
    "request_payment",
    "get_financial_state",
    "record_decision",
)
