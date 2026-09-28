# PR5-R live remediation evidence — 2026-09-28

Status: **REMEDIATED**. Host: `proteu5-Vengeance-X-AMD`.
Probe time: `2026-09-28T20:46:05+01:00`.
Required model: `qwen3.8-27b`, set from the operator approval and present in
`GET /v1/models`.

The runtime module loaded from
`controlops_research/src/controlops_research/runtime/__init__.py`.

## Doctor and model list

| Step | Result |
| --- | --- |
| `python -m controlops_research.runtime doctor` before | Exit 0. `READY qwen3.8-27b` |
| `GET /v1/models` before | HTTP 200. Twelve ids. `qwen3.8-27b` present. |
| Infer `Reply with the single token: PONG`, timeout 120s | Exit 0. Text `PONG`. Finish reason `stop`. Echoed model `qwen3.8-27b`. |
| `GET /v1/models` after | Same twelve ids, same order. |
| `python -m controlops_research.runtime doctor` after | Exit 0. `READY qwen3.8-27b` |
| `bash scripts/controlops doctor` | Exit 0. `PASS=13 WARN=2 FAIL=0`. Warnings are the existing dirty ControlOps and Hermes trees. |
| `bash tests/operations/controlops-smoke.sh` | Exit 0. `PASS: ControlOps operational smoke tests` |

Ordered ids before and after:

```text
qwen3.8-27b
qwen3.8-27b-obliterated
lmstudio-community/qwen3.6-35b-a3b
qwen3.6-27b
text-embedding-nomic-embed-text-v1.5@q4_k_m
deepseek-r1-distill-qwen-32b
unsloth/qwen3.6-35b-a3b
qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-neo-code-di-imatrix-max
gemma-4-31b-it-qat
text-embedding-nomic-embed-text-v1.5@q8_0
llama-3.3-70b-instruct
qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive
```

## Infer URLs

The production transport recorded exactly:

```text
HTTP GET http://127.0.0.1:1234/v1/models
HTTP POST http://127.0.0.1:1234/v1/chat/completions
```

No load, unload, eject, or evict URL was requested. The jail network remains
`--unshare-all` with no `--share-net`. Gateway Bubblewrap was not required and
Compose was not changed.

The infer lock was created at
`/mnt/Storage/AI/Hermes/workspace/runtime/locks/model.lock`. The code requests
mode `0700` for the runtime directories. The workspace filesystem reports
`0755` after that request.

## Tests

`814 passed` from the project virtualenv against the installed `src` tree,
including the PR5-R acceptance and infer tests and the existing architecture
suite.

## PR6

Live acceptance of this probe is recorded. A reviewer decision and a separate
human approval are still required before PR6. PR6 was not started.
