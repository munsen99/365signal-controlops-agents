\set ON_ERROR_STOP on

CREATE TEMPORARY TABLE expected_analyst_review (
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    classification_confidence TEXT NOT NULL,
    PRIMARY KEY (permission_name, permission_type)
);

INSERT INTO expected_analyst_review VALUES
('User.Read', 'Delegated', 'high'),
('Directory.AccessAsUser.All', 'Delegated', 'high'),
('AuditLog.Read.All', 'Delegated', 'high'),
('AppRoleAssignment.ReadWrite.All', 'Application', 'high'),
('DeviceLocalCredential.Read.All', 'Application', 'high'),
('Sites.Selected', 'Application', 'medium'),
('Teamwork.Migrate.All', 'Application', 'high'),
('Chat.Manage.Chat', 'RSC', 'high');

CREATE TEMPORARY TABLE expected_domain_assignment (
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    domain_code TEXT NOT NULL,
    assignment_kind TEXT NOT NULL,
    PRIMARY KEY (permission_name, permission_type, domain_code)
);

INSERT INTO expected_domain_assignment VALUES
('User.Read', 'Delegated', 'DIRECTORY_ORG_MANAGEMENT', 'primary'),
('Directory.AccessAsUser.All', 'Delegated', 'AUTHORIZATION_ACCESS_GOVERNANCE', 'primary'),
('Directory.AccessAsUser.All', 'Delegated', 'PRIVILEGED_ACCESS', 'secondary'),
('AuditLog.Read.All', 'Delegated', 'LOGGING_MONITORING_AUDIT', 'primary'),
('AuditLog.Read.All', 'Delegated', 'AUDIT_ASSURANCE', 'secondary'),
('AppRoleAssignment.ReadWrite.All', 'Application', 'APPLICATION_IDENTITY_CONSENT', 'primary'),
('AppRoleAssignment.ReadWrite.All', 'Application', 'AUTHORIZATION_ACCESS_GOVERNANCE', 'secondary'),
('AppRoleAssignment.ReadWrite.All', 'Application', 'PRIVILEGED_ACCESS', 'secondary'),
('DeviceLocalCredential.Read.All', 'Application', 'ENDPOINT_DEVICE_MANAGEMENT', 'primary'),
('DeviceLocalCredential.Read.All', 'Application', 'AUTHENTICATION', 'secondary'),
('DeviceLocalCredential.Read.All', 'Application', 'PRIVILEGED_ACCESS', 'secondary'),
('Sites.Selected', 'Application', 'SHAREPOINT_ONEDRIVE', 'primary'),
('Sites.Selected', 'Application', 'APPLICATION_IDENTITY_CONSENT', 'secondary'),
('Teamwork.Migrate.All', 'Application', 'MICROSOFT_TEAMS', 'primary'),
('Teamwork.Migrate.All', 'Application', 'APPLICATION_IDENTITY_CONSENT', 'secondary'),
('Teamwork.Migrate.All', 'Application', 'AUDIT_ASSURANCE', 'secondary'),
('Chat.Manage.Chat', 'RSC', 'MICROSOFT_TEAMS', 'primary'),
('Chat.Manage.Chat', 'RSC', 'AUTHORIZATION_ACCESS_GOVERNANCE', 'secondary'),
('Chat.Manage.Chat', 'RSC', 'APPLICATION_IDENTITY_CONSENT', 'secondary');

CREATE TEMPORARY TABLE catalogue_before AS
SELECT count(*) AS row_count,
       md5(string_agg(to_jsonb(permission)::TEXT, E'\n'
                      ORDER BY permission.permission_definition_id)) AS fingerprint
FROM catalogue.permission_definition permission;

CREATE TEMPORARY TABLE selections_before AS
SELECT selection.*
FROM permission_pilot.permission_selection selection
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36';

CREATE TEMPORARY TABLE codex_reviews_before AS
SELECT review.*
FROM permission_pilot.classification_review review
WHERE review.reviewer_kind = 'codex';

CREATE TEMPORARY TABLE codex_domains_before AS
SELECT assignment.*
FROM permission_pilot.review_domain_assignment assignment
JOIN permission_pilot.classification_review review USING (review_id)
WHERE review.reviewer_kind = 'codex';

CREATE TEMPORARY TABLE other_analyst_reviews_before AS
SELECT review.*
FROM permission_pilot.classification_review review
WHERE review.reviewer_kind = 'analyst'
  AND (review.reviewer_identifier <> 'jon_bruce' OR review.review_round <> 1);

CREATE TEMPORARY TABLE disagreements_before AS
SELECT * FROM permission_pilot.disagreement;

\ir ../init/007-load-graph-permission-analyst-batch-1.sql

CREATE TEMPORARY TABLE target_reviews_after_first_run AS
SELECT review.*
FROM permission_pilot.classification_review review
JOIN permission_pilot.permission_selection selection USING (selection_id)
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind = 'analyst'
  AND review.reviewer_identifier = 'jon_bruce'
  AND review.review_round = 1;

CREATE TEMPORARY TABLE target_domains_after_first_run AS
SELECT assignment.*
FROM permission_pilot.review_domain_assignment assignment
JOIN target_reviews_after_first_run review USING (review_id);

\ir ../init/007-load-graph-permission-analyst-batch-1.sql

DO $$
BEGIN
    IF (SELECT count(*)
        FROM permission_pilot.classification_review review
        JOIN permission_pilot.permission_selection selection USING (selection_id)
        JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND review.reviewer_kind = 'analyst'
          AND review.reviewer_identifier = 'jon_bruce'
          AND review.review_round = 1) <> 8 THEN
        RAISE EXCEPTION 'Expected exactly eight jon_bruce round-1 analyst reviews.';
    END IF;

    IF EXISTS (
        SELECT expected.permission_name, expected.permission_type
        FROM expected_analyst_review expected
        EXCEPT
        SELECT permission.permission_name, permission.permission_type
        FROM permission_pilot.classification_review review
        JOIN permission_pilot.permission_selection selection USING (selection_id)
        JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
        JOIN catalogue.permission_definition permission USING (permission_definition_id)
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND review.reviewer_kind = 'analyst'
          AND review.reviewer_identifier = 'jon_bruce'
          AND review.review_round = 1
    ) THEN
        RAISE EXCEPTION 'One or more expected analyst-reviewed permissions is missing.';
    END IF;

    IF EXISTS (
        SELECT review.review_id
        FROM permission_pilot.classification_review review
        JOIN permission_pilot.permission_selection selection USING (selection_id)
        JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND review.reviewer_kind = 'analyst'
          AND review.reviewer_identifier = 'jon_bruce'
          AND review.review_round = 1
        GROUP BY review.review_id
        HAVING count(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM permission_pilot.review_domain_assignment assignment
            WHERE assignment.review_id = review.review_id
              AND assignment.assignment_kind = 'primary'
        )) <> 1
    ) THEN
        RAISE EXCEPTION 'An analyst review does not have exactly one primary domain.';
    END IF;

    IF EXISTS (
        (SELECT expected.permission_name, expected.permission_type,
                expected.domain_code, expected.assignment_kind
         FROM expected_domain_assignment expected
         EXCEPT
         SELECT permission.permission_name, permission.permission_type,
                domain.domain_code, assignment.assignment_kind
         FROM permission_pilot.classification_review review
         JOIN permission_pilot.permission_selection selection USING (selection_id)
         JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
         JOIN catalogue.permission_definition permission USING (permission_definition_id)
         JOIN permission_pilot.review_domain_assignment assignment USING (review_id)
         JOIN catalogue.controlops_domain domain USING (domain_id)
         WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
           AND review.reviewer_kind = 'analyst'
           AND review.reviewer_identifier = 'jon_bruce'
           AND review.review_round = 1)
        UNION ALL
        (SELECT permission.permission_name, permission.permission_type,
                domain.domain_code, assignment.assignment_kind
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
         EXCEPT
         SELECT expected.permission_name, expected.permission_type,
                expected.domain_code, expected.assignment_kind
         FROM expected_domain_assignment expected)
    ) THEN
        RAISE EXCEPTION 'Analyst domain assignments differ from the exact approved set.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM permission_pilot.classification_review review
        JOIN permission_pilot.permission_selection selection USING (selection_id)
        JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
        JOIN catalogue.permission_definition permission USING (permission_definition_id)
        JOIN expected_analyst_review expected
          USING (permission_name, permission_type)
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND review.reviewer_kind = 'analyst'
          AND review.reviewer_identifier = 'jon_bruce'
          AND review.review_round = 1
          AND (review.classification_confidence <> expected.classification_confidence
               OR review.review_status <> 'submitted')
    ) THEN
        RAISE EXCEPTION 'Confidence or submitted status differs from the approved mapping.';
    END IF;

    IF EXISTS (
        (SELECT * FROM target_reviews_after_first_run
         EXCEPT
         SELECT review.*
         FROM permission_pilot.classification_review review
         JOIN permission_pilot.permission_selection selection USING (selection_id)
         JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
         WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
           AND review.reviewer_kind = 'analyst'
           AND review.reviewer_identifier = 'jon_bruce'
           AND review.review_round = 1)
        UNION ALL
        (SELECT review.*
         FROM permission_pilot.classification_review review
         JOIN permission_pilot.permission_selection selection USING (selection_id)
         JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
         WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
           AND review.reviewer_kind = 'analyst'
           AND review.reviewer_identifier = 'jon_bruce'
           AND review.review_round = 1
         EXCEPT SELECT * FROM target_reviews_after_first_run)
    ) OR EXISTS (
        (SELECT * FROM target_domains_after_first_run
         EXCEPT
         SELECT assignment.*
         FROM permission_pilot.review_domain_assignment assignment
         JOIN target_reviews_after_first_run review USING (review_id))
        UNION ALL
        (SELECT assignment.*
         FROM permission_pilot.review_domain_assignment assignment
         JOIN target_reviews_after_first_run review USING (review_id)
         EXCEPT SELECT * FROM target_domains_after_first_run)
    ) THEN
        RAISE EXCEPTION 'Second migration run changed analyst reviews or domains.';
    END IF;

    IF EXISTS ((SELECT * FROM codex_reviews_before
               EXCEPT SELECT * FROM permission_pilot.classification_review
                      WHERE reviewer_kind = 'codex')
              UNION ALL
              (SELECT * FROM permission_pilot.classification_review
               WHERE reviewer_kind = 'codex'
               EXCEPT SELECT * FROM codex_reviews_before))
       OR EXISTS ((SELECT * FROM codex_domains_before
                  EXCEPT
                  SELECT assignment.*
                  FROM permission_pilot.review_domain_assignment assignment
                  JOIN permission_pilot.classification_review review USING (review_id)
                  WHERE review.reviewer_kind = 'codex')
                 UNION ALL
                 (SELECT assignment.*
                  FROM permission_pilot.review_domain_assignment assignment
                  JOIN permission_pilot.classification_review review USING (review_id)
                  WHERE review.reviewer_kind = 'codex'
                  EXCEPT SELECT * FROM codex_domains_before)) THEN
        RAISE EXCEPTION 'Codex reviews or their domain assignments changed.';
    END IF;

    IF EXISTS ((SELECT * FROM other_analyst_reviews_before
               EXCEPT
               SELECT * FROM permission_pilot.classification_review
               WHERE reviewer_kind = 'analyst'
                 AND (reviewer_identifier <> 'jon_bruce' OR review_round <> 1))
              UNION ALL
              (SELECT * FROM permission_pilot.classification_review
               WHERE reviewer_kind = 'analyst'
                 AND (reviewer_identifier <> 'jon_bruce' OR review_round <> 1)
               EXCEPT SELECT * FROM other_analyst_reviews_before)) THEN
        RAISE EXCEPTION 'Another analyst or review round changed.';
    END IF;

    IF EXISTS ((SELECT * FROM disagreements_before
               EXCEPT SELECT * FROM permission_pilot.disagreement)
              UNION ALL
              (SELECT * FROM permission_pilot.disagreement
               EXCEPT SELECT * FROM disagreements_before)) THEN
        RAISE EXCEPTION 'Disagreements were created or changed.';
    END IF;

    IF EXISTS ((SELECT * FROM selections_before
               EXCEPT
               SELECT selection.* FROM permission_pilot.permission_selection selection
               JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
               WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36')
              UNION ALL
              (SELECT selection.* FROM permission_pilot.permission_selection selection
               JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
               WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
               EXCEPT SELECT * FROM selections_before)) THEN
        RAISE EXCEPTION 'The 36 pilot selections changed.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM catalogue_before before
        CROSS JOIN LATERAL (
            SELECT count(*) AS row_count,
                   md5(string_agg(to_jsonb(permission)::TEXT, E'\n'
                                  ORDER BY permission.permission_definition_id)) AS fingerprint
            FROM catalogue.permission_definition permission
        ) current_catalogue
        WHERE current_catalogue.row_count <> before.row_count
           OR current_catalogue.fingerprint IS DISTINCT FROM before.fingerprint
    ) THEN
        RAISE EXCEPTION 'Catalogue permission data changed.';
    END IF;
END;
$$;

SELECT 'analyst_reviews' AS test, count(*)::TEXT AS actual, '8' AS expected
FROM permission_pilot.classification_review review
JOIN permission_pilot.permission_selection selection USING (selection_id)
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind = 'analyst'
  AND review.reviewer_identifier = 'jon_bruce'
  AND review.review_round = 1
UNION ALL
SELECT 'primary_domains', count(*)::TEXT, '8'
FROM permission_pilot.review_domain_assignment assignment
JOIN permission_pilot.classification_review review USING (review_id)
JOIN permission_pilot.permission_selection selection USING (selection_id)
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind = 'analyst'
  AND review.reviewer_identifier = 'jon_bruce'
  AND review.review_round = 1
  AND assignment.assignment_kind = 'primary'
UNION ALL
SELECT 'secondary_domains', count(*)::TEXT, '11'
FROM permission_pilot.review_domain_assignment assignment
JOIN permission_pilot.classification_review review USING (review_id)
JOIN permission_pilot.permission_selection selection USING (selection_id)
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind = 'analyst'
  AND review.reviewer_identifier = 'jon_bruce'
  AND review.review_round = 1
  AND assignment.assignment_kind = 'secondary';

DROP TABLE disagreements_before;
DROP TABLE other_analyst_reviews_before;
DROP TABLE codex_domains_before;
DROP TABLE codex_reviews_before;
DROP TABLE selections_before;
DROP TABLE catalogue_before;
DROP TABLE target_domains_after_first_run;
DROP TABLE target_reviews_after_first_run;
DROP TABLE expected_domain_assignment;
DROP TABLE expected_analyst_review;
