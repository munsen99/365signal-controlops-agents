\set ON_ERROR_STOP on

BEGIN;

CREATE TEMPORARY TABLE proposed_human_correction (
    permission_name TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    capability TEXT NOT NULL,
    access_level TEXT NOT NULL,
    privilege_level TEXT NOT NULL,
    data_sensitivity TEXT NOT NULL,
    destructive_potential TEXT NOT NULL,
    consent_sensitivity TEXT NOT NULL,
    classification_confidence TEXT NOT NULL,
    PRIMARY KEY (permission_name, permission_type)
) ON COMMIT DROP;

INSERT INTO proposed_human_correction VALUES
('AppRoleAssignment.ReadWrite.All','Application','manage','all','critical','moderate','critical','critical','high'),
('AuditLog.Read.All','Delegated','read','all','high','high','none','high','high'),
('DeviceLocalCredential.Read.All','Application','read','all','critical','restricted','critical','high','high'),
('Directory.AccessAsUser.All','Delegated','read','all','high','moderate','moderate','high','high'),
('Sites.Selected','Application','unknown','selected','unknown','moderate','unknown','moderate','medium'),
('Teamwork.Migrate.All','Application','write','all','critical','high','high','high','high'),
('User.Read','Delegated','read','owned','low','low','none','low','high');

CREATE TEMPORARY TABLE target_review ON COMMIT DROP AS
SELECT review.review_id, review.selection_id,
       permission.permission_definition_id,
       permission.permission_name, permission.permission_type
FROM proposed_human_correction proposed
JOIN permission_pilot.pilot_definition pilot
  ON pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
JOIN permission_pilot.permission_selection selection
  ON selection.pilot_id=pilot.pilot_id AND selection.sample_stage='final'
JOIN catalogue.permission_definition permission
  ON permission.permission_definition_id=selection.permission_definition_id
 AND permission.permission_name=proposed.permission_name
 AND permission.permission_type=proposed.permission_type
JOIN permission_pilot.classification_review review
  ON review.selection_id=selection.selection_id
 AND review.reviewer_kind='analyst'
 AND review.reviewer_identifier='jon_bruce'
 AND review.review_round=1;

DO $$
BEGIN
    IF (SELECT count(*) FROM proposed_human_correction)<>7
       OR (SELECT count(*) FROM target_review)<>7 THEN
        RAISE EXCEPTION 'Expected exactly seven proposed and resolved analyst corrections.';
    END IF;
END;
$$;

UPDATE permission_pilot.classification_review review
SET capability=proposed.capability,
    access_level=proposed.access_level,
    privilege_level=proposed.privilege_level,
    data_sensitivity=proposed.data_sensitivity,
    destructive_potential=proposed.destructive_potential,
    consent_sensitivity=proposed.consent_sensitivity,
    classification_confidence=proposed.classification_confidence,
    updated_at=now()
FROM target_review target
JOIN proposed_human_correction proposed
  USING (permission_name,permission_type)
WHERE review.review_id=target.review_id
  AND (review.capability,review.access_level,review.privilege_level,
       review.data_sensitivity,review.destructive_potential,
       review.consent_sensitivity,review.classification_confidence)
      IS DISTINCT FROM
      (proposed.capability,proposed.access_level,proposed.privilege_level,
       proposed.data_sensitivity,proposed.destructive_potential,
       proposed.consent_sensitivity,proposed.classification_confidence);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM target_review target
        JOIN proposed_human_correction proposed USING(permission_name,permission_type)
        JOIN permission_pilot.classification_review review USING(review_id)
        WHERE (review.capability,review.access_level,review.privilege_level,
               review.data_sensitivity,review.destructive_potential,
               review.consent_sensitivity,review.classification_confidence)
          IS DISTINCT FROM
              (proposed.capability,proposed.access_level,proposed.privilege_level,
               proposed.data_sensitivity,proposed.destructive_potential,
               proposed.consent_sensitivity,proposed.classification_confidence)
    ) THEN RAISE EXCEPTION 'A persisted analyst correction differs from the exact human decision.'; END IF;
END;
$$;

COMMIT;
