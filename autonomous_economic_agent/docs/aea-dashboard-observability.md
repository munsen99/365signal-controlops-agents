# AEA dashboard observability

Read-only operator view of the Autonomous Economic Agent inside the Hermes
dashboard. This slice does not add spend, sign, accept, submit, freeze, or
policy controls.

## Architecture

```
Hermes dashboard (127.0.0.1:9119)
  -> GET /api/plugins/aea/status          # dashboard session auth, plugin backend
       -> GET http://127.0.0.1:18700/observability/status
            Authorization: Bearer AEA_OBSERVABILITY_TOKEN
            AEA control plane (loopback)
              -> ledger views / supervisor GET /v1/status / wallet GET /v1/wallet/balances
```

The browser never talks to the signer, wallet debit API, supervisor admin API,
or Postgres. The dashboard plugin holds only the observability token, read from
`AEA_OBSERVABILITY_TOKEN` or `AEA_OBSERVABILITY_TOKEN_FILE`
(`/opt/data/aea/observability.token` in the dashboard container).

Control still must not hold `AEA_SIGNER_TOKEN`, HMAC, or wallet debit.

## Endpoint

`GET /observability/status` on the control plane (`127.0.0.1:18700`).

- Auth: `AEA_OBSERVABILITY_TOKEN` only. Model, control, and supervisor tokens
  are `FORBIDDEN`. Missing token is `401`.
- Methods other than GET return `405`.
- No `/observability/sign`, pay, unfreeze, or enable routes exist.

Stable DTO includes `observation`, `contexts`, and per-field freshness
(`current` / `stale` / `unknown`). Isolated ledgers are never summed.

Facts come from durable ledger views and live supervisor/wallet reads.
Opening capital is a capital field and is never copied into verified revenue.
SOL and ETH reserves are separate native balances; there is no fiat conversion.
A Solana token mint (including wrapped-SOL `So1111…112`) is never displayed
as the owner wallet.

## Information displayed

- Degraded observation banner when supervisor, wallet, reconciliation, or
  policy is not currently authoritative
- Agent state; top-level available USDC only when a live wallet read is
  current and labelled by context (otherwise `—`)
- Separate contexts: M1 default (`controlops`), Phase-C Solana
  (`controlops_phase_c`), Phase-E EVM (`controlops_phase_e`)
- Supervisor flags with freshness: if HTTP is down they are stale/unknown,
  never current yes/no
- Reconciliation: `healthy` only after a live wallet read with zero delta;
  persisted zero delta with an unavailable wallet is `stale`
- Solana and EVM rails: configured identity, current vs last-known balances,
  last settlement
- Merged recent activity (max 20) tagged with context, rail, and network

## Refresh

The dashboard tab polls `GET /api/plugins/aea/status` every 8 seconds while
visible and pauses on `document.visibilitychange` when the page is hidden.
API failures keep the last snapshot and mark it stale, with the last successful
refresh timestamp shown. Unknown is never rendered as healthy.

## Auth boundary

| Secret | Browser | Dashboard plugin | Control |
|---|---|---|---|
| `AEA_OBSERVABILITY_TOKEN` | no | yes (server-side) | verify inbound |
| `AEA_MODEL_TOKEN` | no | no | verify tools only |
| `AEA_SIGNER_TOKEN` / HMAC / debit | no | no | no |
| `AEA_SUPERVISOR_TOKEN` | no | no | no |

Hermes Compose does not mount `~/.config/controlops/economic`. The dashboard
reads the observability token from Hermes data
(`/opt/data/aea/observability.token`). Control mounts
`tokens/observability` from the economic secrets tree.

## Read-only guarantee

- Observability has no write methods.
- The dashboard plugin registers a single GET route.
- The plugin URL allow-list is loopback `GET /observability/status`.
- Tests prove dashboard code cannot invoke signer or debit paths.

## Degraded / fail-closed

| Condition | Display |
|---|---|
| Supervisor unreadable | `readable=unknown`, health not healthy |
| Reconciliation delta ≠ 0 | `mismatch`, warning banner |
| Policy hash unverified | `verified=no`, degraded |
| Wallet probe failed | that rail `unavailable`; other rails remain |
| API timeout | `offline` / stale timestamp |

## Launch

1. Create the observability token (once):

   ```bash
   umask 077
   TOKEN_DIR="$HOME/.config/controlops/economic/tokens"
   DATA_DIR="/mnt/Storage/AI/Hermes/data/aea"
   mkdir -p "$TOKEN_DIR" "$DATA_DIR"
   openssl rand -hex 32 | tee "$TOKEN_DIR/observability" > "$DATA_DIR/observability.token"
   chmod 600 "$TOKEN_DIR/observability" "$DATA_DIR/observability.token"
   ```

2. Install the dashboard plugin from git:

   ```bash
   mkdir -p /mnt/Storage/AI/Hermes/data/plugins
   rm -rf /mnt/Storage/AI/Hermes/data/plugins/aea
   cp -a autonomous_economic_agent/dashboard_plugin /mnt/Storage/AI/Hermes/data/plugins/aea
   ```

   Enable `aea` in `/mnt/Storage/AI/Hermes/data/config.yaml` under
   `plugins.enabled`. Restart `hermes-dashboard` so plugin API routes mount.
   If the running image only discovers bundled plugins, also copy into the
   container plugins tree and rescan (no spend-gate change):

   ```bash
   docker cp autonomous_economic_agent/dashboard_plugin hermes-dashboard:/opt/hermes/plugins/aea
   curl -sS -H "X-Hermes-Session-Token: $DASHBOARD_TOKEN" \
     http://127.0.0.1:9119/api/dashboard/plugins/rescan
   ```

3. Start AEA control with spend gates disabled (do not set `AEA_LIVE_WALLET=1`,
   do not mount the live-spend file, do not pass debit/signer credentials).
   Observability still reads the durable ledger.

4. Open `http://127.0.0.1:9119/aea`.

## Troubleshoot

- Dashboard shows offline: control is down, token file missing, or
  `AEA_CONTROL_URL` is not loopback.
- One rail unavailable: the other rail should still render. Check
  `AEA_WALLET_URL` / `AEA_EVM_WALLET_URL` independently.
- Supervisor unknown: `GET http://127.0.0.1:18703/v1/status` from the host.
- Policy unverified: ledger `policy_versions` hash does not match the loaded
  policy file.
- Never enable live-spend gates to debug this UI.
