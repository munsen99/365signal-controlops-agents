# 07 — Proposed file-change set

Not applied in this turn. Discovery is missing, and the operator has not
waived it with a seed list.

## Create, after a later approval

```text
controlops_research/src/controlops_research/research/__init__.py
controlops_research/src/controlops_research/research/loop.py
controlops_research/src/controlops_research/research/discover.py
controlops_research/src/controlops_research/research/retrieve.py
controlops_research/src/controlops_research/research/extract.py
controlops_research/src/controlops_research/research/packets.py
controlops_research/src/controlops_research/research/parse.py
controlops_research/src/controlops_research/research/citations.py
controlops_research/src/controlops_research/research/artefacts.py
controlops_research/src/controlops_research/research/allowlist.py
controlops_research/tests/test_pr6_acceptance.py
```

`discover.py` stays an explicit missing-dependency stub unless a separate
approval adds a Microsoft-only mechanism. It does not call a search service.
A seed-URL acceptance run passes the operator list into `loop.py` and does
not pretend the stub discovered those URLs.

## Edit, after a later approval

```text
controlops_research/docs/prs/PR6-local-research-loop.md
```

Status text only, after tests and any authorised live run. A live report
would be `controlops_research/docs/prs/reports/pr6-<date>.md`.

## Path inspection

PR6 docs and tests were inspected before this pack. The only PR6 document
was the placeholder specification. It had no source path
`controlops_research/runtime/...`. No PR6 test file existed. No runtime file
is moved. Later source references use
`controlops_research/src/controlops_research/runtime/...` for PR5-R and
`controlops_research/src/controlops_research/research/...` for this loop.

## Frozen

```text
controlops_research/src/controlops_research/runtime/**
controlops_research/src/controlops_research/fetch.py
controlops_research/src/controlops_research/policy.py
controlops_research/src/controlops_research/snapshot.py
hermes-agent
Compose
Econo, Writer, trusted RAG, Postgres, PR7, PR11
```

Run artefacts, when a run is later authorised, go only to
`$WORKSPACE/runtime/runs/<run_id>/` with `question.yaml`,
`candidate-evidence.json`, `finding.yaml`, `citation-validation.json`,
`run.json`, and `evidence/<candidate_id>.bin`.
