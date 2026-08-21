#!/usr/bin/env bash
# Operator freeze stub (PR9). Requires AEA_SUPERVISOR_TOKEN. Does not print secrets.
set -euo pipefail
TOKEN="${AEA_SUPERVISOR_TOKEN:-}"
if [[ -z "${TOKEN}" && -n "${AEA_SUPERVISOR_TOKEN_FILE:-}" ]]; then
  TOKEN="$(tr -d '\n' < "${AEA_SUPERVISOR_TOKEN_FILE}")"
fi
if [[ -z "${TOKEN}" && -f "${HOME}/.config/controlops/economic/tokens/supervisor" ]]; then
  TOKEN="$(tr -d '\n' < "${HOME}/.config/controlops/economic/tokens/supervisor")"
fi
if [[ -z "${TOKEN}" ]]; then
  echo "freeze: AEA_SUPERVISOR_TOKEN is required" >&2
  exit 1
fi
URL="${AEA_SUPERVISOR_URL:-http://127.0.0.1:18703}"
REASON="${1:-operator freeze}"
KEY="${2:-freeze-$(date +%s)-stub000}"
curl -sS -X POST "${URL}/v1/admin/freeze-spend" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"reason\":\"${REASON}\",\"actor\":\"operator\",\"source\":\"operator\",\"idempotency_key\":\"${KEY}\"}"
echo
