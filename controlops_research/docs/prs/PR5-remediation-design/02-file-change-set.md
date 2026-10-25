# 02 — Exact file change set

No file in this list is edited before the pack is approved. `pyproject.toml`
stays as it is: setuptools discovers packages under `src/`. A module that
answers `python -m controlops_research.runtime` therefore lives under
`controlops_research/src/controlops_research/runtime/`. The prompt's
`controlops_research/runtime/*.py` names that same package. A second tree at
`controlops_research/runtime/` will not be created.

## Create

```text
controlops_research/src/controlops_research/runtime/__init__.py
controlops_research/src/controlops_research/runtime/__main__.py
controlops_research/src/controlops_research/runtime/config.py
controlops_research/src/controlops_research/runtime/errors.py
controlops_research/src/controlops_research/runtime/http_client.py
controlops_research/src/controlops_research/runtime/probe.py
controlops_research/src/controlops_research/runtime/lock.py
controlops_research/src/controlops_research/runtime/jail.py
controlops_research/src/controlops_research/runtime/infer.py
controlops_research/src/controlops_research/runtime/doctor.py
controlops_research/tests/test_pr5_acceptance.py
controlops_research/tests/test_pr5_infer.py
controlops_research/tests/support.py
controlops_research/docs/runtime-invariants.md
```

`runtime-invariants.md` will carry this pack's D1–D10 contract in short form.
It will not replace or renumber `docs/architecture-invariants.md`.

`__main__.py` accepts only `doctor`. Any other argv fails closed.
Import of the package performs no network call.

`http_client.py` is the only LM Studio HTTP client. `probe.py` may GET
`/v1/models`. `infer.py` may POST `/v1/chat/completions`. No other runtime
module opens a socket. `fetch.py` is not modified and is not reused for
LM Studio.

Host directories created on first use, mode `0700`, and not source files:

```text
/mnt/Storage/AI/Hermes/workspace/runtime/locks
/mnt/Storage/AI/Hermes/workspace/runtime/tmp
/mnt/Storage/AI/Hermes/workspace/runtime/out
/mnt/Storage/AI/Hermes/workspace/runtime/runs
```

## Edit after approval, before live evidence

```text
controlops_research/docs/prs/PR5-implementation-design/PR5-local-runtime-sandbox.md
```

The prompt names `docs/prs/PR5-local-runtime-sandbox.md`. That path is empty
after the filing move. The edit target is the existing specification. A stub
will not be recreated at the old path. The status line becomes:

```text
IN PROGRESS — NOT ACCEPTED
```

The GPU section is replaced by the D3 sentence. The hardcoded production id
and the whole-workspace mount stop being described as the contract. Acceptance
text from 2026-09-28 remains historical and is marked as the rejected
prototype, not as PR5-R acceptance.

`REMEDIATED` is written only after [06](06-tests.md) live evidence exists.

## Write only after the live pack

```text
controlops_research/docs/prs/reports/pr5-remediation-2026-09-28.md
```

The date changes if the live run is not on 2026-09-28. The report is not
started in the design turn.

## Outside the written allow-list

These two files still implement and bless the rejected prototype. Leaving
them green keeps a false runtime beside the new package. They are not edited
unless the operator adds them to the approved list:

```text
controlops_research/scripts/research-runtime
controlops_research/tests/test_runtime_sandbox.sh
```

Proposed retirement, once added:

- delete `scripts/research-runtime`, or replace it with a non-executing
  message that names `python -m controlops_research.runtime` and does not
  keep a model default, a shared-net switch, or a workspace bind;
- delete `tests/test_runtime_sandbox.sh`. Its surviving assertions move into
  `tests/test_pr5_acceptance.py`, aimed at the Python jail.

`docs/prs/PR5-implementation-design/README.md` and `docs/prs/README.md` also
carry stale status lines. They are outside the allow-list. This pack does not
edit them unless the operator adds them.

## Not in the change set

```text
src/controlops_research/fetch.py
src/controlops_research/evidence.py
src/controlops_research/policy.py
src/controlops_research/verify.py
src/controlops_research/snapshot.py
pyproject.toml
docs/architecture-invariants.md
/home/proteu5/AI/Hermes/hermes-agent
Compose files
scripts/controlops
tests/operations/controlops-smoke.sh
```
