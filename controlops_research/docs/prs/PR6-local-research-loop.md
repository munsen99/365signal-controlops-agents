# PR6 — Qwen local research loop

## Objective

Introduce the first useful Research Agent loop using `qwen3.8-27b`: question -> candidate evidence -> local selection -> local finding draft -> deterministic citation validation -> supported / insufficient. This is the first PR considered an actual Research Agent.

## Why this PR exists

Introduce this capability progressively after review of its specification.

## In scope

Introduce the first useful Research Agent loop using `qwen3.8-27b`: question -> candidate evidence -> local selection -> local finding draft -> deterministic citation validation -> supported / insufficient. This is the first PR considered an actual Research Agent.

## Out of scope

Other PR capabilities; Writer Agent, publication workflow and trusted RAG ingestion.

## Files expected to change

To be specified in the approved implementation design; this placeholder does not authorise implementation.

### Proposed file-change set — source path inspection

Inspected again before implementation. No PR6 test file exists. This specification still has no source-file reference of the form `controlops_research/runtime/...`, so PR6 needs no path rewrite. Runtime code was not moved.

PR5-R source citations that used `runtime/infer.py` or `src/controlops_research/runtime/infer.py` are updated to `controlops_research/src/controlops_research/runtime/infer.py` in:

```text
controlops_research/docs/runtime-invariants.md
controlops_research/docs/prs/PR5-implementation-design/PR5-local-runtime-sandbox.md
controlops_research/docs/prs/PR5-remediation-design/05-infer-contract.md
controlops_research/docs/prs/PR5-remediation-design/02-file-change-set.md
```

The PR5-R file list already named `controlops_research/src/controlops_research/runtime/*.py`. Host data directories `$WORKSPACE/runtime/{locks,tmp,out,runs}` and the inspection note that `controlops_research/runtime/` was absent are not source-file locations and stay unchanged.

Any later PR6 file-change set that names runtime source must use:

```text
controlops_research/src/controlops_research/runtime/...
```

Do not create or cite `controlops_research/runtime/` as a source tree. The import name `controlops_research.runtime` and the host data directories `$WORKSPACE/runtime/{locks,tmp,out,runs}` are not source paths and stay as they are.

## Architecture / design

Introduce the first useful Research Agent loop using `qwen3.8-27b`: question -> candidate evidence -> local selection -> local finding draft -> deterministic citation validation -> supported / insufficient. This is the first PR considered an actual Research Agent. Detailed implementation remains subject to review.

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

PR6A is the seeded loop. An operator passes a question and seed URLs. ControlOps retrieves allowlisted pages on the host, calls the PR5-R infer adapter twice, and checks citation integrity in code. There is no discovery module.

Implementation status: IMPLEMENTED
Live acceptance: PASS. Run `a382219fc35c42718be6a9bbe4716ba0` completed `supported` on 2026-09-28T20:58:47+00:00.
Regression status: `python3 -m unittest tests.test_pr6a_acceptance` passed, 28 tests. `tests.test_pr5_acceptance` and `tests.test_pr5_infer` import and exit 5 with `NO TESTS RAN` because those modules have pytest functions and no `unittest.TestCase`.
Known limitations:
  - no discovery (PR6B)
  - supported is not evidential entailment
  - integrity is retrieve → selection → draft referential integrity only
  - only final HTTP 200 is usable
  - untrusted pages can still contain prompt-injection text; wrapping reduces risk, it does not prove the local model obeyed
Reviewer decision: ACCEPTED — Jon Bruce

The earlier design pack remains the record of the discovery stop. PR6A does not implement that missing discovery. `research/discover.py` is absent. PR6B was not started.

### Test evidence

PR6A unit tests cover the seeded allowlist, redirect cap, content-type skip, byte-cap hash, integrity failure, empty seeds, and the untrusted-source packet wrapper. They do not contact LM Studio or a search service.

### Live acceptance — run `a382219fc35c42718be6a9bbe4716ba0`

Question: Does Microsoft recommend phishing-resistant MFA for privileged Entra roles?

Operator seed URLs:

```text
https://learn.microsoft.com/en-us/entra/identity/conditional-access/how-to-policy-phish-resistant-admin-mfa
https://learn.microsoft.com/en-us/entra/identity/authentication/concept-authentication-strengths
```

The seeded loop ran without a manual paste between stages. `supported` means the model returned that status for integrity-valid selected ids. It does not mean ControlOps proved the pages entail the claim.

| Check | Result |
| --- | --- |
| Doctor before | Exit 0, `READY qwen3.8-27b` |
| `GET /v1/models` before | `qwen3.8-27b` present |
| Doctor after | Exit 0, `READY qwen3.8-27b` with `CONTROLOPS_REQUIRED_MODEL` set |
| `GET /v1/models` after | Same twelve ids, same order |
| Jail argv | `--unshare-all` present, `--share-net` absent |
| `research/discover.py` | Absent |
| PR5-R runtime diff | Empty |

Retrieval:

| Id | Final URL | HTTP | Type | Usable | Truncated | Skip | SHA-256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E1 | `https://learn.microsoft.com/en-us/entra/identity/conditional-access/policy-admin-phish-resistant-mfa` | 200 | text/html | true | false | null | `f6ac1c0b317a8fa42615061b5d77c65b660d67736d7c9316dbfa5f6b63880a6e` |
| E2 | `https://learn.microsoft.com/en-us/entra/identity/authentication/concept-authentication-strengths` | 200 | text/html | true | false | null | `a204f3c435262e5998e7011fb273b5d29e0760e280915e0504b0e28440a41120` |

E1 hops: the operator seed, then the final URL above. E2 hop: the operator seed only. Both stored files match `content_hash`. E1 text is 6336 characters. E2 text is 9873 characters.

Selection artefact `selection.json` chose `E1` only. Dropped ids: none. Model `qwen3.8-27b`. The draft packet contains the E1 source block and does not contain E2. Draft status `supported`, evidence id `E1`, model `qwen3.8-27b`, finish reason `stop`. Selection elapsed about 18.9 seconds. Draft elapsed about 15.3 seconds.

Finding: Microsoft recommends requiring phishing-resistant multifactor authentication (MFA) for privileged Microsoft Entra administrator roles.

`evidence-integrity.json` result: `PASS`. `run.json` status: `completed`. There is no `citation-validation.json`.

### Deviations from design

None in the live seeded run.

### Known issues

`supported` is not semantic entailment. Only a final HTTP 200 is usable.

### Reviewer decision

ACCEPTED — Jon Bruce
