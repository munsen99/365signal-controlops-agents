# ControlOps Service Inventory

## Docker services

| Service | Container | Network | Restart | Purpose |
|---|---|---|---|---|
| `gateway` | `hermes` | host | unless-stopped | Hermes agent gateway |
| `dashboard` | `hermes-dashboard` | host | unless-stopped | Local Hermes dashboard |

Both services use the local `hermes-agent` image. The gateway image is built
from `/home/proteu5/AI/Hermes/hermes-agent` only through the explicit rebuild
operation.

## Bind mounts

| Host path | Container path | Services |
|---|---|---|
| `/mnt/Storage/AI/Hermes/data` | `/opt/data` | gateway, dashboard |
| `/mnt/Storage/AI/Hermes/workspace` | `/workspace` | gateway, dashboard |
| `/mnt/Storage/AI/VectorDBs/LanceDB` | `/opt/data/lancedb` | gateway |

`/home/proteu5/.hermes` is a separate native Hermes state tree and is not used
by the supported ControlOps Compose deployment.

## Host endpoints and capabilities

| Component | Endpoint/transport | Lifecycle |
|---|---|---|
| LM Studio | `http://127.0.0.1:1234/v1` | Externally managed |
| Hermes dashboard | `http://127.0.0.1:9119/` | Docker Compose |
| Graph MCP | stdio | Spawned on demand |
| RAG | filesystem/LanceDB batch processing | Run on demand |

Host networking means there are no Docker-published port mappings. Binding a
Hermes component to `0.0.0.0` would expose it directly through the host network
and requires a separate security review.

## Health model

The upstream Compose services do not define Docker health checks. Operational
readiness is determined using:

- container running state;
- dashboard HTTP responsiveness;
- LM Studio `/v1/models` responsiveness;
- exact runtime bind-mount verification.
