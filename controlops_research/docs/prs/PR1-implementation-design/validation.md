# Package validation record

Date: 2026-09-25. Scope: design artifacts only. PR1 is NOT STARTED.

| Check | Result |
| --- | --- |
| Six stored source snapshots: SHA-256, byte lengths, registry dates and record counts | PASS |
| Complete special-purpose CIDRs copied into proposed exclusions | PASS: 26 IPv4 CIDRs plus multicast; 25 IPv6 CIDRs |
| IPv6 eligibility matches pinned ALLOCATED rows and lies within 2000::/3 | PASS: 36 prefixes; exclusions still win |
| Full special-use namespace provenance and effective coverage | PASS: 42 source rows, six local additions, 16 effective suffixes |
| Address boundary fixtures checked with integer-interval arithmetic | PASS: 351 rows |
| Namespace fixtures checked against the entire suffix set | PASS: 64 rows |
| Fixed decision fixture shape/state/nullability and exact message mapping | PASS: 81 examples, all 17 reason codes |
| Documentation local links and generated-artifact whitespace | PASS |
| Existing tracked/untracked file hashes and staged-index diff unchanged | PASS |
| Application/test/config implementation files introduced | NONE |

The 496 fixtures are proposed expected results, not observed results from a PR1
implementation. No evaluator exists and no PR1 test suite was run. Existing runtime
regressions were not rerun because this package only adds design documentation and
reference data. Range/name checks validate arithmetic and transcription, not live
reachability, DNS or routing. Decision fixtures were checked for contract consistency,
not executed against hypothetical implementation behaviour.

Artifact check command used: `python3 /tmp/validate_pr1_design_package.py`.
It checks hashes, XML-derived table coverage, interval membership, fixture shapes,
reason mappings, links, original-file/index preservation and absence of executable
files. The helper is temporary review tooling outside the repository, not PR1 code.
A namespace near-match fixture was corrected during preparation: `example.com`
is itself excluded even when constructed as `example` plus `.com`.

`git diff --check` passes for existing working-tree changes. Additional explicit
new-file checks pass for authored Markdown/JSON/CSV. Five original IANA XML files
contain upstream trailing whitespace; those raw source bytes are intentionally
preserved for exact hashing, not silently reformatted. Their whitespace warnings
are provenance exceptions, not generated-source formatting errors.

A final package manifest pins every artifact (excluding itself) and the unchanged
parent specification/invariants. Hashes are integrity checks, not approval.
No files staged, no commit created, no PR1/PR2 implementation begun by this task.
