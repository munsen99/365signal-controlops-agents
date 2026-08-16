\set ON_ERROR_STOP on

CREATE TEMPORARY TABLE protected_reviews_before AS
SELECT review.* FROM permission_pilot.classification_review review
WHERE (review.reviewer_kind,review.reviewer_identifier,review.review_round) IN
      (('analyst','jon_bruce',1),('codex','codex_independent_batch_1',1),('codex','codex_remaining_28',1));

CREATE TEMPORARY TABLE submitted_analyst_before AS
SELECT * FROM protected_reviews_before
WHERE reviewer_kind='analyst' AND reviewer_identifier='jon_bruce'
  AND review_round=1 AND review_status='submitted';

CREATE TEMPORARY TABLE codex_before AS
SELECT * FROM protected_reviews_before WHERE reviewer_kind='codex';

CREATE TEMPORARY TABLE protected_domains_before AS
SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment
JOIN protected_reviews_before review USING(review_id);

CREATE TEMPORARY TABLE selections_before AS
SELECT selection.* FROM permission_pilot.permission_selection selection
JOIN permission_pilot.pilot_definition pilot USING(pilot_id)
WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36';

CREATE TEMPORARY TABLE catalogue_before AS
SELECT count(*) row_count,md5(string_agg(to_jsonb(permission)::text,E'\n' ORDER BY permission_definition_id)) fingerprint
FROM catalogue.permission_definition permission;

CREATE TEMPORARY TABLE workflow_before AS
SELECT (SELECT count(*) FROM permission_pilot.disagreement) disagreement_count,
       (SELECT md5(coalesce(string_agg(to_jsonb(disagreement)::text,E'\n' ORDER BY disagreement_id),'')) FROM permission_pilot.disagreement) disagreement_fingerprint,
       (SELECT count(*) FROM permission_pilot.domain_review) domain_review_count,
       (SELECT md5(coalesce(string_agg(to_jsonb(domain_review)::text,E'\n' ORDER BY domain_review_id),'')) FROM permission_pilot.domain_review) domain_review_fingerprint;

\ir ../init/010-create-analyst-drafts-remaining-28.sql

CREATE TEMPORARY TABLE analyst_after_first AS
SELECT review.* FROM permission_pilot.classification_review review
JOIN permission_pilot.permission_selection selection USING(selection_id)
JOIN permission_pilot.pilot_definition pilot USING(pilot_id)
WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind='analyst' AND review.reviewer_identifier='jon_bruce' AND review.review_round=1;

CREATE TEMPORARY TABLE draft_after_first AS
SELECT * FROM analyst_after_first WHERE review_status='draft';

CREATE TEMPORARY TABLE draft_domains_after_first AS
SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment
JOIN draft_after_first review USING(review_id);

\ir ../init/010-create-analyst-drafts-remaining-28.sql

DO $$
DECLARE current_count bigint; current_fingerprint text;
BEGIN
    IF (SELECT count(*) FROM analyst_after_first)<>36
       OR (SELECT count(*) FROM analyst_after_first WHERE review_status='submitted')<>8
       OR (SELECT count(*) FROM draft_after_first)<>28 THEN
        RAISE EXCEPTION 'Expected 36 analyst reviews: 8 submitted and 28 draft.';
    END IF;

    IF EXISTS (
      WITH codex_target AS (
        SELECT selection_id FROM permission_pilot.classification_review
        WHERE reviewer_kind='codex' AND reviewer_identifier='codex_remaining_28'
          AND review_round=1 AND review_status='submitted'),
      actual AS (SELECT selection_id FROM draft_after_first)
      (SELECT * FROM codex_target EXCEPT SELECT * FROM actual)
      UNION ALL (SELECT * FROM actual EXCEPT SELECT * FROM codex_target)
    ) THEN RAISE EXCEPTION 'Draft target set differs from Codex remaining 28.'; END IF;

    IF EXISTS (SELECT 1 FROM draft_after_first WHERE capability IS NULL OR access_level IS NULL
      OR privilege_level IS NULL OR data_sensitivity IS NULL OR destructive_potential IS NULL
      OR consent_sensitivity IS NULL OR classification_confidence IS NULL OR rationale IS NULL OR rationale='')
    THEN RAISE EXCEPTION 'A draft has an incomplete classification.'; END IF;

    IF EXISTS (SELECT review.review_id FROM draft_after_first review LEFT JOIN draft_domains_after_first assignment USING(review_id)
      GROUP BY review.review_id HAVING count(*) FILTER(WHERE assignment_kind='primary')<>1)
    THEN RAISE EXCEPTION 'A draft lacks exactly one primary domain.'; END IF;

    IF EXISTS (
      SELECT 1 FROM draft_after_first analyst
      JOIN permission_pilot.classification_review codex
        ON codex.selection_id=analyst.selection_id AND codex.reviewer_kind='codex'
       AND codex.reviewer_identifier='codex_remaining_28' AND codex.review_round=1
      WHERE (analyst.access_level,analyst.capability,analyst.administrative_capability,
             analyst.privilege_level,analyst.data_sensitivity,analyst.destructive_potential,
             analyst.tenant_wide_impact,analyst.consent_sensitivity,
             analyst.classification_confidence,analyst.rationale)
        IS DISTINCT FROM
            (codex.access_level,codex.capability,codex.administrative_capability,
             codex.privilege_level,codex.data_sensitivity,codex.destructive_potential,
             codex.tenant_wide_impact,codex.consent_sensitivity,
             codex.classification_confidence,codex.rationale)
    ) THEN RAISE EXCEPTION 'Initial analyst draft attributes differ from Codex sources.'; END IF;

    IF EXISTS (
      WITH analyst_domains AS (
        SELECT analyst.selection_id,assignment.domain_id,assignment.assignment_kind,assignment.mapping_rationale
        FROM draft_after_first analyst JOIN draft_domains_after_first assignment USING(review_id)),
      codex_domains AS (
        SELECT codex.selection_id,assignment.domain_id,assignment.assignment_kind,assignment.mapping_rationale
        FROM permission_pilot.classification_review codex
        JOIN permission_pilot.review_domain_assignment assignment USING(review_id)
        WHERE codex.reviewer_kind='codex' AND codex.reviewer_identifier='codex_remaining_28' AND codex.review_round=1)
      (SELECT * FROM analyst_domains EXCEPT SELECT * FROM codex_domains)
      UNION ALL (SELECT * FROM codex_domains EXCEPT SELECT * FROM analyst_domains)
    ) THEN RAISE EXCEPTION 'Initial analyst draft domains differ from Codex sources.'; END IF;

    IF EXISTS ((SELECT * FROM analyst_after_first EXCEPT SELECT review.* FROM permission_pilot.classification_review review
                WHERE review.reviewer_kind='analyst' AND review.reviewer_identifier='jon_bruce' AND review.review_round=1)
               UNION ALL (SELECT review.* FROM permission_pilot.classification_review review
                WHERE review.reviewer_kind='analyst' AND review.reviewer_identifier='jon_bruce' AND review.review_round=1 EXCEPT SELECT * FROM analyst_after_first))
       OR EXISTS ((SELECT * FROM draft_domains_after_first EXCEPT SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment JOIN draft_after_first review USING(review_id))
                  UNION ALL (SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment JOIN draft_after_first review USING(review_id) EXCEPT SELECT * FROM draft_domains_after_first))
    THEN RAISE EXCEPTION 'Second migration run changed analyst rows or domains.'; END IF;

    IF EXISTS ((SELECT * FROM submitted_analyst_before EXCEPT SELECT * FROM analyst_after_first WHERE review_status='submitted')
               UNION ALL (SELECT * FROM analyst_after_first WHERE review_status='submitted' EXCEPT SELECT * FROM submitted_analyst_before))
       OR EXISTS ((SELECT * FROM codex_before EXCEPT SELECT review.* FROM permission_pilot.classification_review review WHERE review.reviewer_kind='codex')
                  UNION ALL (SELECT review.* FROM permission_pilot.classification_review review WHERE review.reviewer_kind='codex' EXCEPT SELECT * FROM codex_before))
    THEN RAISE EXCEPTION 'Submitted analyst batch 1 or Codex reviews changed.'; END IF;

    IF EXISTS ((SELECT assignment.* FROM protected_domains_before assignment JOIN submitted_analyst_before review USING(review_id)
                EXCEPT SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment JOIN submitted_analyst_before review USING(review_id))
               UNION ALL (SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment JOIN submitted_analyst_before review USING(review_id)
                EXCEPT SELECT assignment.* FROM protected_domains_before assignment JOIN submitted_analyst_before review USING(review_id)))
       OR EXISTS ((SELECT assignment.* FROM protected_domains_before assignment JOIN codex_before review USING(review_id)
                   EXCEPT SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment JOIN codex_before review USING(review_id))
                  UNION ALL (SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment JOIN codex_before review USING(review_id)
                   EXCEPT SELECT assignment.* FROM protected_domains_before assignment JOIN codex_before review USING(review_id)))
    THEN RAISE EXCEPTION 'Protected domain assignments changed.'; END IF;

    IF (SELECT count(*) FROM selections_before WHERE sample_stage='final')<>36
       OR EXISTS ((SELECT * FROM selections_before EXCEPT SELECT selection.* FROM permission_pilot.permission_selection selection JOIN permission_pilot.pilot_definition pilot USING(pilot_id) WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36')
                  UNION ALL (SELECT selection.* FROM permission_pilot.permission_selection selection JOIN permission_pilot.pilot_definition pilot USING(pilot_id) WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36' EXCEPT SELECT * FROM selections_before))
    THEN RAISE EXCEPTION 'Pilot selections changed.'; END IF;

    SELECT count(*),md5(string_agg(to_jsonb(permission)::text,E'\n' ORDER BY permission_definition_id)) INTO current_count,current_fingerprint FROM catalogue.permission_definition permission;
    IF EXISTS (SELECT 1 FROM catalogue_before WHERE row_count<>current_count OR fingerprint IS DISTINCT FROM current_fingerprint)
    THEN RAISE EXCEPTION 'Catalogue count or fingerprint changed.'; END IF;

    IF EXISTS (SELECT 1 FROM workflow_before WHERE disagreement_count<>(SELECT count(*) FROM permission_pilot.disagreement)
      OR disagreement_fingerprint IS DISTINCT FROM (SELECT md5(coalesce(string_agg(to_jsonb(disagreement)::text,E'\n' ORDER BY disagreement_id),'')) FROM permission_pilot.disagreement)
      OR domain_review_count<>(SELECT count(*) FROM permission_pilot.domain_review)
      OR domain_review_fingerprint IS DISTINCT FROM (SELECT md5(coalesce(string_agg(to_jsonb(domain_review)::text,E'\n' ORDER BY domain_review_id),'')) FROM permission_pilot.domain_review))
    THEN RAISE EXCEPTION 'Workflow state changed.'; END IF;
END;
$$;

SELECT 'analyst_total' test,count(*)::text actual,'36' expected FROM analyst_after_first
UNION ALL SELECT 'analyst_submitted',count(*)::text,'8' FROM analyst_after_first WHERE review_status='submitted'
UNION ALL SELECT 'analyst_draft',count(*)::text,'28' FROM draft_after_first
UNION ALL SELECT 'draft_primary_domains',count(*)::text,'28' FROM draft_domains_after_first WHERE assignment_kind='primary'
UNION ALL SELECT 'second_run_review_inserts','0','0'
UNION ALL SELECT 'second_run_review_updates','0','0'
UNION ALL SELECT 'second_run_domain_inserts','0','0'
UNION ALL SELECT 'second_run_domain_updates','0','0';

DROP TABLE draft_domains_after_first;
DROP TABLE draft_after_first;
DROP TABLE analyst_after_first;
DROP TABLE workflow_before;
DROP TABLE catalogue_before;
DROP TABLE selections_before;
DROP TABLE protected_domains_before;
DROP TABLE codex_before;
DROP TABLE submitted_analyst_before;
DROP TABLE protected_reviews_before;
