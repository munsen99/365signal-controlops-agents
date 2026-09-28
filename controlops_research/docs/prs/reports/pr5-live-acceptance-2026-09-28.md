# PR5 live-host acceptance evidence — 2026-09-28

Status: **ACCEPT WITH DOCUMENTED EXCEPTION**. The runtime contract is met.
Thirteen acceptance cases have live-host evidence. Case 2 is accepted as a
documented testability exception.

## Host and implementation

| Item | Evidence |
| --- | --- |
| Host | `proteu5-Vengeance-X-AMD` |
| Evidence timestamp | `2026-09-28T19:47:32+01:00` |
| Repository HEAD on entry | `56dd905 feat(research): implement PR3 citation evidence plane` |
| Bubblewrap | `bubblewrap 0.11.1` |
| Required model | `qwen3.8-27b` |
| Models endpoint | `http://127.0.0.1:1234/v1/models` |
| Launcher SHA-256 | `11e7428c31f7e8d802cf51b208ddc6dbb8e2ac84cd00f1fe44452a76c8eb8ccb` |
| Regression test SHA-256 | `c09c21c668d2d485125772b28e87c1237af755ca8368765f489dd36843008def` |

The exact model ID appeared in the live response. The response also contained
`qwen3.8-27b-obliterated`; the regression test confirms that this near-match
alone does not satisfy readiness.

## Effective Bubblewrap invocation

The launcher uses the following fixed arguments before the workload command:

```text
bwrap
  --die-with-parent
  --new-session
  --unshare-all
  --cap-drop ALL
  --clearenv
  --setenv PATH /usr/bin:/bin
  --setenv HOME /tmp
  --setenv TMPDIR /tmp
  --setenv LANG C.UTF-8
  --ro-bind /usr /usr
  --symlink usr/bin /bin
  --symlink usr/lib /lib
  --symlink usr/lib64 /lib64
  --symlink usr/sbin /sbin
  --proc /proc
  --dev /dev
  --tmpfs /tmp
  --dir /opt
  --dir /opt/data
  --ro-bind /mnt/Storage/AI/Hermes/workspace /opt/data/workspace
  --chdir /opt/data/workspace
  -- <workload>
```

The `/usr` read-only bind and merged-usr links are the documented system
runtime exposure required to execute the approved workload. `/proc`, `/dev`,
`/tmp`, `/opt`, and `/opt/data` are created inside the jail. The only
ControlOps content bind is the read-only workspace.

Live mount evidence showed `/usr` and `/opt/data/workspace` read-only and `/tmp`
as an isolated tmpfs. The jail's `/opt/data` contained only `workspace`.

## Acceptance results

| # | Required case | Result | Live evidence |
| --- | --- | --- | --- |
| 1 | Exact model readiness | PASS | Live HTTP response contained exact `qwen3.8-27b`; launcher printed `MODEL_READY qwen3.8-27b`. |
| 2 | Missing required model returns `MODEL_NOT_READY` | EXCEPTION | Production `curl --fail` and exact `jq` comparison, with only the response body replaced by a list containing `qwen3.8-27b-obliterated`. Launcher exited 1 with exactly `MODEL_NOT_READY` before lock acquisition or jailed workload execution. Live LM Studio contains the required model. |
| 3 | Jailed command executes | PASS | Workload printed `JAIL_OK` / `JAIL_COMMAND=PASS`. |
| 4 | Workspace readable | PASS | Jailed process read `controlops_research/README.md`. |
| 5 | Workspace not writable | PASS | Jailed `touch` was denied. |
| 6 | Prohibited host/Hermes paths inaccessible | PASS | `/opt/hermes`, `/root`, and `/home` were absent; synthetic `/opt/data` contained only `workspace`. |
| 7 | Docker socket inaccessible | PASS | `/run/docker.sock` and `/var/run/docker.sock` were absent. |
| 8 | Network namespace unshared | PASS | Host `net:[4026531833]`; jail `net:[4026534184]`; jailed connection to host `127.0.0.1:1234` was blocked. |
| 9 | Second execution returns contention | PASS | Concurrent second process exited 1 with exactly `MODEL_CONTENTION`. |
| 10 | No model state mutation | PASS | Before/after model-ID arrays were identical. No model-management API was called. |
| 11 | Lock released after success | PASS | A subsequent live execution acquired the lock. |
| 12 | Lock released after controlled failure | PASS | Exit-23 workload propagated status 23; next live execution acquired the lock. |
| 13 | `scripts/controlops doctor` | PASS | Exit 0: `PASS=13 WARN=2 FAIL=0`; warnings were existing dirty repository states. |
| 14 | Operational smoke | PASS | Exit 0: `PASS: ControlOps operational smoke tests`. |

The runtime regression test completed with:

```text
PASS: PR5 runtime sandbox regression tests
```

## Model state before and after

The exact ordered model-ID list was unchanged before and after all live tests:

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

## Git scope

PR5 changes are limited to:

```text
controlops_research/scripts/research-runtime
controlops_research/tests/test_runtime_sandbox.sh
controlops_research/docs/prs/PR5-implementation-design/PR5-local-runtime-sandbox.md
controlops_research/docs/prs/reports/pr5-live-acceptance-2026-09-28.md
controlops_research/docs/prs/README.md
```

The user-provided `docs/PR5 Local Runtime Sandbox.md` and pre-existing untracked
PR3 design/prompt files remain untouched. No file under
`/home/proteu5/AI/Hermes/hermes-agent` was modified. No Compose, Econo,
validator, RAG, PostgreSQL, or PR4+ component was changed.

## Independent review — 2026-09-28T20:09:48+01:00

Implementation status: COMPLETE
Acceptance result: ACCEPT WITH DOCUMENTED EXCEPTION
Live acceptance cases: 13 of 14 live PASS; case 2 documented testability exception
Exception: Case 2 uses the production readiness logic. The shim substitutes only the model-list response. No alternate readiness implementation exists. Live `GET /v1/models` returned HTTP 200 and `MODEL_READY qwen3.8-27b`.
Regression status: PASS (`tests/test_runtime_sandbox.sh`; doctor `PASS=13 WARN=2 FAIL=0`; operational smoke PASS; `git diff --check` clean)
Reviewer decision: ACCEPT WITH DOCUMENTED EXCEPTION

The review re-ran the live jail, contention, lock-recovery, doctor, and smoke
checks. No model-management API was called. The ordered model-ID list was
unchanged. `/usr` and `/opt/data/workspace` were mounted read-only, and a jailed
write failed with `Read-only file system`. Host network namespace
`net:[4026531833]` differed from jail namespace `net:[4026534183]`. Host
loopback `127.0.0.1:1234` accepted a connection; the same connection from the
jail was blocked. A concurrent execution exited 1 with exactly
`MODEL_CONTENTION`. An exit-23 workload propagated status 23, and the next
execution acquired the lock. PR5 did not modify
`/home/proteu5/AI/Hermes/hermes-agent`. The workspace diff adds no PR4, Compose,
or runtime-dependency change.

> The outstanding case is a live-testability limitation, not a known runtime defect. Demonstrating the negative live-model state would require altering LM Studio model state, which PR5 explicitly prohibits.
