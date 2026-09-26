# PR1 — Public URL policy

## Objective

Specify pure, deterministic URL validation, canonicalisation, destination
classification and structured decisions: `ACCEPT`, `REJECT` or `REVIEW`, with
stable reason codes. These are policy/workflow states, not network permissions.

This is a documentation/design update only. PR1 implementation is not authorised.
The canonical [programme index](README.md) remains `PLANNED` for PR1.

## Why this PR exists

Syntactic validity does not establish a safe public destination. Define the policy
before introducing network capability, and distinguish security rejection from
a stopped source needing human assessment. Models reason; deterministic controls
establish authority; evidence, not model output, is the system of record.

## In scope

- Pure URL validation and canonicalisation.
- Deterministic hostname/IP classification using reviewed versioned policy data.
- Structured decisions, stable reason codes and a future review-event contract.
- Security-semantic tests and preservation of PR0 architecture boundaries.

## Out of scope

DNS resolution, HTTP requests, redirects, socket connections, database access,
model inference, Docker/service inspection, secret access, external policy
lookups, environment-derived configuration and automatic registry updates.

No persistence, logging of review events, notifications, human-approval service,
exception execution or HTTP-to-HTTPS upgrade. No PR2 capability. IDNA support
requires its own reviewed contract. Writer, publication and trusted RAG ingestion
remain outside the research implementation programme unless separately approved.

## Files expected to change

This design update changes only `docs/prs/PR1-public-url-policy.md`.

The later implementation-design gate should finalise a minimal layout, expected
to include `src/controlops_research/policy.py`, locally bundled versioned policy
data if needed, and `tests/test_url_policy.py`. Approve the exact data tables and
interface before coding. This document creates no application or test files.

## Architecture / design

### Normative definition

An ACCEPTED public-source URL is an absolute HTTPS URL that satisfies the
versioned ControlOps URL policy, contains no userinfo, uses destination port 443,
and identifies either an admissible ASCII DNS hostname or an admissible canonical
public IP literal.

**ACCEPT is candidate admission only. It does not authorise a network connection
or establish that a hostname resolves to a public address.** It does not establish
content trust, evidence status or permission to enter trusted RAG.

**REVIEW identifies a source that cannot proceed automatically under the current
policy but may warrant human assessment. REVIEW is not permission to fetch,
connect, bypass policy or trust the source.** It is an escalation state, not an
authority state.

**REJECT stops malformed, ambiguous, prohibited or unsafe candidates.** A security
or architecture violation cannot be overridden as an ordinary source exception.

### Decision order and reason codes

Policy data must be valid and versioned before evaluation; otherwise return
`REJECT: POLICY_UNAVAILABLE`. For candidate evaluation, apply these stages in
order and return the first failure's code. Within each stage use the rule order
below. Parser exception text is not a stable reason code.

1. Raw input validation.
2. Absolute URL structure validation.
3. Supported scheme check.
4. Userinfo, then authority-encoding checks.
5. Explicit port syntax, then port policy.
6. Host representation, then destination classification.
7. Component grammar, then dot-segment checks.
8. Otherwise eligible HTTP returns `REVIEW: HTTP_NOT_PERMITTED`; eligible HTTPS
   returns `ACCEPT: PUBLIC_URL_CANDIDATE`.

REJECT always takes precedence over HTTP REVIEW. For example,
`http://127.0.0.1/`, HTTP userinfo and HTTP prohibited ports must be rejected.
REVIEW is not a fallback for unsupported schemes or unclassifiable destinations.

### Raw input and parsing

- Require a nonempty string; otherwise `INVALID_INPUT`. No implicit conversion.
- Before parsing, reject raw whitespace/ASCII controls, DEL, backslashes and raw
  non-ASCII characters as `FORBIDDEN_RAW_CHARACTER`. Never trim, remove newlines,
  normalise Unicode or repair input.
- Every `%` must introduce two hexadecimal digits, else
  `MALFORMED_PERCENT_ESCAPE`. Valid escapes encoding bytes `00`–`1F`, `7F` or
  `5C` return `FORBIDDEN_ENCODED_CHARACTER`. Do not recursively decode escapes.
- Require an absolute `scheme://authority` with a nonempty host. Relative or
  scheme-relative inputs, missing authority, malformed brackets, unbracketed
  IPv6 and unparseable authority structures return `MALFORMED_URL`.
- A parser only splits components; independently enforce these rules. Catch
  parsing failures without permissive fallback or inferring a missing scheme.

### Schemes, credentials and ports

Match schemes case-insensitively; canonical output uses lowercase. Only HTTPS can
receive ACCEPT. Otherwise eligible HTTP receives `REVIEW: HTTP_NOT_PERMITTED`.
Do not automatically change HTTP to HTTPS or follow a redirect to find HTTPS.
Reject `file`, `ftp`, `data`, `javascript`, `mailto` and unknown/custom schemes as
`UNSUPPORTED_SCHEME` when the input has passed structural validation.

Reject all userinfo, including empty userinfo, as `USERINFO_FORBIDDEN`. Reject any
percent escape in the authority as `ENCODED_AUTHORITY_FORBIDDEN`. Do not decode
encoded authority separators or hostnames before deciding.

An explicit port must be unsigned decimal 1–65535, without leading zeros;
otherwise `INVALID_PORT`. Only explicit `443` is permitted; all other well-formed
explicit ports return `PORT_NOT_PERMITTED`. This includes `80`, `5432`, `8443`,
`18700`–`18705` and alternate local-service ports. No nonstandard HTTPS exception.

Omitted HTTPS port means 443; remove explicit HTTPS `:443` in canonical output.
Omitted HTTP port is allowed solely for REVIEW classification, not connection
approval. Explicit HTTP `:80` is REJECT under the explicit-port rule. Otherwise
eligible HTTP `:443` remains REVIEW and keeps that port in diagnostic output.
HTTP's implicit 80 is descriptive metadata only. This deliberate distinction
does not permit any HTTP network operation.

### Hostnames

Recognise strict IPv4/bracketed IPv6 before DNS-name admission. Alternative
numeric IP spellings must not fall back to permissive hostname interpretation.
Lowercase ASCII DNS hostnames and require:

- At least two labels, no empty labels and no trailing dot.
- Labels of 1–63 ASCII letters/digits/hyphens, starting and ending alphanumerically.
- Maximum hostname length 253 characters.
- Final label of at least two ASCII letters only.
- No `xn--` label; Unicode/IDNA/punycode admission is deferred.

Representation violations return `HOST_NOT_PERMITTED`. Single-label names such
as `hermes`, `postgres`, `economic-control`, `lm-studio` and
`controlops-msft-validator` fail regardless of local resolver behaviour.

Then reject prohibited namespaces as `DESTINATION_PROHIBITED`. Match exact names
and subordinate names at label boundaries, never arbitrary substrings. Versioned
policy data must include IANA special-use names plus local suffixes `internal`,
`intranet`, `lan`, `corp`, `home` and `arpa`. This excludes `localhost` and its
subdomains, `.local`, `.test`, `.invalid`, `.example` and reserved example domains.
Any known internal ControlOps FQDNs must be reviewed policy data; do not inspect
services, profiles, Docker or secrets to discover them.

A DNS-shaped name may still be nonexistent or resolve internally. PR1 does not
check registration, public suffix delegation, DNS existence or public resolution.
Such uncertainty requires future runtime validation, not a claim of safety.

### IP literals and policy data

IPv4 requires four decimal octets, each 0–255, with no leading zeros except the
single digit `0`. Reject integer, hexadecimal, octal and shortened forms rather
than interpreting them.

IPv6 requires brackets and canonical lowercase compressed spelling: shortest
hexadecimal groups, longest zero run compressed (first wins a tie), and no
compression of one zero group. Reject zone identifiers, IPvFuture, embedded
dotted-IPv4 representations and noncanonical forms. Representation failures
return `HOST_NOT_PERMITTED` (earlier raw/authority failures still take precedence).

Only ordinary public unicast is eligible. Return `DESTINATION_PROHIBITED` for
loopback, RFC1918, link-local, unspecified, multicast, reserved/special-purpose,
carrier-grade NAT, benchmarking, documentation, unique-local IPv6, IPv4-mapped
IPv6, translation/tunnelling forms and other reviewed excluded ranges.

Use explicit reviewed ranges, not `not ip.is_private`, `is_global` alone or other
interpreter-dependent classification defaults. The initial conservative design
excludes all ranges in the pinned IANA IPv4/IPv6 special-purpose snapshots,
including globally reachable exceptions, plus multicast/reserved classes outside
those tables. IPv6 eligibility is additionally restricted to ordinary unicast
within `2000::/3`, minus exclusions. Some otherwise reachable sources are therefore
intentionally excluded.

The implementation-design gate must approve complete concrete range/namespace
tables, snapshot dates/source references, policy version and boundary fixtures
before coding. Categories alone are not permission to invent data during coding.
Approved data must be bundled locally; no runtime lookup or automatic refresh.
Data changes require reviewed policy revisions. Invalid/missing policy data
fails closed as `POLICY_UNAVAILABLE`, never falling back to weaker defaults.

### Path, query, fragments and canonicalisation

Validate RFC 3986 component grammar: path permits `pchar` and `/`; query/fragment
permit `pchar`, `/` and `?`. Here `pchar` is ASCII unreserved characters, valid
percent escapes, sub-delimiters, `:` and `@`. Unreserved characters are letters,
digits and `-._~`; sub-delimiters are `!$&'()*+,;=`. Other raw component characters
return `INVALID_COMPONENT` after earlier raw checks.

Split paths on literal `/`. Reject segments equal to `.` or `..`, treating `%2e`
(case-insensitive) as a dot for this check, as `DOT_SEGMENT_FORBIDDEN`. Include
mixed literal/encoded dots. Do not recursively decode or split on encoded `/`.
Escaped path/query separators remain data and must never become authority syntax.
This destination policy does not claim to detect every server-side path rewrite.

Canonicalisation only lowercases scheme/DNS host, removes accepted HTTPS `:443`,
changes an empty path to `/`, uppercases percent-escape hex digits and removes a
validated fragment. IP literals must already be canonical. Preserve path/query
case, query order, duplicate parameters, escaped bytes and an explicit empty query
delimiter. Do not decode/re-encode parameters, unescape unreserved characters,
normalise slashes or repair traversal. Require idempotence and destination
preservation, not a claim that every equivalent resource URL has one spelling.

For HTTP REVIEW, canonical output is diagnostic only: keep `http`, preserve an
explicit `:443`, and never treat the result as an approved fetch candidate.

### Structured decision and human review contract

| Field | Meaning |
| --- | --- |
| `original_url` | Exact supplied string; null for non-string input. Untrusted data, not permission to log credentials. |
| `decision` | Exactly ACCEPT, REJECT or REVIEW; consumers must not use truthiness as approval. |
| `reason_code` | Stable code from the ordered rules. |
| `policy_version` | Explicit rule/data version evaluated; null when no valid version can be established. |
| `canonical_url` | Candidate for ACCEPT or diagnostic HTTP URL for REVIEW; null for REJECT. Never connection authority. |
| `host`, `host_kind`, `effective_port` | Canonical metadata for ACCEPT/REVIEW; kind is `dns`, `ipv4` or `ipv6`. Null for REJECT. HTTP implicit 80 is descriptive only. |
| `explanation` | Deterministic explanation associated with the reason. |
| `requested_human_action` | REVIEW: supply compliant replacement, abandon, or propose a future governed policy change. Otherwise null. |

No clock reads, random identifiers, persistence, review notifications or logging
inside the pure policy. Future orchestration may add a timestamp/run identifier
outside the deterministic result. A rejected original URL may contain credentials;
future storage/logging must address safe handling, not blindly record it.

```text
Candidate URL -> Deterministic PR1 Policy -> ACCEPT | REVIEW | REJECT

REVIEW -> Record reason (future workflow) -> Human assessment
       -> provide compliant replacement URL -> evaluate full policy again
       -> abandon source
       -> propose future governed exception/policy change
```

PR1 records the stop/review requirement in returned data only. Persistence is not
authorised. No network operation occurs in this workflow. Human assessment does
not convert REVIEW/REJECT into authority; no exception mechanism is implemented.

## Security boundaries

All eighteen [architecture invariants](../architecture-invariants.md) remain
authoritative. No `aea` imports, Econo endpoints/secrets/tokens/mounts, privileged
database identities, Hermes/validator dependency, profile or Compose change.
Policy data describes prohibited destinations without connecting to them. Do not
weaken PR0 static tests; they remain static checks, not runtime isolation.

Port 443 and an ordinary hostname do not prove a service is external: internal
services can have public addresses or reverse proxies. Future approved local
LM Studio access is a separate capability and must not become a public-fetch
policy exception.

### Deferred network controls

PR1 does not solve DNS rebinding. The future fetch PR must establish and test:

1. Re-evaluate candidates using the active policy; stored ACCEPT is not perpetual
   approval. REVIEW/REJECT stop before DNS or network operations.
2. Controlled resolution without local search-suffix expansion; validate all
   resulting A/AAAA addresses against the same reviewed address policy. Reject
   failed, empty or mixed public/prohibited results.
3. Connect only to an approved address from that result; prevent independent
   re-resolution/substitution between checking and connecting. Preserve original
   hostname for verified TLS and HTTP authority.
4. Independently validate the complete URL and resolved addresses of every
   redirect before following it. Resolve relative references against the current
   URL first. Redirects inherit no approval; HTTP remains stopped.
5. Equivalent validation for retries, new connections and alternate routes;
   uncontrolled proxies/environment routing must not bypass host/port/address
   enforcement.
6. Network isolation from ControlOps infrastructure, including publicly numbered
   internal endpoints. Private-address classification alone is insufficient.
7. Fetch-specific timeouts, redirect limits, response-size limits and tests.

These are future preconditions, not implemented controls. Neither URL admission
nor fetching automatically establishes evidence or approved RAG knowledge.

## Tests

These are future tests, not implemented by this documentation update. Split every
group into individual tests; no test contacts the example destination.

| Input | Expected decision / reason | Meaning |
| --- | --- | --- |
| `https://learn.microsoft.com/` | ACCEPT / PUBLIC_URL_CANDIDATE | Ordinary HTTPS |
| `HTTPS://LEARN.MICROSOFT.COM:443` | ACCEPT / PUBLIC_URL_CANDIDATE | Output `https://learn.microsoft.com/` |
| `https://8.8.8.8/` | ACCEPT / PUBLIC_URL_CANDIDATE | Canonical ordinary IPv4 |
| `https://[2606:4700:4700::1111]/` | ACCEPT / PUBLIC_URL_CANDIDATE | Canonical ordinary IPv6 |
| `http://learn.microsoft.com/`, `http://learn.microsoft.com:443/` | REVIEW / HTTP_NOT_PERMITTED | No upgrade, redirect or connection |
| `http://learn.microsoft.com:80/` | REJECT / PORT_NOT_PERMITTED | Explicit-port rejection precedes review |
| `http://127.0.0.1/` | REJECT / DESTINATION_PROHIBITED | Security rejection precedes review |
| `http://user@learn.microsoft.com/` | REJECT / USERINFO_FORBIDDEN | HTTP cannot mask credentials |
| `http://learn.microsoft.com/%ZZ` | REJECT / MALFORMED_PERCENT_ESCAPE | HTTP cannot mask malformed input |
| `https://localhost/`, `https://hermes/`, `https://postgres/`, `https://economic-control/`, `https://lm-studio/`, `https://controlops-msft-validator/` | REJECT / HOST_NOT_PERMITTED | Single-label names |
| `https://a.localhost/`, `https://printer.local/`, `https://host.internal/` | REJECT / DESTINATION_PROHIBITED | Local/internal namespaces |
| `https://host.test/`, `https://host.invalid/`, `https://example.com/` | REJECT / DESTINATION_PROHIBITED | Special-use domains |
| `https://127.0.0.1/`, `https://127.255.255.254/` | REJECT / DESTINATION_PROHIBITED | Loopback range |
| `https://10.0.0.1/`, `https://172.16.0.1/`, `https://192.168.1.1/` | REJECT / DESTINATION_PROHIBITED | RFC1918 |
| `https://169.254.169.254/`, `https://100.64.0.1/`, `https://198.18.0.1/`, `https://192.0.2.1/` | REJECT / DESTINATION_PROHIBITED | Link-local, CGNAT, benchmark, documentation |
| `https://0.0.0.0/`, `https://224.0.0.1/`, `https://240.0.0.1/` | REJECT / DESTINATION_PROHIBITED | Unspecified, multicast, reserved |
| `https://[::]/`, `https://[::1]/`, `https://[fc00::1]/`, `https://[fe80::1]/`, `https://[ff02::1]/`, `https://[2001:db8::1]/` | REJECT / DESTINATION_PROHIBITED | Nonpublic/special IPv6 |
| `https://[::ffff:c0a8:101]/`, `https://[::ffff:808:808]/`, `https://[64:ff9b::808:808]/` | REJECT / DESTINATION_PROHIBITED | Mapped and translation ranges |
| `https://[::ffff:192.168.1.1]/` | REJECT / HOST_NOT_PERMITTED | Dotted embedded IPv4 |
| `https://[fe80::1%25eth0]/` | REJECT / ENCODED_AUTHORITY_FORBIDDEN | Zone identifier encoding |
| `https://2130706433/`, `https://0x7f000001/`, `https://0177.0.0.1/`, `https://127.1/` | REJECT / HOST_NOT_PERMITTED | Alternative IP spellings |
| `https://user@learn.microsoft.com/`, `https://user:pass@learn.microsoft.com/`, `https://@learn.microsoft.com/`, `https://public.example@127.0.0.1/` | REJECT / USERINFO_FORBIDDEN | All userinfo prohibited |
| `https://learn.microsoft.com:18700/` through `:18705/` | REJECT / PORT_NOT_PERMITTED | Test all six individually |
| `https://learn.microsoft.com:80/`, `:5432/`, `:1234/`, `:8443/` (same host) | REJECT / PORT_NOT_PERMITTED | Alternate/local ports |
| `https://learn.microsoft.com:/`, `:0443/`, `:+443/`, `:0/`, `:65536/` (same host) | REJECT / INVALID_PORT | Invalid/noncanonical ports |
| `file:///etc/passwd`, `data:text/plain,x`, `javascript:alert(1)`, `mailto:a@b.com` | REJECT / MALFORMED_URL | Missing required authority structure takes precedence |
| `ftp://host.com/`, `custom://host.com/`, `file://host.com/path` | REJECT / UNSUPPORTED_SCHEME | No generic scheme REVIEW |
| Empty string, non-string value | REJECT / INVALID_INPUT | No implicit conversion |
| `//learn.microsoft.com/`, `/relative`, `https:///path`, `https://[::1/` | REJECT / MALFORMED_URL | Missing structure/malformed brackets |
| `https://bücher.de/` | REJECT / FORBIDDEN_RAW_CHARACTER | Raw Unicode excluded |
| `https://xn--bcher-kva.de/` | REJECT / HOST_NOT_PERMITTED | IDNA deferred |
| `https://learn.microsoft.com./`, `https://a..com/`, `https://-a.com/`, `https://a_b.com/` | REJECT / HOST_NOT_PERMITTED | Host grammar |
| `https://%31%32%37.0.0.1/` | REJECT / ENCODED_AUTHORITY_FORBIDDEN | No encoded host repair |
| `https://learn.microsoft.com%2F@127.0.0.1/` | REJECT / USERINFO_FORBIDDEN | Userinfo precedes encoded-authority rejection |
| Leading space, embedded newline or raw backslash | REJECT / FORBIDDEN_RAW_CHARACTER | Check before parser stripping |
| `https://learn.microsoft.com/%ZZ` | REJECT / MALFORMED_PERCENT_ESCAPE | Malformed escape |
| `https://learn.microsoft.com/%0D%0AHost:x` | REJECT / FORBIDDEN_ENCODED_CHARACTER | Encoded controls |
| `https://learn.microsoft.com/a/../b`, `https://learn.microsoft.com/a/%2e%2e/b` | REJECT / DOT_SEGMENT_FORBIDDEN | Literal/encoded dot segments |
| `https://learn.microsoft.com/a%2fb?q=x%26y&q=Two#section` | ACCEPT / PUBLIC_URL_CANDIDATE | Uppercase `%2F`; preserve query; remove fragment |
| `https://learn.microsoft.com/?next=http%3A%2F%2F127.0.0.1` | ACCEPT / PUBLIC_URL_CANDIDATE | Query data is not the destination |
| `https://learn.microsoft.com/?` | ACCEPT / PUBLIC_URL_CANDIDATE | Preserve empty query delimiter |
| Eligible URL with unavailable/invalid policy data | REJECT / POLICY_UNAVAILABLE | No weaker fallback |

Also test label/hostname length boundaries, excluded address-range boundaries and
neighbours, IPv6 canonicalisation/ties, escape case, encoded fragment controls,
invalid component characters, suffix label boundaries, mixed dot segments,
multiple-failure precedence and stable decisions across supported Python versions.
Test repeatability, idempotence and preservation of query order/duplicates/case.
Instrument evaluation to fail on DNS, socket, subprocess, secret/service access,
clock/random use and persistence. Retain PR0 import/boundary tests and the smallest
appropriate existing regressions. No live DNS/HTTP test fixtures.

## Acceptance criteria

1. Before coding, the implementation-design gate approves concrete versioned
   address/namespace tables, provenance and the decision/data interface.
2. Every matrix case returns the specified decision/reason without I/O.
3. REVIEW occurs only for otherwise eligible HTTP and never masks a rejection,
   upgrades a scheme, fetches, redirects or grants an exception.
4. Only HTTPS with effective port 443 receives ACCEPT. Userinfo, ambiguity and
   prohibited destinations fail closed.
5. Canonicalisation is deterministic/idempotent and preserves destination and
   specified path/query semantics; rejected inputs are not repaired.
6. Explicit policy data determines address decisions independently of interpreter
   defaults, demonstrated by boundary and supported-version tests.
7. Review requirements appear in structured output without persistence; any
   orchestration timestamp remains outside pure policy evaluation.
8. No decision implies DNS validation, connection authority, content trust,
   evidence status or RAG permission.
9. PR0 tests remain effective and pass; no unrelated source/profile/Compose,
   database or model configuration changes occur.
10. No network, DNS, external lookup, service inspection, secret access,
    persistence, model inference or PR2 capability is introduced.

## Evidence to capture

At design approval: exact tables, policy version, dated registry snapshots/source
references, interface and reviewer decision. At later implementation: revision,
exact test commands/results, matrix coverage, canonicalisation examples,
side-effect guard results, regression outcomes, git status/diff checks and limits.
This documentation update does not claim future implementation tests passed.

## Explicitly forbidden changes

Do not implement PR1 or begin PR2 under this instruction. Do not change application
source, Econo, Hermes, validator, Compose, database or model configuration. Do not
perform DNS resolution or create network capability. Do not add ordinary overrides
for architecture violations, generalise REVIEW to arbitrary schemes, upgrade HTTP,
persist/send review events or commit without separate instruction.

## Dependencies

PR0's architecture contract, the completed URL-policy review and the subsequent
ACCEPT/REJECT/REVIEW decisions are authoritative. These references identify
provenance for the future design gate, not runtime dependencies:

- [IANA IPv4 special-purpose registry](https://www.iana.org/assignments/iana-ipv4-special-registry)
- [IANA IPv6 special-purpose registry](https://www.iana.org/assignments/iana-ipv6-special-registry)
- [IANA special-use domains](https://www.iana.org/assignments/special-use-domain-names)
- [RFC 3986 component syntax](https://www.rfc-editor.org/rfc/rfc3986)
- [Python URL parser limitations](https://docs.python.org/3.12/library/urllib.parse.html)

No new runtime dependency is authorised by this specification.

## Exit condition

For this update: a reviewable design preserving all invariants and distinguishing
policy/workflow states from authority. Next, review this specification and complete
the implementation-design gate, including concrete policy tables/interface.
Implementation requires separate explicit authorisation; this document is not
permission to begin PR1 or PR2.

## Implementation result

Status: NOT STARTED
Commit: N/A
Completed: N/A

### Test evidence

Not yet implemented. The matrix and criteria specify future tests; this update
changes documentation only.

### Deviations from design

None recorded. The later three-state decision supersedes the earlier review's
HTTP rejection recommendation. Explicit `:80` remains rejected; otherwise eligible
HTTP with omitted port is REVIEW. Security rejection always takes precedence.

### Known issues

The implementation-design gate must approve concrete versioned range/namespace
tables and snapshots before coding. No runtime enforcement, DNS validation, review
persistence or network authority exists in PR1 yet.

### Reviewer decision

PENDING
