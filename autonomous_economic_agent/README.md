# Autonomous Economic Agent

Isolated economic control plane for the 365signal ControlOps estate.

Hermes is the planner. Spend control is outside the model: policy engine,
isolated signer, mock (phase A) wallet, and an independent supervisor.
The constitution in `constitution/SOUL.md` is behavioural guidance. It is
not the security boundary.

## Layout

- `constitution/` — canonical `SOUL.md` (`constitution/v0.1.0`)
- `config/` — policy YAML, schema, destinations, logging
- `src/aea/` — Python package (`aea`)
- `ops/compose.economic.yaml` — Compose project `controlops-economic`
- `tests/` — unit, integration, e2e (later PRs)

Hermes identity: `agents/economic-agent/` in the repository root.

## M1 scope

Wallet phase **A** (mock). No Solana imports, no live wallet, no live
marketplace adapter. Those are gated later PRs.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

The SOUL consistency check compares this tree’s constitution with
`agents/economic-agent/runtime/SOUL.md`.

## Existing Postgres volume

Init files `platform/postgres/init/013`–`015` run automatically only on a
**fresh** `controlops-postgres` volume. On the current workstation volume:

```bash
bash autonomous_economic_agent/scripts/apply_schema.sh
```

That applies the `economic` schema as `controlops_admin`, optionally sets
`economic_app` / `economic_supervisor` passwords from
`~/.config/controlops/economic/` when those files exist, refreshes policy
and constitution hashes from git, and runs
`platform/postgres/validation/013-economic-schema-validation.sql`.
Hermes must not be given a database URL.
