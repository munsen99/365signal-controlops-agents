# 04 — Result and deterministic failure contract

Decision D6: **APPROVED** on 2026-09-26.

## Result types

`FetchResult` is the closed union `FetchSuccess | FetchFailure`. Both are frozen,
slotted dataclasses and `bool(result)` raises `TypeError`.

`FetchSuccess` contains `retrieval_id`, final URL, raw SHA-256, raw byte length,
metadata path and visible-text path. Paths are relative to the supplied snapshot
root. It is returned only after a complete atomic record exists.

`FetchFailure` contains a closed `FetchFailureCode`, closed `FailureStage`, a
constant explanation, hop index or null, and the relevant immutable PR1 decision
or null. The original URL is excluded from repr. It contains no raw exception,
response body or partially successful snapshot reference. Operational failures
are values; programmer contract violations are not silently converted.

Stages are `POLICY`, `STORAGE`, `DNS`, `CONNECT`, `TLS`, `REDIRECT`, `HTTP`,
`READ`, `CONTENT` and `EXTRACT`.

## Closed failure codes

| Code | Stage | Meaning |
| --- | --- | --- |
| `POLICY_UNAVAILABLE` | POLICY | PR1 authority cannot be established |
| `URL_REJECTED` | POLICY | initial PR1 decision is REJECT |
| `URL_REVIEW_REQUIRED` | POLICY | initial PR1 decision is REVIEW |
| `STORAGE_UNAVAILABLE` | STORAGE | safe staging cannot be initialized |
| `DNS_TIMEOUT` | DNS | bounded resolver deadline expired |
| `DNS_FAILED` | DNS | resolver failed or returned malformed data |
| `DNS_NO_ADDRESS` | DNS | no IPv4/IPv6 stream address exists |
| `RESOLVED_DESTINATION_PROHIBITED` | DNS | at least one answer lacks PR1 ACCEPT |
| `CONNECT_TIMEOUT` | CONNECT | approved addresses could not connect in time |
| `CONNECT_FAILED` | CONNECT | approved addresses all failed connection |
| `TLS_FAILED` | TLS | handshake, trust or identity verification failed |
| `REDIRECT_LOCATION_INVALID` | REDIRECT | Location is absent, repeated, empty or cannot form an accepted URL |
| `REDIRECT_TARGET_REJECTED` | REDIRECT | target PR1 decision is REJECT or unavailable |
| `REDIRECT_TARGET_REVIEW_REQUIRED` | REDIRECT | target PR1 decision is REVIEW |
| `REDIRECT_LOOP` | REDIRECT | canonical target was already visited |
| `REDIRECT_LIMIT_EXCEEDED` | REDIRECT | another redirect exceeds five followed hops |
| `HTTP_STATUS_NOT_ACCEPTED` | HTTP | final status is not 200 or supported redirect |
| `RESPONSE_HEADERS_INVALID` | HTTP | bounded headers are malformed, repeated or conflicting |
| `READ_TIMEOUT` | READ | response-body read inactivity timeout expired |
| `READ_FAILED` | READ | transport ended with a non-timeout read error |
| `RESPONSE_TOO_LARGE` | READ | declaration or observed body exceeds 8 MiB |
| `UNSUPPORTED_CONTENT_TYPE` | CONTENT | media type is absent, malformed or outside the two allowed types |
| `UNSUPPORTED_CONTENT_ENCODING` | CONTENT | a nonidentity representation coding is declared |
| `UNSUPPORTED_CHARSET` | CONTENT | charset is absent from the fixed decoding set or ambiguous |
| `MALFORMED_TEXT` | CONTENT | strict decoding fails |
| `EXTRACTION_FAILED` | EXTRACT | deterministic parser contract cannot complete |
| `EXTRACTED_TEXT_TOO_LARGE` | EXTRACT | derived UTF-8 exceeds 8 MiB |
| `SNAPSHOT_PERSISTENCE_FAILED` | STORAGE | object or complete record cannot be atomically published |
| `NETWORK_DEADLINE_EXCEEDED` | current network stage | 30-second acquisition deadline expired before the final raw body read completed |

Constant explanations are keyed by code and interpolate no URL, hostname,
address, header or exception. Detailed diagnostics can be added only through a
future separately reviewed redaction/logging contract.

## Failure semantics

A denied/reviewed initial URL performs no DNS, socket or filesystem write. A DNS
answer-set failure performs no connection. Redirect failure performs no request
to the target. HTTP/content/extraction/persistence failure never creates a
complete retrieval record. Temporary files are best-effort removed without
masking the primary code.

Status 200 with valid empty content is success, not extraction failure. HTML that
contains only excluded or whitespace content also succeeds with empty derived
text. Transport truncation, invalid declared Content-Length, decode failure and
parser-contract failure are failures even if some raw bytes were received.

`NETWORK_DEADLINE_EXCEEDED` is possible only while DNS, connection, TLS,
redirect/HTTP handling or raw response reading remains active. The deadline ends
as soon as the final raw body is completely read. Later charset/content failures,
extraction failures and persistence failures retain their own codes and stages,
regardless of elapsed wall-clock time. No completed network acquisition is
retroactively classified as a network timeout.
