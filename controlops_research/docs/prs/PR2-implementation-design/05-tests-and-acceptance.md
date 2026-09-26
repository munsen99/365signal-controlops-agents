# 05 — Test design and acceptance criteria

Decision D7: **APPROVED** on 2026-09-26. No test may require the live public
Internet.

## Test architecture

Tests use scripted resolver, connector, TLS and response adapters through private
dependency seams. The public API is separately tested to construct only the
production bounded resolver and pinned connector. Low-level connector tests
monkeypatch `socket.create_connection` and `SSLContext.wrap_socket` to prove the
numeric sockaddr is used while SNI remains the canonical hostname. Protocol-body
tests use `socket.socketpair` or byte streams; they do not bypass public policy in
production code.

The resolver worker has process lifecycle tests for success, malformed results,
timeout, termination and reap. PR1 itself is never mocked when deciding URL or
numeric-address authority; approved fixed public examples are used. Fault tests
may replace only the resolver/transport result around that real policy decision.

## Required cases

- accepted HTTPS URL, public resolution, status 200 plain text and complete record;
- denied, review and policy-unavailable URL never touch storage, resolver or connector;
- exact raw-byte preservation and known SHA-256, including NUL and nontext bytes
  that remain valid under the selected encoding;
- raw hashing before decoding/extraction and content-addressed deduplication;
- predictable plain text, HTML entities, block boundaries, hidden/script/style/
  template/noscript exclusion, malformed nesting and empty visible text;
- UTF-8, UTF-8 BOM, ASCII, missing charset, unsupported charset and invalid bytes;
- redirect to accepted URL, relative Location, fragment removal and five-hop boundary;
- redirect to rejected, review, mixed-DNS or policy-unavailable destination;
- repeated/empty Location, redirect loop and sixth redirect;
- loopback, private, link-local, multicast, unspecified, reserved and PR1-excluded
  resolver answers; both pure and mixed public/prohibited sets;
- IPv4, IPv6, duplicate answers, scoped IPv6 rejection and deterministic ordering;
- pinned socket address, no second DNS call, correct `Host`, SNI and certificate name;
- DNS, connect, TLS, read-inactivity and network-acquisition deadline failures;
- deadline expiry during DNS, connect, redirect and raw-body read maps to
  `NETWORK_DEADLINE_EXCEEDED`, with the active network stage retained;
- advancing the monotonic clock beyond 30 seconds only after the final raw byte
  cannot change successful acquisition into a deadline failure;
- slow/simulated-late decoding and extraction still succeed or return their
  content/extraction codes, and late persistence still succeeds or returns
  `SNAPSHOT_PERSISTENCE_FAILED`, without consulting the closed network deadline;
- status 200 acceptance; all redirect statuses; representative other 2xx/3xx/4xx/5xx rejection;
- missing/repeated/malformed content headers, nonidentity encoding, declared and
  streamed oversize boundaries at 8 MiB and 8 MiB plus one;
- chunk boundaries do not change body/hash/extraction results;
- empty status-200 body succeeds with empty digest and derived text;
- write, fsync, rename, collision and symlink failures publish no complete record;
- repeat extraction from stored raw bytes reproduces visible text and digest;
- immutable exact result fields, closed enums and forbidden truth testing;
- no proxy/environment/credential lookup, model call, database call, logging of
  source values or work at import time;
- all existing PR0/PR1 tests remain unchanged and pass on Python 3.13 and 3.14.

Fixtures are fixed local bytes, expected visible text and scripted response JSON.
Tests verify their hashes so test input drift is explicit.

## Acceptance criteria

PR2 implementation is acceptable only when all statements are demonstrated:

1. The initial URL and every redirect require a current PR1 `ACCEPT`; neither
   `REVIEW` nor a caller assertion grants access.
2. Every DNS answer is independently admitted by PR1 and the connection is pinned
   to the checked numeric set without a second lookup.
3. HTTP hostname and TLS identity remain the approved canonical host, and normal
   certificate validation cannot be disabled.
4. Method, headers, status, redirects and byte consumption obey the fixed
   contract; the 30-second monotonic deadline covers external network acquisition
   only, through completion of the final raw response-body read.
5. Raw response bytes are preserved exactly after transfer framing and before
   decoding, parsing or extraction, and SHA-256 covers those exact bytes.
6. Only the two reviewed text media types and fixed charset rules can succeed.
7. Visible text is reproducible, versioned derived data and never replaces the
   raw source object.
8. Complete metadata binds request, PR1 decisions, redirects, resolution,
   selected address, final response, raw identity and extractor identity.
9. Every defined failure is deterministic, fail closed and incapable of producing
   a complete retrieval record; completed acquisition is not reclassified as a
   network timeout by later extraction or persistence work.
10. Empty valid content is distinguishable from failed acquisition/extraction.
11. No LLM, reasoning, relevance, summarisation, trust, claim extraction,
   browser, database, publication or trusted-RAG capability exists.
12. Existing PR0/PR1 architecture tests and behavior remain intact, with no
   changes outside `controlops_research`.

Implementation review must include the exact changed file list, full test results,
fixture hashes and confirmation that no live public retrieval was used by tests.
