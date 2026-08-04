\set ON_ERROR_STOP on

-- Capture the catalogue and review state before exercising the persistent loader.
CREATE TEMPORARY TABLE permission_catalogue_before AS
SELECT count(*) AS row_count,
       md5(string_agg(
           to_jsonb(pd)::text,
           E'\n' ORDER BY pd.permission_definition_id
       )) AS catalogue_fingerprint
FROM catalogue.permission_definition pd;

CREATE TEMPORARY TABLE pilot_review_before AS
SELECT r.*
FROM permission_pilot.classification_review r
JOIN permission_pilot.permission_selection s USING (selection_id)
JOIN permission_pilot.pilot_definition p USING (pilot_id)
WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36';

\ir ../init/006-load-graph-permission-final-sample.sql

CREATE TEMPORARY TABLE pilot_after_first_load AS
SELECT *
FROM permission_pilot.pilot_definition
WHERE pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36';

CREATE TEMPORARY TABLE selections_after_first_load AS
SELECT s.*
FROM permission_pilot.permission_selection s
JOIN permission_pilot.pilot_definition p USING (pilot_id)
WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36';

-- A second complete run must be a no-op for already matching persistent rows.
\ir ../init/006-load-graph-permission-final-sample.sql

DO $$
DECLARE
    pilot_count INTEGER;
    final_count INTEGER;
    catalogue_matches INTEGER;
    unique_selections INTEGER;
    workload_count INTEGER;
    capability_count INTEGER;
    scope_count INTEGER;
    risk_count INTEGER;
    multi_domain_count INTEGER;
BEGIN
    SELECT count(*) INTO pilot_count
    FROM permission_pilot.pilot_definition
    WHERE pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36';
    IF pilot_count <> 1 THEN
        RAISE EXCEPTION 'Expected one final-sample pilot; found %.', pilot_count;
    END IF;

    SELECT count(*), count(pd.permission_definition_id),
           count(DISTINCT (s.permission_definition_id, s.sample_stage)),
           count(DISTINCT s.sampling_dimensions[1]),
           count(DISTINCT s.sampling_dimensions[2]),
           count(DISTINCT s.sampling_dimensions[3]),
           count(DISTINCT s.sampling_dimensions[4]),
           count(*) FILTER (WHERE s.sampling_dimensions @> ARRAY['potential_multi_domain'])
    INTO final_count, catalogue_matches, unique_selections,
         workload_count, capability_count, scope_count, risk_count,
         multi_domain_count
    FROM permission_pilot.permission_selection s
    JOIN permission_pilot.pilot_definition p USING (pilot_id)
    LEFT JOIN catalogue.permission_definition pd
      ON pd.permission_definition_id = s.permission_definition_id
    WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
      AND s.sample_stage = 'final';

    IF final_count <> 36 THEN
        RAISE EXCEPTION 'Expected 36 final selections; found %.', final_count;
    END IF;
    IF catalogue_matches <> 36 THEN
        RAISE EXCEPTION 'Expected all 36 final selections to match the catalogue.';
    END IF;
    IF unique_selections <> 36 THEN
        RAISE EXCEPTION 'Expected 36 unique final selections.';
    END IF;
    IF workload_count <> 8 OR capability_count <> 7
       OR scope_count <> 2 OR risk_count <> 3 OR multi_domain_count = 0 THEN
        RAISE EXCEPTION
            'Coverage failed: workloads %, capabilities %, scopes %, risks %, multi-domain %.',
            workload_count, capability_count, scope_count, risk_count,
            multi_domain_count;
    END IF;

    IF EXISTS (
        SELECT pd.permission_type, count(*)
        FROM permission_pilot.permission_selection s
        JOIN permission_pilot.pilot_definition p USING (pilot_id)
        JOIN catalogue.permission_definition pd USING (permission_definition_id)
        WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND s.sample_stage = 'final'
        GROUP BY pd.permission_type
        HAVING (pd.permission_type = 'Application' AND count(*) <> 14)
            OR (pd.permission_type = 'Delegated' AND count(*) <> 16)
            OR (pd.permission_type = 'RSC' AND count(*) <> 6)
            OR pd.permission_type NOT IN ('Application', 'Delegated', 'RSC')
    ) THEN
        RAISE EXCEPTION 'Permission-type distribution is not 14/16/6.';
    END IF;

    IF EXISTS (
        (SELECT * FROM pilot_after_first_load
         EXCEPT SELECT * FROM permission_pilot.pilot_definition
                WHERE pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36')
        UNION ALL
        (SELECT * FROM permission_pilot.pilot_definition
         WHERE pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
         EXCEPT SELECT * FROM pilot_after_first_load)
    ) OR EXISTS (
        (SELECT * FROM selections_after_first_load
         EXCEPT SELECT s.* FROM permission_pilot.permission_selection s
                JOIN permission_pilot.pilot_definition p USING (pilot_id)
                WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36')
        UNION ALL
        (SELECT s.* FROM permission_pilot.permission_selection s
         JOIN permission_pilot.pilot_definition p USING (pilot_id)
         WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
         EXCEPT SELECT * FROM selections_after_first_load)
    ) THEN
        RAISE EXCEPTION 'The second loader run changed the pilot or its selections.';
    END IF;

    IF EXISTS (
        (SELECT * FROM pilot_review_before
         EXCEPT
         SELECT r.* FROM permission_pilot.classification_review r
         JOIN permission_pilot.permission_selection s USING (selection_id)
         JOIN permission_pilot.pilot_definition p USING (pilot_id)
         WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36')
    ) THEN
        RAISE EXCEPTION 'Existing review data was removed or changed.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM permission_catalogue_before before
        CROSS JOIN LATERAL (
            SELECT count(*) AS row_count,
                   md5(string_agg(
                       to_jsonb(pd)::text,
                       E'\n' ORDER BY pd.permission_definition_id
                   )) AS catalogue_fingerprint
            FROM catalogue.permission_definition pd
        ) current_catalogue
        WHERE current_catalogue.row_count <> before.row_count
           OR current_catalogue.catalogue_fingerprint IS DISTINCT FROM before.catalogue_fingerprint
    ) THEN
        RAISE EXCEPTION 'Permission catalogue rows changed while loading or validating.';
    END IF;
END;
$$;

SELECT 'pilot_exists' AS test, count(*)::TEXT AS actual, '1' AS expected
FROM permission_pilot.pilot_definition
WHERE pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
UNION ALL
SELECT 'final_sample_count', count(*)::TEXT, '36'
FROM permission_pilot.permission_selection s
JOIN permission_pilot.pilot_definition p USING (pilot_id)
WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND s.sample_stage = 'final'
UNION ALL
SELECT 'application_count', count(*)::TEXT, '14'
FROM permission_pilot.permission_selection s
JOIN permission_pilot.pilot_definition p USING (pilot_id)
JOIN catalogue.permission_definition pd USING (permission_definition_id)
WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND s.sample_stage = 'final' AND pd.permission_type = 'Application'
UNION ALL
SELECT 'delegated_count', count(*)::TEXT, '16'
FROM permission_pilot.permission_selection s
JOIN permission_pilot.pilot_definition p USING (pilot_id)
JOIN catalogue.permission_definition pd USING (permission_definition_id)
WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND s.sample_stage = 'final' AND pd.permission_type = 'Delegated'
UNION ALL
SELECT 'rsc_count', count(*)::TEXT, '6'
FROM permission_pilot.permission_selection s
JOIN permission_pilot.pilot_definition p USING (pilot_id)
JOIN catalogue.permission_definition pd USING (permission_definition_id)
WHERE p.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND s.sample_stage = 'final' AND pd.permission_type = 'RSC';

DROP TABLE selections_after_first_load;
DROP TABLE pilot_after_first_load;
DROP TABLE pilot_review_before;
DROP TABLE permission_catalogue_before;
