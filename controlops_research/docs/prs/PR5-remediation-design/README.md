# PR5-R remediation design pack

Status: **APPROVED**. Revision: `draft-1`.
Prepared: 2026-09-28. Approved: 2026-09-28.
Required model: `qwen3.8-27b`. PR5-R implementation: **REMEDIATED**.

This pack was the approval gate for the PR5 local runtime. The operator
approved it, set the required model, and authorised retirement of the
prototype launcher and its bash test. It does not authorise PR6.

Closed decisions D1–D10 in the remediation prompt are binding. This pack
does not reopen them.

| Item | Subject | Proposed choice | Review |
| --- | --- | --- | --- |
| D1 | Jail network | `--unshare-all` only. No `CONTROLOPS_ALLOW_SHARED_NET` and no `--share-net`. | CLOSED |
| D2 | GPU | LM Studio owns the GPU. The jail uses a fresh `--dev /dev` and receives no GPU device nodes. | CLOSED |
| D3 | GPU claim | Serialised ControlOps jobs plus refusal to start when the required id is absent from `GET /v1/models`. No VRAM, loaded-versus-listed, or other-client claim. | CLOSED |
| D4 | Required model | `CONTROLOPS_REQUIRED_MODEL` has no default. Unset or empty is `CONFIG_INVALID`. The operator names one inspected id below. | CLOSED, ID REQUIRED |
| D5 | Filesystem | Four RW runtime directories only, plus the named execution substrate in [03](03-bind-list.md). | CLOSED |
| D6 | Split | Host preflight, host infer, host-side bubblewrap exec. Gateway has no bubblewrap; Compose stays unchanged. | CLOSED |
| D7 | Infer | One adapter, `POST /v1/chat/completions`, model field equals the required id, lock held only for that request. | CLOSED |
| D8 | Payload failures | `MODEL_STATE_INCOMPATIBLE` is payload shape or protocol. Missing id is `REQUIRED_MODEL_MISSING`. | CLOSED |
| D9 | Doctor | `python -m controlops_research.runtime doctor`. Existing Hermes `scripts/controlops` is recorded, not rewritten. | CLOSED |
| D10 | Status | After approval and before live evidence: `IN PROGRESS — NOT ACCEPTED`. `REMEDIATED` only after the Hermes live pack. | CLOSED |

## Documents

| Document | Subject |
| --- | --- |
| [01 — Inspection](01-inspection.md) | Host, gateway, model ids, absent inputs |
| [02 — File change set](02-file-change-set.md) | Exact files for the approved implementation |
| [03 — Bind list](03-bind-list.md) | RW runtime binds, execution substrate, unmounted paths |
| [04 — Required model](04-required-model.md) | Inspected ids and the unset operator choice |
| [05 — Infer contract](05-infer-contract.md) | The single infer verb |
| [06 — Tests](06-tests.md) | Deterministic tests and the later Hermes live pack |
| [07 — Unchanged](07-unchanged.md) | Trees and claims this remediation will not touch |

## Approval recorded

1. The pack was approved.
2. `CONTROLOPS_REQUIRED_MODEL=qwen3.8-27b` is set in [04](04-required-model.md).
3. Retirement of `scripts/research-runtime` and `tests/test_runtime_sandbox.sh` was authorised and done.
4. Status-only updates to the programme index and the PR5 implementation-design index were authorised and done.

## PR6 gate

Reviewer decision and explicit human operator approval are required before PR6.
This pack does not supply either. PR6 stays unstarted.
