\set ON_ERROR_STOP on

BEGIN;

CREATE TEMPORARY TABLE proposed_analyst_review (
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    classification_confidence TEXT NOT NULL,
    rationale TEXT NOT NULL,
    PRIMARY KEY (permission_name, permission_type)
) ON COMMIT DROP;

INSERT INTO proposed_analyst_review VALUES
('User.Read', 'Delegated', 'high',
 'Reads the signed-in user’s basic directory profile and organization information. Although commonly used during app sign-in, it does not administer authentication methods, credentials, sessions, or authentication policy.'),
('Directory.AccessAsUser.All', 'Delegated', 'high',
 'Grants an application the signed-in user’s effective directory access. The primary concern is delegated authorization, while privileged-access exposure arises when the signed-in user holds elevated directory permissions.'),
('AuditLog.Read.All', 'Delegated', 'high',
 'Grants tenant-wide read access to audit activity. The primary capability is access to logging and audit telemetry, with secondary relevance to assurance and control-evidence activities.'),
('AppRoleAssignment.ReadWrite.All', 'Application', 'high',
 'Grants unattended tenant-wide authority to manage application permission grants and app role assignments. This directly governs application identity and consent, changes effective authorization, and can establish durable privileged application access.'),
('DeviceLocalCredential.Read.All', 'Application', 'high',
 'Grants unattended tenant-wide access to managed-device local credential properties, including passwords. The permission is read-only at the Graph layer, but disclosure of those credentials can enable elevated device access and subsequent destructive activity.'),
('Sites.Selected', 'Application', 'medium',
 'Enables an application to receive separately assigned access to selected SharePoint site collections. The permission is resource-scoped, but effective privilege, data sensitivity and destructive potential depend on the downstream site grant.'),
('Teamwork.Migrate.All', 'Application', 'high',
 'Grants unattended tenant-wide authority to create Teams chat and channel messages using another user’s identity and arbitrary timestamps. It can be abused to fabricate communications without the represented user being signed in, creating critical application-consent and audit-integrity risk.'),
('Chat.Manage.Chat', 'RSC', 'high',
 'Grants an application resource-scoped authority to manage a Teams chat, its membership and access to its data. Although limited to a specific chat, it materially changes authorization and data access through the RSC application-consent model.');

CREATE TEMPORARY TABLE proposed_domain_assignment (
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    domain_code TEXT NOT NULL,
    assignment_kind TEXT NOT NULL,
    PRIMARY KEY (permission_name, permission_type, domain_code),
    FOREIGN KEY (permission_name, permission_type)
        REFERENCES proposed_analyst_review(permission_name, permission_type)
) ON COMMIT DROP;

INSERT INTO proposed_domain_assignment VALUES
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

DO $$
BEGIN
    IF (SELECT count(*) FROM proposed_analyst_review) <> 8 THEN
        RAISE EXCEPTION 'Expected exactly eight proposed analyst reviews.';
    END IF;

    IF EXISTS (
        SELECT permission_name, permission_type
        FROM proposed_domain_assignment
        GROUP BY permission_name, permission_type
        HAVING count(*) FILTER (WHERE assignment_kind = 'primary') <> 1
    ) THEN
        RAISE EXCEPTION 'Every proposed review must have exactly one primary domain.';
    END IF;

    IF (SELECT count(*)
        FROM proposed_analyst_review proposed
        JOIN permission_pilot.pilot_definition pilot
          ON pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
        JOIN permission_pilot.permission_selection selection
          ON selection.pilot_id = pilot.pilot_id
         AND selection.sample_stage = 'final'
        JOIN catalogue.permission_definition permission
          ON permission.permission_definition_id = selection.permission_definition_id
         AND permission.permission_name = proposed.permission_name
         AND permission.permission_type = proposed.permission_type) <> 8 THEN
        RAISE EXCEPTION 'All eight approved permissions must resolve to final pilot selections.';
    END IF;

    IF (SELECT count(DISTINCT domain.domain_code)
        FROM proposed_domain_assignment proposed
        JOIN catalogue.controlops_domain domain
          ON domain.domain_code = proposed.domain_code)
       <> (SELECT count(DISTINCT domain_code) FROM proposed_domain_assignment) THEN
        RAISE EXCEPTION 'Every approved domain code must exist in the catalogue.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM permission_pilot.classification_review review
        JOIN permission_pilot.permission_selection selection USING (selection_id)
        JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
        JOIN catalogue.permission_definition permission USING (permission_definition_id)
        JOIN proposed_analyst_review proposed
          ON proposed.permission_name = permission.permission_name
         AND proposed.permission_type = permission.permission_type
        JOIN permission_pilot.review_domain_assignment assignment
          USING (review_id)
        LEFT JOIN proposed_domain_assignment expected
          ON expected.permission_name = proposed.permission_name
         AND expected.permission_type = proposed.permission_type
         AND expected.domain_code = (
             SELECT domain_code FROM catalogue.controlops_domain
             WHERE domain_id = assignment.domain_id
         )
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND review.reviewer_kind = 'analyst'
          AND review.reviewer_identifier = 'jon_bruce'
          AND review.review_round = 1
          AND expected.domain_code IS NULL
    ) THEN
        RAISE EXCEPTION 'A target review has an existing domain outside the approved set.';
    END IF;
END;
$$;

INSERT INTO permission_pilot.classification_review (
    selection_id, reviewer_kind, reviewer_identifier, review_round,
    access_level, capability, administrative_capability, privilege_level,
    data_sensitivity, destructive_potential, tenant_wide_impact,
    consent_sensitivity, classification_confidence, rationale, review_status
)
SELECT selection.selection_id, 'analyst', 'jon_bruce', 1,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       proposed.classification_confidence, proposed.rationale, 'submitted'
FROM proposed_analyst_review proposed
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

-- Demote an approved secondary first so a changed primary can be
-- refreshed without transiently violating the one-primary unique index.
UPDATE permission_pilot.review_domain_assignment assignment
SET assignment_kind = 'secondary'
FROM permission_pilot.classification_review review
JOIN permission_pilot.permission_selection selection USING (selection_id)
JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
JOIN catalogue.permission_definition permission USING (permission_definition_id)
JOIN proposed_domain_assignment proposed
  ON proposed.permission_name = permission.permission_name
 AND proposed.permission_type = permission.permission_type
JOIN catalogue.controlops_domain domain
  ON domain.domain_code = proposed.domain_code
WHERE assignment.review_id = review.review_id
  AND assignment.domain_id = domain.domain_id
  AND pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND review.reviewer_kind = 'analyst'
  AND review.reviewer_identifier = 'jon_bruce'
  AND review.review_round = 1
  AND proposed.assignment_kind = 'secondary'
  AND assignment.assignment_kind = 'primary';

INSERT INTO permission_pilot.review_domain_assignment (
    review_id, domain_id, assignment_kind, mapping_rationale
)
SELECT review.review_id, domain.domain_id, proposed.assignment_kind,
       approved.rationale
FROM proposed_domain_assignment proposed
JOIN proposed_analyst_review approved
  USING (permission_name, permission_type)
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
 AND review.reviewer_kind = 'analyst'
 AND review.reviewer_identifier = 'jon_bruce'
 AND review.review_round = 1
JOIN catalogue.controlops_domain domain
  ON domain.domain_code = proposed.domain_code
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
        JOIN proposed_analyst_review proposed
          USING (permission_name, permission_type)
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND review.reviewer_kind = 'analyst'
          AND review.reviewer_identifier = 'jon_bruce'
          AND review.review_round = 1) <> 8 THEN
        RAISE EXCEPTION 'Expected exactly eight persisted analyst reviews.';
    END IF;

    IF EXISTS (
        SELECT review.review_id
        FROM permission_pilot.classification_review review
        JOIN permission_pilot.permission_selection selection USING (selection_id)
        JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
        JOIN catalogue.permission_definition permission USING (permission_definition_id)
        JOIN proposed_analyst_review proposed USING (permission_name, permission_type)
        LEFT JOIN permission_pilot.review_domain_assignment assignment USING (review_id)
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND review.reviewer_kind = 'analyst'
          AND review.reviewer_identifier = 'jon_bruce'
          AND review.review_round = 1
        GROUP BY review.review_id
        HAVING count(*) FILTER (WHERE assignment.assignment_kind = 'primary') <> 1
    ) THEN
        RAISE EXCEPTION 'Every persisted analyst review must have one primary domain.';
    END IF;
END;
$$;

COMMIT;
