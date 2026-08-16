# Codex Prompt — Classify Remaining 28 Microsoft Graph Permissions

Work in the ControlOps repository at `/mnt/Storage/AI/Hermes/workspace`.

## Objective

Independently classify and persist the remaining 28 permissions in the approved
36-permission Microsoft Graph pilot sample. The first eight permissions have
already been reviewed by `analyst / jon_bruce / round 1` and
`codex / codex_independent_batch_1 / round 1`. Do not reclassify, modify, or
create new rounds for those eight:

- `User.Read` — Delegated
- `Directory.AccessAsUser.All` — Delegated
- `AuditLog.Read.All` — Delegated
- `AppRoleAssignment.ReadWrite.All` — Application
- `DeviceLocalCredential.Read.All` — Application
- `Sites.Selected` — Application
- `Teamwork.Migrate.All` — Application
- `Chat.Manage.Chat` — RSC

Use pilot code `MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36` and inspect existing
migrations and validations `005` through `008` plus
`docs/graph-permission-classification-pilot.md`.

## Target derivation

Do not hard-code a reconstructed target list. Query PostgreSQL for all final
selections in the pilot minus the eight selections already classified by
`codex_independent_batch_1`. Assert that exactly 28 remain and abort otherwise.

## Independent source rules

Use only `permission_name`, `permission_type`, `display_name`, `description`,
`admin_consent_required`, `is_current`, the existing ControlOps pillar and
domain definitions, and schema-controlled vocabularies. Do not use selection
reasons, sampling dimensions, candidate risk labels, analyst reviews,
disagreement/adjudication data, or classifications inferred elsewhere.

Classify the resource and authority actually granted, not merely the workflow
where a permission is commonly used. Avoid secondary-domain over-tagging: add a
secondary domain only for a meaningful additional control relationship.

Distinguish execution models. Application permissions operate unattended and
may have tenant-wide reach, persistence, application-compromise implications,
and elevated consent sensitivity. Delegated permissions act for a signed-in
user and can inherit or depend on that user's privileges; they are not
automatically low risk. RSC permissions are limited to assigned resources but
can still grant powerful management or data authority within those resources.

Every permission must have exactly one primary domain and zero or more
secondary domains, using only codes in `catalogue.controlops_domain`. The
primary domain represents the dominant control capability. Established mapping
principles include:

- application permission management: `APPLICATION_IDENTITY_CONSENT`, with
  `AUTHORIZATION_ACCESS_GOVERNANCE` when authority is changed;
- credential disclosure: the endpoint or identity resource domain, with
  `AUTHENTICATION` when authentication secrets are exposed;
- `PRIVILEGED_ACCESS` only where elevated authority is genuinely material;
- audit data: `LOGGING_MONITORING_AUDIT` operationally, with
  `AUDIT_ASSURANCE` only for a material assurance/evidence relationship.

Where authority depends on signed-in-user privilege, downstream grants,
external role assignment, or configuration state, use the closest defensible
controlled value. If no value is defensible, use `unknown` and explain the
dependency. Do not change the schema. Report repeated limitations as candidate
schema gaps only.

## Controlled classifications

Verify these values directly from database constraints before implementation:

```text
capability: read, write, read_write, execute, manage, consent, unknown
access_level: none, limited, owned, selected, all, unknown
privilege_level: low, moderate, high, critical, unknown
data_sensitivity: none, low, moderate, high, restricted, unknown
destructive_potential: none, low, moderate, high, critical, unknown
consent_sensitivity: low, moderate, high, critical, unknown
classification_confidence: low, medium, high
```

Populate every field plus `rationale`. Interpret the description and effective
authority rather than parsing the permission name. Reading credentials,
authentication material, mail, chat, files, security telemetry, audit history,
device configuration, or personal data may be highly sensitive.

Classify direct destructive authority separately from downstream misuse. A
credential read can have `destructive_potential = none` even when disclosure
could enable later destructive activity. Use `restricted` data sensitivity only
for clearly strongest-category information. Use `critical` privilege sparingly
for broad privileged administration, creation of privileged access, credential
compromise, arbitrary-user operation, disabling/bypassing controls, or
tenant-wide destructive administration.

## Persistence

Create
`platform/postgres/init/009-load-graph-permission-codex-remaining-28.sql` using:

```text
reviewer_kind = codex
reviewer_identifier = codex_remaining_28
review_round = 1
review_status = submitted
```

Persist `classification_review` and `review_domain_assignment` only. Do not
create disagreements, domain reviews, analyst reviews, or schema changes.

The migration must be transactional, idempotent, scoped to the database-derived
28, and safe to rerun. Resolve the pilot by stable code and each permission by
selection/pilot, definition ID, name, and type. Validate all domain codes before
writes. Preserve review IDs and `created_at`; change `updated_at` only when
values genuinely differ. Never delete unrelated assignments, and fail rather
than overwrite unexpected conflicting assignments. Leave the original eight,
all analyst reviews, sample selections, and catalogue data untouched.

## Validation and reporting

Create
`platform/postgres/validation/009-load-graph-permission-codex-remaining-28-validation.sql`.
Validate exactly 28 reviews and exact target coverage; no batch-1 overlap;
complete controlled attributes; exactly one primary domain per review; no
duplicate or unexpected domains; unchanged analyst and Codex batch-1 reviews,
IDs, timestamps, rationales, attributes, and domains; 36 unchanged final
selections; unchanged catalogue count and fingerprint; and no disagreements or
domain-review adjudications.

Execute migration 009 twice. The second run must produce zero review inserts,
review updates, domain inserts, and domain updates.

Generate read-only summaries by permission type, confidence, privilege,
unknown-bearing permissions, multi-domain classifications, and all non-high
confidence classifications. Report candidate schema-gap themes without schema
changes or `schema_gap` rows.

Update `docs/graph-permission-classification-pilot.md` only with the completed
Codex batch, migration, reviewer/round, validation outcome, confidence counts,
unknown count, and candidate gap themes. Do not add analyst adjudication.

Run `git diff --check` and `git status --short`, show relevant changes separately
from unrelated work, and do not stage, commit, or push.

The task is complete only when exactly 28 remaining permissions have independent
Codex reviews, every new review has exactly one primary domain and complete
controlled fields, ambiguity is represented honestly, reruns are idempotent,
the first eight and analyst data are untouched, and no disagreement or
adjudication processing has occurred.
