INSERT INTO catalogue.source_system (
    source_code,
    source_name,
    vendor,
    platform,
    documentation_url
)
VALUES (
    'MSGRAPH',
    'Microsoft Graph',
    'Microsoft',
    'Microsoft 365',
    'https://learn.microsoft.com/graph/'
)
ON CONFLICT (source_code) DO NOTHING;

INSERT INTO catalogue.interface (
    source_system_id,
    interface_code,
    interface_name,
    interface_type,
    version,
    base_uri,
    authentication_type,
    collector_adapter
)
SELECT
    source_system_id,
    'MSGRAPH_V1',
    'Microsoft Graph v1.0',
    'REST_API',
    'v1.0',
    'https://graph.microsoft.com/v1.0',
    'OAuth2',
    'graph_service_principal'
FROM catalogue.source_system
WHERE source_code = 'MSGRAPH'
ON CONFLICT (interface_code) DO NOTHING;
