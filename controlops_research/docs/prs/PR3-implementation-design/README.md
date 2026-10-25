# PR3 realised implementation record

Status: **IMPLEMENTED, TESTED, REVIEWED AND ACCEPTED WITH FIXES**. Revision:
`realised-1`. Accepted commit: `56dd905 feat(research): implement PR3 citation
evidence plane`.

This pack describes the architecture that commit `56dd905` implements. It is a
retrospective technical record, not a new design, implementation authorisation,
or statement that planned PR4+ capabilities exist. The PR3 specification and
[architecture invariants](../../architecture-invariants.md) remain the
programme references. The accepted implementation and [Sol review](../reports/pr3-sol-review-2026-09-26.md)
are the evidence for realised behavior.

The locked PR3 implementation prompt was not checked into this repository at
the accepted commit. The user-provided copy was available at
`/home/proteu5/Documents/controlops/PR3-codex-implementation-prompt.md`; this
pack does not reconstruct or modify it. Realised claims below follow the
committed runtime and tests, with the Sol review as accepted assurance evidence.

## State

| Capability | State | Evidence |
| --- | --- | --- |
| Source, snapshot-reference and citation provenance | IMPLEMENTED | `evidence.py`, `verify.py` |
| Snapshot hash, deterministic re-extraction and span checking | IMPLEMENTED | `verify.py` |
| Python 3.13/3.14 suite and accepted review | VERIFIED | [assurance record](05-verification-and-assurance.md) |
| PostgreSQL persistence, model use, publication, trusted RAG and PR4+ | FUTURE / NOT IMPLEMENTED | PR3 code has no such execution path |

## Documents

| Document | Realised subject |
| --- | --- |
| [01 — Provenance model](01-provenance-model.md) | Records, authority, identity and binding |
| [02 — Citation verification](02-citation-verification.md) | Disk checks, span rules and verdict codes |
| [03 — Persistence and SQL](03-persistence-and-sql.md) | Runtime JSON catalogue and future SQL contract |
| [04 — Security and isolation](04-security-and-isolation.md) | Runtime dependencies, network and static boundaries |
| [05 — Verification and assurance](05-verification-and-assurance.md) | Accepted tests, review decision and known limits |

## Relationship to PR2

PR2 `SnapshotStore` owns the observation. PR2 stores authoritative captured
bytes as `body.bin`, retrieval metadata, and derived `visible-text.txt`. PR3
does not fetch or copy source bytes. It stores provenance claims and references
to the PR2 retrieval, then verifies those claims against the on-disk PR2
record.

The PR3 `Source.locator` is descriptive identity; no verifier follows it. A
citation points to a `SnapshotRef`, whose `retrieval_id` ultimately selects the
PR2 observation. A catalogue row cannot prove itself because verification
rehashes and re-extracts from the PR2 store before checking the citation.

## Scope

PR3 implements a caller-rooted JSON catalogue, source and snapshot-reference
registration, citation creation, span verification, citation verification,
and a future-only SQL schema file. It deliberately does not implement network
fetch, PostgreSQL runtime access, a model or LLM, Hermes profile integration,
validator integration, LanceDB, publication, or trusted RAG writes. Those
items are FUTURE / NOT IMPLEMENTED.

## State by evidence source

- **IMPLEMENTED:** the accepted Python runtime and SQL contract at commit
  `56dd905`.
- **VERIFIED:** the test and assurance results recorded in the Sol review and
  detailed in [05](05-verification-and-assurance.md).
- **FUTURE / NOT IMPLEMENTED:** PostgreSQL deployment and all downstream
  research, model, publication and RAG capabilities.
