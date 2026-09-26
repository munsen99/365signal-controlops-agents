# PR3 — Evidence Plane and citation verification

## Objective

Introduce schema `research`, evidence storage and deterministic citation verification. Evidence must correspond to a stored snapshot span. Do not use schema `economic` or the reserved assurance `evidence` schema.

## Why this PR exists

Introduce this capability progressively after review of its specification.

## In scope

Introduce schema `research`, evidence storage and deterministic citation verification. Evidence must correspond to a stored snapshot span. Do not use schema `economic` or the reserved assurance `evidence` schema.

## Out of scope

Other PR capabilities; Writer Agent, publication workflow and trusted RAG ingestion.

## Files expected to change

To be specified in the approved implementation design; this placeholder does not authorise implementation.

## Architecture / design

Introduce schema `research`, evidence storage and deterministic citation verification. Evidence must correspond to a stored snapshot span. Do not use schema `economic` or the reserved assurance `evidence` schema. Detailed implementation remains subject to review.

## Security boundaries

Preserve all [architecture invariants](../architecture-invariants.md). Research remains isolated from Econo and Hermes.

## Tests

Define capability-specific checks in the approved implementation design.

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

Status: NOT STARTED
Commit: N/A
Completed: N/A

### Test evidence

Not yet implemented.

### Deviations from design

None recorded.

### Known issues

None recorded.

### Reviewer decision

PENDING
