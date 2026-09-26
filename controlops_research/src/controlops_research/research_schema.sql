CREATE SCHEMA IF NOT EXISTS research;

CREATE TABLE IF NOT EXISTS research.source (
    source_id CHAR(64) PRIMARY KEY,
    source_key TEXT NOT NULL,
    locator TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS research.snapshot_ref (
    snapshot_ref_id CHAR(64) PRIMARY KEY,
    source_id CHAR(64) NOT NULL REFERENCES research.source(source_id),
    retrieval_id CHAR(64) NOT NULL,
    raw_sha256 CHAR(64) NOT NULL,
    extraction_sha256 CHAR(64) NOT NULL,
    extractor_version TEXT NOT NULL,
    media_type TEXT NOT NULL,
    character_count BIGINT NOT NULL CHECK (character_count >= 0),
    byte_length BIGINT NOT NULL CHECK (byte_length >= 0),
    schema_version TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS research.citation (
    citation_id CHAR(64) PRIMARY KEY,
    snapshot_ref_id CHAR(64) NOT NULL REFERENCES research.snapshot_ref(snapshot_ref_id),
    start_offset BIGINT NOT NULL CHECK (start_offset >= 0),
    end_offset BIGINT NOT NULL CHECK (end_offset >= start_offset),
    quoted_text TEXT NOT NULL,
    excerpt_sha256 CHAR(64) NULL,
    verifier_version TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('pass', 'fail', 'indeterminate')),
    reason_code TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL
);
