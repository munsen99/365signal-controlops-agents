\set ON_ERROR_STOP on

BEGIN;

CREATE SCHEMA IF NOT EXISTS permission_pilot;

CREATE TABLE IF NOT EXISTS permission_pilot.pilot_definition (
    pilot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pilot_code TEXT NOT NULL UNIQUE,
    pilot_name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'approved', 'active', 'closed', 'cancelled')),
    target_sample_min SMALLINT NOT NULL DEFAULT 30,
    target_sample_max SMALLINT NOT NULL DEFAULT 40,
    catalogue_baseline_count BIGINT NOT NULL,
    catalogue_baseline_fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (target_sample_min > 0 AND target_sample_max >= target_sample_min)
);

CREATE TABLE IF NOT EXISTS permission_pilot.permission_selection (
    selection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pilot_id UUID NOT NULL REFERENCES permission_pilot.pilot_definition(pilot_id),
    permission_definition_id UUID NOT NULL
        REFERENCES catalogue.permission_definition(permission_definition_id),
    sample_stage TEXT NOT NULL CHECK (sample_stage IN ('candidate', 'final')),
    selection_reason TEXT NOT NULL,
    sampling_dimensions TEXT[] NOT NULL,
    selected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pilot_id, permission_definition_id, sample_stage)
);

CREATE INDEX IF NOT EXISTS ix_pilot_selection_permission
    ON permission_pilot.permission_selection(permission_definition_id);

CREATE TABLE IF NOT EXISTS permission_pilot.classification_review (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    selection_id UUID NOT NULL REFERENCES permission_pilot.permission_selection(selection_id),
    reviewer_kind TEXT NOT NULL CHECK (reviewer_kind IN ('analyst', 'codex')),
    reviewer_identifier TEXT NOT NULL,
    review_round SMALLINT NOT NULL DEFAULT 1 CHECK (review_round > 0),
    access_level TEXT CHECK (access_level IN ('none','limited','owned','selected','all','unknown')),
    capability TEXT CHECK (capability IN ('read','write','read_write','execute','manage','consent','unknown')),
    administrative_capability BOOLEAN,
    privilege_level TEXT CHECK (privilege_level IN ('low','moderate','high','critical','unknown')),
    data_sensitivity TEXT CHECK (data_sensitivity IN ('none','low','moderate','high','restricted','unknown')),
    destructive_potential TEXT CHECK (destructive_potential IN ('none','low','moderate','high','critical','unknown')),
    tenant_wide_impact BOOLEAN,
    consent_sensitivity TEXT CHECK (consent_sensitivity IN ('low','moderate','high','critical','unknown')),
    classification_confidence TEXT CHECK (classification_confidence IN ('low','medium','high')),
    rationale TEXT,
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (review_status IN ('draft','submitted','superseded')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (selection_id, reviewer_kind, reviewer_identifier, review_round)
);

CREATE TABLE IF NOT EXISTS permission_pilot.review_domain_assignment (
    review_id UUID NOT NULL REFERENCES permission_pilot.classification_review(review_id),
    domain_id UUID NOT NULL REFERENCES catalogue.controlops_domain(domain_id),
    assignment_kind TEXT NOT NULL CHECK (assignment_kind IN ('primary','secondary')),
    mapping_rationale TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (review_id, domain_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_pilot_review_one_primary_domain
    ON permission_pilot.review_domain_assignment(review_id)
    WHERE assignment_kind = 'primary';

CREATE TABLE IF NOT EXISTS permission_pilot.disagreement (
    disagreement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    selection_id UUID NOT NULL REFERENCES permission_pilot.permission_selection(selection_id),
    analyst_review_id UUID NOT NULL REFERENCES permission_pilot.classification_review(review_id),
    codex_review_id UUID NOT NULL REFERENCES permission_pilot.classification_review(review_id),
    field_name TEXT NOT NULL,
    analyst_value TEXT,
    codex_value TEXT,
    resolution_status TEXT NOT NULL DEFAULT 'open'
        CHECK (resolution_status IN ('open','resolved','accepted_difference')),
    resolved_value TEXT,
    resolution_rationale TEXT,
    resolved_by TEXT,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (analyst_review_id, codex_review_id, field_name)
);

CREATE TABLE IF NOT EXISTS permission_pilot.domain_review (
    domain_review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disagreement_id UUID NOT NULL REFERENCES permission_pilot.disagreement(disagreement_id),
    domain_id UUID REFERENCES catalogue.controlops_domain(domain_id),
    reviewer_identifier TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('analyst','codex','different','needs_evidence')),
    decided_assignment_kind TEXT CHECK (decided_assignment_kind IN ('primary','secondary')),
    rationale TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS permission_pilot.schema_gap (
    schema_gap_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pilot_id UUID NOT NULL REFERENCES permission_pilot.pilot_definition(pilot_id),
    selection_id UUID REFERENCES permission_pilot.permission_selection(selection_id),
    reported_by TEXT NOT NULL,
    field_or_concept TEXT NOT NULL,
    gap_description TEXT NOT NULL,
    example_value TEXT,
    disposition TEXT NOT NULL DEFAULT 'open'
        CHECK (disposition IN ('open','candidate_rule','schema_change','not_a_gap','deferred')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS permission_pilot.candidate_classification_rule (
    candidate_rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pilot_id UUID NOT NULL REFERENCES permission_pilot.pilot_definition(pilot_id),
    rule_code TEXT NOT NULL,
    rule_description TEXT NOT NULL,
    match_expression TEXT NOT NULL,
    proposed_assignments JSONB NOT NULL,
    supporting_selection_ids UUID[] NOT NULL DEFAULT '{}',
    exception_selection_ids UUID[] NOT NULL DEFAULT '{}',
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    review_status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (review_status IN ('proposed','accepted','rejected','needs_testing')),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pilot_id, rule_code)
);

CREATE OR REPLACE VIEW permission_pilot.analyst_review_export AS
SELECT s.selection_id, p.pilot_code, pd.permission_definition_id,
       pd.permission_name, pd.permission_type, pd.display_name,
       pd.description, pd.admin_consent_required, pd.is_current,
       s.selection_reason, s.sampling_dimensions,
       NULL::TEXT AS access_level, NULL::TEXT AS capability,
       NULL::BOOLEAN AS administrative_capability, NULL::TEXT AS privilege_level,
       NULL::TEXT AS data_sensitivity, NULL::TEXT AS destructive_potential,
       NULL::BOOLEAN AS tenant_wide_impact, NULL::TEXT AS consent_sensitivity,
       NULL::TEXT AS classification_confidence, NULL::TEXT AS primary_domain_code,
       NULL::TEXT AS secondary_domain_codes, NULL::TEXT AS rationale
FROM permission_pilot.permission_selection s
JOIN permission_pilot.pilot_definition p USING (pilot_id)
JOIN catalogue.permission_definition pd USING (permission_definition_id)
WHERE s.sample_stage = 'final';

CREATE OR REPLACE VIEW permission_pilot.codex_review_export AS
SELECT * FROM permission_pilot.analyst_review_export;

CREATE OR REPLACE VIEW permission_pilot.review_comparison AS
WITH review_values AS (
    SELECT r.review_id, r.selection_id, r.reviewer_kind, f.field_name, f.field_value
    FROM permission_pilot.classification_review r
    CROSS JOIN LATERAL (VALUES
      ('access_level', r.access_level), ('capability', r.capability),
      ('administrative_capability', r.administrative_capability::TEXT),
      ('privilege_level', r.privilege_level), ('data_sensitivity', r.data_sensitivity),
      ('destructive_potential', r.destructive_potential),
      ('tenant_wide_impact', r.tenant_wide_impact::TEXT),
      ('consent_sensitivity', r.consent_sensitivity),
      ('classification_confidence', r.classification_confidence),
      ('primary_domain', (SELECT d.domain_code
          FROM permission_pilot.review_domain_assignment a
          JOIN catalogue.controlops_domain d USING (domain_id)
          WHERE a.review_id=r.review_id AND a.assignment_kind='primary')),
      ('secondary_domains', (SELECT string_agg(d.domain_code, ',' ORDER BY d.domain_code)
          FROM permission_pilot.review_domain_assignment a
          JOIN catalogue.controlops_domain d USING (domain_id)
          WHERE a.review_id=r.review_id AND a.assignment_kind='secondary'))
    ) f(field_name, field_value)
    WHERE r.review_status = 'submitted'
), latest AS (
    SELECT rv.*, row_number() OVER
      (PARTITION BY rv.selection_id, rv.reviewer_kind, rv.field_name
       ORDER BY r.review_round DESC, r.updated_at DESC, rv.review_id) AS rn
    FROM review_values rv
    JOIN permission_pilot.classification_review r USING (review_id)
)
SELECT s.selection_id, pd.permission_definition_id, pd.permission_name,
       pd.permission_type, a.field_name, a.field_value AS analyst_value,
       c.field_value AS codex_value,
       a.field_value IS DISTINCT FROM c.field_value AS disagrees,
       a.review_id AS analyst_review_id, c.review_id AS codex_review_id
FROM permission_pilot.permission_selection s
JOIN catalogue.permission_definition pd USING (permission_definition_id)
JOIN latest a ON a.selection_id=s.selection_id AND a.reviewer_kind='analyst' AND a.rn=1
JOIN latest c ON c.selection_id=s.selection_id AND c.reviewer_kind='codex'
             AND c.field_name=a.field_name AND c.rn=1
WHERE s.sample_stage='final';

CREATE OR REPLACE VIEW permission_pilot.disagreement_resolution_export AS
SELECT c.*, d.disagreement_id, d.resolution_status, d.resolved_value,
       d.resolution_rationale, d.resolved_by, d.resolved_at
FROM permission_pilot.review_comparison c
LEFT JOIN permission_pilot.disagreement d
  ON d.analyst_review_id=c.analyst_review_id
 AND d.codex_review_id=c.codex_review_id AND d.field_name=c.field_name
WHERE c.disagrees;

COMMIT;
