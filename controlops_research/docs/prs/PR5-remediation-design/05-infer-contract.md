# 05 — Infer adapter contract

Module: `controlops_research/src/controlops_research/runtime/infer.py`.
Caller-facing function takes the chat messages and a timeout. The timeout is
required. There is no implicit timeout and no retry.

## Order

1. Read `CONTROLOPS_REQUIRED_MODEL`. Unset or empty raises `CONFIG_INVALID`.
2. `LMStudioProbe.require_ready()` performs host `GET /v1/models`.
3. On readiness failure, return that failure. The infer POST is not called.
4. Acquire `ModelLock` non-blocking. If the lock is held, raise
   `MODEL_CONTENTION` without sending the POST.
5. Host `POST http://127.0.0.1:1234/v1/chat/completions` with a JSON body
   whose `model` field is the required id, and with the caller timeout.
6. Release the lock when the request finishes, fails, or times out.
7. Return the assistant text, the raw finish reason, and the model id from
   the response.

The jail is not on this path. Bubblewrap exec is a separate host primitive
and does not call LM Studio. Exec does not hold `ModelLock`, because a jailed
command cannot reach the model. The lock serialises infer calls only.

## Allowed URLs

```text
GET  {base}/v1/models
POST {base}/v1/chat/completions
```

`{base}` in production is `http://127.0.0.1:1234`. Any URL whose path
contains `load`, `unload`, `eject`, or `evict` is refused before the socket
is used. The adapter does not start LM Studio, does not substitute another
id, and does not write chat history to RAG, Econo, or Postgres.

## Fail closed

| Condition | Code |
| --- | --- |
| Required model unset or empty, or infer timeout missing | `CONFIG_INVALID` |
| HTTP 200 model list without the exact id | `REQUIRED_MODEL_MISSING` |
| Connection failure, timeout, or non-200 on the allowed GET or POST | `ENDPOINT_UNAVAILABLE` |
| Model list or chat body has the wrong shape, `choices` is empty, or the echoed model id differs | `MODEL_STATE_INCOMPATIBLE` |
| Lock already held | `MODEL_CONTENTION` |
| Host `bwrap` missing when exec is requested | `BWRAP_NOT_AVAILABLE` |

`MODEL_STATE_INCOMPATIBLE` is only the payload row. It does not mean the
wrong model occupies VRAM. A missing id stays `REQUIRED_MODEL_MISSING`.

## GPU sentence the docs may use

ControlOps will not call load, unload, or evict, will refuse to start if the
required model id is absent from `GET /v1/models`, and will serialise its own
infer calls with a non-blocking flock.

The docs will not claim VRAM occupancy, a distinction between loaded and
listed models, or protection against a person or another client using
LM Studio.
