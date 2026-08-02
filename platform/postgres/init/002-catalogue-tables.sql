CREATE TABLE catalogue.source_system (
    source_system_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_code TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    vendor TEXT NOT NULL DEFAULT 'Microsoft',
    platform TEXT NOT NULL DEFAULT 'Microsoft 365',
    status TEXT NOT NULL DEFAULT 'active',
    documentation_url TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE catalogue.interface (
    interface_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system_id UUID NOT NULL
        REFERENCES catalogue.source_system(source_system_id),
    interface_code TEXT NOT NULL UNIQUE,
    interface_name TEXT NOT NULL,
    interface_type TEXT NOT NULL,
    version TEXT,
    base_uri TEXT,
    authentication_type TEXT,
    collector_adapter TEXT,
    is_preview BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE operations.catalogue_import_run (
    import_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system_id UUID NOT NULL
        REFERENCES catalogue.source_system(source_system_id),
    interface_id UUID
        REFERENCES catalogue.interface(interface_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    collector_version TEXT,
    source_version TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    records_received INTEGER NOT NULL DEFAULT 0,
    records_added INTEGER NOT NULL DEFAULT 0,
    records_changed INTEGER NOT NULL DEFAULT 0,
    records_retired INTEGER NOT NULL DEFAULT 0,
    payload_hash TEXT,
    error_details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE raw.catalogue_snapshot (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    import_run_id UUID NOT NULL
        REFERENCES operations.catalogue_import_run(import_run_id),
    source_uri TEXT,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    http_status INTEGER,
    response_headers JSONB,
    payload JSONB NOT NULL,
    payload_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE catalogue.permission_definition (
    permission_definition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interface_id UUID NOT NULL
        REFERENCES catalogue.interface(interface_id),
    external_id TEXT,
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    access_class TEXT,
    admin_consent_required BOOLEAN,
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    risk_rating TEXT,
    is_least_privileged_candidate BOOLEAN,
    source_property TEXT,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL DEFAULT true,
    source_hash TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_permission_version UNIQUE (
        interface_id,
        permission_type,
        permission_name,
        valid_from
    )
);

CREATE INDEX ix_permission_name
    ON catalogue.permission_definition(permission_name);

CREATE INDEX ix_permission_current
    ON catalogue.permission_definition(is_current)
    WHERE is_current = true;

CREATE INDEX ix_permission_type
    ON catalogue.permission_definition(permission_type);

CREATE INDEX ix_permission_access_class
    ON catalogue.permission_definition(access_class);

CREATE INDEX ix_snapshot_payload_gin
    ON raw.catalogue_snapshot USING GIN(payload);
