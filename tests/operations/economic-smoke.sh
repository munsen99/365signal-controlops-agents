#!/usr/bin/env bash
# PR10 compose mount smoke. Parses YAML; does not require docker up.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE="${ROOT}/autonomous_economic_agent/ops/compose.economic.yaml"
HERMES="${ROOT}/ops/compose.controlops.yaml"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "OK: $*"; }

[[ -f "${COMPOSE}" ]] || fail "missing ${COMPOSE}"

python3 - "${COMPOSE}" "${HERMES}" <<'PY'
import sys
from pathlib import Path

compose = Path(sys.argv[1]).read_text()
hermes = Path(sys.argv[2]).read_text() if Path(sys.argv[2]).is_file() else ""

def section(name: str) -> str:
    key = f"  {name}:"
    start = compose.find(key)
    if start < 0:
        raise SystemExit(f"FAIL missing service {name}")
    nxt = compose.find("\n  economic-", start + len(key))
    if nxt < 0:
        nxt = compose.find("\nvolumes:", start)
    return compose[start:nxt]

control = section("economic-control")
policy = section("economic-policy")
signer = section("economic-signer")
wallet = section("economic-wallet")
market = section("economic-marketplace")
sup = section("economic-supervisor")

for needle in ("wallet_debit", "tokens/signer:", "signer_hmac", "tokens/supervisor", "signer.key"):
    if needle in control:
        raise SystemExit(f"FAIL control mounts {needle}")
if "tokens/model" not in control:
    raise SystemExit("FAIL control must mount tokens/model for inbound verify")

if "wallet_debit" in policy or "signer.key" in policy:
    raise SystemExit("FAIL policy must not mount wallet_debit or signer.key")
if "signer_hmac" not in policy or "tokens/signer:" not in policy:
    raise SystemExit("FAIL policy must mount signer and signer_hmac")

if "wallet_debit" not in signer or "signer_hmac" not in signer:
    raise SystemExit("FAIL signer must mount hmac and debit")

if "tokens/" in wallet and wallet.count("wallet_") < 3:
    raise SystemExit("FAIL wallet must mount three wallet token files")
if "/tokens:/secrets" in wallet:
    raise SystemExit("FAIL wallet must not mount whole tokens dir")

if "wallet_credit" not in market or "tokens/marketplace" not in market:
    raise SystemExit("FAIL marketplace must mount credit and marketplace tokens")

if "wallet_debit" in sup or "signer.key" in sup:
    raise SystemExit("FAIL supervisor must not hold debit or signer.key")

if "aea_run" in hermes or ".config/controlops/economic" in hermes:
    raise SystemExit("FAIL hermes compose must not mount aea_run or economic secrets")

print("OK compose mount matrix")
PY
pass "compose mount matrix"
echo "OK economic-smoke"
