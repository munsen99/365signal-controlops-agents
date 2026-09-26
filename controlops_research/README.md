# ControlOps Research Agent

ControlOps Research Agent is an independent Python package and future research
execution path. It is not part of Hermes or Econo, a plugin/profile, an extension
of the Autonomous Economic Agent, or a Grok Build orchestrator.

PR0 established the scaffold. PR1 adds a pure deterministic URL policy with
ACCEPT, REVIEW and REJECT decisions. PR2 adds a bounded HTTPS acquisition path:
every URL, redirect and resolved address remains subject to PR1; connections are
pinned to approved numeric addresses; exact raw bytes are hashed and preserved
before deterministic text extraction. The package has no model inference,
database connectivity, paid APIs or autonomous reasoning. Later capabilities
require review.
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

There are no third-party runtime dependencies. Importing the package performs no
network, filesystem or other external work. PR2 tests use deterministic local
adapters and never require the live public Internet.
