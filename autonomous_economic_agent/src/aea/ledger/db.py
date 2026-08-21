"""Postgres connection helper for the economic schema.

Uses role ``economic_app`` by default. Never reads Hermes env vars and never
returns or logs the ``controlops_admin`` URL. Callers must not pass a Hermes
database DSN.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5432
DEFAULT_DB = "controlops"
DEFAULT_APP_USER = "economic_app"
DEFAULT_SUPERVISOR_USER = "economic_supervisor"

_APP_PASSWORD_FILE = Path.home() / ".config/controlops/economic/postgres_password"
_SUPERVISOR_PASSWORD_FILE = (
    Path.home() / ".config/controlops/economic/postgres_supervisor_password"
)

_FORBIDDEN_ENV = (
    "HERMES_DATABASE_URL",
    "HERMES_POSTGRES_URL",
    "DATABASE_URL",
    "CONTROL_OPS_ADMIN_DATABASE_URL",
)


class LedgerConfigError(RuntimeError):
    """Misconfigured ledger connection."""


def _read_password_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").rstrip("\n")


def _password_for_role(role: str) -> str | None:
    if role == DEFAULT_SUPERVISOR_USER:
        env = os.environ.get("AEA_POSTGRES_SUPERVISOR_PASSWORD")
        if env:
            return env
        file_env = os.environ.get("AEA_POSTGRES_SUPERVISOR_PASSWORD_FILE")
        return _read_password_file(Path(file_env) if file_env else _SUPERVISOR_PASSWORD_FILE)
    env = os.environ.get("AEA_POSTGRES_PASSWORD")
    if env:
        return env
    file_env = os.environ.get("AEA_POSTGRES_PASSWORD_FILE")
    return _read_password_file(Path(file_env) if file_env else _APP_PASSWORD_FILE)


def connect_kwargs(*, role: str = DEFAULT_APP_USER) -> dict[str, object]:
    """Build psycopg kwargs. Reject Hermes/admin DSN environment."""
    for name in _FORBIDDEN_ENV:
        if os.environ.get(name):
            raise LedgerConfigError(
                f"{name} is set; the economic ledger must not use a Hermes or admin DSN"
            )
    if os.environ.get("AEA_POSTGRES_DSN"):
        raise LedgerConfigError("AEA_POSTGRES_DSN is not supported; use discrete AEA_POSTGRES_* vars")

    user = os.environ.get("AEA_POSTGRES_USER", role)
    if user in {"controlops_admin", "postgres"} and role != "migration":
        raise LedgerConfigError("economic app connections must not use the admin role")

    kwargs: dict[str, object] = {
        "host": os.environ.get("AEA_POSTGRES_HOST", DEFAULT_HOST),
        "port": int(os.environ.get("AEA_POSTGRES_PORT", str(DEFAULT_PORT))),
        "dbname": os.environ.get("AEA_POSTGRES_DB", DEFAULT_DB),
        "user": user,
        "autocommit": False,
    }
    password = _password_for_role(user)
    if password:
        kwargs["password"] = password
    return kwargs


def connect(*, role: str = DEFAULT_APP_USER) -> psycopg.Connection:
    """Open a connection with search_path=economic."""
    conn = psycopg.connect(**connect_kwargs(role=role))
    conn.execute("SET search_path TO economic")
    return conn


@contextmanager
def connection(*, role: str = DEFAULT_APP_USER) -> Iterator[psycopg.Connection]:
    conn = connect(role=role)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
