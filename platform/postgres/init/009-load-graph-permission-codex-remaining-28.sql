\set ON_ERROR_STOP on

BEGIN;

CREATE TEMPORARY TABLE proposed_codex_review (
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    capability TEXT NOT NULL,
    access_level TEXT NOT NULL,
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
('Application.Read.All','Application','read','all',true,'high','moderate','none',true,'high','high','Unattended tenant-wide inventory access exposes application and service-principal configuration, but does not change identities, credentials, grants or consent.'),
('AuditLogsQuery.Read.All','Application','read','all',true,'high','high','none',true,'high','high','Unattended cross-service audit-log query exposes sensitive tenant-wide operational and security history without mutation authority.'),
('DeviceManagementConfiguration.ReadWrite.All','Application','read_write','all',true,'high','high','high',true,'critical','high','Unattended tenant-wide authority can change Intune device configuration, compliance policies and group assignments, directly weakening or disrupting endpoint controls.'),
('Directory.ReadWrite.All','Application','read_write','all',true,'critical','high','high',true,'critical','high','Unattended tenant-wide directory mutation covers users, groups and other directory data; deletion of users and groups is excluded, but broad identity and membership changes remain directly available.'),
('Mail.ReadWrite','Application','read_write','all',true,'critical','restricted','high',true,'critical','high','Unattended access can read, create, change and delete content in every mailbox, exposing restricted communications and directly affecting tenant-wide data integrity and availability.'),
('Mail.Send','Application','execute','all',true,'critical','moderate','moderate',true,'critical','high','Unattended authority to send as any user enables tenant-wide impersonation and communication integrity abuse; it does not itself read or delete mailbox content.'),
('SecurityActions.ReadWrite.All','Application','read_write','all',true,'high','high','high',true,'critical','high','Unattended tenant-wide mutation of security actions can alter automated response records and outcomes, directly affecting security operations and response integrity.'),
('SecurityEvents.Read.All','Application','read','all',true,'high','high','none',true,'high','high','Unattended tenant-wide read access exposes sensitive security-event telemetry but grants no direct response or configuration mutation.'),
('Sites.Manage.All','Application','manage','all',true,'critical','high','high',true,'critical','high','Unattended tenant-wide management can create or delete libraries and lists across all site collections, with direct SharePoint structure and availability impact.'),
('User.ReadBasic.All','Application','read','all',false,'moderate','low','none',true,'moderate','high','Unattended tenant-wide access is limited to basic user profile fields and grants no directory mutation or privileged administration.'),
('Application.ReadWrite.All','Delegated','manage','all',true,'critical','high','critical',true,'critical','high','On behalf of an authorized signed-in user, the app can create, change and delete applications and service principals and manage non-Graph app-role assignments, directly controlling persistent application identities and access.'),
('AppRoleAssignment.ReadWrite.All','Delegated','manage','all',true,'critical','moderate','critical',true,'critical','high','On behalf of an authorized signed-in user, the app can establish or remove application permission grants to any API and application assignments for any app, creating persistent privileged access.'),
('Chat.Read','Delegated','read','owned',false,'moderate','high','none',false,'moderate','high','The app can read the signed-in user’s one-to-one and group chat threads, exposing sensitive collaboration content without mutation or chat-management authority.'),
('DeviceManagementManagedDevices.PrivilegedOperations.All','Delegated','execute','all',true,'critical','high','critical',true,'critical','high','On behalf of an authorized user, the app can invoke high-impact remote device operations including wipe and passcode reset, granting direct tenant device disruption and credential-control authority.'),
('Mail.Read','Delegated','read','owned',false,'moderate','restricted','none',false,'moderate','high','The app reads the signed-in user’s mailbox, exposing restricted message content without direct mailbox mutation.'),
('Mail.Send','Delegated','execute','unknown',false,'high','moderate','moderate',false,'high','medium','The app can send mail in the signed-in user context; effective send-as reach may inherit mailbox delegation or other external assignments, so a fixed owned or all scope is not defensible from this permission record alone.'),
('Policy.ReadWrite.ConditionalAccess','Delegated','manage','all',true,'critical','high','critical',true,'critical','high','On behalf of an authorized administrator, the app can change tenant-wide Conditional Access policy, directly enabling security-control weakening, lockout or bypass.'),
('SecurityIncident.ReadWrite.All','Delegated','read_write','all',true,'high','high','moderate',true,'high','high','On behalf of an authorized user, the app can read and change tenant-wide security incident records, affecting investigation workflow and evidence integrity but not directly changing protected resources.'),
('Sites.FullControl.All','Delegated','manage','all',true,'critical','restricted','critical',true,'critical','high','On behalf of an authorized user, the app receives full control of every site collection, including broad content, configuration and destructive authority.'),
('Sites.Read.All','Delegated','read','all',false,'high','restricted','none',true,'high','high','The app can read documents and list items across all site collections in the signed-in user context, exposing tenant-wide organizational content without mutation.'),
('Sites.Selected','Delegated','unknown','selected',false,'unknown','unknown','unknown',false,'moderate','medium','The Graph permission limits the app to separately selected site collections, but the effective operations, privilege, data exposure and destructive authority depend on the SharePoint permissions configured for those sites.'),
('TeamSettings.ReadWrite.All','Delegated','read_write','all',true,'high','moderate','moderate',true,'high','high','On behalf of an authorized user, the app can read and change settings for every team, directly affecting tenant-wide Teams configuration but not team content or membership.'),
('UserAuthenticationMethod.ReadWrite.All','Delegated','manage','all',true,'critical','high','high',true,'critical','high','On behalf of an authorized user, the app can change authentication methods for all users the user can access; secrets are not readable, but method replacement can materially affect account access and authentication security.'),
('Calls.AccessMedia.Chat','RSC','unknown','selected',true,'high','restricted','none',false,'high','medium','The resource-specific grant exposes live media streams for calls associated with one chat or meeting; the record does not establish whether access is read-only or interactive, so capability remains unknown.'),
('ChannelMessage.Read.Group','RSC','read','selected',false,'high','high','none',false,'high','high','The resource-specific app grant reads channel messages within one assigned team, exposing sensitive collaboration content without mutation authority.'),
('ChannelSettings.ReadWrite.Group','RSC','read_write','selected',true,'moderate','low','moderate',false,'moderate','high','The resource-specific app grant reads and changes channel names, descriptions and settings within one team, creating bounded configuration and integrity impact.'),
('OnlineMeeting.ReadBasic.Chat','RSC','read','selected',false,'low','moderate','none',false,'low','high','The resource-specific app grant reads only basic meeting metadata and notifications for meetings associated with one chat, without content or mutation authority.'),
('TeamsActivity.Send.User','RSC','write','selected',false,'moderate','low','low',false,'moderate','high','The resource-specific app grant creates activity-feed notifications for one assigned user; it cannot read the feed or administer the user, but can affect notification integrity.' );

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
('Application.Read.All','Application','APPLICATION_IDENTITY_CONSENT','primary'),
('AuditLogsQuery.Read.All','Application','LOGGING_MONITORING_AUDIT','primary'),
('AuditLogsQuery.Read.All','Application','AUDIT_ASSURANCE','secondary'),
('DeviceManagementConfiguration.ReadWrite.All','Application','ENDPOINT_DEVICE_MANAGEMENT','primary'),
('Directory.ReadWrite.All','Application','DIRECTORY_ORG_MANAGEMENT','primary'),
('Directory.ReadWrite.All','Application','IDENTITY_LIFECYCLE','secondary'),
('Mail.ReadWrite','Application','EXCHANGE_ONLINE','primary'),
('Mail.Send','Application','EXCHANGE_ONLINE','primary'),
('SecurityActions.ReadWrite.All','Application','SECURITY_AUTOMATION_INTEGRATION','primary'),
('SecurityActions.ReadWrite.All','Application','INCIDENT_INVESTIGATION_RESPONSE','secondary'),
('SecurityEvents.Read.All','Application','THREAT_PROTECTION_DEFENDER','primary'),
('SecurityEvents.Read.All','Application','LOGGING_MONITORING_AUDIT','secondary'),
('Sites.Manage.All','Application','SHAREPOINT_ONEDRIVE','primary'),
('User.ReadBasic.All','Application','DIRECTORY_ORG_MANAGEMENT','primary'),
('Application.ReadWrite.All','Delegated','APPLICATION_IDENTITY_CONSENT','primary'),
('Application.ReadWrite.All','Delegated','AUTHORIZATION_ACCESS_GOVERNANCE','secondary'),
('AppRoleAssignment.ReadWrite.All','Delegated','APPLICATION_IDENTITY_CONSENT','primary'),
('AppRoleAssignment.ReadWrite.All','Delegated','AUTHORIZATION_ACCESS_GOVERNANCE','secondary'),
('AppRoleAssignment.ReadWrite.All','Delegated','PRIVILEGED_ACCESS','secondary'),
('Chat.Read','Delegated','MICROSOFT_TEAMS','primary'),
('DeviceManagementManagedDevices.PrivilegedOperations.All','Delegated','ENDPOINT_DEVICE_MANAGEMENT','primary'),
('DeviceManagementManagedDevices.PrivilegedOperations.All','Delegated','PRIVILEGED_ACCESS','secondary'),
('Mail.Read','Delegated','EXCHANGE_ONLINE','primary'),
('Mail.Send','Delegated','EXCHANGE_ONLINE','primary'),
('Policy.ReadWrite.ConditionalAccess','Delegated','CONDITIONAL_ACCESS','primary'),
('Policy.ReadWrite.ConditionalAccess','Delegated','PRIVILEGED_ACCESS','secondary'),
('SecurityIncident.ReadWrite.All','Delegated','INCIDENT_INVESTIGATION_RESPONSE','primary'),
('Sites.FullControl.All','Delegated','SHAREPOINT_ONEDRIVE','primary'),
('Sites.Read.All','Delegated','SHAREPOINT_ONEDRIVE','primary'),
('Sites.Selected','Delegated','SHAREPOINT_ONEDRIVE','primary'),
('TeamSettings.ReadWrite.All','Delegated','MICROSOFT_TEAMS','primary'),
('UserAuthenticationMethod.ReadWrite.All','Delegated','AUTHENTICATION','primary'),
('UserAuthenticationMethod.ReadWrite.All','Delegated','PRIVILEGED_ACCESS','secondary'),
('Calls.AccessMedia.Chat','RSC','MICROSOFT_TEAMS','primary'),
('ChannelMessage.Read.Group','RSC','MICROSOFT_TEAMS','primary'),
('ChannelSettings.ReadWrite.Group','RSC','MICROSOFT_TEAMS','primary'),
('OnlineMeeting.ReadBasic.Chat','RSC','MICROSOFT_TEAMS','primary'),
('TeamsActivity.Send.User','RSC','MICROSOFT_TEAMS','primary');

CREATE TEMPORARY TABLE target_selection ON COMMIT DROP AS
SELECT selection.selection_id, selection.permission_definition_id,
       permission.permission_name, permission.permission_type
FROM permission_pilot.pilot_definition pilot
JOIN permission_pilot.permission_selection selection USING (pilot_id)
JOIN catalogue.permission_definition permission USING (permission_definition_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND selection.sample_stage = 'final'
  AND NOT EXISTS (
      SELECT 1
      FROM permission_pilot.classification_review batch1
      WHERE batch1.selection_id = selection.selection_id
        AND batch1.reviewer_kind = 'codex'
        AND batch1.reviewer_identifier = 'codex_independent_batch_1'
        AND batch1.review_round = 1
  );

DO $$
BEGIN
    IF (SELECT count(*) FROM target_selection) <> 28 THEN
        RAISE EXCEPTION 'Expected exactly 28 final selections outside Codex batch 1; found %.', (SELECT count(*) FROM target_selection);
    END IF;
    IF (SELECT count(*) FROM proposed_codex_review) <> 28 THEN
        RAISE EXCEPTION 'Expected exactly 28 proposed Codex reviews.';
    END IF;
    IF EXISTS ((SELECT permission_name, permission_type FROM target_selection EXCEPT SELECT permission_name, permission_type FROM proposed_codex_review)
               UNION ALL
               (SELECT permission_name, permission_type FROM proposed_codex_review EXCEPT SELECT permission_name, permission_type FROM target_selection)) THEN
        RAISE EXCEPTION 'Proposed reviews do not exactly match the database-derived remaining 28 selections.';
    END IF;
    IF EXISTS (SELECT permission_name, permission_type FROM proposed_codex_domain GROUP BY permission_name, permission_type HAVING count(*) FILTER (WHERE assignment_kind='primary') <> 1) THEN
        RAISE EXCEPTION 'Every proposed review must have exactly one primary domain.';
    END IF;
    IF (SELECT count(DISTINCT proposed.domain_code) FROM proposed_codex_domain proposed JOIN catalogue.controlops_domain domain USING (domain_code))
       <> (SELECT count(DISTINCT domain_code) FROM proposed_codex_domain) THEN
        RAISE EXCEPTION 'Every proposed domain code must exist.';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM permission_pilot.classification_review review
        JOIN target_selection target USING (selection_id)
        JOIN permission_pilot.review_domain_assignment assignment USING (review_id)
        JOIN catalogue.controlops_domain domain USING (domain_id)
        LEFT JOIN proposed_codex_domain expected
          ON expected.permission_name=target.permission_name
         AND expected.permission_type=target.permission_type
         AND expected.domain_code=domain.domain_code
         AND expected.assignment_kind=assignment.assignment_kind
        WHERE review.reviewer_kind='codex' AND review.reviewer_identifier='codex_remaining_28' AND review.review_round=1
          AND expected.domain_code IS NULL
    ) THEN
        RAISE EXCEPTION 'A target review has an unexpected or conflicting domain assignment.';
    END IF;
END;
$$;

INSERT INTO permission_pilot.classification_review (
    selection_id, reviewer_kind, reviewer_identifier, review_round,
    capability, access_level, administrative_capability, privilege_level,
    data_sensitivity, destructive_potential, tenant_wide_impact,
    consent_sensitivity, classification_confidence, rationale, review_status
)
SELECT target.selection_id, 'codex', 'codex_remaining_28', 1,
       proposed.capability, proposed.access_level, proposed.administrative_capability,
       proposed.privilege_level, proposed.data_sensitivity, proposed.destructive_potential,
       proposed.tenant_wide_impact, proposed.consent_sensitivity,
       proposed.classification_confidence, proposed.rationale, 'submitted'
FROM proposed_codex_review proposed
JOIN target_selection target USING (permission_name, permission_type)
ON CONFLICT (selection_id, reviewer_kind, reviewer_identifier, review_round)
DO UPDATE SET capability=EXCLUDED.capability, access_level=EXCLUDED.access_level,
    administrative_capability=EXCLUDED.administrative_capability,
    privilege_level=EXCLUDED.privilege_level, data_sensitivity=EXCLUDED.data_sensitivity,
    destructive_potential=EXCLUDED.destructive_potential,
    tenant_wide_impact=EXCLUDED.tenant_wide_impact,
    consent_sensitivity=EXCLUDED.consent_sensitivity,
    classification_confidence=EXCLUDED.classification_confidence,
    rationale=EXCLUDED.rationale, review_status=EXCLUDED.review_status,
    updated_at=now()
WHERE (permission_pilot.classification_review.capability,
       permission_pilot.classification_review.access_level,
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
      (EXCLUDED.capability, EXCLUDED.access_level, EXCLUDED.administrative_capability,
       EXCLUDED.privilege_level, EXCLUDED.data_sensitivity, EXCLUDED.destructive_potential,
       EXCLUDED.tenant_wide_impact, EXCLUDED.consent_sensitivity,
       EXCLUDED.classification_confidence, EXCLUDED.rationale, EXCLUDED.review_status);

INSERT INTO permission_pilot.review_domain_assignment (review_id, domain_id, assignment_kind, mapping_rationale)
SELECT review.review_id, domain.domain_id, proposed.assignment_kind, approved.rationale
FROM proposed_codex_domain proposed
JOIN proposed_codex_review approved USING (permission_name, permission_type)
JOIN target_selection target USING (permission_name, permission_type)
JOIN permission_pilot.classification_review review
  ON review.selection_id=target.selection_id
 AND review.reviewer_kind='codex' AND review.reviewer_identifier='codex_remaining_28' AND review.review_round=1
JOIN catalogue.controlops_domain domain USING (domain_code)
ON CONFLICT (review_id, domain_id) DO UPDATE SET mapping_rationale=EXCLUDED.mapping_rationale
WHERE permission_pilot.review_domain_assignment.assignment_kind=EXCLUDED.assignment_kind
  AND permission_pilot.review_domain_assignment.mapping_rationale IS DISTINCT FROM EXCLUDED.mapping_rationale;

DO $$
BEGIN
    IF (SELECT count(*) FROM permission_pilot.classification_review review JOIN target_selection target USING(selection_id)
        WHERE review.reviewer_kind='codex' AND review.reviewer_identifier='codex_remaining_28' AND review.review_round=1) <> 28 THEN
        RAISE EXCEPTION 'Expected exactly 28 persisted Codex remaining-batch reviews.';
    END IF;
    IF EXISTS (
        SELECT review.review_id
        FROM permission_pilot.classification_review review
        JOIN target_selection target USING(selection_id)
        LEFT JOIN permission_pilot.review_domain_assignment assignment USING(review_id)
        WHERE review.reviewer_kind='codex' AND review.reviewer_identifier='codex_remaining_28' AND review.review_round=1
        GROUP BY review.review_id
        HAVING count(*) FILTER (WHERE assignment.assignment_kind='primary') <> 1
    ) THEN
        RAISE EXCEPTION 'Every persisted review must have exactly one primary domain.';
    END IF;
END;
$$;

COMMIT;
