\set ON_ERROR_STOP on

BEGIN;

CREATE TEMPORARY TABLE final_selection ON COMMIT DROP AS
SELECT selection.selection_id, selection.permission_definition_id,
       permission.permission_name, permission.permission_type
FROM permission_pilot.pilot_definition pilot
JOIN permission_pilot.permission_selection selection USING (pilot_id)
JOIN catalogue.permission_definition permission USING (permission_definition_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND selection.sample_stage = 'final';

CREATE TEMPORARY TABLE source_codex_review ON COMMIT DROP AS
SELECT selection.selection_id, selection.permission_definition_id,
       permission.permission_name, permission.permission_type,
       review.review_id AS codex_review_id,
       review.access_level, review.capability, review.administrative_capability,
       review.privilege_level, review.data_sensitivity,
       review.destructive_potential, review.tenant_wide_impact,
       review.consent_sensitivity, review.classification_confidence,
       review.rationale
FROM permission_pilot.pilot_definition pilot
JOIN permission_pilot.permission_selection selection USING (pilot_id)
JOIN catalogue.permission_definition permission USING (permission_definition_id)
JOIN permission_pilot.classification_review review USING (selection_id)
WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND selection.sample_stage = 'final'
  AND review.reviewer_kind = 'codex'
  AND review.reviewer_identifier = 'codex_remaining_28'
  AND review.review_round = 1
  AND review.review_status = 'submitted';

DO $$
DECLARE
    existing_analyst_count integer;
    missing_analyst_count integer;
BEGIN
    IF (SELECT count(*) FROM final_selection) <> 36 THEN
        RAISE EXCEPTION 'Expected exactly 36 final pilot selections; found %.',
            (SELECT count(*) FROM final_selection);
    END IF;

    IF (SELECT count(*) FROM source_codex_review) <> 28 THEN
        RAISE EXCEPTION 'Expected exactly 28 submitted Codex remaining-batch source reviews; found %.',
            (SELECT count(*) FROM source_codex_review);
    END IF;

    IF EXISTS (
        SELECT 1 FROM source_codex_review source
        LEFT JOIN permission_pilot.review_domain_assignment assignment
          ON assignment.review_id = source.codex_review_id
        GROUP BY source.codex_review_id
        HAVING count(*) FILTER (WHERE assignment.assignment_kind = 'primary') <> 1
    ) THEN
        RAISE EXCEPTION 'Every source Codex review must have exactly one primary domain.';
    END IF;

    SELECT count(*) INTO existing_analyst_count
    FROM source_codex_review source
    JOIN permission_pilot.classification_review analyst
      ON analyst.selection_id = source.selection_id
     AND analyst.reviewer_kind = 'analyst'
     AND analyst.reviewer_identifier = 'jon_bruce'
     AND analyst.review_round = 1;

    SELECT count(*) INTO missing_analyst_count
    FROM final_selection target
    WHERE NOT EXISTS (
        SELECT 1 FROM permission_pilot.classification_review analyst
        WHERE analyst.selection_id = target.selection_id
          AND analyst.reviewer_kind = 'analyst'
          AND analyst.reviewer_identifier = 'jon_bruce'
          AND analyst.review_round = 1
    );

    IF missing_analyst_count NOT IN (28, 0) THEN
        RAISE EXCEPTION 'Expected either 28 missing analyst reviews before initialization or 0 on rerun; found %.', missing_analyst_count;
    END IF;

    IF missing_analyst_count = 28 AND EXISTS (
        (SELECT target.selection_id FROM final_selection target
         WHERE NOT EXISTS (
             SELECT 1 FROM permission_pilot.classification_review analyst
             WHERE analyst.selection_id=target.selection_id
               AND analyst.reviewer_kind='analyst'
               AND analyst.reviewer_identifier='jon_bruce'
               AND analyst.review_round=1)
         EXCEPT SELECT selection_id FROM source_codex_review)
        UNION ALL
        (SELECT selection_id FROM source_codex_review EXCEPT
         SELECT target.selection_id FROM final_selection target
         WHERE NOT EXISTS (
             SELECT 1 FROM permission_pilot.classification_review analyst
             WHERE analyst.selection_id=target.selection_id
               AND analyst.reviewer_kind='analyst'
               AND analyst.reviewer_identifier='jon_bruce'
               AND analyst.review_round=1))
    ) THEN
        RAISE EXCEPTION 'The 28 database-derived missing analyst selections do not exactly match the Codex source set.';
    END IF;

    IF existing_analyst_count NOT IN (0, 28) THEN
        RAISE EXCEPTION 'Found % of 28 target analyst reviews. Refusing to initialize or overwrite a partial analyst set.', existing_analyst_count;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM permission_pilot.classification_review analyst
        JOIN permission_pilot.permission_selection selection USING (selection_id)
        JOIN permission_pilot.pilot_definition pilot USING (pilot_id)
        LEFT JOIN source_codex_review source USING (selection_id)
        WHERE pilot.pilot_code = 'MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
          AND analyst.reviewer_kind = 'analyst'
          AND analyst.reviewer_identifier = 'jon_bruce'
          AND analyst.review_round = 1
          AND source.selection_id IS NULL
          AND analyst.review_status <> 'submitted'
    ) THEN
        RAISE EXCEPTION 'An unexpected non-submitted analyst row exists outside the 28 target selections.';
    END IF;
END;
$$;

CREATE TEMPORARY TABLE analyst_draft_to_initialize ON COMMIT DROP AS
SELECT source.*
FROM source_codex_review source
WHERE NOT EXISTS (
    SELECT 1 FROM permission_pilot.classification_review analyst
    WHERE analyst.selection_id = source.selection_id
      AND analyst.reviewer_kind = 'analyst'
      AND analyst.reviewer_identifier = 'jon_bruce'
      AND analyst.review_round = 1
);

INSERT INTO permission_pilot.classification_review (
    selection_id, reviewer_kind, reviewer_identifier, review_round,
    access_level, capability, administrative_capability, privilege_level,
    data_sensitivity, destructive_potential, tenant_wide_impact,
    consent_sensitivity, classification_confidence, rationale, review_status
)
SELECT source.selection_id, 'analyst', 'jon_bruce', 1,
       source.access_level, source.capability, source.administrative_capability,
       source.privilege_level, source.data_sensitivity,
       source.destructive_potential, source.tenant_wide_impact,
       source.consent_sensitivity, source.classification_confidence,
       source.rationale, 'draft'
FROM analyst_draft_to_initialize source
ON CONFLICT (selection_id, reviewer_kind, reviewer_identifier, review_round)
DO NOTHING;

INSERT INTO permission_pilot.review_domain_assignment (
    review_id, domain_id, assignment_kind, mapping_rationale
)
SELECT analyst.review_id, assignment.domain_id, assignment.assignment_kind,
       assignment.mapping_rationale
FROM analyst_draft_to_initialize source
JOIN permission_pilot.classification_review analyst
  ON analyst.selection_id = source.selection_id
 AND analyst.reviewer_kind = 'analyst'
 AND analyst.reviewer_identifier = 'jon_bruce'
 AND analyst.review_round = 1
JOIN permission_pilot.review_domain_assignment assignment
  ON assignment.review_id = source.codex_review_id
ON CONFLICT (review_id, domain_id) DO NOTHING;

DO $$
BEGIN
    IF (SELECT count(*)
        FROM permission_pilot.classification_review analyst
        JOIN source_codex_review source USING (selection_id)
        WHERE analyst.reviewer_kind = 'analyst'
          AND analyst.reviewer_identifier = 'jon_bruce'
          AND analyst.review_round = 1) <> 28 THEN
        RAISE EXCEPTION 'Expected exactly 28 target analyst reviews after initialization.';
    END IF;

    IF EXISTS (
        SELECT analyst.review_id
        FROM permission_pilot.classification_review analyst
        JOIN source_codex_review source USING (selection_id)
        LEFT JOIN permission_pilot.review_domain_assignment assignment
          ON assignment.review_id = analyst.review_id
        WHERE analyst.reviewer_kind = 'analyst'
          AND analyst.reviewer_identifier = 'jon_bruce'
          AND analyst.review_round = 1
        GROUP BY analyst.review_id
        HAVING count(*) FILTER (WHERE assignment.assignment_kind = 'primary') <> 1
    ) THEN
        RAISE EXCEPTION 'Every initialized analyst review must have exactly one primary domain.';
    END IF;
END;
$$;

COMMIT;
