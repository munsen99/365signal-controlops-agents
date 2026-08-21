"""Apply economic schema to the local ControlOps Postgres if reachable."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
APPLY = ROOT / "autonomous_economic_agent" / "scripts" / "apply_schema.sh"
ADMIN_PW = Path.home() / ".config/controlops/postgres/postgres_password"


def _postgres_up() -> bool:
    if not ADMIN_PW.is_file():
        return False
    try:
        import psycopg
    except ImportError:
        return False
    try:
        conn = psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname="controlops",
            user="controlops_admin",
            password=ADMIN_PW.read_text(encoding="utf-8").rstrip("\n"),
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_up(), reason="controlops Postgres is not reachable")


def test_apply_schema_and_recon_delta_zero() -> None:
    import os
    import subprocess

    import psycopg

    env = os.environ.copy()
    proc = subprocess.run(
        ["bash", str(APPLY)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    conn = psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="controlops",
        user="controlops_admin",
        password=ADMIN_PW.read_text(encoding="utf-8").rstrip("\n"),
    )
    row = conn.execute(
        """
        SELECT asset, delta
          FROM economic.v_balance_reconciliation
         WHERE agent_id = 'economic-agent'
         ORDER BY asset
        """
    ).fetchall()
    by_asset = {r[0]: r[1] for r in row}
    assert abs(by_asset["USDC"]) < 0.000001
    assert abs(by_asset["SOL"]) < 0.000001
    app_update = conn.execute(
        """
        SELECT has_table_privilege(
            'economic_app', 'economic.supervisor_state', 'UPDATE'
        )
        """
    ).fetchone()[0]
    assert app_update is False
    catalogue = conn.execute(
        """
        SELECT has_table_privilege(
            'economic_app', 'catalogue.permission_definition', 'SELECT'
        )
        """
    ).fetchone()[0]
    assert catalogue is False
    opening = conn.execute(
        """
        SELECT has_column_privilege(
            'economic_app', 'economic.agent_accounts', 'opening_balance', 'UPDATE'
        )
        """
    ).fetchone()[0]
    assert opening is False
    schema_owner = conn.execute(
        """
        SELECT pg_catalog.pg_get_userbyid(n.nspowner)
          FROM pg_namespace n WHERE n.nspname = 'economic'
        """
    ).fetchone()[0]
    assert schema_owner == "controlops_admin"
    rogue_owners = conn.execute(
        """
        SELECT count(*) FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'economic'
           AND c.relkind IN ('r', 'v')
           AND pg_catalog.pg_get_userbyid(c.relowner) <> 'controlops_admin'
        """
    ).fetchone()[0]
    assert rogue_owners == 0
    conn.close()
