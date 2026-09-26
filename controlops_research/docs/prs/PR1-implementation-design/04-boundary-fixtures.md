# 04 — Boundary and semantic acceptance fixtures

Decision D4: **PENDING**. These are review data, not implemented tests or passing
PR1 behaviour. No policy evaluator has been written or run.

| Artifact | Cases | Purpose |
| --- | --- | --- |
| [address-boundaries.csv](fixtures/address-boundaries.csv) | 351 | Before/first/last/after each deny and IPv6 eligibility prefix, plus envelope boundaries |
| [namespace-boundaries.json](fixtures/namespace-boundaries.json) | 64 | Exact namespace, child, appended public-looking suffix and near-match |
| [decision-examples.json](fixtures/decision-examples.json) | 81 | Independently specified full outputs, precedence, canonicalisation, state semantics |

Address fixtures use set arithmetic over the proposed ranges, not Python global/
private classification or an implementation URL evaluator. A neighbour outside
one range can still reject because it is in another exclusion or outside IPv6
eligibility. Duplicate addresses with different range contexts are intentional.
Namespace neighbours are also evaluated against the whole deny set: appending
`.com` to `example` produces the separately prohibited `example.com`, so that
case remains REJECT. A near-match is not automatically an ACCEPT.

There is no representable predecessor of IPv4 0 or successor of IPv4 maximum;
those two cases are omitted. The 351 rows include four explicit IPv6 envelope
points, all rejected by the narrower proposal.

These generated table-boundary vectors check data coverage but do not independently
prove that the policy choices are correct. Review D1's provenance and the manually
specified decision fixtures as well. Future tests must compare actual outputs to
these fixed expectations; they must not recompute expectations using production
constants or call the implementation to generate its own oracle.

## Required future tests beyond the data files

- Retain the complete parent-spec matrix, including data/javascript/mailto forms;
  fixture examples here supplement rather than replace it.
- Labels: 1 and 63 valid characters; 64 invalid. Full host: valid 253-character
  host `a*63.b*63.c*63.d*61`; reject `a*63.b*63.c*63.d*62` (254). These expressions
  describe literal test strings, not URL syntax. Use canonical alphabetic labels.
- IPv6: canonical compression, longest-zero-run choice and first-run ties;
  reject uppercase, extra leading zeros, dotted-mapped, scoped and IPvFuture forms.
- Inspect exact original/canonical strings, host kind and effective port; REVIEW
  output is diagnostic. Every REJECT must null destination/canonical metadata.
- Canonicalisation idempotence for ACCEPT and REVIEW; deterministic repeated
  evaluation; preserve empty-query marker, parameter order/duplicates and escape
  data. Do not claim `%252e` is server-side traversal protection.
- All 17 reason codes have exact stable explanations and valid state mapping.
  Multiple-failure precedence is independent of a parser's early port validation.
- Built-in str only: reject bytes, bool, list, str subclass and custom objects
  without calling their conversion, repr or user-defined methods.
- Forbidden side effects: fail tests on resolver/socket/network/process access,
  secrets/config reads, writes/logging, service inspection and clock/random use
  during evaluation. Load test modules before guards; test import separately.
- Preserve existing PR0 source-boundary/import tests and existing minimal profile/
  validator/Compose regressions. No relaxation for prohibited endpoint literals:
  keep blocked ports as integers in implementation and attack URLs in tests.
- Execute on Python 3.12, 3.13 and 3.14 at the future implementation gate. If a
  runtime is unavailable, report it untested rather than claiming parity. Future
  versions require explicit validation before claiming support.

No live DNS, sockets, HTTP, service clients or credentials in test fixtures.
The proposal's validation report covers artifact consistency only, not these
future implementation checks.
