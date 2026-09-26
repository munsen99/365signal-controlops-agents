# PR3 Sol review — 2026-09-26

```text
PR3 SOL REVIEW: PASS
Reviewer: Sol
Tree: Luna working tree
Contract: PR3-codex-implementation-prompt.md (D1–D9)

Interpreters run: Python 3.13.14; Python 3.14.4
pytest lines (exact): 3.13: ".. [100%]"; 3.14: ".. [100%]"
Total tests 3.13: 794
Total tests 3.14: 794
Named tests missing on an interpreter: NONE
New PR3 tests counted: 24

Files in PR3 boundary: README.md; docs/prs/README.md; docs/prs/PR3-evidence-plane.md; docs/prs/reports/pr3-implementation-2026-09-26.md; docs/prs/reports/pr3-sol-review-2026-09-26.md (review-authorized evidence); src/controlops_research/evidence.py; src/controlops_research/verify.py; src/controlops_research/research_schema.sql; tests/test_evidence_plane.py; tests/fixtures/evidence/manifest.json; tests/test_architecture_boundaries.py
Files outside boundary: NONE

SHA-256:
evidence.py: 1aad40f4d92cd3174e9c9dcf9d971b968f6c297648c0f2f11d4c3624234b9d09
verify.py: b01f8c567e0e5b2f1ef57c6b6b5c1468a6d34059926ebeaff7993091487b6e2a
research_schema.sql: ee6f76e08238a0cd6498953227ac624a636f29a8c7baabe5babd2fd63e4f10dd
test_evidence_plane.py: a781de1c590cae08eea9b24f2f7a2f2880b65b6b82006e94d95c173765548264

D1 Authority: HOLD — src/controlops_research/verify.py:60-159, 167-200, 217-261
D2 Schema: HOLD — src/controlops_research/research_schema.sql:1-38
D3 Snapshot authority: HOLD — src/controlops_research/evidence.py:67-103; src/controlops_research/verify.py:60-130
D4 Span semantics: HOLD — src/controlops_research/verify.py:133-149
D5 Verifier: HOLD — src/controlops_research/verify.py:60-159, 203-261
D6 Isolation: HOLD — tests/test_architecture_boundaries.py:76-105
D7 Tests: HOLD — tests/test_evidence_plane.py; tests/test_architecture_boundaries.py:76-105
D8 File boundary: HOLD — git status/diff audit; prohibited files have no diff
D9 Persistence: HOLD — src/controlops_research/evidence.py:133-213; process reload test passed

PR2 SnapshotStore remained authoritative: YES
Source bytes duplicated into PR3 persistence: NO
Verifier reconstructed ContentContract from metadata: YES
Verifier called parse_content_contract: NO
Verifier rehashed body.bin: YES
Verifier re-extracted visible text: YES
verify_span requires SnapshotRef: NO
bool(CitationVerdict) raises TypeError: YES
Unicode span test passed: YES
Snapshot A/B binding test passed: YES
Raw tamper → SNAPSHOT_TAMPERED: YES
Extraction tamper → EXTRACTION_MISMATCH: YES
Excerpt hash tamper → EXCERPT_HASH_MISMATCH: YES
Source conflict test passed: YES
JSON catalogue reload test passed: YES
SQL executed at runtime: NO
Network used by PR3 tests: NO

Architecture boundary tests: PASS
git diff --check: PASS

Code changes made by Sol: tests/test_evidence_plane.py HTML oracle fix; tests/test_architecture_boundaries.py forbidden-dependency coverage; README.md brief correction; docs/prs/README.md exact status correction; docs/prs/PR3-evidence-plane.md scope restoration and evidence result
Unrelated files touched? NO
Commit performed? NO
Push performed? NO
PR4 begun? NO

Deviations:
FIX APPLIED: Bound the HTML span test to page-visible.txt, removing exactly its terminal fixture newline, because mandatory case 16 previously used only the new manifest as its oracle.
FIX APPLIED: Extended the PR3 AST test to reject database, LanceDB, Hermes, validator and model-client imports because mandatory case 10 lacked explicit coverage.
FIX APPLIED: Restored PR3 documentation to the §10 edit boundary and exact pending-human-review status.
Known issues: Luna's earlier implementation report remains a non-acceptance claim and records its environment-limited Python 3.14 run; this review supersedes that test evidence.
Blockers: NONE
Reviewer recommendation: ACCEPT WITH FIXES
```

Findings after repair:

- No runtime contract violation remains. PR2 `SnapshotStore` owns captured bytes; PR3 persists only provenance records and verifies against rehashed, re-extracted PR2 data.
- The three review fixes are confined to tests and documentation. No runtime module, PR0–PR2 implementation, dependency declaration, invariant, or out-of-scope component was changed.
- Locked identity payloads use `sha256(canonical_json(payload))` exactly for source, snapshot-reference and citation IDs. No identity deviation was found.
