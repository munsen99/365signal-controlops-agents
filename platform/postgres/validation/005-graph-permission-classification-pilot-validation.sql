\set ON_ERROR_STOP on

BEGIN READ ONLY;

SELECT count(*) AS baseline_classifications,
       (SELECT count(*) FROM catalogue.permission_classification_domain) AS baseline_domains,
       md5(coalesce(string_agg(to_jsonb(pc)::text, E'\n' ORDER BY pc.permission_classification_id),'')) AS baseline_fingerprint
FROM catalogue.permission_classification pc \gset

WITH final_set(permission_type,permission_name,workload,capability,scope,risk,multi) AS (VALUES
('Delegated','User.Read','identity','Read','resource_scoped','obvious_low',false),
('Delegated','Directory.AccessAsUser.All','identity','Unknown','tenant_wide','obvious_critical',true),
('Delegated','UserAuthenticationMethod.ReadWrite.All','identity','ReadWrite','tenant_wide','obvious_critical',true),
('Delegated','Application.ReadWrite.All','application_identity','ReadWrite','tenant_wide','obvious_critical',true),
('Delegated','AppRoleAssignment.ReadWrite.All','application_identity','ReadWrite','tenant_wide','obvious_critical',true),
('Delegated','Mail.Read','mail','Read','resource_scoped','ambiguous',false),
('Delegated','Mail.Send','mail','Write','resource_scoped','ambiguous',false),
('Delegated','Sites.Read.All','sharepoint','Read','tenant_wide','ambiguous',false),
('Delegated','Sites.FullControl.All','sharepoint','FullControl','tenant_wide','obvious_critical',false),
('Delegated','Sites.Selected','sharepoint','Selected','resource_scoped','ambiguous',false),
('Delegated','Chat.Read','teams','Read','resource_scoped','ambiguous',false),
('Delegated','TeamSettings.ReadWrite.All','teams','ReadWrite','tenant_wide','obvious_critical',false),
('Delegated','SecurityIncident.ReadWrite.All','security','ReadWrite','tenant_wide','obvious_critical',true),
('Delegated','DeviceManagementManagedDevices.PrivilegedOperations.All','endpoint_device','Unknown','tenant_wide','obvious_critical',true),
('Delegated','AuditLog.Read.All','audit','Read','tenant_wide','ambiguous',true),
('Delegated','Policy.ReadWrite.ConditionalAccess','identity','ReadWrite','tenant_wide','obvious_critical',true),
('Application','User.ReadBasic.All','identity','Read','tenant_wide','obvious_low',false),
('Application','Directory.ReadWrite.All','identity','ReadWrite','tenant_wide','obvious_critical',true),
('Application','Application.Read.All','application_identity','Read','tenant_wide','ambiguous',true),
('Application','AppRoleAssignment.ReadWrite.All','application_identity','ReadWrite','tenant_wide','obvious_critical',true),
('Application','Mail.ReadWrite','mail','ReadWrite','tenant_wide','obvious_critical',false),
('Application','Mail.Send','mail','Write','tenant_wide','obvious_critical',false),
('Application','Sites.Manage.All','sharepoint','Manage','tenant_wide','obvious_critical',false),
('Application','Sites.Selected','sharepoint','Selected','resource_scoped','ambiguous',false),
('Application','Teamwork.Migrate.All','teams','Unknown','tenant_wide','obvious_critical',true),
('Application','SecurityEvents.Read.All','security','Read','tenant_wide','ambiguous',true),
('Application','SecurityActions.ReadWrite.All','security','ReadWrite','tenant_wide','obvious_critical',false),
('Application','DeviceLocalCredential.Read.All','endpoint_device','Read','tenant_wide','obvious_critical',true),
('Application','DeviceManagementConfiguration.ReadWrite.All','endpoint_device','ReadWrite','tenant_wide','obvious_critical',true),
('Application','AuditLogsQuery.Read.All','audit','Read','tenant_wide','ambiguous',true),
('RSC','ChannelMessage.Read.Group','teams','Read','resource_scoped','ambiguous',false),
('RSC','ChannelSettings.ReadWrite.Group','teams','ReadWrite','resource_scoped','ambiguous',false),
('RSC','Chat.Manage.Chat','teams','Manage','resource_scoped','obvious_critical',true),
('RSC','Calls.AccessMedia.Chat','teams','Unknown','resource_scoped','ambiguous',true),
('RSC','OnlineMeeting.ReadBasic.Chat','teams','Read','resource_scoped','obvious_low',false),
('RSC','TeamsActivity.Send.User','teams','Write','resource_scoped','ambiguous',false)
), measures AS (
 SELECT count(*) sample_size,
   count(pd.permission_definition_id) catalogue_matches,
   count(DISTINCT (f.permission_type,f.permission_name)) unique_selections,
   count(DISTINCT f.permission_type) types,
   count(DISTINCT workload) workloads, count(DISTINCT capability) capabilities,
   count(DISTINCT scope) scopes, count(DISTINCT risk) risks,
   count(*) FILTER (WHERE multi) multi_domain
 FROM final_set f LEFT JOIN catalogue.permission_definition pd
   ON pd.permission_type=f.permission_type AND pd.permission_name=f.permission_name AND pd.is_current
)
SELECT test, actual, expected, passed FROM measures m CROSS JOIN LATERAL (VALUES
 ('final_sample_size_30_40',m.sample_size::text,'30..40',m.sample_size BETWEEN 30 AND 40),
 ('catalogue_matches',m.catalogue_matches::text,m.sample_size::text,m.catalogue_matches=m.sample_size),
 ('unique_permission_type',m.unique_selections::text,m.sample_size::text,m.unique_selections=m.sample_size),
 ('permission_types',m.types::text,'3',m.types=3),
 ('workloads',m.workloads::text,'8',m.workloads=8),
 ('capability_dimensions',m.capabilities::text,'7',m.capabilities=7),
 ('scope_dimensions',m.scopes::text,'2',m.scopes=2),
 ('risk_dimensions',m.risks::text,'3',m.risks=3),
 ('potential_multi_domain',m.multi_domain::text,'>0',m.multi_domain>0)
) result(test,actual,expected,passed);

SELECT 'production_classifications_unchanged' AS test,
       count(*) = :'baseline_classifications'::bigint
       AND (SELECT count(*) FROM catalogue.permission_classification_domain) = :'baseline_domains'::bigint
       AND md5(coalesce(string_agg(to_jsonb(pc)::text,E'\n' ORDER BY pc.permission_classification_id),'')) = :'baseline_fingerprint' AS passed
FROM catalogue.permission_classification pc;

ROLLBACK;
