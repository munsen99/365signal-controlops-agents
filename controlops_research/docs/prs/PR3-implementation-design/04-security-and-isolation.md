# 04 — Security and isolation boundaries

Status: **PR3 boundaries IMPLEMENTED; static architecture coverage VERIFIED**.

## Authority and trust boundary

PR3 performs no fetch and opens no network socket. A source locator is stored
as descriptive identity and is not dereferenced. The only observation
authority is the already stored PR2 retrieval: PR2 `SnapshotStore` owns the
raw `body.bin`; PR3 references its `retrieval_id`, checks the raw bytes and
rebuilds visible text from the stored extraction contract.

The JSON catalogue contains provenance records and claims. It is not a second
snapshot store, source-content database, or verification authority. In
particular, a catalogue result field or quote cannot override a raw, extraction,
span, or excerpt-digest failure.

## Implemented isolation

The PR3 runtime modules use the Python standard library and import the shared
PR2 snapshot definitions and extractor. They do not import `fetch`,
`policy_data`, or a network client; the verifier does not call
`parse_content_contract` or `SnapshotStore`. PR3 has no live PostgreSQL client
or connection, and it does not execute `research_schema.sql`.

There is no PR3 path into Econo, its ports or credentials, `aea` or `aea_run`,
Hermes profiles, validator services, LanceDB, a model/LLM, or trusted RAG
writing. No publication workflow or PR4+ capability is implemented.

## Filesystem checks

The verifier rejects a symlink store root, retrieval path components, metadata
file, raw object path components, and visible-text path components before
reading. It returns closed missing or extraction-failure codes when relevant
paths cannot be read. The JSON catalogue rejects a symlink root and catalogue
file. Writes use restrictive directory/file modes, a temporary file, flush and
fsync, atomic replace, and directory fsync. This is the implemented path
handling and persistence posture; it is not described here as a general host
filesystem sandbox.

## Architecture checks and limits

`tests/test_architecture_boundaries.py` retains the package AST checks for
forbidden imports and configuration strings. Its PR3 extension checks the new
evidence/verifier modules for network clients, PostgreSQL clients, SQLAlchemy,
LanceDB, Hermes, validator and model-client imports; it also rejects imports of
`fetch` and `policy_data`, `parse_content_contract` use, and `SnapshotStore`
inside the verifier. The tests do not claim to prove absence of dynamically
constructed or indirect runtime behavior beyond their static checks.

PR3 tests build snapshots with the local PR2 `SnapshotStore` helper and fixture
files; they do not run a fetch operation. The accepted review records the
architecture suite as PASS and no network use by PR3 tests.

## State

- **IMPLEMENTED:** no-network provenance and verification path over local PR2
  snapshots; caller-selected filesystem storage.
- **VERIFIED:** architecture boundary checks, fixture-only tests, symlink-root
  rejection cases, and no SQL runtime path.
- **FUTURE / NOT IMPLEMENTED:** OS sandboxing, network acquisition, database
  authentication, model isolation, Hermes integration, and RAG publication.
