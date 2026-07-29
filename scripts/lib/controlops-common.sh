#!/usr/bin/env bash

# Shared, non-destructive helpers for the ControlOps Hermes lifecycle command.

CONTROL_OPS_ROOT="/mnt/Storage/AI/Hermes/workspace"
HERMES_SOURCE_ROOT="/home/proteu5/AI/Hermes/hermes-agent"
HERMES_DATA_ROOT="/mnt/Storage/AI/Hermes/data"
LANCEDB_ROOT="/mnt/Storage/AI/VectorDBs/LanceDB"
CONTROL_OPS_PROJECT="controlops-hermes"
CONTROL_OPS_ENV_FILE="${HERMES_SOURCE_ROOT}/.env.controlops"
HERMES_BASE_COMPOSE="${HERMES_SOURCE_ROOT}/docker-compose.yml"
CONTROL_OPS_OVERRIDE="${CONTROL_OPS_ROOT}/ops/compose.controlops.yaml"
LM_STUDIO_MODELS_URL="http://127.0.0.1:1234/v1/models"
HERMES_DASHBOARD_URL="http://127.0.0.1:9119/"

CONTROL_OPS_COMPOSE=(
  docker compose
  --project-name "${CONTROL_OPS_PROJECT}"
  --env-file "${CONTROL_OPS_ENV_FILE}"
  -f "${HERMES_BASE_COMPOSE}"
  -f "${CONTROL_OPS_OVERRIDE}"
)

controlops_error() {
  printf 'ERROR: %s\n' "$*" >&2
}

controlops_warn() {
  printf 'WARN: %s\n' "$*" >&2
}

controlops_compose() {
  "${CONTROL_OPS_COMPOSE[@]}" "$@"
}

controlops_require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    controlops_error "Required command not found: $1"
    return 1
  }
}

controlops_validate_required_paths() {
  local failed=0
  local path

  for path in \
    "${CONTROL_OPS_ROOT}" \
    "${HERMES_SOURCE_ROOT}" \
    "${HERMES_DATA_ROOT}" \
    "${LANCEDB_ROOT}"; do
    if [[ ! -d "${path}" ]]; then
      controlops_error "Required directory is missing: ${path}"
      failed=1
    fi
  done

  for path in \
    "${CONTROL_OPS_ENV_FILE}" \
    "${HERMES_BASE_COMPOSE}" \
    "${CONTROL_OPS_OVERRIDE}"; do
    if [[ ! -f "${path}" ]]; then
      controlops_error "Required file is missing: ${path}"
      failed=1
    fi
  done

  return "${failed}"
}

controlops_validate_docker() {
  controlops_require_command docker || return 1
  docker compose version >/dev/null 2>&1 || {
    controlops_error "Docker Compose is unavailable."
    return 1
  }
  docker info >/dev/null 2>&1 || {
    controlops_error "Docker daemon is unavailable or access is denied."
    return 1
  }
}

controlops_render_config_json() {
  controlops_compose config --format json
}

controlops_validate_config_json() {
  local config_json="${1:-}"
  local check
  local failed=0

  [[ -n "${config_json}" ]] || {
    controlops_error "Effective Compose configuration is empty."
    return 1
  }

  controlops_require_command jq || return 1

  while IFS=$'\t' read -r check description; do
    if ! jq -e "${check}" >/dev/null 2>&1 <<<"${config_json}"; then
      controlops_error "Effective Compose validation failed: ${description}"
      failed=1
    fi
  done <<'EOF'
.name == "controlops-hermes"	project name is controlops-hermes
(.services | has("gateway")) and (.services | has("dashboard"))	services include gateway and dashboard
.services.gateway.container_name == "hermes"	gateway container name is hermes
.services.dashboard.container_name == "hermes-dashboard"	dashboard container name is hermes-dashboard
.services.gateway.network_mode == "host"	gateway uses host networking
.services.dashboard.network_mode == "host"	dashboard uses host networking
.services.gateway.restart == "unless-stopped"	gateway restart policy is unless-stopped
.services.dashboard.restart == "unless-stopped"	dashboard restart policy is unless-stopped
any(.services.gateway.volumes[]; .type == "bind" and .source == "/mnt/Storage/AI/Hermes/data" and .target == "/opt/data")	gateway persistent data mount
any(.services.gateway.volumes[]; .type == "bind" and .source == "/mnt/Storage/AI/Hermes/workspace" and .target == "/workspace")	gateway workspace mount
any(.services.gateway.volumes[]; .type == "bind" and .source == "/mnt/Storage/AI/VectorDBs/LanceDB" and .target == "/opt/data/lancedb")	gateway LanceDB mount
any(.services.dashboard.volumes[]; .type == "bind" and .source == "/mnt/Storage/AI/Hermes/data" and .target == "/opt/data")	dashboard persistent data mount
any(.services.dashboard.volumes[]; .type == "bind" and .source == "/mnt/Storage/AI/Hermes/workspace" and .target == "/workspace")	dashboard workspace mount
.services.gateway.environment.HERMES_UID != null and .services.gateway.environment.HERMES_GID != null	gateway UID/GID configuration
.services.dashboard.environment.HERMES_UID != null and .services.dashboard.environment.HERMES_GID != null	dashboard UID/GID configuration
.services.gateway.environment.LM_API_KEY == "lm-studio"	gateway LM Studio configuration
.services.dashboard.environment.LM_API_KEY == "lm-studio"	dashboard LM Studio configuration
EOF

  return "${failed}"
}

controlops_validate_effective_config() {
  local config_json

  config_json="$(controlops_render_config_json)" || {
    controlops_error "Unable to render the effective Compose configuration."
    return 1
  }
  controlops_validate_config_json "${config_json}"
}

controlops_check_lm_studio() {
  controlops_require_command curl || return 1
  curl --fail --silent --show-error --max-time 5 \
    "${LM_STUDIO_MODELS_URL}" >/dev/null
}

controlops_container_running() {
  local container="$1"
  [[ "$(docker inspect --format '{{.State.Running}}' "${container}" 2>/dev/null)" == "true" ]]
}

controlops_dashboard_responding() {
  local code
  code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --max-time 3 "${HERMES_DASHBOARD_URL}" 2>/dev/null)" || return 1
  [[ "${code}" != "000" ]]
}

controlops_wait_ready() {
  local attempts="${1:-30}"
  local attempt

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if controlops_container_running hermes &&
      controlops_container_running hermes-dashboard &&
      controlops_dashboard_responding; then
      return 0
    fi
    sleep 1
  done

  controlops_error "Hermes did not become ready within ${attempts} seconds."
  return 1
}

controlops_expected_mounts_for() {
  case "$1" in
    hermes)
      printf '%s\n' \
        "${HERMES_DATA_ROOT}|/opt/data" \
        "${CONTROL_OPS_ROOT}|/workspace" \
        "${LANCEDB_ROOT}|/opt/data/lancedb"
      ;;
    hermes-dashboard)
      printf '%s\n' \
        "${HERMES_DATA_ROOT}|/opt/data" \
        "${CONTROL_OPS_ROOT}|/workspace"
      ;;
    *)
      return 1
      ;;
  esac
}

controlops_verify_container_mounts() {
  local container
  local actual
  local expected
  local failed=0

  for container in hermes hermes-dashboard; do
    actual="$(docker inspect --format \
      '{{range .Mounts}}{{.Source}}|{{.Destination}}{{println}}{{end}}' \
      "${container}" 2>/dev/null)" || {
      controlops_error "Cannot inspect mounts for ${container}."
      failed=1
      continue
    }

    while IFS= read -r expected; do
      if ! grep -Fqx -- "${expected}" <<<"${actual}"; then
        controlops_error "${container} is missing expected mount: ${expected}"
        failed=1
      fi
    done < <(controlops_expected_mounts_for "${container}")
  done

  return "${failed}"
}

controlops_git_dirty() {
  local repository="$1"
  [[ -n "$(git -C "${repository}" status --short 2>/dev/null)" ]]
}

controlops_preflight() {
  controlops_validate_docker &&
    controlops_require_command jq &&
    controlops_validate_required_paths &&
    controlops_validate_effective_config
}
