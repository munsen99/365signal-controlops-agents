# 01 — Authority, redirects, DNS and connection safety

Decisions D1 and D2: **APPROVED** on 2026-09-26.

## Authority contract

`fetch_snapshot(value, snapshot_root)` calls PR1 `evaluate_url(value)` itself.
It does not accept a caller-created decision, exception, allowlist, policy
version or resolver override. Retrieval proceeds only when all of these hold:

- decision is `Decision.ACCEPT`;
- reason is `PUBLIC_URL_CANDIDATE`;
- `canonical_url`, host and effective port are present;
- policy version is `controlops-public-url/v1.0.0`.

`REVIEW` is a stop state, not approval. Consequently PR2 v1 supports HTTPS only;
PR1-approved HTTP review does not reach DNS or a socket. Invalid or unavailable
policy data also stops before external I/O. PR2 stores the complete initial PR1
decision and the equivalent decision for every redirect target.

The runtime imports the public PR1 types and `evaluate_url` only. It must not
import `_load_policy`, copy CIDR/namespace tables, or use interpreter properties
such as `is_private` or `is_global` as substitute policy.

## Redirect lifecycle

The HTTP client disables automatic redirects. It handles only 301, 302, 303,
307 and 308 from a GET response. Each redirect must have exactly one nonempty
`Location` header. The target is resolved against the current canonical URL with
`urllib.parse.urljoin`, then passed as a fresh exact string to PR1. Only a new
`ACCEPT` may continue.

Canonical URLs identify loops. The initial canonical URL is in the visited set.
A target already present fails `REDIRECT_LOOP`. At most five redirects may be
followed, allowing no more than six network requests. A sixth redirect response
fails `REDIRECT_LIMIT_EXCEEDED` without evaluating or connecting to another hop.
Redirect response bodies are not read or stored; the connection is closed.

Every followed hop repeats policy evaluation, bounded DNS resolution, validation
of every resolved address, address pinning and TLS verification. A redirect
never inherits authority, DNS results or a connection from its predecessor.

The redirect record contains the zero-based hop, source canonical URL, status,
raw `Location`, canonical target URL and complete PR1 target decision. It contains
no response headers or body.

## Bounded DNS resolution

DNS names are resolved with `socket.getaddrinfo(host, 443, type=SOCK_STREAM,
proto=IPPROTO_TCP)` inside a dedicated spawned worker process. The parent waits
at most 3 seconds. On timeout it terminates, then kills if necessary, and reaps
the worker. It accepts only successful IPv4/IPv6 numeric results and never
accepts a hostname returned by a resolver.

The implementation deduplicates answers by address family and numeric address.
IPv6 scope identifiers and nonzero scope IDs are rejected. Empty results fail.
Addresses are ordered deterministically: IPv4 before IPv6, then ascending numeric
value. This proposal favors reproducibility over a racing “Happy Eyeballs” path.

The resolver result is frozen for that hop. PR2 does not cache it across redirects
or later retrievals, and it does not perform a reverse lookup.

## PR1 validation of resolved addresses

For each unique answer, PR2 parses the numeric value with `ipaddress`, constructs
a synthetic HTTPS literal URL (`https://192.0.2.1/` or
`https://[2001:db8::1]/`) and calls public `evaluate_url`. The synthetic URL is a
query to PR1, not a second policy. Every result must be `ACCEPT` under the same
policy version as the hop decision. A mapped IPv6 spelling containing a dotted
tail, a noncanonical result, a rejected address, `REVIEW`, or policy failure
rejects the entire answer set before connection.

Requiring every answer to pass prevents a mixed public/private response from
becoming selection-dependent. Metadata records the sorted answer set and each
address decision. These checks are repeated after every redirect resolution.

## Pinned connection

The connector receives the frozen numeric socket address; it must not receive the
hostname for connection setup and must not call `getaddrinfo`. It attempts the
approved addresses sequentially within the network-acquisition deadline. The
selected numeric address is recorded.

For TLS, a default `ssl.SSLContext` with certificate verification and hostname
checking enabled wraps the connected socket with `server_hostname` equal to the
PR1 canonical DNS hostname. TLS 1.2 is the minimum. Literal-IP URLs use the
canonical IP as certificate identity. The HTTP `Host` header uses the canonical
host and omits default port 443. No verification disable flag or custom trust
store is exposed.

This separation preserves both properties: TCP cannot be rebound to an address
outside the checked set, and the peer certificate must authenticate the original
PR1-approved host. Connection retry never triggers re-resolution.
