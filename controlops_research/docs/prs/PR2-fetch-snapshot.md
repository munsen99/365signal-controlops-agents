# PR2 — Controlled fetch, snapshot and hash

## Objective

Introduce controlled public HTTP retrieval. Store/source raw bytes, SHA-256 and extracted visible text. Still no model reasoning.

## Why this PR exists

Introduce this capability progressively after review of its specification.

## In scope

Introduce controlled public HTTP retrieval. Store/source raw bytes, SHA-256 and extracted visible text. Still no model reasoning.

## Out of scope

Other PR capabilities; Writer Agent, publication workflow and trusted RAG ingestion.

## Files expected to change

The exact boundary is recorded in the
[approved implementation design](PR2-implementation-design/06-proposed-file-change-set.md).

## Architecture / design

The [approved design](PR2-implementation-design/README.md) defines the PR1
authority gate, DNS/connection pinning, bounded HTTPS behavior, raw snapshot and
extraction contracts, deterministic failures, tests and file boundary. D1-D8
were approved on 2026-09-26; D3 was approved as amended.

## Security boundaries

Preserve all [architecture invariants](../architecture-invariants.md). Research remains isolated from Econo and Hermes.

## Tests

The approved D7 suite uses deterministic local resolver/transport/TLS/response
seams and fixtures. It requires no live public Internet.

## Acceptance criteria

Demonstrate the stated intent and preserve the architecture contract; detailed acceptance checks require review.

## Evidence to capture

Implementation revision, test results and reviewer decision when implemented.

## Explicitly forbidden changes

No unrelated Econo, validator or Hermes changes; no direct raw-research ingestion into trusted RAG. No implementation in PR0.

## Dependencies

PR0 architecture contract and review of this specification. Further dependencies will be established in the approved design.

## Exit condition

Reviewed implementation and acceptance evidence for this PR. This document alone is not permission to begin.

## Implementation result

Status: PR2 IMPLEMENTED AND TESTED — PENDING HUMAN REVIEW
Commit: N/A
Completed: 2026-09-26

### Test evidence

Python 3.14: 768 passed. Python 3.13: 768 passed. No live public retrieval was
used. See [the implementation report](reports/pr2-implementation-2026-09-26.md).

### Deviations from design

NONE. D8 was amended with explicit human approval to preserve the PR1-pinned
architecture document.

### Known issues

No acceptance-blocking issue is known. Production network behavior is exercised
through deterministic seams; tests do not contact the live public Internet.

### Reviewer decision

PENDING
