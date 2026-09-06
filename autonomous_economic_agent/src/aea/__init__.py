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

# Declared capabilities are callable only when they also appear in
# IMPLEMENTED_ECONOMIC_TOOLS (schema + authenticated control route + plugin
# handler). PR16 implements the full declared set.
DECLARED_ECONOMIC_TOOLS: tuple[str, ...] = NINE_TOOLS + (
    "research_opportunities",
    "discover_counterparties",
    "send_message",
    "get_counterparty_profile",
    "post_service_offer",
    "read_messages",
    "follow_up_message",
    "propose_collaboration",
    "get_market_status",
    "list_active_conversations",
)

IMPLEMENTED_ECONOMIC_TOOLS: tuple[str, ...] = DECLARED_ECONOMIC_TOOLS

DECLARED_UNIMPLEMENTED_TOOLS: tuple[str, ...] = tuple(
    name for name in DECLARED_ECONOMIC_TOOLS if name not in IMPLEMENTED_ECONOMIC_TOOLS
)
