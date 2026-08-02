BEGIN;

CREATE TABLE IF NOT EXISTS catalogue.controlops_pillar (
    pillar_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pillar_code TEXT NOT NULL,
    pillar_name TEXT NOT NULL,
    description TEXT,
    display_order SMALLINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_controlops_pillar_code UNIQUE (pillar_code),
    CONSTRAINT uq_controlops_pillar_name UNIQUE (pillar_name),
    CONSTRAINT uq_controlops_pillar_display_order UNIQUE (display_order)
);

CREATE TABLE IF NOT EXISTS catalogue.controlops_domain (
    domain_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pillar_id UUID NOT NULL
        REFERENCES catalogue.controlops_pillar(pillar_id),
    domain_code TEXT NOT NULL,
    domain_name TEXT NOT NULL,
    description TEXT,
    display_order SMALLINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_controlops_domain_code UNIQUE (domain_code),
    CONSTRAINT uq_controlops_domain_name_per_pillar
        UNIQUE (pillar_id, domain_name),
    CONSTRAINT uq_controlops_domain_order_per_pillar
        UNIQUE (pillar_id, display_order)
);

CREATE INDEX IF NOT EXISTS ix_controlops_domain_pillar_id
    ON catalogue.controlops_domain(pillar_id);

CREATE TABLE IF NOT EXISTS catalogue.permission_classification (
    permission_classification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    permission_definition_id UUID NOT NULL
        REFERENCES catalogue.permission_definition(permission_definition_id),
    access_level TEXT,
    capability TEXT,
    administrative_capability BOOLEAN,
    privilege_level TEXT,
    data_sensitivity TEXT,
    destructive_potential TEXT,
    tenant_wide_impact BOOLEAN,
    consent_sensitivity TEXT,
    classification_confidence TEXT,
    classification_source TEXT,
    review_status TEXT NOT NULL DEFAULT 'draft',
    analyst_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_permission_classification_definition
        UNIQUE (permission_definition_id),
    CONSTRAINT ck_permission_classification_access_level CHECK (
        access_level IN ('none', 'limited', 'owned', 'selected', 'all', 'unknown')
    ),
    CONSTRAINT ck_permission_classification_capability CHECK (
        capability IN (
            'read', 'write', 'read_write', 'execute', 'manage', 'consent', 'unknown'
        )
    ),
    CONSTRAINT ck_permission_classification_privilege_level CHECK (
        privilege_level IN ('low', 'moderate', 'high', 'critical', 'unknown')
    ),
    CONSTRAINT ck_permission_classification_data_sensitivity CHECK (
        data_sensitivity IN (
            'none', 'low', 'moderate', 'high', 'restricted', 'unknown'
        )
    ),
    CONSTRAINT ck_permission_classification_destructive_potential CHECK (
        destructive_potential IN (
            'none', 'low', 'moderate', 'high', 'critical', 'unknown'
        )
    ),
    CONSTRAINT ck_permission_classification_consent_sensitivity CHECK (
        consent_sensitivity IN ('low', 'moderate', 'high', 'critical', 'unknown')
    ),
    CONSTRAINT ck_permission_classification_confidence CHECK (
        classification_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_permission_classification_source CHECK (
        classification_source IN ('analyst', 'microsoft', 'rule', 'imported', 'other')
    ),
    CONSTRAINT ck_permission_classification_review_status CHECK (
        review_status IN (
            'draft', 'in_review', 'approved', 'rejected', 'needs_review'
        )
    )
);

CREATE INDEX IF NOT EXISTS ix_permission_classification_privilege_level
    ON catalogue.permission_classification(privilege_level);

CREATE INDEX IF NOT EXISTS ix_permission_classification_review_status
    ON catalogue.permission_classification(review_status);

CREATE INDEX IF NOT EXISTS ix_permission_classification_source
    ON catalogue.permission_classification(classification_source);

CREATE TABLE IF NOT EXISTS catalogue.permission_classification_domain (
    permission_classification_id UUID NOT NULL
        REFERENCES catalogue.permission_classification(permission_classification_id),
    domain_id UUID NOT NULL
        REFERENCES catalogue.controlops_domain(domain_id),
    is_primary BOOLEAN NOT NULL DEFAULT false,
    mapping_rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT permission_classification_domain_pkey
        PRIMARY KEY (permission_classification_id, domain_id)
);

CREATE INDEX IF NOT EXISTS ix_permission_classification_domain_domain_id
    ON catalogue.permission_classification_domain(domain_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_permission_classification_one_primary_domain
    ON catalogue.permission_classification_domain(permission_classification_id)
    WHERE is_primary = true;

INSERT INTO catalogue.controlops_pillar (
    pillar_code,
    pillar_name,
    description,
    display_order
)
VALUES
    (
        'IDENTITY_ACCESS',
        'Identity and Access',
        'Identity assurance, authentication, authorization, access governance and privileged access across cloud services.',
        1
    ),
    (
        'DATA_PROTECTION_GOVERNANCE',
        'Data Protection and Governance',
        'Protection, governance, lifecycle, discovery and privacy management for organizational information.',
        2
    ),
    (
        'SECURITY_OPERATIONS',
        'Security Operations',
        'Detection, investigation, response, monitoring and improvement of the organization''s security posture.',
        3
    ),
    (
        'INFRASTRUCTURE_PLATFORM',
        'Infrastructure and Platform',
        'Administration and protection of cloud infrastructure, devices, networks and shared platform services.',
        4
    ),
    (
        'APPLICATIONS_WORKLOADS',
        'Applications and Workloads',
        'Administration and assurance of Microsoft 365 workloads, APIs and business applications.',
        5
    ),
    (
        'GOVERNANCE_RISK_COMPLIANCE',
        'Governance, Risk and Compliance',
        'Enterprise governance, risk, compliance, assurance and regulatory oversight capabilities.',
        6
    )
ON CONFLICT (pillar_code) DO NOTHING;

INSERT INTO catalogue.controlops_domain (
    pillar_id,
    domain_code,
    domain_name,
    description,
    display_order
)
SELECT
    p.pillar_id,
    seed.domain_code,
    seed.domain_name,
    seed.description,
    seed.display_order
FROM catalogue.controlops_pillar p
JOIN (
    VALUES
        ('IDENTITY_ACCESS', 'AUTHENTICATION', 'Authentication', 'Sign-in methods, credentials, sessions and mechanisms used to establish identity.', 1),
        ('IDENTITY_ACCESS', 'CONDITIONAL_ACCESS', 'Conditional Access', 'Context-aware access policies and enforcement conditions for users, applications and resources.', 2),
        ('IDENTITY_ACCESS', 'PRIVILEGED_ACCESS', 'Privileged Access', 'Assignment, activation, oversight and protection of elevated administrative access.', 3),
        ('IDENTITY_ACCESS', 'IDENTITY_LIFECYCLE', 'Identity Lifecycle', 'Creation, maintenance, synchronization and retirement of identities and memberships.', 4),
        ('IDENTITY_ACCESS', 'DIRECTORY_ORG_MANAGEMENT', 'Directory and Organization Management', 'Administration of directory-wide objects, organization settings and structural boundaries.', 5),
        ('IDENTITY_ACCESS', 'AUTHORIZATION_ACCESS_GOVERNANCE', 'Authorization and Access Governance', 'Entitlements, access reviews, role assignment and governance of authorization decisions.', 6),
        ('IDENTITY_ACCESS', 'APPLICATION_IDENTITY_CONSENT', 'Application Identity and Consent', 'Application identities, service principals, credentials, API authorization and consent governance.', 7),

        ('DATA_PROTECTION_GOVERNANCE', 'INFORMATION_PROTECTION', 'Information Protection', 'Classification, labeling, encryption and protection of sensitive information.', 1),
        ('DATA_PROTECTION_GOVERNANCE', 'DATA_LOSS_PREVENTION', 'Data Loss Prevention', 'Policies and controls that detect or prevent inappropriate disclosure and movement of data.', 2),
        ('DATA_PROTECTION_GOVERNANCE', 'RECORDS_RETENTION', 'Records and Retention', 'Retention, disposition, records declaration and defensible information lifecycle controls.', 3),
        ('DATA_PROTECTION_GOVERNANCE', 'EDISCOVERY_CONTENT_SEARCH', 'eDiscovery and Content Search', 'Discovery, preservation, search, review and export of organizational content.', 4),
        ('DATA_PROTECTION_GOVERNANCE', 'DATA_LIFECYCLE_RECOVERY', 'Data Lifecycle and Recovery', 'Lifecycle administration, restoration, recovery and continuity of organizational data.', 5),
        ('DATA_PROTECTION_GOVERNANCE', 'PRIVACY_DATA_SUBJECT', 'Privacy and Data Subject Management', 'Privacy operations, data subject rights and governance of personal information.', 6),

        ('SECURITY_OPERATIONS', 'THREAT_PROTECTION_DEFENDER', 'Threat Protection and Defender', 'Threat prevention, detection and protection capabilities across identities, endpoints, applications and data.', 1),
        ('SECURITY_OPERATIONS', 'SECURITY_POSTURE_VULNERABILITY', 'Security Posture and Vulnerability Management', 'Assessment and improvement of exposure, vulnerabilities, configurations and security posture.', 2),
        ('SECURITY_OPERATIONS', 'INCIDENT_INVESTIGATION_RESPONSE', 'Incident Investigation and Response', 'Triage, investigation, containment and remediation of security incidents and alerts.', 3),
        ('SECURITY_OPERATIONS', 'LOGGING_MONITORING_AUDIT', 'Logging, Monitoring and Audit', 'Collection, access, analysis and oversight of logs, audit events and operational telemetry.', 4),
        ('SECURITY_OPERATIONS', 'SECURITY_AUTOMATION_INTEGRATION', 'Security Automation and Integration', 'Automated security workflows, integrations, orchestration and machine-driven response.', 5),

        ('INFRASTRUCTURE_PLATFORM', 'AZURE_RESOURCE_MANAGEMENT', 'Azure Resource Management', 'Governance and administration of Azure subscriptions, resource groups and resources.', 1),
        ('INFRASTRUCTURE_PLATFORM', 'ENDPOINT_DEVICE_MANAGEMENT', 'Endpoint and Device Management', 'Enrollment, configuration, compliance and lifecycle management of endpoints and devices.', 2),
        ('INFRASTRUCTURE_PLATFORM', 'NETWORK_CONNECTIVITY', 'Network and Connectivity', 'Network configuration, connectivity, boundaries and traffic-control capabilities.', 3),
        ('INFRASTRUCTURE_PLATFORM', 'CLOUD_PLATFORM_SERVICES', 'Cloud Platform Services', 'Shared cloud platform capabilities and supporting services not limited to a single workload.', 4),
        ('INFRASTRUCTURE_PLATFORM', 'PLATFORM_CONFIGURATION_ADMIN', 'Platform Configuration and Administration', 'Tenant and platform configuration, operational settings and broad administrative functions.', 5),

        ('APPLICATIONS_WORKLOADS', 'MICROSOFT_GRAPH_API', 'Microsoft Graph and API Access', 'Microsoft Graph, API exposure, API operations and cross-service programmatic access.', 1),
        ('APPLICATIONS_WORKLOADS', 'EXCHANGE_ONLINE', 'Exchange Online', 'Messaging, mailboxes, calendaring and Exchange Online administration.', 2),
        ('APPLICATIONS_WORKLOADS', 'SHAREPOINT_ONEDRIVE', 'SharePoint and OneDrive', 'Sites, files, collaboration content and SharePoint or OneDrive administration.', 3),
        ('APPLICATIONS_WORKLOADS', 'MICROSOFT_TEAMS', 'Microsoft Teams', 'Teams collaboration, meetings, calling, messaging and Teams administration.', 4),
        ('APPLICATIONS_WORKLOADS', 'BUSINESS_APPLICATIONS', 'Business Applications', 'Line-of-business, productivity and organizational applications and their data.', 5),
        ('APPLICATIONS_WORKLOADS', 'WORKLOAD_APPLICATION_MANAGEMENT', 'Workload Application Management', 'Configuration and lifecycle management of workload applications and integrations.', 6),

        ('GOVERNANCE_RISK_COMPLIANCE', 'COMPLIANCE_MANAGEMENT', 'Compliance Management', 'Assessment, management and reporting of organizational compliance obligations and posture.', 1),
        ('GOVERNANCE_RISK_COMPLIANCE', 'RISK_POLICY_MANAGEMENT', 'Risk and Policy Management', 'Definition, operation and oversight of organizational risks and governing policies.', 2),
        ('GOVERNANCE_RISK_COMPLIANCE', 'AUDIT_ASSURANCE', 'Audit and Assurance', 'Independent review, evidence, testing and assurance over controls and operational claims.', 3),
        ('GOVERNANCE_RISK_COMPLIANCE', 'REGULATORY_FRAMEWORK_MANAGEMENT', 'Regulatory and Framework Management', 'Mapping and management of regulatory requirements, standards and control frameworks.', 4),
        ('GOVERNANCE_RISK_COMPLIANCE', 'SERVICE_GOVERNANCE_ADMIN', 'Service Governance and Administration', 'Service-wide governance, administrative oversight, health and organizational accountability.', 5)
) AS seed (
    pillar_code,
    domain_code,
    domain_name,
    description,
    display_order
) ON seed.pillar_code = p.pillar_code
ON CONFLICT (domain_code) DO NOTHING;

COMMIT;
