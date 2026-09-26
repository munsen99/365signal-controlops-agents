"""Read-only ledger connections for observability. Never mutate."""

from __future__ import annotations

from aea.config import LoadedPolicy, load_policy
from aea.ledger.db import connect
from aea.ledger.service import LedgerService


def open_readonly_ledger(dbname: str, *, policy: LoadedPolicy | None = None) -> LedgerService:
    """Open ``economic_app`` against ``dbname`` inside a READ ONLY transaction."""
    conn = connect(dbname=dbname, readonly=True)
    return LedgerService(conn, policy=policy or load_policy())
