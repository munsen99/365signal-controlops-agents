# 01 — Flow and trust boundary

## Inspected runtime

PR5-R source is only:

```text
controlops_research/src/controlops_research/runtime/
```

Present modules: `config.py`, `doctor.py`, `errors.py`, `http_client.py`,
`infer.py`, `jail.py`, `lock.py`, `probe.py`, `__init__.py`, `__main__.py`.

The prompt names `exec.py`, `lmstudio.py`, and `sandbox.py`. Those files are
absent. Exec is `jail.py`. Readiness is `probe.py`. The LM Studio socket client
is `http_client.py`, used only by `probe.py` and `infer.py`. There is no
leftover package at `controlops_research/runtime/`.

`infer()` calls `LMStudioProbe.require_ready()` and then holds `ModelLock`
for one `POST /v1/chat/completions`. `jail.py` builds `--unshare-all` and
rejects `--share-net`. PR6 does not edit these modules.

## Loop

The research loop runs on the host:

1. Read `CONTROLOPS_REQUIRED_MODEL`. The recorded value is `qwen3.8-27b`.
   The code does not embed that string as a default.
2. Take operator seed URLs, or a future discovery result. This pack has
   neither a discovery implementation nor a seed list.
3. Retrieve each candidate on the host. Follow a redirect only after the
   next `Location` is on the allowlist.
4. Keep at most `max_retrieve = 5` usable sources and `max_discover = 8`
   input URLs.
5. Call `controlops_research.runtime.infer` for evidence selection.
6. Call it again for the finding draft. Each call takes the lock separately.
7. Validate citations in code.
8. Write the run directory.

Retrieved bytes are data inside the prompt packet. They are not executed,
imported as configuration, or written outside the run directory.

## Status

`run.json` `status` is `completed` or `failed`.

Hard-fail (`failed`, no supported finding) when readiness fails, the lock
returns `MODEL_CONTENTION`, the infer adapter raises, model output is not
the required JSON, or zero usable candidates remain.

`insufficient` is a completed run. It means at least one usable candidate
was retrieved and the draft is unsupported, or citation validation failed
and the status was forced to `insufficient`.

The jail is not used to reach LM Studio or the web. Research code does not
import `http_client` or `LMStudioProbe`.
