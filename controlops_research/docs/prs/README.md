# ControlOps Research Agent build programme

This is the canonical build index. PR statuses are maintained here.
Future specifications record intent; they do not authorise implementation.

| PR | Scope | Status |
| --- | --- | --- |
| [PR0](PR0-research-scaffold.md) | Scaffold and architecture invariants | IN PROGRESS |
| [PR1](PR1-public-url-policy.md) | Public URL policy | ACCEPTED |
| [PR2](PR2-fetch-snapshot.md) | Controlled fetch, snapshot and hash | PLANNED |
| [PR3](PR3-evidence-plane.md) | Evidence Plane and citation verification | PLANNED |
| [PR4](PR4-budget-gate.md) | Budget and escalation gate | PLANNED |
| [PR5](PR5-local-runtime-sandbox.md) | Local runtime sandbox and GPU protection | PLANNED |
| [PR6](PR6-local-research-loop.md) | Qwen local research loop | PLANNED |
| [PR7](PR7-learn-discovery.md) | Microsoft Learn discovery | PLANNED |
| [PR8](PR8-roadmap-monitor.md) | Microsoft Roadmap monitoring | PLANNED |
| [PR9](PR9-frontier-escalation.md) | Grok frontier escalation | BLOCKED |
| [PR10](PR10-integration-acceptance.md) | Integration and acceptance | PLANNED |

PR9 is BLOCKED until the local/evidence architecture exists and the Grok isolation
spike has passed. Frontier inference must never be the default execution path.

PR0 stops at the scaffold. PR1 implementation is complete and accepted; see the
[final acceptance record](approvals/pr1-final-acceptance-2026-09-26.md) for commit
conditions. Runtime acceptance is satisfied
under the approved Python >=3.13 target (3.13 baseline, 3.14 preferred).
PR2–PR10 require subsequent review and authorisation.
Writer Agent, publication workflow and trusted RAG ingestion remain outside this
programme unless explicitly introduced by a later approved architecture decision.
