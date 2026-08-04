\set ON_ERROR_STOP on

BEGIN;

CREATE TEMPORARY TABLE proposed_codex_review (
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    access_level TEXT NOT NULL,
    capability TEXT NOT NULL,
    administrative_capability BOOLEAN NOT NULL,
    privilege_level TEXT NOT NULL,
    data_sensitivity TEXT NOT NULL,
    destructive_potential TEXT NOT NULL,
    tenant_wide_impact BOOLEAN NOT NULL,
    consent_sensitivity TEXT NOT NULL,
    classification_confidence TEXT NOT NULL,
    rationale TEXT NOT NULL,
    PRIMARY KEY (permission_name, permission_type)
) ON COMMIT DROP;

INSERT INTO proposed_codex_review VALUES
('User.Read', 'Delegated', 'owned', 'read', false, 'low', 'low', 'none', false, 'low', 'high',
 'Delegated read access is limited to the signed-in user’s own basic profile and company information; it grants no directory administration or mutation authority.'),
('Directory.AccessAsUser.All', 'Delegated', 'all', 'unknown', true, 'high', 'high', 'high', true, 'critical', 'medium',
 'The app receives the signed-in user’s effective directory authority, so capability and impact depend on that user while potentially extending to privileged tenant-wide directory operations.'),
('AuditLog.Read.All', 'Delegated', 'all', 'read', false, 'high', 'high', 'none', true, 'high', 'high',
 'Delegated tenant-wide read access exposes sensitive audit telemetry but does not itself modify audit data or configuration.'),
('AppRoleAssignment.ReadWrite.All', 'Application', 'all', 'manage', true, 'critical', 'moderate', 'critical', true, 'critical', 'high',
 'Unattended authority to manage application permission grants and app role assignments can establish or remove tenant-wide application access to any API.'),
('DeviceLocalCredential.Read.All', 'Application', 'all', 'read', true, 'critical', 'restricted', 'none', true, 'critical', 'high',
 'Unattended tenant-wide read access exposes device local passwords; the Graph operation is non-mutating, but the credential disclosure is highly privileged and sensitive.'),
('Sites.Selected', 'Application', 'selected', 'unknown', true, 'unknown', 'unknown', 'unknown', false, 'high', 'medium',
 'The app-only grant is confined to separately selected SharePoint sites, while its effective operations and impact depend on the permissions assigned in SharePoint.'),
('Teamwork.Migrate.All', 'Application', 'all', 'write', true, 'critical', 'high', 'high', true, 'critical', 'high',
 'Unattended tenant-wide message creation with another user’s identity and arbitrary timestamps grants powerful migration authority with severe communications-integrity impact.'),
('Chat.Manage.Chat', 'RSC', 'selected', 'manage', true, 'high', 'high', 'high', false, 'high', 'high',
 'The resource-specific app grant can manage one chat, its membership and access to its data, creating significant but chat-bounded authorization and content impact.');

CREATE TEMPORARY TABLE proposed_codex_domain (
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    domain_code TEXT NOT NULL,
    assignment_kind TEXT NOT NULL,
    PRIMARY KEY (permission_name, permission_type, domain_code),
    FOREIGN KEY (permission_name, permission_type)
        REFERENCES proposed_codex_review(permission_name, permission_type)
) ON COMMIT DROP;

INSERT INTO proposed_codex_domain VALUES
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

DO $$
BEGIN
    IF (SELECT count(*) FROM proposed_codex_review) <> 8 THEN
        RAISE EXCEPTION 'Expected exactly eight proposed Codex reviews.';
    END IF;

    IF EXISTS (
        SELECT permission_name, permission_type
        FROM proposed_codex_domain
        GROUP BY permission_name, permission_type
        HAVING count(*) FILTER (WHERE assignment_kind = 'primary') <> 1
    ) THEN
        RAISE EXCEPTION 'Every proposed Codex review must have exactly one primary domain.';
    END IF;

    IF (SELECT count(*)
        FROM proposed_codex_review proposed
        JOIN permission_pilot.pilot_definition pilot
          ON pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
        JOIN permission_pilot.permission_selection selection
          ON selection.pilot_id = pilot.pilot_id
         AND selection.sample_stage = 'final'
        JOIN catalogue.permission_definition permission
          ON permission.permission_definition_id = selection.permission_definition_id
         AND permission.permission_name = proposed.permission_name
         AND permission.permission_type = proposed.permission_type) <> 8 THEN
        RAISE EXCEPTION 'All eight permissions must resolve to final pilot selections.';
    END IF;

    IF (SELECT count(DISTINCT domain.domain_code)
        FROM proposed_codex_domain proposed
        JOIN catalogue.controlops_domain domain
          ON domain.domain_code = proposed.domain_code)
       <> (SELECT count(DISTINCT domain_code) FROM proposed_codex_domain) THEN
        RAISE EXCEPTION 'Every proposed domain code must exist.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM permission_pilot.classification_review review
        JOIN permission_pilot.permission_selection selection USING (selection_id)
        JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
        JOIN catalogue.permission_definition permission USING (permission_definition_id)
        JOIN proposed_codex_review proposed
          ON proposed.permission_name = permission.permission_name
         AND proposed.permission_type = permission.permission_type
        JOIN permission_pilot.review_domain_assignment assignment USING (review_id)
        JOIN catalogue.controlops_domain domain USING (domain_id)
        LEFT JOIN proposed_codex_domain expected
          ON expected.permission_name = proposed.permission_name
         AND expected.permission_type = proposed.permission_type
         AND expected.domain_code = domain.domain_code
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND review.reviewer_kind = 'codex'
          AND review.reviewer_identifier = 'codex_independent_batch_1'
          AND review.review_round = 1
          AND expected.domain_code IS NULL
    ) THEN
        RAISE EXCEPTION 'A target Codex review has an assignment outside the proposed set.';
    END IF;
END;
$$;

INSERT INTO permission_pilot.classification_review (
    selection_id, reviewer_kind, reviewer_identifier, review_round,
    access_level, capability, administrative_capability, privilege_level,
    data_sensitivity, destructive_potential, tenant_wide_impact,
    consent_sensitivity, classification_confidence, rationale, review_status
)
SELECT selection.selection_id, 'codex', 'codex_independent_batch_1', 1,
       proposed.access_level, proposed.capability,
       proposed.administrative_capability, proposed.privilege_level,
       proposed.data_sensitivity, proposed.destructive_potential,
       proposed.tenant_wide_impact, proposed.consent_sensitivity,
       proposed.classification_confidence, proposed.rationale, 'submitted'
FROM proposed_codex_review proposed
JOIN permission_pilot.pilot_definition pilot
  ON pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
JOIN permission_pilot.permission_selection selection
  ON selection.pilot_id = pilot.pilot_id
 AND selection.sample_stage = 'final'
JOIN catalogue.permission_definition permission
  ON permission.permission_definition_id = selection.permission_definition_id
 AND permission.permission_name = proposed.permission_name
 AND permission.permission_type = proposed.permission_type
ON CONFLICT (selection_id, reviewer_kind, reviewer_identifier, review_round)
DO UPDATE SET
    access_level = EXCLUDED.access_level,
    capability = EXCLUDED.capability,
    administrative_capability = EXCLUDED.administrative_capability,
    privilege_level = EXCLUDED.privilege_level,
    data_sensitivity = EXCLUDED.data_sensitivity,
    destructive_potential = EXCLUDED.destructive_potential,
    tenant_wide_impact = EXCLUDED.tenant_wide_impact,
    consent_sensitivity = EXCLUDED.consent_sensitivity,
    classification_confidence = EXCLUDED.classification_confidence,
    rationale = EXCLUDED.rationale,
    review_status = EXCLUDED.review_status,
    updated_at = now()
WHERE (permission_pilot.classification_review.access_level,
       permission_pilot.classification_review.capability,
       permission_pilot.classification_review.administrative_capability,
       permission_pilot.classification_review.privilege_level,
       permission_pilot.classification_review.data_sensitivity,
       permission_pilot.classification_review.destructive_potential,
       permission_pilot.classification_review.tenant_wide_impact,
       permission_pilot.classification_review.consent_sensitivity,
       permission_pilot.classification_review.classification_confidence,
       permission_pilot.classification_review.rationale,
       permission_pilot.classification_review.review_status)
  IS DISTINCT FROM
      (EXCLUDED.access_level, EXCLUDED.capability,
       EXCLUDED.administrative_capability, EXCLUDED.privilege_level,
       EXCLUDED.data_sensitivity, EXCLUDED.destructive_potential,
       EXCLUDED.tenant_wide_impact, EXCLUDED.consent_sensitivity,
       EXCLUDED.classification_confidence, EXCLUDED.rationale,
       EXCLUDED.review_status);

UPDATE permission_pilot.review_domain_assignment assignment
SET assignment_kind = 'secondary'
FROM permission_pilot.classification_review review
JOIN permission_pilot.permission_selection selection USING (selection_id)
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
JOIN catalogue.permission_definition permission USING (permission_definition_id)
JOIN proposed_codex_domain proposed
  ON proposed.permission_name = permission.permission_name
 AND proposed.permission_type = permission.permission_type
JOIN catalogue.controlops_domain domain
  ON domain.domain_code = proposed.domain_code
WHERE assignment.review_id = review.review_id
  AND assignment.domain_id = domain.domain_id
  AND pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind = 'codex'
  AND review.reviewer_identifier = 'codex_independent_batch_1'
  AND review.review_round = 1
  AND proposed.assignment_kind = 'secondary'
  AND assignment.assignment_kind = 'primary';

INSERT INTO permission_pilot.review_domain_assignment (
    review_id, domain_id, assignment_kind, mapping_rationale
)
SELECT review.review_id, domain.domain_id, proposed.assignment_kind,
       approved.rationale
FROM proposed_codex_domain proposed
JOIN proposed_codex_review approved USING (permission_name, permission_type)
JOIN permission_pilot.pilot_definition pilot
  ON pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
JOIN permission_pilot.permission_selection selection
  ON selection.pilot_id = pilot.pilot_id
 AND selection.sample_stage = 'final'
JOIN catalogue.permission_definition permission
  ON permission.permission_definition_id = selection.permission_definition_id
 AND permission.permission_name = proposed.permission_name
 AND permission.permission_type = proposed.permission_type
JOIN permission_pilot.classification_review review
  ON review.selection_id = selection.selection_id
 AND review.reviewer_kind = 'codex'
 AND review.reviewer_identifier = 'codex_independent_batch_1'
 AND review.review_round = 1
JOIN catalogue.controlops_domain domain ON domain.domain_code = proposed.domain_code
ON CONFLICT (review_id, domain_id) DO UPDATE SET
    assignment_kind = EXCLUDED.assignment_kind,
    mapping_rationale = EXCLUDED.mapping_rationale
WHERE (permission_pilot.review_domain_assignment.assignment_kind,
       permission_pilot.review_domain_assignment.mapping_rationale)
  IS DISTINCT FROM (EXCLUDED.assignment_kind, EXCLUDED.mapping_rationale);

DO $$
BEGIN
    IF (SELECT count(*)
        FROM permission_pilot.classification_review review
        JOIN permission_pilot.permission_selection selection USING (selection_id)
        JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
        JOIN catalogue.permission_definition permission USING (permission_definition_id)
        JOIN proposed_codex_review proposed USING (permission_name, permission_type)
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND review.reviewer_kind = 'codex'
          AND review.reviewer_identifier = 'codex_independent_batch_1'
          AND review.review_round = 1) <> 8 THEN
        RAISE EXCEPTION 'Expected exactly eight persisted Codex reviews.';
    END IF;

    IF EXISTS (
        SELECT review.review_id
        FROM permission_pilot.classification_review review
        JOIN permission_pilot.permission_selection selection USING (selection_id)
        JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
        JOIN catalogue.permission_definition permission USING (permission_definition_id)
        JOIN proposed_codex_review proposed USING (permission_name, permission_type)
        LEFT JOIN permission_pilot.review_domain_assignment assignment USING (review_id)
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND review.reviewer_kind = 'codex'
          AND review.reviewer_identifier = 'codex_independent_batch_1'
          AND review.review_round = 1
        GROUP BY review.review_id
        HAVING count(*) FILTER (WHERE assignment.assignment_kind = 'primary') <> 1
    ) THEN
        RAISE EXCEPTION 'Every persisted Codex review must have one primary domain.';
    END IF;
END;
$$;

COMMIT;
