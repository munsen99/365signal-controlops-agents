"""Ledger service errors. Codes are M0 §7.3 stable machine codes."""

from __future__ import annotations


class LedgerError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
