# 06 — Tests

Deterministic tests use a fake transport in `tests/support.py`. They do not
contact `127.0.0.1:1234`. Files:

```text
controlops_research/tests/test_pr5_acceptance.py
controlops_research/tests/test_pr5_infer.py
controlops_research/tests/support.py
```

## Acceptance

1. Unset and empty `CONTROLOPS_REQUIRED_MODEL` raise `CONFIG_INVALID` and
   perform no HTTP.
2. `CONTROLOPS_ALLOW_SHARED_NET=1` and any share-net request leave the
   bubblewrap argv containing `--unshare-all` and not `--share-net`.
3. A jailed process cannot see `/root`, `/home/proteu5`, `hermes-agent`,
   either Docker socket, `/etc/shadow`, `/etc/ssh`, or the workspace outside
   `runtime/{locks,tmp,out,runs}`. The Docker-socket assertion checks the
   socket paths.
4. Fresh `--dev /dev` does not expose `/dev/nvidia0`, `/dev/dri`, or
   `/dev/kfd`.
5. Readiness is a host GET. The recorded bubblewrap argv is built only for
   exec, and that argv has no network share.
6. Exact id match succeeds against a fake model list. A near-match alone is
   `REQUIRED_MODEL_MISSING`.
7. Lock release after a successful infer and after a failed infer. A second
   overlapping infer receives `MODEL_CONTENTION`.
8. `python -m controlops_research.runtime doctor` exits non-zero when the
   fake endpoint is down, and it does not POST.
9. A jailed writer can create a file under each of the four runtime binds and
   cannot create a file outside them. The host tree outside the temporary
   runtime root gains no file.

## Infer

1. A URL containing `load`, `unload`, `eject`, or `evict` is refused with no
   socket call.
2. The POST body `model` equals the configured required id.
3. The first infer holds the flock for the duration of the POST. A second
   infer started while that POST is in progress returns `MODEL_CONTENTION`.
4. The fake transport records every URL. The only GET path is `/v1/models`.
   The only POST path is `/v1/chat/completions`.
5. When `require_ready()` fails, the POST count stays zero.
6. Non-200, empty `choices`, and a mismatched model echo fail closed.
   Empty `choices` and a bad echo are `MODEL_STATE_INCOMPATIBLE`. Non-200 is
   `ENDPOINT_UNAVAILABLE`.

## Live pack, Hermes host, after implementation

Not part of this design turn. Run only with the operator-selected id from
[04](04-required-model.md):

1. `python -m controlops_research.runtime doctor` before.
2. `GET /v1/models` before. Record ids only.
3. One infer of `Reply with the single token: PONG` with an explicit timeout.
4. `GET /v1/models` after.
5. Doctor after.
6. The required id is present and identical before and after. The id list is
   unchanged.
7. The client log shows no load, unload, eject, or evict URL.
8. `bash scripts/controlops doctor` and
   `bash tests/operations/controlops-smoke.sh`, because both files exist.
9. Write `docs/prs/reports/pr5-remediation-<date>.md`.
10. Only then set the specification status to `REMEDIATED`.

Gateway is not used for bubblewrap. Compose is not changed to install it.
