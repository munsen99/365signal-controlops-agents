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
