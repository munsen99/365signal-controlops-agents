# PR5 — Local runtime sandbox and GPU protection

Status: **REMEDIATED**

## Objective

Provide the host-side boundary for later ControlOps Research work: exact LM
Studio readiness, one infer verb, a non-blocking infer lock, and a Bubblewrap
jail with an unshared network namespace. PR5 does not implement a research loop.

## Contract

`python -m controlops_research.runtime doctor` is the doctor entry.
`CONTROLOPS_REQUIRED_MODEL` has no default in code. Unset or empty fails with
`CONFIG_INVALID` and performs no HTTP. The operator-approved value, taken from
the inspected `GET /v1/models` list, is:

```text
qwen3.8-27b
```

The production base URL is the fixed value `http://127.0.0.1:1234`.

ControlOps will not call load, unload, or evict, will refuse to start if the
required model id is absent from `GET /v1/models`, and will serialise its own
infer calls with a non-blocking flock.

## Host and jail

Readiness and infer run on the Hermes host. The gateway container has no
Bubblewrap, so exec stays on the host. Compose is unchanged.

The jail is `bwrap --unshare-all` with capabilities dropped, a cleared
environment, `/usr` read-only, merged-usr symlinks, a new `/proc`, a fresh
`--dev /dev`, and a private `/tmp`. The fresh device directory does not receive
GPU nodes. `--share-net` is absent. `CONTROLOPS_ALLOW_SHARED_NET` cannot enable
it.

Read-write ControlOps content is only:

```text
$WORKSPACE/runtime/locks
$WORKSPACE/runtime/tmp
$WORKSPACE/runtime/out
$WORKSPACE/runtime/runs
```

mapped at `/opt/data/workspace/runtime/...`. `$WORKSPACE` is
`/mnt/Storage/AI/Hermes/workspace`. The whole workspace is not mounted.
The runtime directories are created on first use with mode `0700`. This host's
workspace filesystem does not store that mode and reports `0755`.

## Infer

`controlops_research/src/controlops_research/runtime/infer.py` is the only LM Studio infer client, together with the
readiness GET in the same runtime package. The call order is readiness, then
the non-blocking lock, then `POST /v1/chat/completions` with `model` equal to
the required id. The lock covers that request only. The result is assistant
text, the raw finish reason, and the echoed model id. A caller timeout is
required. There is no fallback model and no chat-history write.

`REQUIRED_MODEL_MISSING` means the exact id is absent from an HTTP 200 model
list. `MODEL_STATE_INCOMPATIBLE` means the payload shape or protocol failed.
`ENDPOINT_UNAVAILABLE` means connection failure, timeout, or a non-200 response.
`MODEL_CONTENTION` means the infer lock is already held.

## Evidence

Deterministic tests do not contact LM Studio. The full suite on this host was
`814 passed`. The Hermes live probe is recorded in
[the remediation report](../reports/pr5-remediation-2026-09-28.md).

## Historical prototype

`scripts/research-runtime` previously hardcoded `qwen3.8-27b`, locked a file
under `/run/user`, and mounted the whole workspace read-only. That jail could
exec a command and could not call LM Studio. The 2026-09-28 write-up of that
prototype remains at
[pr5-live-acceptance-2026-09-28.md](../reports/pr5-live-acceptance-2026-09-28.md).
It is not PR5-R acceptance. The launcher is now a non-executing pointer, and
`tests/test_runtime_sandbox.sh` has been removed.

## Out of scope

PR5 adds no research loop, discovery, Writer Agent, frontier escalation,
trusted RAG ingestion, or PostgreSQL persistence. It does not modify Hermes
source or Compose. PR6 stays forbidden until a reviewer decision and a separate
human approval.

## Implementation result

Implementation status: REMEDIATED
Acceptance result: Hermes live probe passed on 2026-09-28T20:46:05+01:00
Required model: qwen3.8-27b
Regression status: PASS (814 passed)
Reviewer decision: PR5-R design pack approved by the operator. PR6 remains forbidden pending a reviewer decision and a separate human approval.
