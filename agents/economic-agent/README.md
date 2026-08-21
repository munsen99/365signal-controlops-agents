# economic-agent

Hermes identity for the ControlOps Autonomous Economic Agent.

Canonical constitution: `autonomous_economic_agent/constitution/SOUL.md`.
`runtime/SOUL.md` must remain a byte-identical copy.

This folder is identity and profile only. The isolated control plane lives
under `autonomous_economic_agent/`. Policy, signer, supervisor, and wallet
are not in this tree.

M1 uses mock wallet and mock marketplace only. Do not point this profile
at a live wallet or live marketplace.
