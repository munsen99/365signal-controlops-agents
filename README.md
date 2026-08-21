# 365signal ControlOps Agents

Version-controlled definitions, contracts, tests and deployment material for
the 365signal ControlOps agent estate.

## Architecture

Hermes Agent provides the runtime.

This repository contains the ControlOps-owned agent definitions and does not
vendor or modify the Hermes source code.

## Directory model

- `agents/` — individual ControlOps agent definitions
- `autonomous_economic_agent/` — isolated economic control plane (policy, ledger,
  mock wallet, signer, supervisor). Not a general-purpose agent framework.
- `platform/` — Postgres init, validation SQL, and related platform assets
- `scripts/` — deployment and validation utilities
- `docs/` — architecture and operational documentation

Live Hermes profile data is stored outside this repository and is not committed.

Secrets, freeze flags, and wallet keys for the economic agent live outside
this repository (`~/.config/controlops/economic/`) and are never mounted into
Hermes.

## Agents

### `controlops-msft-validator`

Validates Microsoft 365, Microsoft Entra and Azure technical assertions against
approved authoritative sources and produces traceable evidence records.

### `economic-agent`

Constrained autonomous economic actor. Hermes identity lives in
`agents/economic-agent/`. The control plane lives in
`autonomous_economic_agent/`. v0.1 is mock-first (wallet phase A): no live
wallet and no live marketplace in this milestone.
