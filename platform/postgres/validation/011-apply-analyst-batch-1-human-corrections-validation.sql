\set ON_ERROR_STOP on

CREATE TEMPORARY TABLE all_reviews_before AS
SELECT review.* FROM permission_pilot.classification_review review;

CREATE TEMPORARY TABLE all_domains_before AS
SELECT assignment.* FROM permission_pilot.review_domain_assignment assignment;

CREATE TEMPORARY TABLE workflow_before AS
SELECT (SELECT count(*) FROM permission_pilot.disagreement) disagreement_count,
       (SELECT md5(coalesce(string_agg(to_jsonb(disagreement)::text,E'\n' ORDER BY disagreement_id),'')) FROM permission_pilot.disagreement) disagreement_fingerprint,
       (SELECT count(*) FROM permission_pilot.domain_review) domain_review_count,
       (SELECT md5(coalesce(string_agg(to_jsonb(domain_review)::text,E'\n' ORDER BY domain_review_id),'')) FROM permission_pilot.domain_review) domain_review_fingerprint;

\ir ../init/011-apply-analyst-batch-1-human-corrections.sql

CREATE TEMPORARY TABLE corrected_after_first AS
SELECT review.* FROM permission_pilot.classification_review review
JOIN permission_pilot.permission_selection selection USING(selection_id)
JOIN permission_pilot.pilot_definition pilot USING(pilot_id)
JOIN catalogue.permission_definition permission USING(permission_definition_id)
WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind='analyst' AND review.reviewer_identifier='jon_bruce' AND review.review_round=1
  AND (permission.permission_name,permission.permission_type) IN
      (('AppRoleAssignment.ReadWrite.All','Application'),('AuditLog.Read.All','Delegated'),
       ('DeviceLocalCredential.Read.All','Application'),('Directory.AccessAsUser.All','Delegated'),
       ('Sites.Selected','Application'),('Teamwork.Migrate.All','Application'),('User.Read','Delegated'));

CREATE TEMPORARY TABLE all_reviews_after_first AS SELECT * FROM permission_pilot.classification_review;

\ir ../init/011-apply-analyst-batch-1-human-corrections.sql

DO $$
BEGIN
    IF (SELECT count(*) FROM corrected_after_first)<>7 THEN RAISE EXCEPTION 'Expected seven corrected rows.'; END IF;

    IF EXISTS (
      WITH expected(permission_name,permission_type,capability,access_level,privilege_level,data_sensitivity,destructive_potential,consent_sensitivity,classification_confidence) AS (VALUES
       ('AppRoleAssignment.ReadWrite.All','Application','manage','all','critical','moderate','critical','critical','high'),
       ('AuditLog.Read.All','Delegated','read','all','high','high','none','high','high'),
       ('DeviceLocalCredential.Read.All','Application','read','all','critical','restricted','critical','high','high'),
       ('Directory.AccessAsUser.All','Delegated','read','all','high','moderate','moderate','high','high'),
       ('Sites.Selected','Application','unknown','selected','unknown','moderate','unknown','moderate','medium'),
       ('Teamwork.Migrate.All','Application','write','all','critical','high','high','high','high'),
       ('User.Read','Delegated','read','owned','low','low','none','low','high'))
      SELECT 1 FROM corrected_after_first review
      JOIN permission_pilot.permission_selection selection USING(selection_id)
      JOIN catalogue.permission_definition permission USING(permission_definition_id)
      JOIN expected USING(permission_name,permission_type)
      WHERE (review.capability,review.access_level,review.privilege_level,review.data_sensitivity,
             review.destructive_potential,review.consent_sensitivity,review.classification_confidence)
        IS DISTINCT FROM
            (expected.capability,expected.access_level,expected.privilege_level,expected.data_sensitivity,
             expected.destructive_potential,expected.consent_sensitivity,expected.classification_confidence)
    ) THEN RAISE EXCEPTION 'A corrected value does not match the human decision.'; END IF;

    IF EXISTS (
      SELECT 1 FROM corrected_after_first current
      JOIN all_reviews_before before USING(review_id)
      WHERE current.review_id<>before.review_id OR current.created_at<>before.created_at
         OR current.review_status IS DISTINCT FROM before.review_status
         OR current.rationale IS DISTINCT FROM before.rationale
         OR current.administrative_capability IS DISTINCT FROM before.administrative_capability
         OR current.tenant_wide_impact IS DISTINCT FROM before.tenant_wide_impact
    ) THEN RAISE EXCEPTION 'A non-authorized field changed on a corrected review.'; END IF;

    IF EXISTS (
      SELECT 1 FROM all_reviews_before before
      LEFT JOIN corrected_after_first target USING(review_id)
      JOIN permission_pilot.classification_review current ON current.review_id=before.review_id
      WHERE target.review_id IS NULL AND to_jsonb(current) IS DISTINCT FROM to_jsonb(before)
    ) THEN RAISE EXCEPTION 'An unrelated analyst or Codex review changed.'; END IF;

    IF EXISTS ((SELECT * FROM all_domains_before EXCEPT SELECT * FROM permission_pilot.review_domain_assignment)
               UNION ALL (SELECT * FROM permission_pilot.review_domain_assignment EXCEPT SELECT * FROM all_domains_before))
    THEN RAISE EXCEPTION 'A domain assignment changed.'; END IF;

    IF EXISTS ((SELECT * FROM all_reviews_after_first EXCEPT SELECT * FROM permission_pilot.classification_review)
               UNION ALL (SELECT * FROM permission_pilot.classification_review EXCEPT SELECT * FROM all_reviews_after_first))
    THEN RAISE EXCEPTION 'Second migration run changed a review.'; END IF;

    IF EXISTS (SELECT 1 FROM workflow_before WHERE disagreement_count<>(SELECT count(*) FROM permission_pilot.disagreement)
      OR disagreement_fingerprint IS DISTINCT FROM (SELECT md5(coalesce(string_agg(to_jsonb(disagreement)::text,E'\n' ORDER BY disagreement_id),'')) FROM permission_pilot.disagreement)
      OR domain_review_count<>(SELECT count(*) FROM permission_pilot.domain_review)
      OR domain_review_fingerprint IS DISTINCT FROM (SELECT md5(coalesce(string_agg(to_jsonb(domain_review)::text,E'\n' ORDER BY domain_review_id),'')) FROM permission_pilot.domain_review))
    THEN RAISE EXCEPTION 'Workflow state changed.'; END IF;
END;
$$;

SELECT 'corrected_reviews' test,count(*)::text actual,'7' expected FROM corrected_after_first
UNION ALL SELECT 'second_run_updates','0','0'
UNION ALL SELECT 'domain_changes','0','0'
UNION ALL SELECT 'disagreements',count(*)::text,'0' FROM permission_pilot.disagreement
UNION ALL SELECT 'domain_reviews',count(*)::text,'0' FROM permission_pilot.domain_review;

DROP TABLE all_reviews_after_first;
DROP TABLE corrected_after_first;
DROP TABLE workflow_before;
DROP TABLE all_domains_before;
DROP TABLE all_reviews_before;
