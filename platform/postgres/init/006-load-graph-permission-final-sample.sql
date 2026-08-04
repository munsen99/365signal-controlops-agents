\set ON_ERROR_STOP on

BEGIN;

CREATE TEMPORARY TABLE proposed_final_sample (
    permission_definition_id UUID PRIMARY KEY,
    permission_type TEXT NOT NULL,
    permission_name TEXT NOT NULL,
    workload TEXT NOT NULL,
    capability_dimension TEXT NOT NULL,
    scope_dimension TEXT NOT NULL,
    risk_dimension TEXT NOT NULL,
    potential_multi_domain BOOLEAN NOT NULL,
    selection_reason TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO proposed_final_sample VALUES
('1d86a9f2-39a1-4bbb-8c4b-da7da84dfe65','Delegated','User.Read','identity','Read','resource_scoped','obvious_low',false,'Baseline low-risk signed-in-user profile permission.'),
('f4b2e6ec-dca8-42bf-b586-dd5a7e1b1dd0','Delegated','Directory.AccessAsUser.All','identity','Unknown','tenant_wide','obvious_critical',true,'Broad delegated directory reach with access inherited from the user.'),
('c4c7d6a1-abcf-4924-aaa3-25a4e67cb91b','Delegated','UserAuthenticationMethod.ReadWrite.All','identity','ReadWrite','tenant_wide','obvious_critical',true,'Authentication-method administration tests identity and credential sensitivity.'),
('c5b0e406-8660-4277-824e-2b65ae322905','Delegated','Application.ReadWrite.All','application_identity','ReadWrite','tenant_wide','obvious_critical',true,'Application and service-principal administration with cross-domain implications.'),
('8e8802b8-bcd8-4b86-8dca-a658d74dcc06','Delegated','AppRoleAssignment.ReadWrite.All','application_identity','ReadWrite','tenant_wide','obvious_critical',true,'Permission-grant and app-role administration is consent-sensitive and multi-domain.'),
('fcc36dfa-32eb-4e77-a922-92a36f555c94','Delegated','Mail.Read','mail','Read','resource_scoped','ambiguous',false,'User-scoped mailbox read tests data sensitivity despite non-admin consent.'),
('3bdaae4f-e170-45e3-801b-f813c3a682f9','Delegated','Mail.Send','mail','Write','resource_scoped','ambiguous',false,'Send-as-user capability is write-like although catalogue access class is Unknown.'),
('3020382c-0bf8-4f8f-9ed3-4cc2bcd0dcda','Delegated','Sites.Read.All','sharepoint','Read','tenant_wide','ambiguous',false,'All-site read tests broad content exposure without admin consent.'),
('89e4c815-3575-4fd6-a9ec-174353bfdb62','Delegated','Sites.FullControl.All','sharepoint','FullControl','tenant_wide','obvious_critical',false,'Explicit full control tests the catalogue Unknown/access-class gap.'),
('3c3f5df2-b261-4fe2-86ea-c28cc38676ec','Delegated','Sites.Selected','sharepoint','Selected','resource_scoped','ambiguous',false,'Selected-resource grant tests scope dependent on external assignment.'),
('e499cc99-424a-4170-930a-d2014aaf807a','Delegated','Chat.Read','teams','Read','resource_scoped','ambiguous',false,'Non-admin chat read tests sensitive collaboration data in user context.'),
('29706f89-b740-4768-9fd6-3b4b89a6970c','Delegated','TeamSettings.ReadWrite.All','teams','ReadWrite','tenant_wide','obvious_critical',false,'Tenant-wide Teams configuration mutation.'),
('0e875970-e5aa-48d7-a5e4-4a8974bd16f9','Delegated','SecurityIncident.ReadWrite.All','security','ReadWrite','tenant_wide','obvious_critical',true,'Security incident mutation spans security operations and audit concerns.'),
('b01a37a3-c984-45bc-86b9-f3da81d91735','Delegated','DeviceManagementManagedDevices.PrivilegedOperations.All','endpoint_device','Unknown','tenant_wide','obvious_critical',true,'High-impact remote device actions expose an Unknown access-class case.'),
('c55ad4ea-441b-4126-aa42-98710c72968c','Delegated','AuditLog.Read.All','audit','Read','tenant_wide','ambiguous',true,'Broad audit access tests security versus assurance domain mapping.'),
('768aaaab-544c-451f-b356-17424d124e41','Delegated','Policy.ReadWrite.ConditionalAccess','identity','ReadWrite','tenant_wide','obvious_critical',true,'Conditional Access policy mutation crosses identity, security and governance.'),
('34ef9694-5502-4eaa-ad7b-c6d365a88bb4','Application','User.ReadBasic.All','identity','Read','tenant_wide','obvious_low',false,'Limited-profile application read is a low-risk comparator.'),
('cd3e54b8-a570-44f3-bec3-3851b9dea9e8','Application','Directory.ReadWrite.All','identity','ReadWrite','tenant_wide','obvious_critical',true,'Unattended broad directory mutation.'),
('8d3f20cd-63ed-457b-be15-965a17ba233b','Application','Application.Read.All','application_identity','Read','tenant_wide','ambiguous',true,'Application/service-principal inventory read tests sensitive metadata.'),
('5695b827-75ea-4024-8869-d5b6ef4c4ecf','Application','AppRoleAssignment.ReadWrite.All','application_identity','ReadWrite','tenant_wide','obvious_critical',true,'Unattended application-permission grant administration.'),
('e012bca4-7839-4709-9885-2792fc52b883','Application','Mail.ReadWrite','mail','ReadWrite','tenant_wide','obvious_critical',false,'Unattended read/write access to every mailbox.'),
('437a606f-9695-48cb-991b-ad6a8a956c48','Application','Mail.Send','mail','Write','tenant_wide','obvious_critical',false,'Send as any user provides explicit write-like coverage from Unknown.'),
('52342463-0829-40c9-9515-58d2ac1ed9f1','Application','Sites.Manage.All','sharepoint','Manage','tenant_wide','obvious_critical',false,'Explicit Manage permission covers destructive SharePoint administration.'),
('a18e7c97-76fd-4e28-be6b-771aefc623c0','Application','Sites.Selected','sharepoint','Selected','resource_scoped','ambiguous',false,'Application selected-site grant tests assignment-dependent effective scope.'),
('cbe82429-09c1-4eb2-a729-3573dee3284f','Application','Teamwork.Migrate.All','teams','Unknown','tenant_wide','obvious_critical',true,'Identity impersonation and backdating make this an ambiguous multi-domain case.'),
('afd96bdd-764d-4a25-af97-8c8a44a77c93','Application','SecurityEvents.Read.All','security','Read','tenant_wide','ambiguous',true,'Unattended security telemetry read tests sensitivity and audit overlap.'),
('30ea68ad-9554-4396-89dc-748b6e243950','Application','SecurityActions.ReadWrite.All','security','ReadWrite','tenant_wide','obvious_critical',false,'Unattended security response action mutation.'),
('81b8672f-1507-4601-903b-f7247386e2af','Application','DeviceLocalCredential.Read.All','endpoint_device','Read','tenant_wide','obvious_critical',true,'Read-labelled permission exposes device passwords and credential sensitivity.'),
('ee9a647f-cce7-4768-9182-c6819ea2b576','Application','DeviceManagementConfiguration.ReadWrite.All','endpoint_device','ReadWrite','tenant_wide','obvious_critical',true,'Unattended Intune policy and assignment mutation.'),
('b9ff92a9-25a2-4fdf-83d1-dd9937559f4e','Application','AuditLogsQuery.Read.All','audit','Read','tenant_wide','ambiguous',true,'Cross-service audit query creates security, workload and assurance overlap.'),
('8fb06ad4-3b31-410e-b672-f495b898017e','RSC','ChannelMessage.Read.Group','teams','Read','resource_scoped','ambiguous',false,'RSC message read tests team-bound content exposure.'),
('194a03aa-b431-449a-94c6-02d7ca7764d2','RSC','ChannelSettings.ReadWrite.Group','teams','ReadWrite','resource_scoped','ambiguous',false,'RSC configuration mutation tests team-bound write access.'),
('3283255f-d5ea-47f5-ad53-e5bb3d643072','RSC','Chat.Manage.Chat','teams','Manage','resource_scoped','obvious_critical',true,'Chat management includes membership and data-access grants.'),
('98ca686f-7389-4c99-9f08-72f7104fec9f','RSC','Calls.AccessMedia.Chat','teams','Unknown','resource_scoped','ambiguous',true,'Live media access is sensitive but catalogue access class is Unknown.'),
('357d33e1-bef3-4486-b5a2-7ffe35d1d1ae','RSC','OnlineMeeting.ReadBasic.Chat','teams','Read','resource_scoped','obvious_low',false,'Limited RSC meeting metadata is a low-risk scoped comparator.'),
('fda12f36-decc-4272-8046-b28479e586ca','RSC','TeamsActivity.Send.User','teams','Write','resource_scoped','ambiguous',false,'User-bound notification send adds write-like RSC coverage from Unknown.');

DO $$
BEGIN
    IF (SELECT count(*) FROM proposed_final_sample) <> 36 THEN
        RAISE EXCEPTION 'Expected exactly 36 proposed final sample rows.';
    END IF;

    IF (SELECT count(*) FROM proposed_final_sample p
        JOIN catalogue.permission_definition pd
          ON pd.permission_definition_id = p.permission_definition_id
         AND pd.permission_type = p.permission_type
         AND pd.permission_name = p.permission_name) <> 36 THEN
        RAISE EXCEPTION 'All 36 proposed rows must match catalogue ID, type and name.';
    END IF;

    IF EXISTS (
        SELECT permission_type, count(*)
        FROM proposed_final_sample
        GROUP BY permission_type
        HAVING (permission_type = 'Application' AND count(*) <> 14)
            OR (permission_type = 'Delegated' AND count(*) <> 16)
            OR (permission_type = 'RSC' AND count(*) <> 6)
            OR permission_type NOT IN ('Application', 'Delegated', 'RSC')
    ) OR (SELECT count(DISTINCT permission_type) FROM proposed_final_sample) <> 3 THEN
        RAISE EXCEPTION 'Expected Application 14, Delegated 16 and RSC 6.';
    END IF;
END;
$$;

WITH catalogue_baseline AS (
    SELECT count(*) AS row_count,
           md5(string_agg(
               to_jsonb(pd)::text,
               E'\n' ORDER BY pd.permission_definition_id
           )) AS catalogue_fingerprint
    FROM catalogue.permission_definition pd
)
INSERT INTO permission_pilot.pilot_definition (
    pilot_code, pilot_name, purpose, status,
    target_sample_min, target_sample_max,
    catalogue_baseline_count, catalogue_baseline_fingerprint
)
SELECT
    'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36',
    'Microsoft Graph permission classification final sample',
    'Independent analyst and Codex classification of the approved 36-permission final sample.',
    'approved', 36, 36, row_count, catalogue_fingerprint
FROM catalogue_baseline
ON CONFLICT (pilot_code) DO UPDATE SET
    pilot_name = EXCLUDED.pilot_name,
    purpose = EXCLUDED.purpose,
    target_sample_min = EXCLUDED.target_sample_min,
    target_sample_max = EXCLUDED.target_sample_max,
    catalogue_baseline_count = EXCLUDED.catalogue_baseline_count,
    catalogue_baseline_fingerprint = EXCLUDED.catalogue_baseline_fingerprint,
    updated_at = now()
WHERE (permission_pilot.pilot_definition.pilot_name,
       permission_pilot.pilot_definition.purpose,
       permission_pilot.pilot_definition.target_sample_min,
       permission_pilot.pilot_definition.target_sample_max,
       permission_pilot.pilot_definition.catalogue_baseline_count,
       permission_pilot.pilot_definition.catalogue_baseline_fingerprint)
  IS DISTINCT FROM
      (EXCLUDED.pilot_name, EXCLUDED.purpose,
       EXCLUDED.target_sample_min, EXCLUDED.target_sample_max,
       EXCLUDED.catalogue_baseline_count, EXCLUDED.catalogue_baseline_fingerprint);

INSERT INTO permission_pilot.permission_selection (
    pilot_id, permission_definition_id, sample_stage,
    selection_reason, sampling_dimensions
)
SELECT pdef.pilot_id, proposed.permission_definition_id, 'final',
       proposed.selection_reason,
       ARRAY[proposed.workload, proposed.capability_dimension,
             proposed.scope_dimension, proposed.risk_dimension] ||
       CASE WHEN proposed.potential_multi_domain
            THEN ARRAY['potential_multi_domain']::TEXT[]
            ELSE ARRAY[]::TEXT[] END
FROM proposed_final_sample proposed
CROSS JOIN permission_pilot.pilot_definition pdef
WHERE pdef.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
ON CONFLICT (pilot_id, permission_definition_id, sample_stage) DO UPDATE SET
    selection_reason = EXCLUDED.selection_reason,
    sampling_dimensions = EXCLUDED.sampling_dimensions
WHERE (permission_pilot.permission_selection.selection_reason,
       permission_pilot.permission_selection.sampling_dimensions)
  IS DISTINCT FROM (EXCLUDED.selection_reason, EXCLUDED.sampling_dimensions);

DO $$
DECLARE
    loaded_count INTEGER;
BEGIN
    SELECT count(*) INTO loaded_count
    FROM permission_pilot.permission_selection s
    JOIN permission_pilot.pilot_definition p USING (pilot_id)
    WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
      AND s.sample_stage = 'final';

    IF loaded_count <> 36 THEN
        RAISE EXCEPTION 'Expected exactly 36 persisted final selections; found %.', loaded_count;
    END IF;

    IF EXISTS (
        SELECT pd.permission_type, count(*)
        FROM permission_pilot.permission_selection s
        JOIN permission_pilot.pilot_definition p USING (pilot_id)
        JOIN catalogue.permission_definition pd USING (permission_definition_id)
        WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND s.sample_stage = 'final'
        GROUP BY pd.permission_type
        HAVING (pd.permission_type = 'Application' AND count(*) <> 14)
            OR (pd.permission_type = 'Delegated' AND count(*) <> 16)
            OR (pd.permission_type = 'RSC' AND count(*) <> 6)
            OR pd.permission_type NOT IN ('Application', 'Delegated', 'RSC')
    ) OR (
        SELECT count(DISTINCT pd.permission_type)
        FROM permission_pilot.permission_selection s
        JOIN permission_pilot.pilot_definition p USING (pilot_id)
        JOIN catalogue.permission_definition pd USING (permission_definition_id)
        WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND s.sample_stage = 'final'
    ) <> 3 THEN
        RAISE EXCEPTION 'Persisted distribution must be Application 14, Delegated 16 and RSC 6.';
    END IF;
END;
$$;

COMMIT;
