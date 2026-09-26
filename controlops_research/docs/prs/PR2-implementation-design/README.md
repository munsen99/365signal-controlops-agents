# PR2 implementation-design review package

Status: **DESIGN APPROVED — IMPLEMENTATION NOT AUTHORISED**. Revision: `approved-1`.
Prepared: 2026-09-26. PR2 implementation: **NOT STARTED**.

This package designs controlled HTTPS retrieval, immutable source snapshots and
deterministic visible-text extraction. It does not implement PR2, perform a live
retrieval, approve its own decisions, or authorise a commit. The accepted PR1
implementation at `e33a2dff5b272c6cc970783305e9729c450eab53` and the
[architecture invariants](../../architecture-invariants.md) remain authoritative.

The repository review found no PR1 defect that prevents this design. PR1's public
`evaluate_url` function is sufficient for candidate, redirect and resolved-address
checks. PR2 must not import PR1 private functions or reproduce its address tables.

| Decision | Subject | Proposed choice | Review |
| --- | --- | --- | --- |
| D1 | [Authority and redirect boundary](01-authority-and-network.md) | Only PR1 `ACCEPT`; evaluate every hop independently | APPROVED |
| D2 | [DNS and connection safety](01-authority-and-network.md) | Bounded resolution; validate every answer through PR1; pin numeric connection | APPROVED |
| D3 | [HTTP and resource limits](02-retrieval-contract.md) | GET-only HTTPS, 5 redirects, 30 s network acquisition, 8 MiB body | APPROVED |
| D4 | [Content and extraction](03-snapshot-and-extraction.md) | UTF-8/ASCII `text/plain` and `text/html`; versioned deterministic extraction | APPROVED |
| D5 | [Snapshot and provenance](03-snapshot-and-extraction.md) | Content-addressed raw bytes plus atomic retrieval record | APPROVED |
| D6 | [Result and failure contract](04-result-and-failures.md) | Closed immutable result types and stable fail-closed codes | APPROVED |
| D7 | [Tests and acceptance](05-tests-and-acceptance.md) | No live Internet; scripted transports and connection-pin tests | APPROVED |
| D8 | [Future file boundary](06-proposed-file-change-set.md) | Two runtime modules, one test module, fixed fixtures and scoped docs | APPROVED |

## Security posture

An accepted hostname is not sufficient connection authority. For every request
hop, PR2 obtains a fresh PR1 `ACCEPT`, resolves once within a bounded worker,
submits every unique numeric answer back through `evaluate_url`, rejects the
entire hop if any answer is not accepted, and connects only to one of that frozen
set. The original hostname remains the HTTP `Host` value and TLS SNI/certificate
identity. The connection path performs no second name lookup.

HTTP URLs remain non-executable because PR1 returns `REVIEW`. There is no human
override flag in PR2. Redirects to HTTP, private destinations or any other
non-`ACCEPT` target fail.

## Scope and dependencies

The proposal uses the Python standard library only. It adds no model, browser,
JavaScript, PDF, Office, image, database, queue, proxy, cookie, credential,
publication or trusted-RAG capability. Raw snapshots are acquisition records,
not verified evidence or approved knowledge.

## Review outcome

D1-D8, including the amended D3 network-acquisition deadline, were approved by
the human reviewer on 2026-09-26. The approval is recorded in
[pr2-design-2026-09-26.md](../approvals/pr2-design-2026-09-26.md).
No architectural question is left for implementation to decide. Design approval
does not authorise implementation.

```text
D1 authority/redirects: APPROVED
D2 DNS/connection pinning: APPROVED
D3 HTTP/limits: APPROVED AS AMENDED
D4 content/extraction: APPROVED
D5 snapshot/provenance: APPROVED
D6 failures/results: APPROVED
D7 tests/acceptance: APPROVED
D8 file boundary: APPROVED
Reviewer / date: human reviewer / 2026-09-26
Implementation authorisation: NOT GIVEN
```
