# 02 — Retrieval and HTTP contract

Decision D3: **APPROVED AS AMENDED** on 2026-09-26. Fetch policy version:
`controlops-fetch/v1.0.0`.

## Fixed capability

The sole public operation is:

```python
fetch_snapshot(value: object, snapshot_root: pathlib.Path) -> FetchResult
```

It performs one logical retrieval and persistence transaction. Security limits
are module constants, not caller options. Private dependency seams may accept a
resolver, connector, clock and filesystem adapter in tests; the public function
always constructs production components.

| Setting | Fixed value |
| --- | --- |
| Method | `GET` only |
| Schemes executable | HTTPS only, as a consequence of PR1 `ACCEPT` |
| DNS timeout | 3 seconds per hop |
| Connect/TLS handshake timeout | 5 seconds per address attempt |
| Socket read inactivity timeout | 10 seconds |
| Network-acquisition monotonic deadline | 30 seconds from initial DNS start through completion of the final raw body read |
| Redirects followed | 5 maximum |
| Raw body limit | 8,388,608 bytes (8 MiB) |
| Read chunk | 65,536 bytes |
| Derived UTF-8 text limit | 8,388,608 bytes |

Every blocking network timeout is capped by the remaining network-acquisition
deadline. That deadline starts immediately before DNS for the initial hop and
covers resolution, all connection/TLS attempts, requests, redirect processing,
response headers and the final raw response-body read. If it expires during
those stages, `NETWORK_DEADLINE_EXCEEDED` wins over the current network stage's
ordinary error.

The deadline closes when the final response body has been read completely (EOF,
or the declared body length has been satisfied). It is not consulted during
subsequent decoding, extraction, metadata construction or atomic persistence.
Once raw acquisition completes successfully, slower local work cannot reclassify
it as a network deadline failure. Extraction remains bounded by the 8 MiB raw and
derived-text limits; persistence remains bounded by those artefacts, the fixed
metadata structures and its deterministic storage failure contract.

## Request behavior

The request target is the canonical path plus query from PR1. Fragments are
already removed by canonicalisation. PR2 sends only these headers:

```text
Host: <canonical authority>
User-Agent: ControlOps-Research-Fetch/1.0
Accept: text/html, text/plain;q=0.9
Accept-Encoding: identity
Connection: close
```

Callers cannot add headers. There is no Authorization, Cookie, Referer, range,
conditional request, request body, proxy, environment-derived proxy, connection
pool, cache or credential lookup. Response cookies and authentication challenges
are ignored. Imports and ordinary result construction perform no external I/O.

## Response admission

Only status 200 can become a snapshot. Defined redirect statuses follow the
redirect lifecycle. Every other status, including other 2xx and all 4xx/5xx,
fails `HTTP_STATUS_NOT_ACCEPTED`; its body is not read or stored.

Headers must satisfy the standard library line/count bounds and this design's
semantic checks. Conflicting or repeated `Content-Type`, `Content-Length`,
`Content-Encoding` or redirect `Location` fields fail. A valid Content-Length
over 8 MiB fails before body reading. A smaller declaration does not replace the
streaming limit.

`Content-Encoding` must be absent or exactly `identity` (case-insensitive).
PR2 performs no gzip, Brotli or deflate decoding. The accepted media types and
character decoding rules are defined in
[03-snapshot-and-extraction.md](03-snapshot-and-extraction.md).

The source artefact is the exact sequence returned by the HTTP body reader after
HTTP transfer framing (for example chunk markers) has been removed, and before
character decoding or parsing. Because content codings are rejected, it is also
the received representation data. Hashing and temporary-file writing occur on
each byte chunk before any text work.

The reader requests at most the remaining limit plus one byte. Receiving byte
8,388,609 fails `RESPONSE_TOO_LARGE`. Empty status-200 content is a successful
source artefact if its content type and charset contract are valid; its SHA-256
is the standard empty-byte digest and its derived text is empty.

## Lifecycle and precedence

1. Evaluate the initial URL through PR1; stop unless `ACCEPT`.
2. Initialize a private staging directory under the supplied snapshot root.
3. For each hop: resolve, validate every address through PR1, pin/connect, verify
   TLS, issue GET, then process redirect or status 200.
4. Stream the final raw body into staging while hashing and enforcing limits.
5. Close the network deadline; validate content metadata, decode, and extract
   versioned visible text under the fixed byte limits.
6. Build canonical provenance metadata and validate its internal references.
7. Atomically publish the raw object and complete retrieval record.
8. Return immutable success only after publication completes.

Any failure closes sockets, removes the private staging record and returns one
closed failure code. After raw acquisition, extraction failures remain `CONTENT`
or `EXTRACT` failures and filesystem failures remain `STORAGE` failures; neither
can become `NETWORK_DEADLINE_EXCEEDED`. A content object published before a later
atomic-record failure is an unreferenced object, not a successful retrieval
record or evidence.
