# PR5 — Local Runtime Sandbox and GPU Protection

## Objective

Implement the minimum execution boundary required for the future ControlOps Research Agent.

PR5 must provide:

- a restricted Bubblewrap execution jail;
- exact LM Studio model readiness validation;
- exclusive protection against concurrent research-model use;
- repeatable host-verified acceptance evidence.

PR5 does **not** implement the Research Agent loop.

## Required Model

The required local research model is:

```text
qwen3.8-27b
```

Readiness means:

```text
GET http://127.0.0.1:1234/v1/models
```

returns HTTP 200 **and the response contains the exact required model ID**.

No alternative model, alias, fallback or automatic model loading is permitted.

If the model is absent:

```text
MODEL_NOT_READY
```

and execution must stop.

## Hermes Source Modification Boundary

No files under:

```text
/home/proteu5/AI/Hermes/hermes-agent
```

may be modified by PR5.

If implementation requires a Hermes source or Compose change, stop and report the requirement rather than modifying the repository.

PR5 implementation must remain within the ControlOps workspace.

## Bubblewrap Filesystem Allow List

The Bubblewrap jail must use an explicit filesystem allow list.

Permitted ControlOps content:

```text
/opt/data/workspace
```

mounted **read-only**.

Permitted runtime scratch space:

```text
/tmp
```

provided as an isolated temporary filesystem inside the jail.

No other Hermes persistent-state, workspace, host-storage or credential paths may be exposed.

Specifically prohibited include:

```text
/opt/data
/opt/hermes
/run/docker.sock
/var/run/docker.sock
/root
/home
```

except where Bubblewrap requires minimal system runtime files solely to execute the approved process.

Any required system bind must be explicitly documented in the implementation evidence.

Do not use broad host or parent-directory binds.

## Network Boundary

The Bubblewrap jail must run with an **unshared network namespace**.

The jailed process must not directly access the host network.

LM Studio readiness checks are performed **outside the jail**, from the Hermes host/runtime boundary, against:

```text
127.0.0.1:1234
```

The readiness result is established before the jailed workload begins.

Do not weaken the jail networking merely to allow the sandbox to probe LM Studio.

## Model Contention Protection

Only one ControlOps research execution may own the local research-model runtime at a time.

Use one exclusive lock.

If the lock is already held, execution must fail immediately with:

```text
MODEL_CONTENTION
```

There is:

- no wait queue;
- no retry loop;
- no override flag;
- no permit flag;
- no automatic model eviction;
- no model unload;
- no model replacement.

The lock must be released on normal completion and controlled failure.

## Runtime Behaviour

PR5 must:

1. verify Bubblewrap is available;
2. verify LM Studio responds;
3. verify the exact required model ID is present;
4. acquire the exclusive research-runtime lock;
5. establish the Bubblewrap jail;
6. execute the bounded test workload;
7. release the lock.

Failure at any prerequisite must prevent workload execution.

## Existing Regression Checks

After implementation run the existing ControlOps runtime checks:

```bash
bash scripts/controlops doctor
```

and:

```bash
bash tests/operations/controlops-smoke.sh
```

Both must complete without new failures attributable to PR5.

## Acceptance Tests

PR5 is complete only when live testing demonstrates:

1. Exact `qwen3.8-27b` model readiness succeeds.
2. Missing required model returns `MODEL_NOT_READY`.
3. A jailed test command executes successfully.
4. `/opt/data/workspace` is readable.
5. `/opt/data/workspace` is not writable.
6. Prohibited Hermes/host paths are inaccessible.
7. Docker socket is inaccessible.
8. The jail has an unshared network namespace.
9. A second simultaneous execution returns `MODEL_CONTENTION`.
10. No model is loaded, unloaded, replaced or evicted by ControlOps.
11. The exclusive lock is released after success.
12. The exclusive lock is released after controlled failure.
13. `scripts/controlops doctor` passes without new PR5 regressions.
14. `tests/operations/controlops-smoke.sh` passes without new PR5 regressions.

## Evidence Rule

Acceptance evidence must be collected from the **actual Hermes Linux host and running ControlOps/Hermes environment**.

Static code inspection, mocked responses, inferred behaviour or tests executed only outside the deployed Hermes environment are insufficient.

Evidence must include:

- host identity and timestamp;
- exact model ID returned by `/v1/models`;
- Bubblewrap version;
- effective Bubblewrap invocation;
- effective bind list;
- network-isolation test;
- prohibited-path tests;
- exclusive-lock contention test;
- model-state before and after testing;
- `doctor` result;
- `controlops-smoke.sh` result;
- Git diff showing the exact PR5 changes.

If live-host evidence cannot be produced, PR5 status remains:

```text
NOT COMPLETE
```

## Explicitly Out of Scope

Do not implement:

- autonomous research;
- web discovery;
- Research Pack;
- Writer Agent;
- frontier escalation;
- trusted RAG ingestion;
- PostgreSQL assurance persistence;
- scheduling;
- dynamic agent orchestration.

## Exit Condition

PR5 is complete when the live Hermes host demonstrates a repeatable, filesystem-restricted, network-isolated execution jail that requires the exact approved local model and prevents concurrent ControlOps research execution without changing existing Hermes behaviour.
