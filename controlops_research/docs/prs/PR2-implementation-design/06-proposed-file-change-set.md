# 06 — Exact proposed future file-change set

Decision D8: **APPROVED AS AMENDED** on 2026-09-26. This list is the complete
implementation boundary.
None of these implementation changes is made by this design task.

## Files to create during a separately authorised implementation

| File | Purpose |
| --- | --- |
| `src/controlops_research/fetch.py` | Public result types, policy gate, redirect/DNS/TLS/HTTP lifecycle and fixed limits |
| `src/controlops_research/snapshot.py` | Raw hashing, extraction, canonical metadata and atomic filesystem store |
| `tests/test_fetch_snapshot.py` | Public contract, adversarial boundary, transport, persistence and isolation tests |
| `tests/fixtures/fetch/plain-utf8.txt` | Exact plain-text source bytes |
| `tests/fixtures/fetch/page.html` | Exact HTML source bytes covering extraction rules |
| `tests/fixtures/fetch/page-visible.txt` | Expected derived HTML text |
| `tests/fixtures/fetch/empty.txt` | Zero-byte successful source fixture |
| `tests/fixtures/fetch/responses.json` | Scripted status/header/redirect cases and fixture SHA-256 values |

## Files to modify during that implementation

| File | Purpose |
| --- | --- |
| `README.md` | Describe the implemented bounded acquisition capability and local snapshot boundary |
| `docs/architecture-invariants.md` | **Intentionally unchanged by approved amendment:** PR1 pins its exact bytes; PR2 invariants remain in the approved PR2 design/specification |
| `docs/prs/README.md` | Update PR2 status only after its actual review state is known |
| `docs/prs/PR2-fetch-snapshot.md` | Link approved design, implementation record and final acceptance state |
| `tests/test_architecture_boundaries.py` | Extend static dependency/configuration checks for the new network module without weakening PR0/PR1 guards |
| `pyproject.toml` | Add no runtime dependency; update only packaging/test configuration if implementation proves it necessary and review explicitly permits it |

`src/controlops_research/__init__.py`, PR1 policy/data/fixtures/tests, other PR
specifications and every non-Research path are excluded. If implementation needs
another file or a dependency, it must stop and obtain a design amendment rather
than expanding scope silently.

## Files actually changed by this design-only task

Only the seven new Markdown files in
`docs/prs/PR2-implementation-design/` are created:

1. `README.md`
2. `01-authority-and-network.md`
3. `02-retrieval-contract.md`
4. `03-snapshot-and-extraction.md`
5. `04-result-and-failures.md`
6. `05-tests-and-acceptance.md`
7. `06-proposed-file-change-set.md`

The user-modified parent prompt, runtime source, tests, fixtures, package metadata
and programme index are not changed in this task. No retrieval, commit or push is
performed.
