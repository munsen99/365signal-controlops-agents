# Codex Prompt — Create Analyst Draft Reviews for Remaining 28 Graph Permissions

Work from the ControlOps repository root:
`/mnt/Storage/AI/Hermes/workspace`.

## Objective and state

Populate the remaining 28 Microsoft Graph pilot permissions as machine-proposed
analyst working reviews for human review in DBeaver:

```text
reviewer_kind = analyst
reviewer_identifier = jon_bruce
review_round = 1
review_status = draft
```

They are not human-approved. Only the human analyst may later change them from
`draft` to `submitted`. Preserve the existing eight submitted analyst reviews.

Pilot code: `MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36`.

Existing review sets are eight submitted `analyst / jon_bruce / round 1`, eight
submitted `codex / codex_independent_batch_1 / round 1`, and 28 submitted
`codex / codex_remaining_28 / round 1`.

Inspect migrations and validations `005` through `009`, the pilot documentation,
the permission catalogue and taxonomy tables, and the pilot, selection, review,
domain-assignment, disagreement, and domain-review structures.

## Target derivation and source

Derive the target from PostgreSQL as all final selections in the pilot minus
existing `analyst / jon_bruce / round 1` reviews. Assert the initial relationship:

```text
36 final selections - 8 existing analyst reviews = 28 missing reviews
```

Abort if the initializer target is not exactly 28. Do not manually reconstruct
the list.

Use the persisted submitted `codex_remaining_28` review for each matching
permission as the proposed analyst draft source. Copy without semantic changes:

- capability;
- access level;
- administrative capability;
- privilege level;
- data sensitivity;
- destructive potential;
- tenant-wide impact;
- consent sensitivity;
- classification confidence;
- rationale;
- the primary domain and all secondary domains.

Preserve machine provenance in migration and documentation. Prefer leaving the
rationale unchanged so comparison data is not polluted.

## Controlled values

Verify database constraints before persistence. Use only:

```text
reviewer_kind: analyst, codex
review_status: draft, submitted, superseded
classification_confidence: low, medium, high
capability: read, write, read_write, execute, manage, consent, unknown
access_level: none, limited, owned, selected, all, unknown
privilege_level: low, moderate, high, critical, unknown
data_sensitivity: none, low, moderate, high, restricted, unknown
destructive_potential: none, low, moderate, high, critical, unknown
consent_sensitivity: low, moderate, high, critical, unknown
assignment_kind: primary, secondary
```

## Persistence and safety

Create
`platform/postgres/init/010-create-analyst-drafts-remaining-28.sql`.
Persist exactly 28 analyst draft reviews and matching domain assignments.

The migration must be transactional and idempotent and act as a one-time draft
initializer, not a synchronization job. Create a draft only if no analyst review
exists for that selection, reviewer, and round. Never overwrite or revert an
existing analyst review, manual edit, domain edit, or status change. If an
unexpected or partial analyst target set exists, report/fail rather than replace
it. A rerun after human review must leave human work untouched.

Preserve byte-for-byte logically the eight submitted analyst decisions for:

- `User.Read` — Delegated
- `Directory.AccessAsUser.All` — Delegated
- `AuditLog.Read.All` — Delegated
- `AppRoleAssignment.ReadWrite.All` — Application
- `DeviceLocalCredential.Read.All` — Application
- `Sites.Selected` — Application
- `Teamwork.Migrate.All` — Application
- `Chat.Manage.Chat` — RSC

Preserve both Codex review sets, including IDs, timestamps, rationales,
attributes, status, and domains. Do not create or modify disagreements or
domain-review adjudications.

## Validation

Create
`platform/postgres/validation/010-create-analyst-drafts-remaining-28-validation.sql`.
After migration validate 36 analyst reviews: eight submitted and 28 draft. The
28 drafts must exactly correspond to `codex_remaining_28`, not batch 1. Each
must have complete controlled attributes, rationale, exactly one primary domain,
and an initial domain set exactly matching Codex.

Confirm unchanged: the submitted analyst batch 1, both Codex sets, 36 final
selections, catalogue count and fingerprint. Confirm zero disagreements and
zero domain-review adjudications.

Run migration 010 a second time and demonstrate:

```text
analyst review inserts = 0
analyst review updates = 0
domain inserts = 0
domain updates = 0
```

## Human review support

Provide read-only DBeaver SQL showing all 36 analyst reviews with permission
name/type, status, all controlled fields, primary and secondary domains, and
rationale. Order drafts first, then permission type and name. Also provide a
draft-only query for the 28 awaiting review. Do not automate approval.

## Documentation and prompt records

Update `docs/graph-permission-classification-pilot.md` with migration 010, the
28 machine-proposed drafts, reviewer `jon_bruce`, round 1, draft status, Codex
copy provenance, human-only submission, and non-overwrite behavior.

Create these non-empty operational prompt records:

- `docs/prompts/codex-graph-permission-classify-remaining-28.md`, containing the
  full migration-009 classification instructions with the title
  `# Codex Prompt — Classify Remaining 28 Microsoft Graph Permissions`;
- `docs/prompts/codex-graph-permission-create-analyst-drafts-remaining-28.md`,
  containing this migration-010 prompt with the title
  `# Codex Prompt — Create Analyst Draft Reviews for Remaining 28 Graph Permissions`.

The first must retain target derivation, classification principles,
vocabularies, domain and inherited-authority rules, persistence and validation,
confidence/unknown and schema-gap reporting, workflow isolation, and no
commit/push. Do not overwrite unrelated documentation.

## Git and final report

Do not stage, commit, or push. Run `git diff --check` and `git status --short`.
Show a relevant diff stat limited to migration 010, validation 010, pilot docs,
and both prompt records.

Report target derivation, initial analyst state, inserts and domain counts,
final 36/8/28 state, preservation evidence, second-run zero counts, prompt
records, changed files, git checks, and analyst concerns before DBeaver review.

The task is complete when all 36 permissions have analyst rows, the first eight
remain submitted, the remaining 28 are drafts initially matching Codex,
rerunning cannot overwrite analyst work, workflow tables remain empty, both
prompts are preserved, and drafts are ready for deliberate manual review.
