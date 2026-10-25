# 01 — Provenance model

Status: **IMPLEMENTED** at accepted commit `56dd905`.

## Realised record graph

```text
Source
  └── SnapshotRef
        ├── source_id
        ├── retrieval_id ───────────> PR2 retrieval record
        ├── raw_sha256
        ├── extraction_sha256
        ├── extractor/media/schema pins and sizes
        └── capture and registration timestamps
              └── Citation
                    ├── snapshot_ref_id
                    ├── Python str offsets [start_offset, end_offset)
                    ├── quoted_text
                    └── excerpt_sha256
```

`Source` identifies a logical source using `source_key` and an optional
`locator`. The locator is descriptive identity only and is never dereferenced.
`SnapshotRef` points to one PR2 `retrieval_id` and records integrity pins and
metadata. It has no source-body or visible-text field. `Citation` points to the
snapshot reference, stores the asserted quote and its span, and records the
verification result and reason.

PR2 `SnapshotStore` owns the observation. Its content-addressed `body.bin` is
the authoritative captured source material. PR3 does not duplicate source
bytes. The PR2 extraction metadata and deterministic extraction define the
visible text used by the verifier. Citation authority therefore follows
`Citation.snapshot_ref_id` to `SnapshotRef.retrieval_id` and then to the PR2
retrieval on disk.

The JSON catalogue stores provenance claims and references; agreement among
catalogue fields is not proof. `verify_citation` reopens the pinned PR2
retrieval, checks it, and only then tests the claim.

## Deterministic identities

IDs are SHA-256 hex digests of `snapshot.canonical_json(payload)`. The
implemented canonical JSON uses sorted keys, compact separators,
`ensure_ascii=False`, UTF-8 encoding, and one trailing newline. Timestamps are
excluded from identity payloads.

| ID | Canonical identity payload |
| --- | --- |
| `source_id` | `{"source_key": source_key, "locator": locator}` |
| `snapshot_ref_id` | `{"source_id": source_id, "retrieval_id": retrieval_id, "raw_sha256": raw_sha256, "extraction_sha256": extraction_sha256}` |
| `citation_id` | `{"snapshot_ref_id": snapshot_ref_id, "start_offset": start_offset, "end_offset": end_offset, "quoted_text": quoted_text}` |

The payload keys and values above are hashed as JSON objects; displayed key
order is illustrative because canonicalisation sorts keys. No random identity
is used. Same source key and locator reuses the stored source; a different
locator for that key raises `SOURCE_CONFLICT`. Existing snapshot pins reuse a
snapshot reference. Repeated citation identity is re-verified against the
current store before its record is written again.

## State

- **IMPLEMENTED:** `Source`, `SnapshotRef`, and `Citation` records and the
  identity construction above.
- **VERIFIED:** source conflict and idempotence, snapshot pins, no duplicate
  body/text on `SnapshotRef`, and A/B retrieval binding are tested.
- **FUTURE / NOT IMPLEMENTED:** source discovery, fetch, content caching, and
  any downstream finding or publication model.
