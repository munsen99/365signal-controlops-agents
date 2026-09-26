# PR1 final human acceptance — 2026-09-26

PR1 — Public URL Policy `controlops-public-url/v1.0.0`: **ACCEPTED**.
The approved implementation, fixture amendment and runtime acceptance amendment
constitute the final PR1 record.

Authority: [human reviewer instruction](../Approved.txt).
Instruction SHA-256: `3533646f7fa090113cff90f9a8368718b18dd3528d9dc3aac24d1a90ceef08be`.

## Accepted record

- [Canonical PR1 specification and implementation evidence](../PR1-public-url-policy.md).
- [Detailed design](../PR1-implementation-design/README.md) and
  [design approval](pr1-design-2026-09-25.md).
- [Approved fixture amendment](pr1-fixture-amendment-2026-09-25/README.md).
- [Approved runtime acceptance amendment](pr1-runtime-acceptance-2026-09-26.md).
- [Implementation report](../reports/pr1-implementation-2026-09-26.md), including
  reviewed source/fixture hashes and successful Python 3.13/3.14 results.

Amended design manifest SHA-256:
`90e3b506ae26fc936b6822161d693b7f0c7507abff4b3c91b286a4e47d605278`.
The six implementation/test/fixture hashes in the report and all approved manifest
artifacts/inputs were verified before staging. No policy behaviour, policy data,
fixtures or tests changed during commit preparation.

## Commit authorisation and conditions

Stage only required ControlOps Research PR0/PR1 files and approved audit evidence.
The PR2–PR10 specification placeholders are part of the original PR0 scaffold;
including those documents does not begin their implementation.

Before committing, show the exact staged list, verify scope, run
`git diff --cached --check`, and run the Python 3.14 Research suite once against
the final staged working state. Commit only if all checks pass. Stop without
committing if any unexpected file or difference appears.

This record supersedes earlier pending-review/no-commit statements as a subsequent
human decision. Prior records remain historical evidence. No unrelated workspace
changes, PR2 work or push is authorised. Git history will identify the resulting
commit; this acceptance record does not claim that a commit already exists.
