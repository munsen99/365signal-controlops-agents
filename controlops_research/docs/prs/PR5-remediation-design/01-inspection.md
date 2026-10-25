# 01 — Inspection result

Session: 2026-09-28T20:32:58+01:00.
Host: `proteu5-Vengeance-X-AMD`.
Kernel: `Linux 7.0.0-34-generic x86_64`.
Host Python: `3.14.4`.
Host Bubblewrap: `/usr/bin/bwrap`, `bubblewrap 0.11.1`.

Hermes paths and LM Studio were visible from this machine. The
"sandbox cannot see Hermes" stop does not apply. The approval stop does.

## Paths

| Path | Result |
| --- | --- |
| `/home/proteu5/AI/Hermes/hermes-agent` | Present. Not modified. |
| `/mnt/Storage/AI/Hermes/workspace` | Present. This is `$WORKSPACE`. |
| `controlops_research/scripts/research-runtime` | Present. Bash prototype. |
| `controlops_research/tests/test_runtime_sandbox.sh` | Present. Asserts the prototype. |
| `controlops_research/src/controlops_research/` | Present. PR0–PR3 package. No `runtime` subpackage. |
| `controlops_research/runtime/` | Absent. |
| `src/controlops_research/runtime/` | Absent. |
| `$WORKSPACE/runtime/{locks,tmp,out,runs}` | Absent. Not created during inspection. |
| `docs/architecture-invariants.md` | Present. Eighteen items. Not rewritten. |
| `docs/runtime-invariants.md` | Absent. |
| `docs/prs/PR5-local-runtime-sandbox.md` | Absent. The specification lives at `docs/prs/PR5-implementation-design/PR5-local-runtime-sandbox.md`. |
| `docs/prs/reports/pr5-sol-review-2026-09-28.md` | Absent. Sol's rejection text is not in the tree. D1–D10 of the remediation prompt are the constraints used. |
| `docs/prs/reports/pr5-live-acceptance-2026-09-28.md` | Present. It records the rejected prototype's earlier live exec checks. It is not PR5-R acceptance. |
| `scripts/controlops` | Present on the Hermes workspace. |
| `tests/operations/controlops-smoke.sh` | Present on the Hermes workspace. |

`docs/architecture-invariants.md` item 11 restricts future local-model access
to the approved LM Studio interface. Its later prose names `qwen3.8-27b` as
future Research Driver architecture. That sentence is not a PR5-R default.
The file is outside the remediation allow-list.

## What the tree actually runs

`scripts/research-runtime` is the whole local runtime:

- hardcoded `REQUIRED_MODEL_ID="qwen3.8-27b"`;
- host `GET http://127.0.0.1:1234/v1/models` before the jail;
- non-blocking `flock` at `/run/user/<uid>/controlops-research-model.lock`;
- `bwrap --unshare-all` with no `--share-net`;
- read-only bind of the entire workspace at `/opt/data/workspace`;
- `--dev /dev`, `/usr` read-only, private `/tmp`;
- then exec of the caller command.

There is no infer verb. The jail has no network, so a jailed command cannot
reach LM Studio. `CONTROLOPS_ALLOW_SHARED_NET` and `CONTROLOPS_REQUIRED_MODEL`
do not occur anywhere in the tree. `controlops-research-local` does not occur.
No Python module calls LM Studio. `fetch.py` has its own `http.client` path
for PR2 retrieval and is not an infer client.

The bash test requires the hardcoded model id and the whole-workspace
`--ro-bind`. Those assertions describe the prototype Sol rejected.

## Gateway

Compose service `gateway`, container `/hermes`, image `hermes-agent`, state
`running`. `docker exec hermes` found no `bwrap`. Gateway Python is
`/opt/hermes/.venv/bin/python3`. Bubblewrap exec stays on the Hermes host.
Compose files were read and not modified.

## LM Studio

`GET http://127.0.0.1:1234/v1/models` returned HTTP 200. The body is
`{"object","data"}`. Each row has only `id`, `object`, and `owned_by`. There
is no loaded-versus-listed field. Ids, in response order:

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

Full model objects were not written into git.

## Existing doctor

`bash scripts/controlops doctor` in this session exited 0:
`PASS=13 WARN=2 FAIL=0`. The warnings are dirty ControlOps and Hermes git
trees. This doctor does not know about the PR5 runtime package, because that
package does not exist yet. Smoke was not re-run for this design pass.
Both commands exist and will be recorded again in the live pack after
implementation.

## Fresh `--dev /dev` nodes

With `/usr` read-only, the merged-usr symlinks including `usr/lib64`, and
`--dev /dev`, the jail device directory was:

```text
core fd full null ptmx pts random shm stderr stdin stdout tty urandom zero
```

`/dev/nvidia0`, `/dev/nvidiactl`, `/dev/nvidia-uvm`, `/dev/dri`, and
`/dev/kfd` were absent. The host has those nodes. The jail did not receive
them. `usr/lib64` is required on this host; without it, dynamically linked
`/usr/bin/ls` fails to start.
