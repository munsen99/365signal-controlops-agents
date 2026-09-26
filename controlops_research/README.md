# ControlOps Research Agent

ControlOps Research Agent is an independent Python package and future research
execution path. It is not part of Hermes or Econo, a plugin/profile, an extension
of the Autonomous Economic Agent, or a Grok Build orchestrator.

PR0 established the scaffold. PR1 adds a pure deterministic URL policy with
ACCEPT, REVIEW and REJECT decisions; candidate admission never authorises a
connection. The package has no network access, model inference, database
connectivity, paid APIs or autonomous behaviour. Later capabilities require review.
The canonical build programme and status index live in [docs/prs/](docs/prs/README.md).

Models reason. Deterministic controls establish authority.
Evidence, not model output, is the system of record.

Research creates evidence. Review creates knowledge.

Future publication and RAG ingestion are downstream of reviewed/approved
knowledge and are not part of PR0. Only approved knowledge enters the trusted RAG.
See the [architecture invariants](docs/architecture-invariants.md).

Python 3.13 is the compatibility baseline; Python 3.14 is the preferred runtime.
For development, from this directory in a Python 3.13+ virtual environment:

```sh
python -m pip install -e '.[dev]'
python -m pytest
```

There are no runtime dependencies. Importing the package performs no runtime work.
