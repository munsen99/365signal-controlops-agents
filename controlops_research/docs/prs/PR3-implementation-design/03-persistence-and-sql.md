# 03 — Persistence and SQL contract

Status: **JSON persistence IMPLEMENTED; SQL is FUTURE / NOT IMPLEMENTED at runtime**.

## Runtime JSON catalogue

Runtime persistence is a filesystem JSON catalogue rooted at the caller's
`catalogue_root: Path`. It uses `catalogue.json` with schema version
`controlops-research-catalogue/v1.0.0` and three record arrays under
`research`: `source`, `snapshot_ref`, and `citation`.

| Record | Persisted fields and role |
| --- | --- |
| `Source` | `source_id`, `source_key`, optional `locator`, `created_at` |
| `SnapshotRef` | Identity/source/retrieval IDs, raw and extraction digests, extractor/media/schema pins, byte and character counts, capture and registration timestamps |
| `Citation` | Citation and snapshot-reference IDs, offsets, quote, excerpt digest, verifier version, result/reason, creation and verification timestamps |

Catalogue operations read from disk on each operation, so another process can
reopen the root and load/verify persisted records. Writes serialize canonical
JSON to a temporary file, flush and fsync it, replace `catalogue.json`, and
fsync the containing directory. The implementation sets catalogue directory
permissions to `0700` and catalogue file permissions to `0600`. It rejects a
symlink catalogue root or catalogue file.

Persisted records do not include source bytes, `body.bin`, or an authoritative
visible-text copy. Citation `quoted_text` is retained as the provenance claim;
it is never treated as the observed document or sufficient evidence of a pass.

## Future PostgreSQL contract

`src/controlops_research/research_schema.sql` defines a future PostgreSQL
contract. It creates schema `research` and only these tables:

| Table | Role and relationship |
| --- | --- |
| `research.source` | Logical source identity and descriptive locator |
| `research.snapshot_ref` | Integrity pins and retrieval reference; FK to `source` |
| `research.citation` | Span claim and verifier record; FK to `snapshot_ref` |

The relationship is `citation → snapshot_ref → source`. The SQL has no
`research.snapshot`, no `evidence` or `economic` schema, and no source-content
or blob authority. It is not deployed or executed by PR3. Runtime does not
connect to PostgreSQL, require a PostgreSQL client, or read this SQL file.

## Complete closed reason-code set

| Code | Meaning / result |
| --- | --- |
| `SPAN_MATCH` | Exact live span matches; `pass` |
| `SNAPSHOT_MISSING` | Retrieval or needed snapshot path unavailable; `fail` |
| `SNAPSHOT_SCHEMA_UNSUPPORTED` | PR2 retrieval schema is unsupported; `fail` |
| `SNAPSHOT_TAMPERED` | Raw bytes or raw retrieval identity fail integrity checks; `fail` |
| `EXTRACTION_MISMATCH` | Re-extracted or stored derived representation disagrees; `fail` |
| `EXTRACTOR_UNKNOWN` | Unsupported extractor; `indeterminate` |
| `SPAN_INVALID` | Invalid offset types or bounds; `fail` |
| `QUOTE_MISMATCH` | Live span differs from claimed quote; `fail` |
| `EXCERPT_HASH_MISMATCH` | Live matching span digest disagrees with citation row; `fail` |
| `SOURCE_NOT_FOUND` | Source row absent when registering a snapshot reference; `fail` |
| `SOURCE_CONFLICT` | Existing source key has a different locator; `fail` |
| `SNAPSHOT_REF_NOT_FOUND` | Snapshot reference absent; `fail` |
| `CITATION_NOT_FOUND` | Citation absent; `fail` |
| `STORAGE_UNAVAILABLE` | Catalogue/storage read or write failure; `fail` |
| `SCHEMA_FORBIDDEN` | Unsupported catalogue schema or forbidden catalogue schema request; `fail` |

Each code has a constant explanation in the runtime. Verdict values are
`pass`, `fail`, or `indeterminate`; `bool(CitationVerdict)` raises `TypeError`.

## State

- **IMPLEMENTED:** caller-rooted filesystem JSON catalogue and atomic,
  restrictive writes.
- **VERIFIED:** persistence, source conflict behavior and process-level reload
  followed by citation verification.
- **FUTURE / NOT IMPLEMENTED:** PostgreSQL connection, migration/application,
  deployed SQL tables, or database-backed runtime persistence.
