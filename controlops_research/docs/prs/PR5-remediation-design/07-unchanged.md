# 07 — What will not change

- `/home/proteu5/AI/Hermes/hermes-agent`, including its Compose files.
- Workspace Compose under `ops/` and `platform/`.
- Econo, Writer, trusted RAG, Postgres, and the Microsoft validator.
- PR6 through PR11, including `docs/prs/PR6-local-research-loop.md`. Reviewer decision and explicit human operator approval are required before PR6.
- `docs/architecture-invariants.md`.
- `src/controlops_research/fetch.py`, `evidence.py`, `policy.py`,
  `snapshot.py`, and `verify.py`.
- `pyproject.toml`.
- `scripts/controlops` and `tests/operations/controlops-smoke.sh`.
- LM Studio model state. This design turn performed one GET and did not POST.

The jail network stays unshared. No `--share-net` default is added. The
sandbox receives no GPU device node. ControlOps does not load, unload, evict,
or pin a model.

The approved implementation and the Hermes live probe are recorded in
`docs/prs/reports/pr5-remediation-2026-09-28.md`. The specification status is
`REMEDIATED`. PR6 stays forbidden until a reviewer decision and a separate
human approval.
