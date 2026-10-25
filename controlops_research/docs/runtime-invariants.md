# Runtime invariants

PR5-R local runtime contract. This file does not replace
`docs/architecture-invariants.md`.

1. The jail network namespace stays unshared. `CONTROLOPS_ALLOW_SHARED_NET` is not a switch, and the bubblewrap argv has no `--share-net`.

2. LM Studio owns the GPU. The jail uses a fresh `--dev /dev` and does not receive GPU device nodes. ControlOps does not load, unload, evict, or pin a model.

3. ControlOps will not call load, unload, or evict, will refuse to start if the required model id is absent from `GET /v1/models`, and will serialise its own infer calls with a non-blocking flock. This is not a claim about VRAM occupancy, loaded-versus-listed state, or other clients.

4. `CONTROLOPS_REQUIRED_MODEL` has no default. Unset or empty is `CONFIG_INVALID`. The operator-approved id is `qwen3.8-27b`, the exact string selected from the inspected `GET /v1/models` list.

5. The only read-write ControlOps binds are `$WORKSPACE/runtime/locks`, `tmp`, `out`, and `runs`, mapped at `/opt/data/workspace/runtime/...`. The execution substrate is the named `/usr` read-only tree, merged-usr symlinks, `/proc`, fresh `/dev`, and private `/tmp`.

6. `GET /v1/models` and `POST /v1/chat/completions` run on the host. Bubblewrap exec is a separate host primitive and does not call LM Studio. The gateway container has no bubblewrap; Compose is unchanged.

7. `controlops_research/src/controlops_research/runtime/infer.py` is the only infer adapter. The JSON `model` field equals `CONTROLOPS_REQUIRED_MODEL`. URLs containing load, unload, eject, or evict are refused before a socket is opened. Infer calls `LMStudioProbe.require_ready()`, holds `ModelLock` only for the request, requires a caller timeout, and returns text, raw finish reason, and model id.

8. `MODEL_STATE_INCOMPATIBLE` means the payload shape or protocol failed. A missing required id is `REQUIRED_MODEL_MISSING`. Non-200, timeout, and connection failure are `ENDPOINT_UNAVAILABLE`.

9. Doctor is `python -m controlops_research.runtime doctor`. It fails closed when `127.0.0.1:1234` is down.

10. The specification status is `REMEDIATED` only after live Hermes evidence. Until that evidence exists it is `IN PROGRESS — NOT ACCEPTED`. PR6 stays forbidden until live acceptance, a reviewer decision, and a separate human approval.
