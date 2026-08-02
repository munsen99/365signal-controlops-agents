\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
    IF (SELECT count(*) FROM catalogue.controlops_pillar) <> 6 THEN
        RAISE EXCEPTION 'Expected 6 ControlOps pillars.';
    END IF;

    IF (SELECT count(*) FROM catalogue.controlops_domain) <> 34 THEN
        RAISE EXCEPTION 'Expected 34 ControlOps domains from the approved seed list.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM catalogue.controlops_domain d
        LEFT JOIN catalogue.controlops_pillar p ON p.pillar_id = d.pillar_id
        WHERE p.pillar_id IS NULL
    ) THEN
        RAISE EXCEPTION 'A ControlOps domain has no valid pillar.';
    END IF;

    IF EXISTS (
        SELECT pillar_code
        FROM catalogue.controlops_pillar
        GROUP BY pillar_code
        HAVING count(*) > 1
    ) OR EXISTS (
        SELECT domain_code
        FROM catalogue.controlops_domain
        GROUP BY domain_code
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate pillar or domain codes found.';
    END IF;

    IF (SELECT count(*) FROM catalogue.permission_definition) <> 1562
       OR (SELECT count(*) FROM catalogue.permission_definition WHERE is_current) <> 1562 THEN
        RAISE EXCEPTION 'Expected 1,562 total and current permission definitions.';
    END IF;
END;
$$;

CREATE TEMPORARY TABLE permission_catalogue_baseline ON COMMIT DROP AS
SELECT
    count(*) AS row_count,
    count(*) FILTER (WHERE pd.is_current) AS current_row_count,
    md5(string_agg(
        to_jsonb(pd)::text,
        E'\n' ORDER BY pd.permission_definition_id
    )) AS catalogue_fingerprint
FROM catalogue.permission_definition pd;

CREATE TEMPORARY TABLE validation_test_classification (
    permission_definition_id UUID PRIMARY KEY,
    permission_classification_id UUID UNIQUE
) ON COMMIT DROP;

INSERT INTO validation_test_classification (permission_definition_id)
SELECT pd.permission_definition_id
FROM catalogue.permission_definition pd
WHERE pd.is_current = true
  AND NOT EXISTS (
      SELECT 1
      FROM catalogue.permission_classification pc
      WHERE pc.permission_definition_id = pd.permission_definition_id
  )
ORDER BY pd.permission_definition_id
LIMIT 1;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM validation_test_classification) THEN
        RAISE EXCEPTION
            'Validation requires at least one unclassified current permission.';
    END IF;
END;
$$;

WITH inserted_classification AS (
    INSERT INTO catalogue.permission_classification (
        permission_definition_id,
        access_level,
        capability,
        administrative_capability,
        privilege_level,
        data_sensitivity,
        destructive_potential,
        tenant_wide_impact,
        consent_sensitivity,
        classification_confidence,
        classification_source,
        review_status,
        analyst_notes
    )
    SELECT
        permission_definition_id,
        'all',
        'read_write',
        true,
        'high',
        'high',
        'moderate',
        true,
        'high',
        'high',
        'analyst',
        'draft',
        'Temporary schema validation record; rolled back.'
    FROM validation_test_classification
    RETURNING permission_definition_id, permission_classification_id
)
UPDATE validation_test_classification test_record
SET permission_classification_id = inserted.permission_classification_id
FROM inserted_classification inserted
WHERE inserted.permission_definition_id = test_record.permission_definition_id;

WITH test_classification AS (
    SELECT permission_classification_id
    FROM validation_test_classification
), test_domains AS (
    SELECT domain_id, row_number() OVER (ORDER BY domain_code) AS domain_number
    FROM catalogue.controlops_domain
    WHERE domain_code IN ('AUTHENTICATION', 'MICROSOFT_GRAPH_API')
)
INSERT INTO catalogue.permission_classification_domain (
    permission_classification_id,
    domain_id,
    is_primary,
    mapping_rationale
)
SELECT
    c.permission_classification_id,
    d.domain_id,
    d.domain_number = 1,
    'Temporary multi-domain validation mapping; rolled back.'
FROM test_classification c
CROSS JOIN test_domains d;

DO $$
DECLARE
    test_classification_id UUID;
    second_domain_id UUID;
BEGIN
    SELECT permission_classification_id
    INTO test_classification_id
    FROM validation_test_classification;

    IF test_classification_id IS NULL THEN
        RAISE EXCEPTION 'Temporary validation classification was not created.';
    END IF;

    IF (
        SELECT count(*)
        FROM catalogue.permission_classification_domain
        WHERE permission_classification_id = test_classification_id
    ) <> 2 THEN
        RAISE EXCEPTION 'A classification could not be mapped to two domains.';
    END IF;

    SELECT domain_id
    INTO second_domain_id
    FROM catalogue.permission_classification_domain
    WHERE permission_classification_id = test_classification_id
      AND is_primary = false;

    BEGIN
        UPDATE catalogue.permission_classification_domain
        SET is_primary = true
        WHERE permission_classification_id = test_classification_id
          AND domain_id = second_domain_id;
        RAISE EXCEPTION 'A second primary domain was incorrectly accepted.';
    EXCEPTION
        WHEN unique_violation THEN
            NULL;
    END;

    BEGIN
        UPDATE catalogue.permission_classification
        SET privilege_level = 'invalid_privilege'
        WHERE permission_classification_id = test_classification_id;
        RAISE EXCEPTION 'An invalid controlled classification value was accepted.';
    EXCEPTION
        WHEN check_violation THEN
            NULL;
    END;
END;
$$;

DO $$
DECLARE
    baseline_count BIGINT;
    baseline_current_count BIGINT;
    baseline_fingerprint TEXT;
    current_count BIGINT;
    current_current_count BIGINT;
    current_fingerprint TEXT;
BEGIN
    SELECT row_count, current_row_count, catalogue_fingerprint
    INTO baseline_count, baseline_current_count, baseline_fingerprint
    FROM permission_catalogue_baseline;

    SELECT
        count(*),
        count(*) FILTER (WHERE pd.is_current),
        md5(string_agg(
            to_jsonb(pd)::text,
            E'\n' ORDER BY pd.permission_definition_id
        ))
    INTO current_count, current_current_count, current_fingerprint
    FROM catalogue.permission_definition pd;

    IF current_count <> baseline_count
       OR current_current_count <> baseline_current_count
       OR current_fingerprint IS DISTINCT FROM baseline_fingerprint THEN
        RAISE EXCEPTION 'Permission catalogue rows changed during validation.';
    END IF;
END;
$$;

SELECT 'pillars' AS validation_item, count(*) AS actual_count, 6 AS expected_count
FROM catalogue.controlops_pillar
UNION ALL
SELECT 'domains', count(*), 34
FROM catalogue.controlops_domain
UNION ALL
SELECT 'permission definitions', count(*), 1562
FROM catalogue.permission_definition
UNION ALL
SELECT 'temporary domain mappings', count(*), 2
FROM catalogue.permission_classification_domain pcd
JOIN validation_test_classification test_record
  ON test_record.permission_classification_id = pcd.permission_classification_id;

SELECT
    permission_definition_id AS validation_permission_definition_id,
    permission_classification_id AS validation_permission_classification_id
FROM validation_test_classification
\gset

ROLLBACK;

SELECT 1 / CASE
    WHEN NOT EXISTS (
        SELECT 1
        FROM catalogue.permission_classification
        WHERE permission_classification_id =
              :'validation_permission_classification_id'::uuid
    )
    AND NOT EXISTS (
        SELECT 1
        FROM catalogue.permission_classification_domain
        WHERE permission_classification_id =
              :'validation_permission_classification_id'::uuid
    )
    AND to_regclass('pg_temp.permission_catalogue_baseline') IS NULL
    AND to_regclass('pg_temp.validation_test_classification') IS NULL
    THEN 1
    ELSE 0
END AS cleanup_validation;

-- Example: permission counts by pillar and domain, including empty domains.
SELECT
    p.pillar_name,
    d.domain_name,
    count(DISTINCT pc.permission_definition_id) AS permission_count
FROM catalogue.controlops_pillar p
JOIN catalogue.controlops_domain d ON d.pillar_id = p.pillar_id
LEFT JOIN catalogue.permission_classification_domain pcd
  ON pcd.domain_id = d.domain_id
LEFT JOIN catalogue.permission_classification pc
  ON pc.permission_classification_id = pcd.permission_classification_id
LEFT JOIN catalogue.permission_definition pd
  ON pd.permission_definition_id = pc.permission_definition_id
 AND pd.is_current = true
GROUP BY p.pillar_id, p.pillar_name, p.display_order,
         d.domain_id, d.domain_name, d.display_order
ORDER BY p.display_order, d.display_order;

-- Example: current permissions with no classification.
SELECT
    pd.permission_definition_id,
    pd.permission_name,
    pd.permission_type,
    pd.display_name
FROM catalogue.permission_definition pd
LEFT JOIN catalogue.permission_classification pc
  ON pc.permission_definition_id = pd.permission_definition_id
WHERE pd.is_current = true
  AND pc.permission_classification_id IS NULL
ORDER BY pd.permission_name, pd.permission_type;

-- Example: approved high or critical privilege application permissions.
SELECT
    pd.permission_name,
    pd.display_name,
    pc.privilege_level,
    pc.capability,
    pc.consent_sensitivity
FROM catalogue.permission_definition pd
JOIN catalogue.permission_classification pc
  ON pc.permission_definition_id = pd.permission_definition_id
WHERE pd.is_current = true
  AND pd.permission_type = 'Application'
  AND pc.review_status = 'approved'
  AND pc.privilege_level IN ('high', 'critical')
ORDER BY pc.privilege_level DESC, pd.permission_name;

-- Example: permissions mapped to more than one domain.
SELECT
    pd.permission_definition_id,
    pd.permission_name,
    pd.permission_type,
    count(*) AS domain_count,
    string_agg(d.domain_name, ', ' ORDER BY d.domain_name) AS domains
FROM catalogue.permission_definition pd
JOIN catalogue.permission_classification pc
  ON pc.permission_definition_id = pd.permission_definition_id
JOIN catalogue.permission_classification_domain pcd
  ON pcd.permission_classification_id = pc.permission_classification_id
JOIN catalogue.controlops_domain d ON d.domain_id = pcd.domain_id
WHERE pd.is_current = true
GROUP BY pd.permission_definition_id, pd.permission_name, pd.permission_type
HAVING count(*) > 1
ORDER BY domain_count DESC, pd.permission_name;

-- Example: classification coverage across current permissions.
SELECT
    count(*) AS current_permission_count,
    count(pc.permission_classification_id) AS classified_permission_count,
    round(
        100.0 * count(pc.permission_classification_id) / NULLIF(count(*), 0),
        2
    ) AS coverage_percentage
FROM catalogue.permission_definition pd
LEFT JOIN catalogue.permission_classification pc
  ON pc.permission_definition_id = pd.permission_definition_id
WHERE pd.is_current = true;

-- Example: classifications awaiting review.
SELECT
    pd.permission_definition_id,
    pd.permission_name,
    pd.permission_type,
    pc.review_status,
    pc.classification_source,
    pc.classification_confidence,
    pc.updated_at
FROM catalogue.permission_definition pd
JOIN catalogue.permission_classification pc
  ON pc.permission_definition_id = pd.permission_definition_id
WHERE pd.is_current = true
  AND pc.review_status IN ('draft', 'in_review', 'needs_review')
ORDER BY pc.updated_at, pd.permission_name;
