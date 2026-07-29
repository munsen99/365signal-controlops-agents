#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

ROOT="/mnt/Storage/AI/Hermes/workspace"
COMMAND="${ROOT}/scripts/controlops"
COMMON="${ROOT}/scripts/lib/controlops-common.sh"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

[[ -r "${COMMAND}" ]] || fail "scripts/controlops is not readable"
[[ -r "${COMMON}" ]] || fail "shared library is not readable"
[[ -r "${ROOT}/ops/compose.controlops.yaml" ]] || fail "canonical override is missing"

help_output="$(bash "${COMMAND}" help)"
grep -Fq 'Usage: scripts/controlops' <<<"${help_output}" ||
  fail "help output lacks usage"
for subcommand in start stop restart status logs doctor rebuild help; do
  grep -Fq "${subcommand}" <<<"${help_output}" ||
    fail "help output lacks ${subcommand}"
done

if bash "${COMMAND}" unknown-command >/dev/null 2>&1; then
  fail "unknown command unexpectedly succeeded"
fi

if bash "${COMMAND}" logs --unsafe-option >/dev/null 2>&1; then
  fail "invalid logs option unexpectedly succeeded"
fi

# Source only the shared declarations and invoke read-only validators. No
# lifecycle subcommand is called by this test.
# shellcheck source=scripts/lib/controlops-common.sh
source "${COMMON}"
controlops_validate_required_paths
controlops_validate_docker
controlops_validate_effective_config

printf 'PASS: ControlOps operational smoke tests\n'
