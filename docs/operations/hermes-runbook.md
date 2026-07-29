# ControlOps Hermes Runbook

## Supported command

Run all lifecycle operations from the ControlOps repository:

```bash
bash scripts/controlops help
```

The workspace is currently hosted on NTFS/FUSE with executable mode bits
suppressed, so invoke the script through `bash`.

The command always pins:

- Compose project: `controlops-hermes`
- Environment file: `/home/proteu5/AI/Hermes/hermes-agent/.env.controlops`
- Upstream base: `/home/proteu5/AI/Hermes/hermes-agent/docker-compose.yml`
- ControlOps override: `/mnt/Storage/AI/Hermes/workspace/ops/compose.controlops.yaml`

The legacy `compose.override.yaml` and `docker-compose.controlops.yml` files in
the Hermes source repository are not part of the supported invocation.

## Lifecycle

```bash
bash scripts/controlops start
bash scripts/controlops status
bash scripts/controlops logs
bash scripts/controlops logs --follow
bash scripts/controlops restart
bash scripts/controlops stop
```

Normal start uses `docker compose up -d`. It does not build an image. Normal
stop uses `docker compose stop`; it does not remove containers, networks,
mounts, or persistent data.

Image building is deliberately separate:

```bash
bash scripts/controlops rebuild
```

`rebuild` validates the same dependencies, runs `docker compose build gateway`,
and recreates/starts the gateway and dashboard.

## Startup contract

Before starting, the command:

1. Checks Docker, Compose, `jq`, required files, and required directories.
2. Renders and validates the effective Compose model.
3. Requires LM Studio to answer at `http://127.0.0.1:1234/v1/models`.
4. Starts `gateway` and `dashboard`.
5. Waits for both containers and the dashboard with a 30-second bound.
6. Verifies the actual container bind mounts.

LM Studio is externally managed. Load the configured model in LM Studio before
starting Hermes.

## Diagnostics

```bash
bash scripts/controlops doctor
```

Doctor is read-only. It reports `PASS`, `WARN`, and `FAIL`. A dirty Git tree,
stopped optional runtime, or unavailable externally managed dependency is a
warning. Missing required files, inaccessible Docker, or an invalid effective
Compose model is a failure.

Doctor never reads or prints credential files or secret values.

## Failure recovery

If startup refuses to proceed:

1. Run `bash scripts/controlops doctor`.
2. Confirm LM Studio is running and its models endpoint responds.
3. Confirm the three host mount paths are mounted and accessible.
4. Inspect bounded logs with `bash scripts/controlops logs`.
5. Use `bash scripts/controlops rebuild` only when the local image genuinely needs
   rebuilding.

Do not use `docker compose down -v`, Docker prune commands, recursive ownership
changes, or Git cleanup/reset commands as recovery steps.

## External capabilities

- Microsoft Graph MCP is an on-demand stdio process. It is not a daemon.
- RAG is a batch/filesystem capability backed by LanceDB. No RAG API is assumed.
- The dashboard is expected at `http://127.0.0.1:9119/`.
