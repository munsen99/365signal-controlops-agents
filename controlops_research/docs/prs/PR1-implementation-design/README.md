# PR1 implementation-design approval package

Status: **PROPOSED — PENDING REVIEW**. Revision: `draft-1`.
Prepared: 2026-09-25. PR1 implementation: **NOT STARTED**.

This package supplies the five items requested for review. It does not approve
its own decisions, implement policy, or authorise PR1/PR2 execution. The parent
[PR1 specification](../PR1-public-url-policy.md) and
[architecture invariants](../../architecture-invariants.md) remain authoritative.
Where this package proposes a refinement, it is explicitly marked for review;
it does not silently supersede the parent specification.

| Decision | Item | Proposed choice | Reviewer decision |
| --- | --- | --- | --- |
| D1 | [Concrete address/namespace tables](01-policy-tables.md) | Pin exclusions; deny overrides; narrower allocated IPv6 eligibility | PENDING |
| D2 | [Source snapshots](02-source-snapshots.md) | Six original IANA XML files, exact hashes and provenance | PENDING |
| D3 | [Policy version](03-policy-version.md) | Reserve controlops-public-url/v1.0.0; immutable reviewed changes | PENDING |
| D4 | [Boundary fixtures](04-boundary-fixtures.md) | Fixed address/name/decision expectations and future test requirements | PENDING |
| D5 | [Decision/data interface](05-decision-interface.md) | Pure evaluate_url, immutable three-state result, stable codes | PENDING |

## Decisions needing particular attention

- **D1a: IPv6 allocation restriction.** `2000::/3` includes reserved space. Permit
  only pinned ALLOCATED prefixes minus all exclusions. Newly allocated prefixes
  require a policy revision; no automatic refresh.
- **D1: conservative exclusions.** All special-purpose ranges reject, even when
  marked globally reachable. ASCII-only hostnames, IDN exclusion and blocked
  special-use domains remain intentional. Empty extra internal-FQDN inventory
  is disclosed; it is not proof that unknown internal names cannot pass syntax.
- **D5a: HTTP port distinction.** Eligible HTTP with omitted port REVIEW;
  explicit 80 REJECT; explicit 443 REVIEW. No upgrade, fetch or override.
- **D5b: interface purity.** Only exact built-in strings, no policy overrides;
  immutable outputs and bool(result) raises rather than treating REJECT as truthy.
- **D4: runtime validation target.** Proposed Python 3.12–3.14 test matrix;
  unavailable versions must be reported, not silently assumed equivalent.

## Review form

Copy this form into your response or annotate it in a later authorised edit:

```text
D1: APPROVE / REJECT / REQUEST CHANGES — comments:
D1a (IPv6 allocation restriction): APPROVE / REJECT — comments:
D2: APPROVE / REJECT / REQUEST CHANGES — comments:
D3: APPROVE / REJECT / REQUEST CHANGES — comments:
D4: APPROVE / REJECT / REQUEST CHANGES — comments:
D5: APPROVE / REJECT / REQUEST CHANGES — comments:
D5a (HTTP ports): CONFIRM / REQUEST CHANGES — comments:
D5b (exact str and immutable interface): APPROVE / REJECT — comments:
Reviewer / date:
Package manifest SHA-256:
Implementation authorisation: NOT GIVEN
```

Approval of a subset does not approve the rest. Rejection of a detail requires a
revised proposal, not a fallback chosen during implementation. Even full design
approval does not override the explicit instruction not to build PR1; implementation
requires a separate explicit instruction.

## Verification and artifacts

[validation.md](validation.md) distinguishes package consistency checks from
unimplemented runtime tests. [package-manifest.json](package-manifest.json) pins
all artifacts plus the unchanged parent spec/invariants. Source byte hashes are
also in [snapshots/manifest.json](snapshots/manifest.json).

All files here are documentation, reference data or proposed fixtures. There is
no executable application/test code in this package, no candidate fetch, no DNS
policy implementation, no database/model/service configuration and no commit.
