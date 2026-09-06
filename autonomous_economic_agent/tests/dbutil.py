"""Transactional ledger isolation for tests sharing the live economic schema.

TRUNCATE runs inside the test connection's transaction and is rolled back
with the fixture, so live rows are restored. It is not a permanent DB edit.
"""

from __future__ import annotations

_LEDGER_TABLES = (
    "economic.audit_events",
    "economic.decisions",
    "economic.revenues",
    "economic.economic_costs",
    "economic.payment_requests",
    "economic.jobs",
    "economic.opportunities",
)


def isolate_economic_ledger(conn) -> None:
    conn.execute("TRUNCATE " + ", ".join(_LEDGER_TABLES) + " CASCADE")
    conn.execute(
        "DELETE FROM economic.transfers WHERE classification NOT IN ('opening_capital', 'fee_reserve')"
    )
    conn.execute("UPDATE economic.agent_accounts SET current_balance = opening_balance")
