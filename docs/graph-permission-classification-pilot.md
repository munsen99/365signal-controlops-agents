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

## Independent Codex remaining 28

Migration `009-load-graph-permission-codex-remaining-28.sql` independently
classifies the 28 final selections not reviewed in Codex batch 1. It persists
submitted reviews under reviewer identifier `codex_remaining_28`, review round
`1`, without creating analyst reviews, disagreements or adjudications.

Validation `009-load-graph-permission-codex-remaining-28-validation.sql`
confirmed 28 reviews and 28 primary domain assignments, exact coverage of the
database-derived remainder, complete controlled attributes, unchanged analyst
and Codex batch-1 records, 36 unchanged final selections, an unchanged
catalogue count and fingerprint, unchanged workflow state, and a no-op second
migration run. Confidence is 25 `high`, 3 `medium` and 0 `low`. Three reviews
contain one or more `unknown` classification values.

Candidate schema-gap themes observed during this batch are delegated authority
inherited from mailbox or signed-in-user assignments, selected-resource rights
whose effective capability depends on a separate SharePoint grant, and RSC
media access whose directionality is not expressed by the capability
vocabulary. These are observations for later human review; no `schema_gap` rows
or schema changes were created.

## Analyst drafts for the remaining 28

Migration `010-create-analyst-drafts-remaining-28.sql` creates 28
machine-proposed analyst working drafts for reviewer `jon_bruce`, review round
`1`, with status `draft`. Their initial attributes, rationales and domain
assignments are copied unchanged from the submitted `codex_remaining_28`
reviews. This provides a starting point for deliberate human review; only the
human analyst may approve a draft and change its status to `submitted`.

Migration `010` is an initializer, not a synchronization process. It inserts
the complete set only when all 28 target analyst rows are absent, performs no
updates when all 28 exist, and fails on a partial target set. Rerunning it
therefore cannot revert analyst edits or status changes.

Validation `010-create-analyst-drafts-remaining-28-validation.sql` confirms 36
analyst reviews (8 submitted and 28 draft), exact initial equivalence with the
Codex source reviews and domains, protected review isolation, unchanged pilot
and catalogue state, unchanged workflow state, and a no-op second run.

### DBeaver analyst review queries

All 36 analyst reviews, with drafts first:

```sql
SELECT permission.permission_name,
       permission.permission_type,
       review.review_status,
       review.capability,
       review.access_level,
       review.privilege_level,
       review.data_sensitivity,
       review.destructive_potential,
       review.consent_sensitivity,
       review.classification_confidence,
       max(domain.domain_code) FILTER
           (WHERE assignment.assignment_kind = 'primary') AS primary_domain,
       coalesce(string_agg(domain.domain_code, ', ' ORDER BY domain.domain_code)
           FILTER (WHERE assignment.assignment_kind = 'secondary'), '')
           AS secondary_domains,
       review.rationale
FROM permission_pilot.classification_review review
JOIN permission_pilot.permission_selection selection USING (selection_id)
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
JOIN catalogue.permission_definition permission USING (permission_definition_id)
JOIN permission_pilot.review_domain_assignment assignment USING (review_id)
JOIN catalogue.controlops_domain domain USING (domain_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind = 'analyst'
  AND review.reviewer_identifier = 'jon_bruce'
  AND review.review_round = 1
GROUP BY permission.permission_name, permission.permission_type,
         review.review_id
ORDER BY CASE review.review_status WHEN 'draft' THEN 0 ELSE 1 END,
         permission.permission_type, permission.permission_name;
```

To show only the 28 drafts awaiting review, use the same query with this
additional predicate before `GROUP BY`:

```sql
  AND review.review_status = 'draft'
```
