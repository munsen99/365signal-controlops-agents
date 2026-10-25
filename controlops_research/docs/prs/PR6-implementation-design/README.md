# PR6 implementation-design pack

Status: **DESIGN WRITTEN — IMPLEMENTATION STOPPED**.
Prepared: 2026-09-28T21:05:09+01:00. Host: `proteu5-Vengeance-X-AMD`.

PR5-R acceptance exists:
`docs/prs/reports/pr5-remediation-2026-09-28.md` records status
**REMEDIATED** and required model `qwen3.8-27b`. A live
`GET /v1/models` during this inspection returned HTTP 200 and included
that exact id.

Microsoft-only discovery is not in the tree. D4 says the implement pass
stops when that dependency is missing. This pack does not authorise
implementation, a search provider, PR7, or PR11.

Seed URLs for the live question are allowed only after the operator
records them. None were supplied with this inspection.

| Document | Subject |
| --- | --- |
| [01 — Flow and trust boundary](01-flow-and-trust-boundary.md) | Host loop, frozen PR5-R, hard-fail versus insufficient |
| [02 — Retrieval allowlist](02-retrieval-allowlist.md) | Microsoft hosts, aka.ms hops, byte cap |
| [03 — Discovery dependency](03-discovery-dependency.md) | Missing discovery; why implementation stops |
| [04 — Infer packets and parse](04-infer-packets-and-parse.md) | Two adapter calls and JSON failure |
| [05 — Citation validation](05-citation-validation.md) | Code checks and forced insufficient |
| [06 — Tests and acceptance](06-tests-and-acceptance.md) | Deterministic tests and the blocked live question |
| [07 — Proposed file-change set](07-proposed-file-change-set.md) | Files for a later approved implement pass |
