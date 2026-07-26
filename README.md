# 365signal ControlOps Agents

Version-controlled definitions, contracts, tests and deployment material for
the 365signal ControlOps agent estate.

## Architecture

Hermes Agent provides the runtime.

This repository contains the ControlOps-owned agent definitions and does not
vendor or modify the Hermes source code.

## Directory model

- `agents/` — individual ControlOps agent definitions
- `scripts/` — deployment and validation utilities
- `docs/` — architecture and operational documentation

Live Hermes profile data is stored outside this repository and is not committed.

## Initial agent

`controlops-msft-validator`

Validates Microsoft 365, Microsoft Entra and Azure technical assertions against
approved authoritative sources and produces traceable evidence records.
