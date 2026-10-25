# 05 — Verification and assurance record

Status: **VERIFIED; human disposition ACCEPT WITH FIXES**.

## Accepted review

The accepted assurance source is the [Sol review report](../reports/pr3-sol-review-2026-09-26.md),
not Luna's earlier implementation report. The human accepted Sol's three
recorded test/documentation fixes. The disposition is **ACCEPT WITH FIXES**;
the accepted commit is `56dd905 feat(research): implement PR3 citation evidence
plane`.

| Evidence | Accepted result |
| --- | --- |
| Python 3.13.14 full suite | 794 tests passed |
| Python 3.14.4 full suite | 794 tests passed |
| Architecture-boundary tests | PASS |
| `git diff --check` | PASS |
| Sol D1–D9 review | All HOLD; no remaining contract violation |
| Human disposition | ACCEPT WITH FIXES |

## Assurance cases

| Case | Test evidence |
| --- | --- |
| Exact visible-text span passes; altered quote fails | Exact span and quote mismatch tests |
| Unicode offsets use Python `str` positions | Unicode fixture includes `ControlOps £ café 🚀 assurance`; byte length before the offset differs from the Python offset |
| Snapshot A citation stays bound after B is stored | A/B binding test verifies the citation using A's reference after publishing B |
| Raw body tamper fails | Mutated raw object produces `SNAPSHOT_TAMPERED` |
| Derived visible-text tamper fails | Mutated `visible-text.txt` produces `EXTRACTION_MISMATCH` |
| Persisted excerpt digest tamper fails | Changed citation digest produces `EXCERPT_HASH_MISMATCH` |
| Source identity conflict is detected | Same source key with a different locator raises `SOURCE_CONFLICT` without replacing the original |
| Catalogue survives a process boundary | Separate process reloads the catalogue and verifies the citation |
| SQL remains future-only | SQL test parses the schema/table names; runtime code has no SQL execution path |
| PR3 tests use no network | Fixture construction uses `SnapshotStore.publish` and local files; tests do not call fetch |

The suite also checks missing retrievals, empty spans, HTML extraction against
the PR2 `page-visible.txt` fixture, forbidden schema names, symlink roots,
closed verdict truth behavior, source/snapshot persistence, and that a
catalogue-only `pass` claim cannot verify when the PR2 retrieval is missing.

## Accepted Sol fixes

1. The HTML test was tied to the existing `page-visible.txt` oracle. It removes
   exactly the fixture's terminal newline before comparing with the extractor
   result.
2. The PR3 AST test explicitly rejects PostgreSQL/database, LanceDB, Hermes,
   validator, and model-client imports.
3. PR3 documentation was restored to the implementation-result edit scope and
   the exact pending-human-review status before the human acceptance update.

The review confirms that the implementation, test fixtures, and SQL match the
approved PR3 file boundary. Runtime hashes were unchanged by review fixes.

## State

- **IMPLEMENTED:** PR3 files in accepted commit `56dd905`.
- **VERIFIED:** both supported interpreter suites, architecture checks, hash
  review, and accepted Sol assurance findings shown above.
- **FUTURE / NOT IMPLEMENTED:** runtime PostgreSQL, trusted RAG writes, model
  use, publication workflow, and PR4+ capabilities.
