# PR0 — Scaffold and architecture invariants

## Objective

Establish an independent package, documentation programme and static architecture safety contract.

## Why this PR exists

Establish enforceable boundaries before adding research capabilities. Models reason; deterministic controls establish authority; evidence, not model output, is the system of record.

## In scope

Minimal src-layout Python package, identity constants, import and static boundary tests, architecture invariants, canonical PR index and PR0–PR10 specifications.

## Out of scope

All operational research: fetching, search, Microsoft Learn/Roadmap integration, LM Studio/Qwen/Grok/xAI inference, database connectivity or schema changes, bubblewrap execution, Hermes/Econo profiles or plugins, autonomous behaviour, background services, systemd, Docker/Compose and paid APIs. Writer/publication/RAG ingestion is also excluded.

## Files expected to change

`README.md`, `pyproject.toml`, `src/controlops_research/{__init__,constants}.py`, `tests/test_architecture_boundaries.py`, `tests/test_package_import.py`, `docs/architecture-invariants.md`, and the twelve Markdown files in `docs/prs/` (index plus PR0–PR10). No future implementation files.

## Architecture / design

Independent package with zero runtime dependencies and no import side effects. Static AST checks target runtime Python source only; documentation/test fixtures and bare blocked-port integers must not fail. Future architecture is documented in [architecture invariants](../architecture-invariants.md).

## Security boundaries

All eighteen [architecture invariants](../architecture-invariants.md) are mandatory. Do not import `aea`, call ports 18700–18705, use `aea_run`, authenticate as `economic_app`/`controlops_admin`, read economic secrets or use the economic model token. Static checks establish only the currently enforceable contract; future runtime capabilities need additional enforcement.

## Tests

Install into a package test environment; verify import and absence of external import activity; run boundary checks with rejected/accepted fixtures. Run the smallest existing Econo/Hermes/profile/validator regression checks, report environmental blockers honestly, and run git diff/check. Do not alter existing tests to obtain a pass.

## Acceptance criteria

- package installs successfully.
- package imports successfully.
- unit tests pass.
- no `aea` runtime dependency.
- no Econo runtime connection.
- no Econo secret dependency.
- no Hermes research profile.
- no Compose change.
- no existing Econo behaviour change.
- no existing validator behaviour change.
- canonical PR documentation structure exists.
- PR1–PR10 specification placeholders exist.
- PR0 introduces no network capability.
- PR0 introduces no model inference.
- PR0 introduces no database migration.
- PR0 introduces no paid API capability.

## Evidence to capture

Initial/final git status and diff statistics; package installation/import results; exact new and existing test results; verification that pre-existing unrelated files remain unchanged; limitations and reviewer decision.

## Explicitly forbidden changes

Do not modify behaviour under `autonomous_economic_agent/`, `agents/economic-agent/` or `agents/controlops-msft-validator/`; do not modify `scripts/economic`, `ops/compose.controlops.yaml`, or existing Hermes/Econo Compose configuration. Do not reset, clean, stash, checkout or overwrite unrelated work. Do not create a research Hermes profile. Do not begin PR1. Do not commit without explicit instruction.

## Dependencies

Inspect repository structure and record git status before editing. Preserve existing user changes. Stop and report unsafe or ambiguous repository conditions. Python 3.12+, setuptools for packaging and pytest for tests; no services or credentials required.

## Exit condition

Prepare the working tree for review, report PASS/FAIL/BLOCKED with files, exact tests, architecture assertions, deviations, repository issues, git status/diff statistics and capability-change confirmations. Stop and wait for review; do not begin PR1.

## Implementation result

Status: IMPLEMENTED — PENDING REVIEW
Commit: N/A (not committed)
Completed: 2026-09-25

### Test evidence

- Offline editable installation: `/tmp/controlops-pr0-venv/bin/python -m pip install --no-build-isolation --no-deps --no-index -e ./controlops_research` — successfully installed `controlops-research-0.1.0`.
- From `controlops_research/`: `/tmp/controlops-pr0-venv/bin/python -m pytest` — **29 passed in 0.02s** (Python 3.14.4, pytest 9.1.1).
- From `autonomous_economic_agent/`: `../autonomous_economic_agent/.venv/bin/python -m pytest tests/unit/test_profile.py tests/unit/test_hashing.py` — **8 passed in 0.03s**. Covers Hermes economic profile, validator identity, Compose symlink and deterministic hashing.
- `git diff --check` and whitespace validation of new source/docs/config — passed.
- SHA-256 comparison of all 382 unrelated baseline files — no changes.
- Import succeeds in a fresh isolated interpreter with external activity guarded.
- Future PR files contain specification placeholders only; index remains PR0 IN PROGRESS, PR9 BLOCKED and all others PLANNED.

These are static/unit checks, not live-service integration tests. No live service test
is required by this scaffold. No existing tests were changed.

### Deviations from design

None recorded.

### Known issues

The repository already contained 29 modified tracked files and unrelated untracked
Econo/platform work. All were preserved. The initial generic Python environment
lacked pytest; pytest was installed from the offline uv cache in a temporary test
environment (cache access required sandbox escalation). Test startup emitted
`Failed to create stream fd: Operation not permitted`; the existing regression
invocation also emitted a virtualenv prefix warning due to its relative path.
Both test commands exited successfully with the results recorded above.

### Reviewer decision

PENDING
