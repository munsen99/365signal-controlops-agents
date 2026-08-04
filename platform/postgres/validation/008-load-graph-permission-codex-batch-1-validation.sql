\set ON_ERROR_STOP on

CREATE TEMPORARY TABLE expected_codex_permission (
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    PRIMARY KEY (permission_name, permission_type)
);

INSERT INTO expected_codex_permission VALUES
('User.Read', 'Delegated'),
('Directory.AccessAsUser.All', 'Delegated'),
('AuditLog.Read.All', 'Delegated'),
('AppRoleAssignment.ReadWrite.All', 'Application'),
('DeviceLocalCredential.Read.All', 'Application'),
('Sites.Selected', 'Application'),
('Teamwork.Migrate.All', 'Application'),
('Chat.Manage.Chat', 'RSC');

CREATE TEMPORARY TABLE expected_codex_domain (
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    domain_code TEXT NOT NULL,
    assignment_kind TEXT NOT NULL,
    PRIMARY KEY (permission_name, permission_type, domain_code)
);

INSERT INTO expected_codex_domain VALUES
('User.Read', 'Delegated', 'DIRECTORY_ORG_MANAGEMENT', 'primary'),
('Directory.AccessAsUser.All', 'Delegated', 'AUTHORIZATION_ACCESS_GOVERNANCE', 'primary'),
('Directory.AccessAsUser.All', 'Delegated', 'PRIVILEGED_ACCESS', 'secondary'),
('AuditLog.Read.All', 'Delegated', 'LOGGING_MONITORING_AUDIT', 'primary'),
('AppRoleAssignment.ReadWrite.All', 'Application', 'APPLICATION_IDENTITY_CONSENT', 'primary'),
('AppRoleAssignment.ReadWrite.All', 'Application', 'AUTHORIZATION_ACCESS_GOVERNANCE', 'secondary'),
('DeviceLocalCredential.Read.All', 'Application', 'ENDPOINT_DEVICE_MANAGEMENT', 'primary'),
('DeviceLocalCredential.Read.All', 'Application', 'AUTHENTICATION', 'secondary'),
('Sites.Selected', 'Application', 'SHAREPOINT_ONEDRIVE', 'primary'),
('Teamwork.Migrate.All', 'Application', 'MICROSOFT_TEAMS', 'primary'),
('Chat.Manage.Chat', 'RSC', 'MICROSOFT_TEAMS', 'primary'),
('Chat.Manage.Chat', 'RSC', 'AUTHORIZATION_ACCESS_GOVERNANCE', 'secondary');

-- Opaque snapshots prove blindness-sensitive records are unchanged without
-- returning analyst content to the validation output.
CREATE TEMPORARY TABLE analyst_review_state_before AS
SELECT count(*) AS row_count,
       md5(coalesce(string_agg(to_jsonb(review)::TEXT, E'\n'
                               ORDER BY review.review_id), '')) AS fingerprint
FROM permission_pilot.classification_review review
WHERE review.reviewer_kind = 'analyst';

CREATE TEMPORARY TABLE analyst_domain_state_before AS
SELECT count(*) AS row_count,
       md5(coalesce(string_agg(to_jsonb(assignment)::TEXT, E'\n'
                               ORDER BY assignment.review_id, assignment.domain_id), '')) AS fingerprint
FROM permission_pilot.review_domain_assignment assignment
JOIN permission_pilot.classification_review review USING (review_id)
WHERE review.reviewer_kind = 'analyst';

CREATE TEMPORARY TABLE disagreement_state_before AS
SELECT count(*) AS row_count,
       md5(coalesce(string_agg(to_jsonb(disagreement)::TEXT, E'\n'
                               ORDER BY disagreement.disagreement_id), '')) AS fingerprint
FROM permission_pilot.disagreement disagreement;

CREATE TEMPORARY TABLE catalogue_state_before AS
SELECT count(*) AS row_count,
       md5(string_agg(to_jsonb(permission)::TEXT, E'\n'
                      ORDER BY permission.permission_definition_id)) AS fingerprint
FROM catalogue.permission_definition permission;

CREATE TEMPORARY TABLE selection_state_before AS
SELECT selection.*
FROM permission_pilot.permission_selection selection
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36';

\ir ../init/008-load-graph-permission-codex-batch-1.sql

CREATE TEMPORARY TABLE codex_reviews_after_first_run AS
SELECT review.*
FROM permission_pilot.classification_review review
JOIN permission_pilot.permission_selection selection USING (selection_id)
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind = 'codex'
  AND review.reviewer_identifier = 'codex_independent_batch_1'
  AND review.review_round = 1;

CREATE TEMPORARY TABLE codex_domains_after_first_run AS
SELECT assignment.*
FROM permission_pilot.review_domain_assignment assignment
JOIN codex_reviews_after_first_run review USING (review_id);

\ir ../init/008-load-graph-permission-codex-batch-1.sql

DO $$
BEGIN
    IF (SELECT count(*) FROM codex_reviews_after_first_run) <> 8 THEN
        RAISE EXCEPTION 'Expected exactly eight Codex batch-1 reviews.';
    END IF;

    IF EXISTS (
        (SELECT permission_name, permission_type FROM expected_codex_permission
         EXCEPT
         SELECT permission.permission_name, permission.permission_type
         FROM permission_pilot.classification_review review
         JOIN permission_pilot.permission_selection selection USING (selection_id)
         JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
         JOIN catalogue.permission_definition permission USING (permission_definition_id)
         WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
           AND review.reviewer_kind = 'codex'
           AND review.reviewer_identifier = 'codex_independent_batch_1'
           AND review.review_round = 1)
        UNION ALL
        (SELECT permission.permission_name, permission.permission_type
         FROM permission_pilot.classification_review review
         JOIN permission_pilot.permission_selection selection USING (selection_id)
         JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
         JOIN catalogue.permission_definition permission USING (permission_definition_id)
         WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
           AND review.reviewer_kind = 'codex'
           AND review.reviewer_identifier = 'codex_independent_batch_1'
           AND review.review_round = 1
         EXCEPT SELECT permission_name, permission_type FROM expected_codex_permission)
    ) THEN
        RAISE EXCEPTION 'Codex reviewer is not limited to the exact eight permissions.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM codex_reviews_after_first_run
        WHERE access_level IS NULL OR capability IS NULL
           OR administrative_capability IS NULL OR privilege_level IS NULL
           OR data_sensitivity IS NULL OR destructive_potential IS NULL
           OR tenant_wide_impact IS NULL OR consent_sensitivity IS NULL
           OR classification_confidence IS NULL OR rationale IS NULL
           OR review_status <> 'submitted'
    ) THEN
        RAISE EXCEPTION 'A Codex review has a null controlled attribute or is not submitted.';
    END IF;

    IF EXISTS (
        SELECT review_id
        FROM codex_reviews_after_first_run review
        LEFT JOIN permission_pilot.review_domain_assignment assignment USING (review_id)
        GROUP BY review_id
        HAVING count(*) FILTER (WHERE assignment.assignment_kind = 'primary') <> 1
    ) THEN
        RAISE EXCEPTION 'A Codex review does not have exactly one primary domain.';
    END IF;

    IF EXISTS (
        (SELECT expected.permission_name, expected.permission_type,
                expected.domain_code, expected.assignment_kind
         FROM expected_codex_domain expected
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
           AND review.reviewer_kind = 'codex'
           AND review.reviewer_identifier = 'codex_independent_batch_1'
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
           AND review.reviewer_kind = 'codex'
           AND review.reviewer_identifier = 'codex_independent_batch_1'
           AND review.review_round = 1
         EXCEPT
         SELECT expected.permission_name, expected.permission_type,
                expected.domain_code, expected.assignment_kind
         FROM expected_codex_domain expected)
    ) THEN
        RAISE EXCEPTION 'Codex domain assignments differ from the expected set.';
    END IF;

    IF EXISTS (
        (SELECT * FROM codex_reviews_after_first_run
         EXCEPT
         SELECT review.*
         FROM permission_pilot.classification_review review
         JOIN permission_pilot.permission_selection selection USING (selection_id)
         JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
         WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
           AND review.reviewer_kind = 'codex'
           AND review.reviewer_identifier = 'codex_independent_batch_1'
           AND review.review_round = 1)
        UNION ALL
        (SELECT review.*
         FROM permission_pilot.classification_review review
         JOIN permission_pilot.permission_selection selection USING (selection_id)
         JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
         WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
           AND review.reviewer_kind = 'codex'
           AND review.reviewer_identifier = 'codex_independent_batch_1'
           AND review.review_round = 1
         EXCEPT SELECT * FROM codex_reviews_after_first_run)
    ) OR EXISTS (
        (SELECT * FROM codex_domains_after_first_run
         EXCEPT
         SELECT assignment.*
         FROM permission_pilot.review_domain_assignment assignment
         JOIN codex_reviews_after_first_run review USING (review_id))
        UNION ALL
        (SELECT assignment.*
         FROM permission_pilot.review_domain_assignment assignment
         JOIN codex_reviews_after_first_run review USING (review_id)
         EXCEPT SELECT * FROM codex_domains_after_first_run)
    ) THEN
        RAISE EXCEPTION 'The second migration run changed Codex rows.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM analyst_review_state_before before
        CROSS JOIN LATERAL (
            SELECT count(*) AS row_count,
                   md5(coalesce(string_agg(to_jsonb(review)::TEXT, E'\n'
                                           ORDER BY review.review_id), '')) AS fingerprint
            FROM permission_pilot.classification_review review
            WHERE review.reviewer_kind = 'analyst'
        ) current_state
        WHERE current_state.row_count <> before.row_count
           OR current_state.fingerprint IS DISTINCT FROM before.fingerprint
    ) OR EXISTS (
        SELECT 1 FROM analyst_domain_state_before before
        CROSS JOIN LATERAL (
            SELECT count(*) AS row_count,
                   md5(coalesce(string_agg(to_jsonb(assignment)::TEXT, E'\n'
                                           ORDER BY assignment.review_id,
                                                    assignment.domain_id), '')) AS fingerprint
            FROM permission_pilot.review_domain_assignment assignment
            JOIN permission_pilot.classification_review review USING (review_id)
            WHERE review.reviewer_kind = 'analyst'
        ) current_state
        WHERE current_state.row_count <> before.row_count
           OR current_state.fingerprint IS DISTINCT FROM before.fingerprint
    ) THEN
        RAISE EXCEPTION 'Analyst review content or domain assignments changed.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM disagreement_state_before before
        CROSS JOIN LATERAL (
            SELECT count(*) AS row_count,
                   md5(coalesce(string_agg(to_jsonb(disagreement)::TEXT, E'\n'
                                           ORDER BY disagreement.disagreement_id), '')) AS fingerprint
            FROM permission_pilot.disagreement disagreement
        ) current_state
        WHERE current_state.row_count <> before.row_count
           OR current_state.fingerprint IS DISTINCT FROM before.fingerprint
    ) THEN
        RAISE EXCEPTION 'Disagreements were created or changed.';
    END IF;

    IF EXISTS (
        (SELECT * FROM selection_state_before
         EXCEPT
         SELECT selection.* FROM permission_pilot.permission_selection selection
         JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
         WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36')
        UNION ALL
        (SELECT selection.* FROM permission_pilot.permission_selection selection
         JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
         WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
         EXCEPT SELECT * FROM selection_state_before)
    ) THEN
        RAISE EXCEPTION 'Pilot selections changed.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM catalogue_state_before before
        CROSS JOIN LATERAL (
            SELECT count(*) AS row_count,
                   md5(string_agg(to_jsonb(permission)::TEXT, E'\n'
                                  ORDER BY permission.permission_definition_id)) AS fingerprint
            FROM catalogue.permission_definition permission
        ) current_state
        WHERE current_state.row_count <> before.row_count
           OR current_state.fingerprint IS DISTINCT FROM before.fingerprint
    ) THEN
        RAISE EXCEPTION 'Catalogue permission data changed.';
    END IF;
END;
$$;

SELECT 'codex_reviews' AS test, count(*)::TEXT AS actual, '8' AS expected
FROM codex_reviews_after_first_run
UNION ALL
SELECT 'primary_domains', count(*)::TEXT, '8'
FROM codex_domains_after_first_run WHERE assignment_kind = 'primary'
UNION ALL
SELECT 'secondary_domains', count(*)::TEXT, '4'
FROM codex_domains_after_first_run WHERE assignment_kind = 'secondary'
UNION ALL
SELECT 'null_controlled_attributes', count(*)::TEXT, '0'
FROM codex_reviews_after_first_run
WHERE access_level IS NULL OR capability IS NULL
   OR administrative_capability IS NULL OR privilege_level IS NULL
   OR data_sensitivity IS NULL OR destructive_potential IS NULL
   OR tenant_wide_impact IS NULL OR consent_sensitivity IS NULL
   OR classification_confidence IS NULL;

DROP TABLE codex_domains_after_first_run;
DROP TABLE codex_reviews_after_first_run;
DROP TABLE selection_state_before;
DROP TABLE catalogue_state_before;
DROP TABLE disagreement_state_before;
DROP TABLE analyst_domain_state_before;
DROP TABLE analyst_review_state_before;
DROP TABLE expected_codex_domain;
DROP TABLE expected_codex_permission;
