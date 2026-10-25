"""Closed failure codes for the PR5-R runtime."""

from __future__ import annotations


class RuntimeFailure(Exception):
    """Fail-closed runtime result. `code` is the stable contract token."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail or code)
