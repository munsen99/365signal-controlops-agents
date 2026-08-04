# Controlled Microsoft Graph permission classification pilot

## Safety and lifecycle

Migration `005` creates only `permission_pilot` objects. It references
the catalogue and approved taxonomy by foreign key, but neither changes the
taxonomy nor inserts into `catalogue.permission_classification` or
`catalogue.permission_classification_domain`. Review
`platform/postgres/init/005-graph-permission-classification-pilot.sql` before
any deployment.

The sample preview and candidate query both start a `READ ONLY` transaction
and roll it back. The approved sample contains 36 catalogue records: 16
Delegated, 14 Application and 6 RSC. Migration `006` is the separate,
persistent loader for that approved sample.

## Candidate generation

`platform/postgres/pilot/graph-permission-candidate-selection.sql` labels only
current catalogue rows using permission name and existing `access_class`.
It recognizes eight requested workload families, derives sampling-only
capability, scope and risk labels, ranks within permission-type/workload/
capability strata using a stable UUID hash, and caps the output at 96 rows.
These labels are not classifications and are not persisted.

## Sample preview and definition

`platform/postgres/pilot/graph-permission-final-sample.sql` is the reviewable,
non-persistent definition of the exact approved set. It validates the exact
permission IDs, types and names by joining them to the catalogue and then
rolls back. It does not create a pilot or load selections.

The final set was judgementally
stratified from exact live records. It emphasizes paired contrasts: delegated
versus application, read versus mutation, tenant-wide versus selected/RSC,
apparently low-risk versus clearly critical, and permissions whose name,
description and `access_class` disagree or leave room for interpretation.

## Persistent pilot loader

`platform/postgres/init/006-load-graph-permission-final-sample.sql` creates or
refreshes the stable pilot code
`MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36` and upserts its 36 `final`
selections. It checks every proposed ID/type/name triple before persisting and
uses the same deterministic catalogue count and fingerprint expression as the
`004` taxonomy validation.

The loader is transactional and idempotent. Matching pilot and selection rows
retain their IDs and timestamps; changed reasons or sampling dimensions are
refreshed, while an existing pilot's lifecycle status is preserved. It neither
deletes selections nor touches review tables. An extra
or missing final selection for this pilot causes the transaction to fail
instead of deleting potentially reviewed data. Other pilots are outside its
scope.

## Review workflow

After migrations `005` and `006` are applied, two reviewers independently populate
`classification_review` and `review_domain_assignment`. Use:

- `permission_pilot.analyst_review_export` for the analyst worksheet;
- `permission_pilot.codex_review_export` for a separately completed Codex pass;
- `permission_pilot.review_comparison` for field-level comparison;
- `permission_pilot.disagreement_resolution_export` for adjudication.

The views deliberately provide identical blank input columns to each reviewer.
Submitted reviews are compared field by field. Domain disagreements can be
recorded and adjudicated in `domain_review`; limitations go to `schema_gap`;
repeated patterns may be proposed, but not activated, in
`candidate_classification_rule`.

## Analyst batch 1

Migration `007-load-graph-permission-analyst-batch-1.sql` persists the first
human-approved analyst batch for reviewer `jon_bruce`, review round `1`. All
eight reviews are stored as `reviewer_kind = 'analyst'` and
`review_status = 'submitted'`; no Codex reviews or disagreements are created.

| Permission | Type | Primary domain | Secondary domains |
| --- | --- | --- | --- |
| `User.Read` | Delegated | `DIRECTORY_ORG_MANAGEMENT` | None |
| `Directory.AccessAsUser.All` | Delegated | `AUTHORIZATION_ACCESS_GOVERNANCE` | `PRIVILEGED_ACCESS` |
| `AuditLog.Read.All` | Delegated | `LOGGING_MONITORING_AUDIT` | `AUDIT_ASSURANCE` |
| `AppRoleAssignment.ReadWrite.All` | Application | `APPLICATION_IDENTITY_CONSENT` | `AUTHORIZATION_ACCESS_GOVERNANCE`, `PRIVILEGED_ACCESS` |
| `DeviceLocalCredential.Read.All` | Application | `ENDPOINT_DEVICE_MANAGEMENT` | `AUTHENTICATION`, `PRIVILEGED_ACCESS` |
| `Sites.Selected` | Application | `SHAREPOINT_ONEDRIVE` | `APPLICATION_IDENTITY_CONSENT` |
| `Teamwork.Migrate.All` | Application | `MICROSOFT_TEAMS` | `APPLICATION_IDENTITY_CONSENT`, `AUDIT_ASSURANCE` |
| `Chat.Manage.Chat` | RSC | `MICROSOFT_TEAMS` | `AUTHORIZATION_ACCESS_GOVERNANCE`, `APPLICATION_IDENTITY_CONSENT` |

The schema stores controlled vocabulary in lowercase. Human confidence `High`
is stored as `high`, and `Medium` as `medium`. The human `Medium-high` decision
for `Directory.AccessAsUser.All` has no exact schema value and is stored as
`high`, the closest upper-band value; its original wording remains documented
here. The approved decisions did not explicitly assign access level,
capability, administrative capability, privilege level, data sensitivity,
destructive potential, tenant-wide impact or consent sensitivity. Those
nullable columns remain null rather than converting contextual wording in the
rationales into additional analyst decisions.

## Limitations and non-inferable criteria

- Delegated catalogue rows currently have null Microsoft `display_name` values.
  The exact nulls are exported; descriptions remain available.
- The catalogue contains only current rows (1,562 at inspection), so the sample
  cannot include a retired record even though status is exported.
- `access_class` has no explicit `Write` or `FullControl` values. Those sampling
  dimensions can be inferred from exact names/descriptions, while affected rows
  may retain `Unknown` in the source column.
- Effective scope for `Selected`, `OwnedBy`, `WhereInstalled`, delegated and RSC
  permissions depends on grants, assignments, signed-in-user privilege and/or
  resource installation. The catalogue alone cannot prove effective reach.
- Admin-consent requirement is catalogue metadata, not a risk rating. All
  Application sample rows require it; RSC sample rows do not.
- “Obvious low”, “obvious critical”, ambiguity and multi-domain potential are
  sampling judgements, not completed classifications. Independent review must
  determine the actual classification and taxonomy mappings.
- No authoritative workload column exists. Workload labels are conservative
  name-based sampling aids; cross-service permissions need human adjudication.

## Validation

`platform/postgres/validation/005-graph-permission-classification-pilot-validation.sql`
is the read-only schema/sample-preview validation.

`platform/postgres/validation/006-load-graph-permission-final-sample-validation.sql`
is the persistent-loader validation. Run it with `psql` from its repository
location so its relative include resolves. It invokes migration `006` twice and
proves pilot existence, exact count, catalogue membership, uniqueness, the
14/16/6 permission-type distribution, eight workloads, seven capability
dimensions, both scope dimensions, all three risk dimensions, multi-domain
coverage, rerun idempotency, preservation of existing reviews, and an unchanged
permission catalogue fingerprint.

`platform/postgres/validation/007-load-graph-permission-analyst-batch-1-validation.sql`
invokes migration `007` twice and checks the exact eight reviews and nineteen
domain assignments, one primary domain per review, the exact approved
secondary-domain sets, rerun idempotency, no reviews on the remaining 28
permissions, unchanged Codex and other-analyst reviews, no disagreements, and
unchanged catalogue and selection data.

## Independent Codex batch 1

An independent Codex review of the same eight batch-1 permissions was
performed under reviewer identifier `codex_independent_batch_1`, review round
`1`. Migration `008-load-graph-permission-codex-batch-1.sql` persists the
submitted reviews, and
`008-load-graph-permission-codex-batch-1-validation.sql` validates the batch.

Local validation confirmed eight Codex reviews, eight primary and four
secondary domain assignments, no null controlled attributes, idempotent reruns,
unchanged analyst records, unchanged catalogue and selection data, and no
created disagreements. Analyst and Codex decisions remain intentionally
uncompared pending the separate comparison stage.
