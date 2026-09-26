# PR9 — Grok frontier escalation

## Objective

Introduce a tightly governed frontier reasoning worker only after the security/isolation spike passes. It must not become the default orchestrator. Require an explicit reason code, explicit budget, maximum one escalation per research run, a curated evidence packet, no browsing, no subagents, no access to Econo or ControlOps secrets, and deterministic citation validation after the response.

## Why this PR exists

Introduce this capability progressively after review of its specification.

## In scope

Introduce a tightly governed frontier reasoning worker only after the security/isolation spike passes. It must not become the default orchestrator. Require an explicit reason code, explicit budget, maximum one escalation per research run, a curated evidence packet, no browsing, no subagents, no access to Econo or ControlOps secrets, and deterministic citation validation after the response.

## Out of scope

Other PR capabilities; Writer Agent, publication workflow and trusted RAG ingestion.

## Files expected to change

To be specified in the approved implementation design; this placeholder does not authorise implementation.

## Architecture / design

Introduce a tightly governed frontier reasoning worker only after the security/isolation spike passes. It must not become the default orchestrator. Require an explicit reason code, explicit budget, maximum one escalation per research run, a curated evidence packet, no browsing, no subagents, no access to Econo or ControlOps secrets, and deterministic citation validation after the response. Detailed implementation remains subject to review.

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

Local/evidence architecture must exist and the Grok isolation spike must pass. PR9 remains BLOCKED.

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
