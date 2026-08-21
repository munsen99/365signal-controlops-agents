"""Ledger connection helper must not use Hermes or admin DSNs."""

from __future__ import annotations

import os

import pytest

from aea.ledger.db import LedgerConfigError, connect_kwargs


def test_connect_kwargs_defaults_to_economic_app(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("AEA_POSTGRES") or key in {
            "HERMES_DATABASE_URL",
            "DATABASE_URL",
        }:
            monkeypatch.delenv(key, raising=False)
    kwargs = connect_kwargs()
    assert kwargs["user"] == "economic_app"
    assert kwargs["dbname"] == "controlops"
    assert kwargs["host"] == "127.0.0.1"
    assert "HERMES" not in str(kwargs)


def test_rejects_hermes_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_DATABASE_URL", "postgresql://controlops_admin@localhost/controlops")
    with pytest.raises(LedgerConfigError, match="HERMES_DATABASE_URL"):
        connect_kwargs()


def test_rejects_admin_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_DATABASE_URL", raising=False)
    monkeypatch.setenv("AEA_POSTGRES_USER", "controlops_admin")
    with pytest.raises(LedgerConfigError, match="admin role"):
        connect_kwargs()


def test_rejects_dsn_shortcut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_DATABASE_URL", raising=False)
    monkeypatch.setenv("AEA_POSTGRES_DSN", "postgresql://economic_app@127.0.0.1/controlops")
    with pytest.raises(LedgerConfigError, match="AEA_POSTGRES_DSN"):
        connect_kwargs()
