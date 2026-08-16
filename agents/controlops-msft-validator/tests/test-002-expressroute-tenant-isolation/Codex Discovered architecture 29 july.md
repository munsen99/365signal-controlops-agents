## Discovered architecture

  LM Studio (host, 127.0.0.1:1234)
                   │
                   ▼
  Hermes containers using host networking
    ├─ hermes             gateway
    └─ hermes-dashboard   dashboard, 127.0.0.1:9119
                   │
                   ├─ /opt/data  ← /mnt/Storage/AI/Hermes/data
                   ├─ /workspace ← /mnt/Storage/AI/Hermes/workspace
                   └─ LanceDB    ← /mnt/Storage/AI/VectorDBs/LanceDB

  ControlOps Graph MCP
    └─ host-side, on-demand stdio process; no network listener

  RAG
    └─ host-side batch ingestion pipeline and filesystem-backed LanceDB;
       no persistent API service found

  At inspection time, Docker was running but the Hermes application was entirely stopped: zero containers, zero Compose projects, zero
  named volumes, and no user-defined networks. A local hermes-agent:latest image exists, built July 25, approximately 3.8 GB.

  No files were changed.

  ## 1. Git repositories and state

  ### ControlOps workspace

  Root:

  /mnt/Storage/AI/Hermes/workspace

  State:

  - Branch: main
  - Tracking: origin/main
  - Ahead by one commit
  - HEAD: 134815a test: add ExpressRoute tenant isolation validation
  - Four tracked validator files modified
  - Several untracked scripts, evidence, output, and test-002 files

  This is a dirty working tree and must not be cleaned, reset, or overwritten by operational tooling.

  The repository describes itself as the version-controlled ControlOps agent-definition repository. It intentionally excludes live
  Hermes state.

  ### Hermes source/deployment repository

  Root:

  /home/proteu5/AI/Hermes/hermes-agent

  State:

  - Branch: controlops-hermes-poc
  - Remote: https://github.com/NousResearch/hermes-agent.git
  - HEAD: c998937 test: add ExpressRoute tenant isolation validation
  - Modified Compose files
  - Deleted legacy test
  - Untracked override and test directory

  This repository is also dirty. It should be treated as upstream application source plus experimental deployment configuration, not as
  the preferred home for new ControlOps operational code.

  ## 2. Docker Compose files

  Verified files:

  - /home/proteu5/AI/Hermes/hermes-agent/docker-compose.yml
  - /home/proteu5/AI/Hermes/hermes-agent/docker-compose.controlops.yml
  - /home/proteu5/AI/Hermes/hermes-agent/compose.override.yaml
  - /home/proteu5/AI/Hermes/hermes-agent/docker-compose.windows.yml
  - /home/proteu5/AI/Hermes/hermes-agent/.env.controlops

  Intended Linux ControlOps stack:

  docker compose \
    --project-name controlops-hermes \
    --env-file /home/proteu5/AI/Hermes/hermes-agent/.env.controlops \
    -f /home/proteu5/AI/Hermes/hermes-agent/docker-compose.yml \
    -f /home/proteu5/AI/Hermes/hermes-agent/docker-compose.controlops.yml \
    ...

  Using explicit -f arguments is important: it prevents accidental automatic loading of compose.override.yaml.

  The Windows Compose file is standalone and uses the published NousResearch image, explicit dashboard port mapping, and
  ${USERPROFILE}/.hermes.

  ## 3. Operational scripts and documentation

  Relevant Hermes material includes:

  - Main README.md
  - AGENTS.md
  - SECURITY.md
  - setup-hermes.sh
  - scripts/install.sh
  - Docker entrypoint, wrapper, s6 stage hook, and exec shim
  - Documentation for sessions, cron, observability, relay, and network isolation

  ControlOps workspace currently has:

  - A short architecture README
  - Validator runtime configuration and SOUL.md
  - scripts/ingest_learn_catalog.py
  - Validation templates and tests

  There is no existing unified ControlOps start/stop/status/logs/doctor command.

  RAG documentation exists at:

  - /mnt/Storage/AI/RAG/MultimodalIngest/README.md

  Graph MCP documentation and activation script exist at:

  - /mnt/Storage/AI/MCP/controlops-graph-mcp/README.md
  - /mnt/Storage/AI/MCP/controlops-graph-mcp/activate-controlops.sh

  ## 4. Hermes runtime details

  ### Compose services and container names

   Compose service    Container name      Command
  ━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   gateway            hermes              gateway run
  ─────────────────  ──────────────────  ──────────────────────────────────────
   dashboard          hermes-dashboard    dashboard --host 127.0.0.1 --no-open

  Both use:

  - Image: hermes-agent
  - Restart policy: unless-stopped
  - Network mode: host
  - UID/GID passed through from .env.controlops
  - LM_API_KEY=lm-studio

  ### Ports

  Because both services use host networking, Docker publishes no port mappings.

  Verified intended endpoints:

  - LM Studio: 127.0.0.1:1234/v1
  - Hermes dashboard: 127.0.0.1:9119
  - Hermes API gateway: disabled unless separately configured
  - Graph MCP: stdio only; configured MCP_PORT=8010 is presently inert
  - RAG: no API listener found

  At inspection time:

  - Nothing was listening on 1234 or 9119.
  - An unrelated or unidentified service was listening on all interfaces at TCP/UDP port 4000.
  - Ports used by NoMachine were also present.
  - The port-4000 service should be identified separately before treating the host listener inventory as clean.

  ### Volumes and bind mounts

  Effective ControlOps intentions:

   Service      Host                           Container
  ━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━
   gateway      /mnt/Storage/AI/Hermes/data    /opt/data
  ───────────  ─────────────────────────────  ───────────────────
   gateway      workspace repository           /workspace
  ───────────  ─────────────────────────────  ───────────────────
   gateway      shared LanceDB                 /opt/data/lancedb
  ───────────  ─────────────────────────────  ───────────────────
   dashboard    /mnt/Storage/AI/Hermes/data    /opt/data
  ───────────  ─────────────────────────────  ───────────────────
   dashboard    workspace repository           /workspace

  No Docker named volumes currently exist.

  ### Networks

  - Services use the built-in Docker host network.
  - No Compose bridge network is created.
  - Only Docker’s standard bridge, host, and none networks exist.

  ### Health checks

  No Compose health checks are defined for either service.

  depends_on makes the dashboard start after the gateway container is started, but it does not establish gateway readiness. Current
  health can therefore only be inferred from container state, logs, runtime-state files, and HTTP probes.

  ## 5. Relationship between the three main paths

  These are separate physical directories, not symlinks:

   Path                                    Role
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   /home/proteu5/AI/Hermes/hermes-agent    Hermes application source, Docker build context, Compose definitions
  ──────────────────────────────────────  ──────────────────────────────────────────────────────────────────────
   /home/proteu5/.hermes                   Native/host Hermes profile and state
  ──────────────────────────────────────  ──────────────────────────────────────────────────────────────────────
   /mnt/Storage/AI/Hermes/workspace        ControlOps Git repository, mounted into containers as /workspace

  There is a fourth crucial path:

  /mnt/Storage/AI/Hermes/data

  This is the actual container persistence root under docker-compose.controlops.yml, mounted as /opt/data. It contains:

  - Root Hermes configuration and state
  - active_profile
  - Logs and databases
  - The live controlops-msft-validator profile
  - Profile-specific configuration, logs, state, credentials, and evidence database

  Consequently, /home/proteu5/.hermes and /mnt/Storage/AI/Hermes/data are two independent Hermes state trees. The ControlOps containers
  use the latter, not the former.

  /home/proteu5/.hermes/workspace is also a separate directory; it is not the ControlOps Git workspace.

  ## 6. Host-side ControlOps services

  ### LM Studio

  Expected endpoint:

  http://127.0.0.1:1234/v1

  Configured in:

  - /mnt/Storage/AI/Hermes/data/config.yaml
  - Live controlops-msft-validator profile
  - Workspace validator runtime config

  It was not running during inspection.

  The native /home/proteu5/.hermes/config.yaml selects the same LM Studio model/provider but has an empty base_url.

  ### RAG and LanceDB

  Verified components:

  - Pipeline: /mnt/Storage/AI/RAG/MultimodalIngest
  - Shared database: /mnt/Storage/AI/VectorDBs/LanceDB
  - Workspace ingestion script imports the RAG pipeline directly
  - Numerous LanceDB tables already exist, including Microsoft Learn, M365 technical documentation, architecture patterns, frameworks,
    and multimodal data

  This is currently a batch/filesystem architecture, not an API service. No FastAPI/Uvicorn RAG daemon or systemd unit was found.

  ### Microsoft Graph MCP

  Verified project:

  /mnt/Storage/AI/MCP/controlops-graph-mcp

  Properties:

  - Console command: controlops-mcp
  - Python module: controlops_graph_mcp
  - Transport: stdio only
  - Enforced Microsoft Graph host and HTTPS
  - GET-only Graph design
  - Expected virtual environment: /home/proteu5/.venvs/controlops-graph-mcp
  - No persistent daemon or listening port
  - No systemd service found
  - Intended to be spawned by an MCP client when required

  No ControlOps-specific system or user systemd services were found.

  ## Risks and inconsistencies

  1. Both Git repositories are dirty. Implementation must avoid rewriting or “normalizing” existing Compose changes.
  2. There are two independent Hermes state trees:
      - /home/proteu5/.hermes
      - /mnt/Storage/AI/Hermes/data

     Operators could inspect or edit the wrong one.

  3. Compose override ambiguity:
      - docker-compose.controlops.yml mounts the workspace at /workspace.
      - compose.override.yaml mounts it at /opt/data/workspace.
      - Implicit versus explicit Compose invocation produces different deployments.

  4. The base Compose file’s ~/.hermes:/opt/data intent is replaced by the ControlOps /mnt/Storage/.../data:/opt/data mount. This is
     correct only when the intended file pair is used.

  5. No health checks exist. running is not equivalent to ready.
  6. Host networking removes Docker port isolation. Any Hermes service configured for 0.0.0.0 becomes a host/LAN exposure.
  7. LM Studio is a hard runtime dependency but is not managed by Docker or systemd and was stopped.
  8. Native Hermes config has an empty LM Studio URL, whereas the container data and validator profile use 127.0.0.1:1234/v1.
  9. restart: unless-stopped can produce surprising boot behavior after Docker starts. Explicit status should distinguish desired
     Compose state from actual container state.

  10. The shared LanceDB mount is writable. Concurrent ingestion and Hermes access should be checked for locking and schema
     compatibility.

  11. Live credentials exist in profile and MCP .env locations. Doctor and logs commands must never print environment values or
     credential files.

  12. The workspace is on an NTFS/FUSE filesystem while application source and native state are on ext4. Unix ownership, executable
     bits, locking, and atomic rename behavior may differ.

  13. Port 4000 is exposed on all interfaces but was not attributable to a ControlOps process from the available inspection. It should
     be reported by doctor as an unexpected listener, not assumed harmless.

  ## Safest operational design

  Use one committed wrapper in the ControlOps repository as the only supported entry point. It should:

  - Pin the project name and both exact Compose files.
  - Pin the env file.
  - Never depend on current directory or implicit override discovery.
  - Validate all paths before taking action.
  - Refuse to start if the effective Compose configuration differs from expected mounts, host networking, container names, or image.
  - Avoid sourcing secret-bearing files.
  - Treat LM Studio and MCP as external dependencies.
  - Use docker compose stop for normal stop, preserving containers and state.
  - Reserve down for an explicit separately named command, never as the default stop.
  - Never use down -v, prune, delete, or reset operations.
  - Keep status and doctor entirely read-only.

  Recommended behavior:

  - start: preflight, verify LM Studio, then up -d --build; wait for probes.
  - stop: docker compose stop, dashboard first if ordering is desired.
  - restart: controlled stop followed by start, with readiness checks.
  - status: Compose state, container state, selected mounts, ports, image ID, LM Studio probe, dashboard probe, disk/mount
    availability.

  - logs: docker compose logs, bounded by default with --tail; optional --follow.
  - doctor: no mutation; validate Git dirtiness, paths, effective Compose model, Docker access, image availability, mounts, UID/GID,
    listeners, LM Studio model endpoint, dashboard readiness, profile selection, LanceDB accessibility, and MCP executable/
    configuration without printing secrets.

  ## Proposed files to create after approval

  Prefer placing these in the ControlOps workspace:

  - scripts/controlops
      - Unified start/stop/restart/status/logs/doctor entry point.

  - scripts/lib/controlops-common.sh
      - Path constants, Compose invocation, safe probes, formatting.

  - docs/operations/hermes-runbook.md
      - Architecture, ownership boundaries, failure recovery, and exact commands.

  - docs/operations/service-inventory.md
      - Verified services, ports, mounts, networks, and external dependencies.

  - config/controlops.env.example
      - Non-secret documented settings only.

  - tests/operations/controlops-smoke.sh
      - Static/read-only wrapper tests.

  Optionally, after deciding how to handle the dirty Hermes clone:

  - ops/compose.controlops.yaml in the ControlOps repository as the canonical override, eliminating dependence on an uncommitted file
    in the Hermes source clone.

  I would not add a persistent systemd service for the stdio MCP server. It should remain client-spawned. LM Studio lifecycle
  automation should only be added if a supported headless command is verified.

  ## Commands proposed for implementation

  Representative commands the wrapper would use:

  docker compose \
    --project-name controlops-hermes \
    --env-file /home/proteu5/AI/Hermes/hermes-agent/.env.controlops \
    -f /home/proteu5/AI/Hermes/hermes-agent/docker-compose.yml \
    -f /home/proteu5/AI/Hermes/hermes-agent/docker-compose.controlops.yml \
    config

  Start:

  curl --fail --silent --show-error \
    http://127.0.0.1:1234/v1/models

  docker compose ... up -d --build

  Stop:

  docker compose ... stop dashboard gateway

  Restart:

  docker compose ... stop dashboard gateway
  docker compose ... up -d gateway dashboard

  Status:

  docker compose ... ps --all
  docker inspect hermes hermes-dashboard
  ss -lntp
  curl --fail --silent http://127.0.0.1:1234/v1/models
  curl --fail --silent http://127.0.0.1:9119/

  Logs:

  docker compose ... logs --tail 200 gateway dashboard
  docker compose ... logs --follow --tail 200 gateway dashboard

  Doctor/static checks:

  git -C /mnt/Storage/AI/Hermes/workspace status --short --branch
  git -C /home/proteu5/AI/Hermes/hermes-agent status --short --branch
  docker compose ... config
  docker compose ... ps --all
  docker image inspect hermes-agent:latest
  findmnt -T /mnt/Storage/AI/Hermes/data
  findmnt -T /mnt/Storage/AI/Hermes/workspace
  findmnt -T /mnt/Storage/AI/VectorDBs/LanceDB
  ss -lntp

  No implementation should proceed until the canonical Compose ownership decision is approved: either retain the existing Hermes-clone
  override or move the ControlOps-specific override into the ControlOps repository.
