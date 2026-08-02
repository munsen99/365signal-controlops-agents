CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS catalogue;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS evidence;
CREATE SCHEMA IF NOT EXISTS assurance;
CREATE SCHEMA IF NOT EXISTS reporting;
CREATE SCHEMA IF NOT EXISTS operations;

COMMENT ON SCHEMA catalogue IS
'Source systems, interfaces, permissions, capabilities and taxonomies.';

COMMENT ON SCHEMA raw IS
'Immutable source imports and unprocessed evidence metadata.';

COMMENT ON SCHEMA evidence IS
'Normalised Microsoft 365 evidence records.';

COMMENT ON SCHEMA assurance IS
'Control assessments, findings, risks and remediation records.';

COMMENT ON SCHEMA reporting IS
'Curated views and materialised views for Power BI and evidence packs.';

COMMENT ON SCHEMA operations IS
'Collector executions, failures, freshness and catalogue changes.';
