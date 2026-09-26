# PR3 implementation report — 2026-09-26

## Result

Implemented the PR3 evidence plane within the approved file boundary. Runtime
records persist in a caller-rooted, reload-on-operation JSON catalogue with
atomic writes and restrictive permissions. Citation verification validates the
PR2 snapshot metadata and raw digest, rebuilds the extraction contract, reruns
the deterministic extractor, compares the stored visible-text bytes, and then
checks the citation span and excerpt digest. `research_schema.sql` is a
future-only schema definition; runtime does not connect to PostgreSQL.

## Validation

- Python 3.13.14: full suite passed, 794 tests.
- Python 3.14.4: 792 tests passed. The two isolated-install tests require the
  package to be editable-installed for that interpreter; this workspace has no
  such installation, and its isolated subprocesses intentionally ignore
  `PYTHONPATH`. The remaining suite passes under Python 3.14.4.
- `git diff --check`: passed.
- Evidence-plane tests use locally published PR2 fixtures and make no network
  requests.

## Scope

Changed the PR3 runtime modules, future SQL schema, evidence fixture and tests,
architecture boundary test, README, PR3 specification result, programme index,
and this report. PR4 was not started. No commit was created.

## Review

Status: IMPLEMENTED AND TESTED — PENDING REVIEW
Reviewer decision: PENDING
