# 03 — Policy identity, pinning and change control

Decision D3: **PENDING**.

| Item | Proposed value |
| --- | --- |
| Policy version reserved for the first approved contract | `controlops-public-url/v1.0.0` |
| Proposal revision | `draft-1` |
| Current approval state | PROPOSED_NOT_APPROVED |
| Activation | None: no PR1 implementation exists |
| Code/package version | Unchanged; distinct from URL-policy version |

The version identifies the entire rule/normalisation/reason/interface/data
contract, not just a deny list. In examples it is proposed, not an active runtime
version. `package-manifest.json` pins the parent specification and every package
artifact by SHA-256. It excludes itself to avoid a recursive hash. This is review
integrity evidence, not a cryptographic authorisation or an authenticated signature.

Before approval, edits increment the proposal revision and regenerate the manifest;
no earlier approval can be assumed to cover changed bytes. Upon approval, record
reviewer, decision, date and manifest digest in the review record. Do not rewrite
source snapshots. Implementation authorisation remains a separate user decision.

After activation, never reuse the same policy version for changed behaviour or
data. Propose v1.0.1 for a reviewed data-only tightening, v1.1.0 for new supported
capability requiring architecture review, and v2.0.0 for an incompatible interface
or decision contract. Semantic version numbers never substitute for review.
Documentation-only corrections that cannot alter interpretation may retain the
policy version but require a new package revision/hash.

No time-based expiry, automatic refresh, policy download or environment override
is introduced. New allocations remain rejected until a reviewed revision. A
future fetcher must re-evaluate with its active version and must not reuse old
ACCEPT as network authority. A caller cannot choose an older or weaker version.

Proposed implementation representation: immutable Python tuples/strings in
`policy_data.py`, compiled from the approved tables by a reviewed code change,
with no registry/XML/JSON loading during evaluation. No runtime external data
loader, new packaging dependency, or network client. Verify data shape/canonical
CIDRs/coverage and exact table equivalence in tests and perform pure local
consistency checks before evaluation. A valid built-in policy is the only policy;
invalid/unavailable policy returns POLICY_UNAVAILABLE with null policy_version.
A broken installation that cannot import must stop; it cannot promise a returned
result but must never permit a fallback connection. Test fault cases through
private test fixtures, not a public override API.
