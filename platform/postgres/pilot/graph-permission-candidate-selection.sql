\set ON_ERROR_STOP on

BEGIN READ ONLY;

-- Heuristic labels are sampling aids, not classifications. Stable hashes make
-- the approximately 90-row result repeatable for an unchanged live catalogue.
WITH labelled AS (
  SELECT pd.*,
    CASE
      WHEN permission_name ~* 'Application|AppRole|ServicePrincipal|Oauth|Consent' THEN 'application_identity'
      WHEN permission_name ~* 'AuditLog|Reports' THEN 'audit'
      WHEN permission_name ~* 'Device|Intune|CloudPC' THEN 'endpoint_device'
      WHEN permission_name ~* 'Mail|Mailbox|Exchange' THEN 'mail'
      WHEN permission_name ~* 'Sites|Files|SharePoint|FileStorage' THEN 'sharepoint'
      WHEN permission_name ~* 'Security|Threat|Incident|Alert' THEN 'security'
      WHEN permission_name ~* 'Team|Chat|Channel|Call|Meeting' THEN 'teams'
      WHEN permission_name ~* 'User|Group|Directory|Role|Policy|Identity|Authentication' THEN 'identity'
      ELSE NULL
    END AS workload,
    CASE
      WHEN permission_name ~* 'FullControl' THEN 'FullControl'
      WHEN access_class = 'Read-Selected' OR permission_name ~* 'Selected' THEN 'Selected'
      WHEN access_class = 'ReadWrite' THEN 'ReadWrite'
      WHEN access_class = 'Manage' THEN 'Manage'
      WHEN access_class IN ('Read','Read-Limited') THEN 'Read'
      WHEN permission_name ~* '(^|\.)Write($|\.)|Send|Create|Delete|Update|Edit|Command' THEN 'Write'
      ELSE 'Unknown'
    END AS capability_sample,
    CASE WHEN permission_type='RSC' OR permission_name ~* 'Selected|\.Chat$|\.Group$|\.User$|OwnedBy|WhereInstalled'
         THEN 'resource_scoped' ELSE 'tenant_or_subject_scoped' END AS scope_sample,
    CASE
      WHEN permission_name ~* 'FullControl|AccessAsUser|AppRoleAssignment|PrivilegedOperations|Password|Credential|ConditionalAccess|ReadWrite\.All|Migrate'
        THEN 'obvious_critical'
      WHEN access_class IN ('Unknown','Manage','Consent-Grant') OR permission_name ~* 'Selected|OwnedBy|WhereInstalled'
        THEN 'ambiguous'
      ELSE 'obvious_low_or_read_only'
    END AS risk_sample,
    CASE WHEN permission_name ~* '(User|Group|Directory|Application).*(Mail|Team|Security|Device)|AuditLogsQuery|AppRoleAssignment|ConditionalAccess'
         THEN true ELSE false END AS potential_multi_domain
  FROM catalogue.permission_definition pd
  WHERE pd.is_current
), eligible AS (
  SELECT *, row_number() OVER (
      PARTITION BY permission_type, workload, capability_sample
      ORDER BY md5(permission_definition_id::text)
    ) AS stratum_rank
  FROM labelled WHERE workload IS NOT NULL
), bounded AS (
  SELECT * FROM eligible WHERE stratum_rank <= 2
), ranked AS (
  SELECT *, row_number() OVER (ORDER BY
    CASE permission_type WHEN 'RSC' THEN 0 WHEN 'Application' THEN 1 ELSE 2 END,
    workload, capability_sample, md5(permission_definition_id::text)) AS pool_rank
  FROM bounded
)
SELECT permission_definition_id, permission_name, permission_type, display_name,
       description, admin_consent_required, is_current, access_class,
       workload, capability_sample, scope_sample, risk_sample,
       potential_multi_domain,
       concat_ws('; ', 'workload='||workload, 'capability='||capability_sample,
         'scope='||scope_sample, 'risk='||risk_sample,
         CASE WHEN potential_multi_domain THEN 'potential_multi_domain' END) AS sampling_dimensions
FROM ranked
WHERE pool_rank <= 96
ORDER BY pool_rank;

ROLLBACK;
