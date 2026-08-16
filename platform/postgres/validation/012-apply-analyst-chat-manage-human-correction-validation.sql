\set ON_ERROR_STOP on

CREATE TEMPORARY TABLE reviews_before AS
SELECT review.* FROM permission_pilot.classification_review review;

CREATE TEMPORARY TABLE domains_before AS
SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment;

CREATE TEMPORARY TABLE workflow_before AS
SELECT (SELECT count(*) FROM permission_pilot.disagreement) disagreement_count,
       (SELECT md5(coalesce(string_agg(to_jsonb(disagreement)::text,E'\n' ORDER BY disagreement_id),'')) FROM permission_pilot.disagreement) disagreement_fingerprint,
       (SELECT count(*) FROM permission_pilot.domain_review) domain_review_count,
       (SELECT md5(coalesce(string_agg(to_jsonb(domain_review)::text,E'\n' ORDER BY domain_review_id),'')) FROM permission_pilot.domain_review) domain_review_fingerprint;

\ir ../init/012-apply-analyst-chat-manage-human-correction.sql

CREATE TEMPORARY TABLE corrected_after_first AS
SELECT review.* FROM permission_pilot.classification_review review
JOIN permission_pilot.permission_selection selection USING(selection_id)
JOIN permission_pilot.pilot_definition pilot USING(pilot_id)
JOIN catalogue.permission_definition permission USING(permission_definition_id)
WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND permission.permission_name='Chat.Manage.Chat' AND permission.permission_type='RSC'
  AND review.reviewer_kind='analyst' AND review.reviewer_identifier='jon_bruce' AND review.review_round=1;

CREATE TEMPORARY TABLE reviews_after_first AS
SELECT review.* FROM permission_pilot.classification_review review;

\ir ../init/012-apply-analyst-chat-manage-human-correction.sql

DO $$
BEGIN
    IF (SELECT count(*) FROM corrected_after_first)<>1 THEN RAISE EXCEPTION 'Expected one corrected review.'; END IF;

    IF EXISTS (SELECT 1 FROM corrected_after_first review
      WHERE (review.capability,review.access_level,review.privilege_level,
             review.data_sensitivity,review.destructive_potential,
             review.consent_sensitivity,review.classification_confidence)
        IS DISTINCT FROM ('manage','selected','high','high','high','high','high'))
    THEN RAISE EXCEPTION 'Corrected fields differ from the human decision.'; END IF;

    IF EXISTS (
      SELECT 1 FROM corrected_after_first current
      JOIN reviews_before before USING(review_id)
      WHERE current.review_status IS DISTINCT FROM before.review_status
         OR current.rationale IS DISTINCT FROM before.rationale
         OR current.review_id<>before.review_id
         OR current.created_at<>before.created_at
         OR current.administrative_capability IS DISTINCT FROM before.administrative_capability
         OR current.tenant_wide_impact IS DISTINCT FROM before.tenant_wide_impact)
    THEN RAISE EXCEPTION 'A prohibited target field changed.'; END IF;

    IF EXISTS (
      SELECT 1 FROM reviews_before before
      JOIN permission_pilot.classification_review current USING(review_id)
      LEFT JOIN corrected_after_first target USING(review_id)
      WHERE target.review_id IS NULL AND to_jsonb(current) IS DISTINCT FROM to_jsonb(before))
    THEN RAISE EXCEPTION 'An unrelated analyst or Codex review changed.'; END IF;

    IF EXISTS ((SELECT * FROM domains_before EXCEPT SELECT * FROM permission_pilot.review_domain_assignment)
               UNION ALL (SELECT * FROM permission_pilot.review_domain_assignment EXCEPT SELECT * FROM domains_before))
    THEN RAISE EXCEPTION 'A domain assignment changed.'; END IF;

    IF EXISTS ((SELECT * FROM reviews_after_first EXCEPT SELECT * FROM permission_pilot.classification_review)
               UNION ALL (SELECT * FROM permission_pilot.classification_review EXCEPT SELECT * FROM reviews_after_first))
    THEN RAISE EXCEPTION 'Second migration run changed a review.'; END IF;

    IF EXISTS (SELECT 1 FROM workflow_before WHERE disagreement_count<>(SELECT count(*) FROM permission_pilot.disagreement)
      OR disagreement_fingerprint IS DISTINCT FROM (SELECT md5(coalesce(string_agg(to_jsonb(disagreement)::text,E'\n' ORDER BY disagreement_id),'')) FROM permission_pilot.disagreement)
      OR domain_review_count<>(SELECT count(*) FROM permission_pilot.domain_review)
      OR domain_review_fingerprint IS DISTINCT FROM (SELECT md5(coalesce(string_agg(to_jsonb(domain_review)::text,E'\n' ORDER BY domain_review_id),'')) FROM permission_pilot.domain_review))
    THEN RAISE EXCEPTION 'Workflow state changed.'; END IF;
END;
$$;

SELECT 'corrected_reviews' test,count(*)::text actual,'1' expected FROM corrected_after_first
UNION ALL SELECT 'second_run_updates','0','0'
UNION ALL SELECT 'domain_changes','0','0'
UNION ALL SELECT 'disagreements',count(*)::text,'0' FROM permission_pilot.disagreement
UNION ALL SELECT 'domain_reviews',count(*)::text,'0' FROM permission_pilot.domain_review;

DROP TABLE reviews_after_first;
DROP TABLE corrected_after_first;
DROP TABLE workflow_before;
DROP TABLE domains_before;
DROP TABLE reviews_before;
