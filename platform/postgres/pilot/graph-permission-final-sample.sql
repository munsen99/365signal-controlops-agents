\set ON_ERROR_STOP on

BEGIN READ ONLY;

-- Proposed final set: exact IDs and names observed in the live catalogue on
-- 2026-08-03. This query intentionally writes nothing.
WITH proposed(permission_definition_id, permission_type, permission_name,
              workload, capability_dimension, scope_dimension, risk_dimension,
              potential_multi_domain, selection_reason) AS (VALUES
('1d86a9f2-39a1-4bbb-8c4b-da7da84dfe65'::uuid,'Delegated','User.Read','identity','Read','resource_scoped','obvious_low',false,'Baseline low-risk signed-in-user profile permission.'),
('f4b2e6ec-dca8-42bf-b586-dd5a7e1b1dd0'::uuid,'Delegated','Directory.AccessAsUser.All','identity','Unknown','tenant_wide','obvious_critical',true,'Broad delegated directory reach with access inherited from the user.'),
('c4c7d6a1-abcf-4924-aaa3-25a4e67cb91b'::uuid,'Delegated','UserAuthenticationMethod.ReadWrite.All','identity','ReadWrite','tenant_wide','obvious_critical',true,'Authentication-method administration tests identity and credential sensitivity.'),
('c5b0e406-8660-4277-824e-2b65ae322905'::uuid,'Delegated','Application.ReadWrite.All','application_identity','ReadWrite','tenant_wide','obvious_critical',true,'Application and service-principal administration with cross-domain implications.'),
('8e8802b8-bcd8-4b86-8dca-a658d74dcc06'::uuid,'Delegated','AppRoleAssignment.ReadWrite.All','application_identity','ReadWrite','tenant_wide','obvious_critical',true,'Permission-grant and app-role administration is consent-sensitive and multi-domain.'),
('fcc36dfa-32eb-4e77-a922-92a36f555c94'::uuid,'Delegated','Mail.Read','mail','Read','resource_scoped','ambiguous',false,'User-scoped mailbox read tests data sensitivity despite non-admin consent.'),
('3bdaae4f-e170-45e3-801b-f813c3a682f9'::uuid,'Delegated','Mail.Send','mail','Write','resource_scoped','ambiguous',false,'Send-as-user capability is write-like although catalogue access class is Unknown.'),
('3020382c-0bf8-4f8f-9ed3-4cc2bcd0dcda'::uuid,'Delegated','Sites.Read.All','sharepoint','Read','tenant_wide','ambiguous',false,'All-site read tests broad content exposure without admin consent.'),
('89e4c815-3575-4fd6-a9ec-174353bfdb62'::uuid,'Delegated','Sites.FullControl.All','sharepoint','FullControl','tenant_wide','obvious_critical',false,'Explicit full control tests the catalogue Unknown/access-class gap.'),
('3c3f5df2-b261-4fe2-86ea-c28cc38676ec'::uuid,'Delegated','Sites.Selected','sharepoint','Selected','resource_scoped','ambiguous',false,'Selected-resource grant tests scope dependent on external assignment.'),
('e499cc99-424a-4170-930a-d2014aaf807a'::uuid,'Delegated','Chat.Read','teams','Read','resource_scoped','ambiguous',false,'Non-admin chat read tests sensitive collaboration data in user context.'),
('29706f89-b740-4768-9fd6-3b4b89a6970c'::uuid,'Delegated','TeamSettings.ReadWrite.All','teams','ReadWrite','tenant_wide','obvious_critical',false,'Tenant-wide Teams configuration mutation.'),
('0e875970-e5aa-48d7-a5e4-4a8974bd16f9'::uuid,'Delegated','SecurityIncident.ReadWrite.All','security','ReadWrite','tenant_wide','obvious_critical',true,'Security incident mutation spans security operations and audit concerns.'),
('b01a37a3-c984-45bc-86b9-f3da81d91735'::uuid,'Delegated','DeviceManagementManagedDevices.PrivilegedOperations.All','endpoint_device','Unknown','tenant_wide','obvious_critical',true,'High-impact remote device actions expose an Unknown access-class case.'),
('c55ad4ea-441b-4126-aa42-98710c72968c'::uuid,'Delegated','AuditLog.Read.All','audit','Read','tenant_wide','ambiguous',true,'Broad audit access tests security versus assurance domain mapping.'),
('768aaaab-544c-451f-b356-17424d124e41'::uuid,'Delegated','Policy.ReadWrite.ConditionalAccess','identity','ReadWrite','tenant_wide','obvious_critical',true,'Conditional Access policy mutation crosses identity, security and governance.'),
('34ef9694-5502-4eaa-ad7b-c6d365a88bb4'::uuid,'Application','User.ReadBasic.All','identity','Read','tenant_wide','obvious_low',false,'Limited-profile application read is a low-risk comparator.'),
('cd3e54b8-a570-44f3-bec3-3851b9dea9e8'::uuid,'Application','Directory.ReadWrite.All','identity','ReadWrite','tenant_wide','obvious_critical',true,'Unattended broad directory mutation.'),
('8d3f20cd-63ed-457b-be15-965a17ba233b'::uuid,'Application','Application.Read.All','application_identity','Read','tenant_wide','ambiguous',true,'Application/service-principal inventory read tests sensitive metadata.'),
('5695b827-75ea-4024-8869-d5b6ef4c4ecf'::uuid,'Application','AppRoleAssignment.ReadWrite.All','application_identity','ReadWrite','tenant_wide','obvious_critical',true,'Unattended application-permission grant administration.'),
('e012bca4-7839-4709-9885-2792fc52b883'::uuid,'Application','Mail.ReadWrite','mail','ReadWrite','tenant_wide','obvious_critical',false,'Unattended read/write access to every mailbox.'),
('437a606f-9695-48cb-991b-ad6a8a956c48'::uuid,'Application','Mail.Send','mail','Write','tenant_wide','obvious_critical',false,'Send as any user provides explicit write-like coverage from Unknown.'),
('52342463-0829-40c9-9515-58d2ac1ed9f1'::uuid,'Application','Sites.Manage.All','sharepoint','Manage','tenant_wide','obvious_critical',false,'Explicit Manage permission covers destructive SharePoint administration.'),
('a18e7c97-76fd-4e28-be6b-771aefc623c0'::uuid,'Application','Sites.Selected','sharepoint','Selected','resource_scoped','ambiguous',false,'Application selected-site grant tests assignment-dependent effective scope.'),
('cbe82429-09c1-4eb2-a729-3573dee3284f'::uuid,'Application','Teamwork.Migrate.All','teams','Unknown','tenant_wide','obvious_critical',true,'Identity impersonation and backdating make this an ambiguous multi-domain case.'),
('afd96bdd-764d-4a25-af97-8c8a44a77c93'::uuid,'Application','SecurityEvents.Read.All','security','Read','tenant_wide','ambiguous',true,'Unattended security telemetry read tests sensitivity and audit overlap.'),
('30ea68ad-9554-4396-89dc-748b6e243950'::uuid,'Application','SecurityActions.ReadWrite.All','security','ReadWrite','tenant_wide','obvious_critical',false,'Unattended security response action mutation.'),
('81b8672f-1507-4601-903b-f7247386e2af'::uuid,'Application','DeviceLocalCredential.Read.All','endpoint_device','Read','tenant_wide','obvious_critical',true,'Read-labelled permission exposes device passwords and credential sensitivity.'),
('ee9a647f-cce7-4768-9182-c6819ea2b576'::uuid,'Application','DeviceManagementConfiguration.ReadWrite.All','endpoint_device','ReadWrite','tenant_wide','obvious_critical',true,'Unattended Intune policy and assignment mutation.'),
('b9ff92a9-25a2-4fdf-83d1-dd9937559f4e'::uuid,'Application','AuditLogsQuery.Read.All','audit','Read','tenant_wide','ambiguous',true,'Cross-service audit query creates security, workload and assurance overlap.'),
('8fb06ad4-3b31-410e-b672-f495b898017e'::uuid,'RSC','ChannelMessage.Read.Group','teams','Read','resource_scoped','ambiguous',false,'RSC message read tests team-bound content exposure.'),
('194a03aa-b431-449a-94c6-02d7ca7764d2'::uuid,'RSC','ChannelSettings.ReadWrite.Group','teams','ReadWrite','resource_scoped','ambiguous',false,'RSC configuration mutation tests team-bound write access.'),
('3283255f-d5ea-47f5-ad53-e5bb3d643072'::uuid,'RSC','Chat.Manage.Chat','teams','Manage','resource_scoped','obvious_critical',true,'Chat management includes membership and data-access grants.'),
('98ca686f-7389-4c99-9f08-72f7104fec9f'::uuid,'RSC','Calls.AccessMedia.Chat','teams','Unknown','resource_scoped','ambiguous',true,'Live media access is sensitive but catalogue access class is Unknown.'),
('357d33e1-bef3-4486-b5a2-7ffe35d1d1ae'::uuid,'RSC','OnlineMeeting.ReadBasic.Chat','teams','Read','resource_scoped','obvious_low',false,'Limited RSC meeting metadata is a low-risk scoped comparator.'),
('fda12f36-decc-4272-8046-b28479e586ca'::uuid,'RSC','TeamsActivity.Send.User','teams','Write','resource_scoped','ambiguous',false,'User-bound notification send adds write-like RSC coverage from Unknown.')
)
SELECT pd.permission_definition_id, pd.permission_name, pd.permission_type,
       pd.display_name, pd.description, pd.admin_consent_required,
       pd.is_current, p.selection_reason,
       ARRAY[p.workload, p.capability_dimension, p.scope_dimension,
             p.risk_dimension] ||
         CASE WHEN p.potential_multi_domain THEN ARRAY['potential_multi_domain']::text[]
              ELSE ARRAY[]::text[] END AS sampling_dimensions
FROM proposed p
JOIN catalogue.permission_definition pd
  ON pd.permission_definition_id=p.permission_definition_id
 AND pd.permission_type=p.permission_type
 AND pd.permission_name=p.permission_name
ORDER BY p.permission_type, p.permission_name;

ROLLBACK;
