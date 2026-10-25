# 02 — Citation verification

Status: **IMPLEMENTED** at accepted commit `56dd905`.

## Realised `verify_citation` path

```mermaid
flowchart TD
    C[PR3 Citation from JSON catalogue] --> R[SnapshotRef from JSON catalogue]
    R --> ID[PR2 retrieval_id]
    ID --> M[metadata.json]
    M --> B[Read body.bin using metadata raw.object_path]
    B --> H[Recompute raw SHA-256 and byte length]
    H -->|match| CC[Reconstruct ContentContract from metadata]
    CC --> X[extract_visible_text raw bytes with contract]
    X --> EH[Compare extraction SHA-256, byte length and character count]
    X --> VT[Compare exact stored visible-text.txt bytes]
    EH --> S[Check half-open Python str offsets]
    VT --> S
    S --> Q[Compare slice with quoted_text exactly]
    Q --> D[Compare slice SHA-256 with Citation.excerpt_sha256]
    D --> V[CitationVerdict: pass | fail | indeterminate]
    H -->|raw digest or length mismatch| T[SNAPSHOT_TAMPERED]
    EH -->|derived representation mismatch| E[EXTRACTION_MISMATCH]
    VT -->|stored text mismatch| E
    S -->|invalid range| I[SPAN_INVALID]
    Q -->|different quote| QM[QUOTE_MISMATCH]
    D -->|different persisted digest| XH[EXCERPT_HASH_MISMATCH]
    CC -->|unsupported extractor| U[EXTRACTOR_UNKNOWN: indeterminate]
```

`verify_span` uses the same PR2 disk integrity and extraction path but accepts
`store_root` and `retrieval_id` directly. It does not load a catalogue or
require a `SnapshotRef`. `verify_citation` loads the citation and reference,
performs the disk checks, compares the current retrieval with the reference
pins, and checks the stored excerpt digest.

## Realised check order and meaning

The verifier rejects symlink store roots and symlink components along resolved
retrieval and content paths. It loads `retrievals/<retrieval_id>/metadata.json`
and requires the PR2 retrieval schema. It reads raw bytes using
`metadata.raw.object_path`, checks the recorded raw length and SHA-256, then
reconstructs `ContentContract` from `media_type`, `declared_charset`,
`applied_charset`, and `extraction.version`. It calls the shared
`extract_visible_text`; it does not parse HTTP headers or call `SnapshotStore`.

The re-extracted UTF-8 bytes must match the recorded extraction digest and
length/count metadata, and must equal the bytes in the stored
`visible-text.txt`. Span bounds use `len(visible_text)` and Python slicing, so
offsets are Python `str` positions in the exact re-extracted representation.
The actual slice must equal `quoted_text`; no normalisation or similarity rule
is applied. The slice's UTF-8 SHA-256 is then compared with the persisted
excerpt digest for citation verification.

| Code | Implemented meaning |
| --- | --- |
| `SNAPSHOT_TAMPERED` | Recorded raw size or digest does not match bytes, or the retrieval metadata identifies a different retrieval. |
| `EXTRACTION_MISMATCH` | Re-extraction, extraction metadata, extractor/media pairing, or stored visible-text bytes disagree. |
| `EXCERPT_HASH_MISMATCH` | A matching live span has a digest different from the persisted citation excerpt digest. |
| `QUOTE_MISMATCH` | A validly bounded live span differs from the supplied/persisted quote. |
| `SPAN_INVALID` | Start/end types or bounds do not define an allowed half-open span. |
| `EXTRACTOR_UNKNOWN` | Extractor version is unsupported; result is `indeterminate`. |

Other closed reasons cover absent records, unsupported PR2 schema, missing
storage, source conflicts, and forbidden catalogue schema. The complete set is
listed in [03 — persistence and SQL](03-persistence-and-sql.md).

## Why the catalogue is not an authority

The catalogue supplies record identifiers, pins and citation claims. It does
not supply the observation used to establish a pass. Verification follows the
reference to the PR2 retrieval, rehashes the authoritative captured bytes,
repeats the deterministic extraction, compares the derived file, and then
checks the quote and excerpt digest. A changed body, changed derived text, or
changed citation digest produces a distinct failure. A `result: pass` value in
the catalogue cannot bypass these checks.

## State

- **IMPLEMENTED:** `verify_span`, `verify_citation`, and creation-time
  verification through shared verifier logic.
- **VERIFIED:** exact/altered quotes, invalid ranges, Unicode string offsets,
  raw tampering, extracted-text tampering, excerpt-digest tampering, empty
  spans, catalogue-only claims, and A/B snapshot binding.
- **FUTURE / NOT IMPLEMENTED:** cached-text verification, similarity checks,
  model judgement, or validation from catalogue fields alone.
