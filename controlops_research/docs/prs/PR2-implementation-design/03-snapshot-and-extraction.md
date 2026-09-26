# 03 — Snapshot, provenance and derived text

Decisions D4 and D5: **APPROVED** on 2026-09-26.

## Content admission

PR2 v1 accepts only `text/plain` and `text/html`. MIME comparison is
case-insensitive; parameters other than one `charset` are rejected. A declared
charset may be `utf-8`, `utf8` or `us-ascii`, normalized to `utf-8` or
`us-ascii`. With no declaration, strict UTF-8 is the deterministic default.

A UTF-8 BOM is accepted only for UTF-8 input, removed from derived text and
recorded as applied charset `utf-8-sig`. Decoding is strict. PR2 does not sniff
HTML meta tags, guess encodings or replace invalid sequences. Unsupported or
ambiguous declarations and undecodable bytes fail after raw acquisition but
before publication of a complete record.

PDF, Office formats, XML, JSON, images, audio, video, multipart data, archives,
feeds and arbitrary binary types are outside PR2 v1. There is no JavaScript,
CSS layout, browser automation, OCR or download recursion.

## Extraction versions

`text/plain` uses extractor `plain-text/v1`: strict decode, remove one leading
UTF-8 BOM when applicable, preserve every other Unicode scalar and line ending.
No Unicode normalization or whitespace trimming occurs.

`text/html` uses extractor `html-visible-text/v1`, implemented with
`html.parser.HTMLParser(convert_charrefs=True)`:

- ignore comments, declarations and processing instructions;
- exclude content inside `script`, `style`, `template` and `noscript` elements;
- exclude a subtree rooted at an element carrying the HTML `hidden` attribute;
- emit a line boundary for `br`, `p`, `div`, `li`, headings, `tr`, `section`,
  `article`, `header`, `footer`, `main`, `nav`, `aside`, `blockquote`, `pre` and
  `title` start/end events;
- include decoded data from all other nonexcluded elements;
- map every run of Unicode whitespace to one ASCII space within a line, trim
  line edges, remove empty lines, and join lines with `\n`;
- do not apply CSS, ARIA semantics, URL fetching, DOM repair beyond the parser,
  Unicode normalization or semantic interpretation.

This output is a deterministic textual approximation, not proof of browser
visibility. Parser exceptions, unclosed exclusion state, or output beyond the
derived limit fail extraction. The derived file is UTF-8 without BOM and ends
without an added newline. Re-extraction from stored raw bytes, recorded media
type/charset and the same extractor version must reproduce its digest exactly.

## Storage layout

The caller supplies an explicit `pathlib.Path` snapshot root. PR2 does not read
an environment variable or default to another ControlOps project. It creates
private directories/files with modes 0700/0600 and rejects symlinked storage
targets.

```text
<root>/
  objects/sha256/ab/<64-hex>/body.bin
  retrievals/<64-hex>/metadata.json
  retrievals/<64-hex>/visible-text.txt
  .staging/<private-temporary-record>/...
```

The object key is SHA-256 over exact raw body bytes. An existing object is reused
only after its type, length and digest are verified; mismatches fail closed.
Metadata and visible text are completed in staging, flushed, and the retrieval
directory is atomically renamed into place. `metadata.json` is the completion
marker. Existing identical records are idempotent; an existing nonidentical
record at the same identifier is a persistence failure.

JSON is UTF-8, `sort_keys=True`, compact separators, `ensure_ascii=False`, with
one trailing newline. The retrieval identifier is SHA-256 over canonical metadata
before adding `retrieval_id` and storage-relative paths. Timestamp variation
therefore creates distinct retrieval records while the raw object is deduplicated.

## Exact metadata shape

Every complete `metadata.json` has these keys:

| Key | Contract |
| --- | --- |
| `schema_version` | `controlops-retrieval-record/v1.0.0` |
| `retrieval_id` | 64 lowercase hex characters |
| `fetch_policy_version` | `controlops-fetch/v1.0.0` |
| `requested_url` | exact initial built-in string |
| `initial_policy_decision` | all ten PR1 `UrlDecision` fields |
| `final_url` | final PR1 canonical URL |
| `redirect_chain` | ordered redirect records, possibly empty |
| `resolution_events` | one event per requested hop |
| `started_at` | UTC RFC 3339 timestamp with microseconds and `Z` |
| `completed_at` | same format, not earlier than start |
| `http_status` | integer 200 |
| `media_type` | `text/plain` or `text/html` |
| `declared_charset` | normalized string or null |
| `applied_charset` | `utf-8`, `utf-8-sig` or `us-ascii` |
| `content_encoding` | `identity` |
| `raw` | byte length, SHA-256 and relative object path |
| `extraction` | version, Unicode character count, UTF-8 byte length, SHA-256 and relative path |

A resolution event records canonical URL, host, port, sorted numeric answers,
the complete PR1 decision for each synthetic literal URL, and selected address.
No DNS server, TTL or reverse name is claimed because `getaddrinfo` does not
provide them. No arbitrary response headers, cookies, certificate bodies or
exception strings are stored.

Raw `body.bin` is authoritative. Metadata is provenance. `visible-text.txt` is
derived and replaceable by a future explicitly versioned extractor; it never
replaces or changes the source object. PR2 records are not PR3 Evidence Plane
records and do not imply truth, relevance, approval or trusted-RAG eligibility.
