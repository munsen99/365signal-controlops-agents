# PR2 implementation report

Date: 2026-09-26

Design: `approved-1` at `e5026c8`, with approved D8 option-1 amendment

Status: **PR2 IMPLEMENTED AND TESTED — PENDING HUMAN REVIEW**

## Summary and files

PR2 implements PR1-gated HTTPS GET acquisition, independent redirect and DNS
address evaluation, frozen numeric connection pinning, verified TLS hostname/SNI,
bounded network activity, exact raw-byte SHA-256 snapshots, atomic content-addressed
storage and versioned deterministic plain-text/HTML extraction. It performs no
model reasoning and creates acquisition records, not Evidence Plane records.

Created: `src/controlops_research/fetch.py`,
`src/controlops_research/snapshot.py`, `tests/test_fetch_snapshot.py`, five files
under `tests/fixtures/fetch/`, the D8 amendment record and this report.

Modified: `README.md`, `docs/prs/README.md`, `docs/prs/PR2-fetch-snapshot.md`,
the PR2 design README and file-set document, and
`tests/test_architecture_boundaries.py`.

`docs/architecture-invariants.md` is intentionally unchanged under the approved
D8 amendment. `pyproject.toml`, package `__init__.py`, and all PR1 source, data,
fixtures, manifest and tests are unchanged.

## D1-D8 and security mapping

- D1: only PR1 `ACCEPT`; every redirect is re-evaluated.
- D2: bounded resolver, every answer evaluated by PR1, mixed sets reject, and
  connections use frozen numeric addresses with canonical Host/SNI.
- D3: HTTPS GET only; fixed headers; 3/5/10-second stage limits, five redirects,
  8 MiB body and 30-second network-only deadline.
- D4: strict UTF-8/ASCII plain text and deterministic HTML extraction.
- D5: raw SHA-256 object store plus atomic canonical metadata/derived text.
- D6: frozen slotted results, closed enums and explicit failure stages.
- D7: deterministic no-Internet security, boundary and persistence suite.
- D8: exact file boundary implemented with approved option-1 amendment.

The public API accepts no resolver, transport, headers, policy override, TLS
override or proxy configuration. Production resolution is bounded and reaped;
the connector performs no second DNS lookup and uses TLS 1.2 minimum with default
verification. Extraction and persistence cannot emit a network deadline failure
after raw-body completion.

## Test evidence and acceptance

```text
/tmp/controlops-pr1-py314/bin/python -m pytest
768 passed in 0.56s

/tmp/controlops-pr1-py313/bin/python -m pytest
768 passed in 0.55s
```

All twelve approved acceptance criteria are covered, including policy/redirect
gates, mixed DNS rejection, resolver lifecycle, numeric pinning, Host/SNI/TLS,
timeouts/deadlines, exact bytes/hashes, limits, charsets/extraction, empty content,
idempotent persistence, symlink rejection, immutable results, isolation and all
PR0/PR1 regressions. No test used the live public Internet.

## SHA-256 identities

```text
545be5952c7b8141c2a143d373b249181156210db5b5149b2827631f85e5b4a1  fetch.py
d13e4332e91044cd3b687678339db379352eefc74e160cc7a5064c00c96488b3  snapshot.py
1f7095a8dac0f1abd5f54d3cae40dab17d1a50d510f13881c5a344cc45dfb8c7  test_fetch_snapshot.py
266c201c590fca5fab967a0913cc007922e28b5444a2f40ea69fd23a8a4b8d86  plain-utf8.txt
ccf8c17e17c1c23581efc0cafb8bc3971f25f3a66a6ffb6ad91cca1022936d5e  page.html
abb04f55e7c0a0fc0663e08c060346374c1e66727f9ba83b2bf766b15f0abe44  page-visible.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  empty.txt
429f6af96fe620c59327740cc18aa6c9757852d963fcf1352e37ee477b7c705a  responses.json
```

Deviations from the amended approved design: **NONE**. Known limitations are the
approved narrow status-200 UTF-8/ASCII text/HTML boundary and deterministic seam
testing instead of live Internet access.

## Working tree and review proposal

Review and, if accepted, stage only the created/modified ControlOps Research
files listed above. Existing scratch/reference files and all unrelated Econo,
platform and workspace changes remain excluded. No files were staged, committed
or pushed.
