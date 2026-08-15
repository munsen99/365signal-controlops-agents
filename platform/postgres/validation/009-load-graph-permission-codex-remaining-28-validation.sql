\set ON_ERROR_STOP on

CREATE TEMPORARY TABLE protected_review_before AS
SELECT review.*
FROM permission_pilot.classification_review review
WHERE (review.reviewer_kind, review.reviewer_identifier, review.review_round) IN
      (('analyst','jon_bruce',1), ('codex','codex_independent_batch_1',1));

CREATE TEMPORARY TABLE protected_domain_before AS
SELECT assignment.*
FROM permission_pilot.review_domain_assignment assignment
JOIN protected_review_before review USING (review_id);

CREATE TEMPORARY TABLE selection_before AS
SELECT selection.* FROM permission_pilot.permission_selection selection
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36';

CREATE TEMPORARY TABLE catalogue_before AS
SELECT count(*) row_count,
       md5(string_agg(to_jsonb(permission)::text, E'\n' ORDER BY permission.permission_definition_id)) fingerprint
FROM catalogue.permission_definition permission;

CREATE TEMPORARY TABLE workflow_before AS
SELECT (SELECT count(*) FROM permission_pilot.disagreement) disagreement_count,
       (SELECT md5(coalesce(string_agg(to_jsonb(disagreement)::text,E'\n' ORDER BY disagreement_id),'')) FROM permission_pilot.disagreement) disagreement_fingerprint,
       (SELECT count(*) FROM permission_pilot.domain_review) domain_review_count,
       (SELECT md5(coalesce(string_agg(to_jsonb(domain_review)::text,E'\n' ORDER BY domain_review_id),'')) FROM permission_pilot.domain_review) domain_review_fingerprint;

\ir ../init/009-load-graph-permission-codex-remaining-28.sql

CREATE TEMPORARY TABLE review_after_first AS
SELECT review.* FROM permission_pilot.classification_review review
JOIN permission_pilot.permission_selection selection USING(selection_id)
JOIN permission_pilot.pilot_definition pilot USING(pilot_id)
WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind='codex' AND review.reviewer_identifier='codex_remaining_28' AND review.review_round=1;

CREATE TEMPORARY TABLE domain_after_first AS
SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment
JOIN review_after_first review USING(review_id);

\ir ../init/009-load-graph-permission-codex-remaining-28.sql

DO $$
DECLARE
    current_catalogue_count bigint;
    current_catalogue_fingerprint text;
BEGIN
    IF (SELECT count(*) FROM review_after_first) <> 28 THEN
        RAISE EXCEPTION 'Review count is not 28.';
    END IF;

    IF EXISTS (
        WITH pilot AS (SELECT pilot_id FROM permission_pilot.pilot_definition WHERE pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'),
        expected AS (
          SELECT selection.selection_id FROM permission_pilot.permission_selection selection JOIN pilot USING(pilot_id)
          WHERE selection.sample_stage='final' AND NOT EXISTS (
            SELECT 1 FROM permission_pilot.classification_review batch1
            WHERE batch1.selection_id=selection.selection_id AND batch1.reviewer_kind='codex'
              AND batch1.reviewer_identifier='codex_independent_batch_1' AND batch1.review_round=1)),
        actual AS (SELECT selection_id FROM review_after_first)
        (SELECT * FROM expected EXCEPT SELECT * FROM actual)
        UNION ALL (SELECT * FROM actual EXCEPT SELECT * FROM expected)
    ) THEN RAISE EXCEPTION 'Coverage is not exactly the database-derived remaining 28.'; END IF;

    IF EXISTS (
      SELECT 1 FROM review_after_first review
      JOIN permission_pilot.classification_review batch1 USING(selection_id)
      WHERE batch1.reviewer_kind='codex' AND batch1.reviewer_identifier='codex_independent_batch_1' AND batch1.review_round=1
    ) THEN RAISE EXCEPTION 'The remaining-batch reviewer contains a batch-1 permission.'; END IF;

    IF EXISTS (SELECT 1 FROM review_after_first WHERE capability IS NULL OR access_level IS NULL
       OR administrative_capability IS NULL OR privilege_level IS NULL OR data_sensitivity IS NULL
       OR destructive_potential IS NULL OR tenant_wide_impact IS NULL OR consent_sensitivity IS NULL
       OR classification_confidence IS NULL OR rationale IS NULL OR rationale='' OR review_status IS NULL OR review_status<>'submitted')
    THEN RAISE EXCEPTION 'A review is incomplete or not submitted.'; END IF;

    IF EXISTS (SELECT review.review_id FROM review_after_first review LEFT JOIN domain_after_first assignment USING(review_id)
               GROUP BY review.review_id HAVING count(*) FILTER(WHERE assignment_kind='primary')<>1)
    THEN RAISE EXCEPTION 'A review lacks exactly one primary domain.'; END IF;

    IF EXISTS (SELECT review_id,domain_id FROM domain_after_first GROUP BY review_id,domain_id HAVING count(*)>1)
    THEN RAISE EXCEPTION 'Duplicate domain assignment found.'; END IF;

    IF EXISTS (SELECT 1 FROM domain_after_first assignment LEFT JOIN catalogue.controlops_domain domain USING(domain_id) WHERE domain.domain_id IS NULL)
    THEN RAISE EXCEPTION 'Unexpected domain code found.'; END IF;

    IF EXISTS ((SELECT * FROM review_after_first EXCEPT
                SELECT review.* FROM permission_pilot.classification_review review
                WHERE review.reviewer_kind='codex' AND review.reviewer_identifier='codex_remaining_28' AND review.review_round=1)
               UNION ALL
               (SELECT review.* FROM permission_pilot.classification_review review
                WHERE review.reviewer_kind='codex' AND review.reviewer_identifier='codex_remaining_28' AND review.review_round=1
                EXCEPT SELECT * FROM review_after_first))
       OR EXISTS ((SELECT * FROM domain_after_first EXCEPT SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment JOIN review_after_first review USING(review_id))
                  UNION ALL (SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment JOIN review_after_first review USING(review_id) EXCEPT SELECT * FROM domain_after_first))
    THEN RAISE EXCEPTION 'Second run was not idempotent.'; END IF;

    IF EXISTS ((SELECT * FROM protected_review_before EXCEPT
                SELECT review.* FROM permission_pilot.classification_review review
                WHERE (review.reviewer_kind,review.reviewer_identifier,review.review_round) IN (('analyst','jon_bruce',1),('codex','codex_independent_batch_1',1)))
               UNION ALL
               (SELECT review.* FROM permission_pilot.classification_review review
                WHERE (review.reviewer_kind,review.reviewer_identifier,review.review_round) IN (('analyst','jon_bruce',1),('codex','codex_independent_batch_1',1))
                EXCEPT SELECT * FROM protected_review_before))
       OR EXISTS ((SELECT * FROM protected_domain_before EXCEPT SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment JOIN protected_review_before review USING(review_id))
                  UNION ALL (SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment JOIN protected_review_before review USING(review_id) EXCEPT SELECT * FROM protected_domain_before))
    THEN RAISE EXCEPTION 'Protected analyst or Codex batch-1 state changed.'; END IF;

    IF EXISTS ((SELECT * FROM selection_before EXCEPT SELECT selection.* FROM permission_pilot.permission_selection selection JOIN permission_pilot.pilot_definition pilot USING(pilot_id) WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36')
               UNION ALL (SELECT selection.* FROM permission_pilot.permission_selection selection JOIN permission_pilot.pilot_definition pilot USING(pilot_id) WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36' EXCEPT SELECT * FROM selection_before))
       OR (SELECT count(*) FROM selection_before WHERE sample_stage='final')<>36
    THEN RAISE EXCEPTION 'Pilot selection state changed or final count is not 36.'; END IF;

    SELECT count(*),md5(string_agg(to_jsonb(permission)::text,E'\n' ORDER BY permission.permission_definition_id))
      INTO current_catalogue_count,current_catalogue_fingerprint FROM catalogue.permission_definition permission;
    IF EXISTS (SELECT 1 FROM catalogue_before WHERE row_count<>current_catalogue_count OR fingerprint IS DISTINCT FROM current_catalogue_fingerprint)
    THEN RAISE EXCEPTION 'Catalogue baseline count or fingerprint changed.'; END IF;

    IF EXISTS (SELECT 1 FROM workflow_before WHERE disagreement_count<>(SELECT count(*) FROM permission_pilot.disagreement)
      OR disagreement_fingerprint IS DISTINCT FROM (SELECT md5(coalesce(string_agg(to_jsonb(disagreement)::text,E'\n' ORDER BY disagreement_id),'')) FROM permission_pilot.disagreement)
      OR domain_review_count<>(SELECT count(*) FROM permission_pilot.domain_review)
      OR domain_review_fingerprint IS DISTINCT FROM (SELECT md5(coalesce(string_agg(to_jsonb(domain_review)::text,E'\n' ORDER BY domain_review_id),'')) FROM permission_pilot.domain_review))
    THEN RAISE EXCEPTION 'Disagreement or domain-review workflow state changed.'; END IF;
END;
$$;

SELECT 'review_count' test,count(*)::text actual,'28' expected FROM review_after_first
UNION ALL SELECT 'primary_domain_count',count(*)::text,'28' FROM domain_after_first WHERE assignment_kind='primary'
UNION ALL SELECT 'second_run_review_inserts','0','0'
UNION ALL SELECT 'second_run_review_updates','0','0'
UNION ALL SELECT 'second_run_domain_inserts','0','0'
UNION ALL SELECT 'second_run_domain_updates','0','0'
UNION ALL SELECT 'final_selection_count',count(*)::text,'36' FROM selection_before WHERE sample_stage='final';

-- Read-only quality summaries for targeted human review.
SELECT permission.permission_type,count(*) review_count
FROM review_after_first review JOIN permission_pilot.permission_selection selection USING(selection_id)
JOIN catalogue.permission_definition permission USING(permission_definition_id)
GROUP BY permission.permission_type ORDER BY permission.permission_type;

SELECT classification_confidence,count(*) review_count FROM review_after_first GROUP BY classification_confidence ORDER BY classification_confidence;
SELECT privilege_level,count(*) review_count FROM review_after_first GROUP BY privilege_level ORDER BY privilege_level;

SELECT permission.permission_name,permission.permission_type,
       concat_ws(',',CASE WHEN review.capability='unknown' THEN 'capability' END,
                     CASE WHEN review.access_level='unknown' THEN 'access_level' END,
                     CASE WHEN review.privilege_level='unknown' THEN 'privilege_level' END,
                     CASE WHEN review.data_sensitivity='unknown' THEN 'data_sensitivity' END,
                     CASE WHEN review.destructive_potential='unknown' THEN 'destructive_potential' END,
                     CASE WHEN review.consent_sensitivity='unknown' THEN 'consent_sensitivity' END) unknown_fields
FROM review_after_first review JOIN permission_pilot.permission_selection selection USING(selection_id)
JOIN catalogue.permission_definition permission USING(permission_definition_id)
WHERE 'unknown' IN (review.capability,review.access_level,review.privilege_level,review.data_sensitivity,review.destructive_potential,review.consent_sensitivity)
ORDER BY permission.permission_type,permission.permission_name;

SELECT permission.permission_name,permission.permission_type,
       string_agg(domain.domain_code,',' ORDER BY domain.domain_code) FILTER(WHERE assignment.assignment_kind='secondary') secondary_domains
FROM review_after_first review JOIN permission_pilot.permission_selection selection USING(selection_id)
JOIN catalogue.permission_definition permission USING(permission_definition_id)
JOIN domain_after_first assignment USING(review_id) JOIN catalogue.controlops_domain domain USING(domain_id)
GROUP BY permission.permission_name,permission.permission_type
HAVING count(*) FILTER(WHERE assignment.assignment_kind='secondary')>0
ORDER BY permission.permission_type,permission.permission_name;

SELECT permission.permission_name,permission.permission_type,review.classification_confidence
FROM review_after_first review JOIN permission_pilot.permission_selection selection USING(selection_id)
JOIN catalogue.permission_definition permission USING(permission_definition_id)
WHERE review.classification_confidence<>'high' ORDER BY permission.permission_type,permission.permission_name;

DROP TABLE domain_after_first;
DROP TABLE review_after_first;
DROP TABLE workflow_before;
DROP TABLE catalogue_before;
DROP TABLE selection_before;
DROP TABLE protected_domain_before;
DROP TABLE protected_review_before;
