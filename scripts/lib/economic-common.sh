# Shared helpers for scripts/economic. Do not print secrets.

ECONOMIC_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
AEA_DIR="${ECONOMIC_ROOT}/autonomous_economic_agent"
COMPOSE_FILE="${AEA_DIR}/ops/compose.economic.yaml"
AEA_SECRETS="${AEA_SECRETS:-${HOME}/.config/controlops/economic}"
SUPERVISOR_URL="${AEA_SUPERVISOR_URL:-http://127.0.0.1:18703}"
CONTROL_URL="${AEA_CONTROL_URL:-http://127.0.0.1:18700}"

economic_error() { printf 'economic: %s\n' "$*" >&2; }
economic_read_token_file() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    economic_error "missing token file"
    return 1
  fi
  tr -d '\n' < "${path}"
}

economic_supervisor_token() {
  if [[ -n "${AEA_SUPERVISOR_TOKEN_FILE:-}" ]]; then
    economic_read_token_file "${AEA_SUPERVISOR_TOKEN_FILE}"
    return
  fi
  economic_read_token_file "${AEA_SECRETS}/tokens/supervisor"
}

economic_curl_admin() {
  local path="$1"
  local body="$2"
  local token
  token="$(economic_supervisor_token)" || return 1
  curl -sS -X POST "${SUPERVISOR_URL}${path}" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    --data-binary "${body}"
}
