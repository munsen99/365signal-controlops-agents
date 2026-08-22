#!/usr/bin/env bash
# Apply economic schema 013–016 to an existing controlops Postgres volume,
# then run validation. Fresh volumes also load these files from
# platform/postgres/init/ on first container start.
#
# Operator (controlops_admin) only. Hermes must not receive a DB URL.
#
# Usage:
#   bash autonomous_economic_agent/scripts/apply_schema.sh

set -o errexit
set -o nounset
set -o pipefail

ROOT="/mnt/Storage/AI/Hermes/workspace"
INIT="${ROOT}/platform/postgres/init"
VALIDATION="${ROOT}/platform/postgres/validation/013-economic-schema-validation.sql"
ADMIN_PASSWORD_FILE="${CONTROL_OPS_POSTGRES_PASSWORD_FILE:-/home/proteu5/.config/controlops/postgres/postgres_password}"
APP_PASSWORD_FILE="${AEA_POSTGRES_PASSWORD_FILE:-/home/proteu5/.config/controlops/economic/postgres_password}"
SUPERVISOR_PASSWORD_FILE="${AEA_POSTGRES_SUPERVISOR_PASSWORD_FILE:-/home/proteu5/.config/controlops/economic/postgres_supervisor_password}"
PGHOST="${AEA_POSTGRES_HOST:-127.0.0.1}"
PGPORT="${AEA_POSTGRES_PORT:-5432}"
PGDATABASE="${AEA_POSTGRES_DB:-controlops}"
PGUSER="${AEA_POSTGRES_ADMIN_USER:-controlops_admin}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -r "${ADMIN_PASSWORD_FILE}" ]] || fail "admin password file is missing: ${ADMIN_PASSWORD_FILE}"
[[ -r "${INIT}/013-economic-schema.sql" ]] || fail "013-economic-schema.sql is missing"
command -v psql >/dev/null 2>&1 || fail "psql is required"

export PGPASSWORD
PGPASSWORD="$(cat "${ADMIN_PASSWORD_FILE}")"

psql_admin() {
  psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" \
    -v ON_ERROR_STOP=1 --no-psqlrc "$@"
}

printf 'Applying 013-economic-schema.sql\n'
psql_admin -f "${INIT}/013-economic-schema.sql"
printf 'Applying 014-economic-roles-and-grants.sql\n'
psql_admin -f "${INIT}/014-economic-roles-and-grants.sql"
printf 'Applying 015-economic-seed.sql\n'
psql_admin -f "${INIT}/015-economic-seed.sql"
printf 'Applying 016-economic-multirail.sql\n'
psql_admin -f "${INIT}/016-economic-multirail.sql"

AEA_ROOT="${ROOT}/autonomous_economic_agent"
PY="${AEA_ROOT}/.venv/bin/python"
if [[ ! -e "${PY}" ]]; then
  PY="python3"
fi
command -v "${PY}" >/dev/null 2>&1 || PY="python3"

PYTHONPATH="${AEA_ROOT}/src" AEA_ROOT="${AEA_ROOT}" \
  PGHOST="${PGHOST}" PGPORT="${PGPORT}" PGDATABASE="${PGDATABASE}" PGUSER="${PGUSER}" \
  AEA_APP_PASSWORD_FILE="${APP_PASSWORD_FILE}" \
  AEA_SUPERVISOR_PASSWORD_FILE="${SUPERVISOR_PASSWORD_FILE}" \
  "${PY}" - <<'PY'
import json
import os
from pathlib import Path

import psycopg
from psycopg import sql

from aea.config import load_policy
from aea.hashing import sha256_hex

root = Path(os.environ["AEA_ROOT"])
conn = psycopg.connect(
    host=os.environ["PGHOST"],
    port=os.environ["PGPORT"],
    dbname=os.environ["PGDATABASE"],
    user=os.environ["PGUSER"],
    password=os.environ["PGPASSWORD"],
)
conn.execute("SET search_path TO economic")

def maybe_password(role: str, env_name: str) -> None:
    path = Path(os.environ[env_name])
    if not path.is_file():
        print(f"WARN: {path} not present; role {role} has no password yet")
        return
    pw = path.read_text(encoding="utf-8").rstrip("\n")
    conn.execute(
        sql.SQL("ALTER ROLE {} PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(pw)
        )
    )
    print(f"Updated password for role {role}")

maybe_password("economic_app", "AEA_APP_PASSWORD_FILE")
maybe_password("economic_supervisor", "AEA_SUPERVISOR_PASSWORD_FILE")

policy = load_policy()
constitution_hash = sha256_hex((root / "constitution" / "SOUL.md").read_bytes())
conn.execute(
    """
    UPDATE economic.policy_versions
       SET policy_document = %s::jsonb,
           policy_hash = %s,
           is_current = true
     WHERE policy_version = 'policy/v0.1.0'
    """,
    (json.dumps(policy.raw, default=str), policy.policy_hash),
)
conn.execute(
    """
    UPDATE economic.constitution_versions
       SET constitution_hash = %s
     WHERE constitution_version = 'constitution/v0.1.0'
    """,
    (constitution_hash,),
)
conn.commit()
conn.close()
print("Refreshed policy and constitution hashes from git files")
PY

printf 'Running 013-economic-schema-validation.sql\n'
psql_admin -f "${VALIDATION}"

printf 'economic schema apply complete\n'
