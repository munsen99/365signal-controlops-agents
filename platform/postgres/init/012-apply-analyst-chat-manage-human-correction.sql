\set ON_ERROR_STOP on

BEGIN;

CREATE TEMPORARY TABLE target_review ON COMMIT DROP AS
SELECT review.review_id
FROM permission_pilot.pilot_definition pilot
JOIN permission_pilot.permission_selection selection USING(pilot_id)
JOIN catalogue.permission_definition permission USING(permission_definition_id)
JOIN permission_pilot.classification_review review USING(selection_id)
WHERE pilot.pilot_code='MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36'
  AND selection.sample_stage='final'
  AND permission.permission_name='Chat.Manage.Chat'
  AND permission.permission_type='RSC'
  AND review.reviewer_kind='analyst'
  AND review.reviewer_identifier='jon_bruce'
  AND review.review_round=1;

DO $$
BEGIN
    IF (SELECT count(*) FROM target_review)<>1 THEN
        RAISE EXCEPTION 'Expected exactly one Chat.Manage.Chat RSC analyst review; found %.',
            (SELECT count(*) FROM target_review);
    END IF;
END;
$$;

UPDATE permission_pilot.classification_review review
SET capability='manage',
    access_level='selected',
    privilege_level='high',
    data_sensitivity='high',
    destructive_potential='high',
    consent_sensitivity='high',
    classification_confidence='high',
    updated_at=now()
FROM target_review target
WHERE review.review_id=target.review_id
  AND (review.capability,review.access_level,review.privilege_level,
       review.data_sensitivity,review.destructive_potential,
       review.consent_sensitivity,review.classification_confidence)
      IS DISTINCT FROM
      ('manage','selected','high','high','high','high','high');

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM target_review target
        JOIN permission_pilot.classification_review review USING(review_id)
        WHERE (review.capability,review.access_level,review.privilege_level,
               review.data_sensitivity,review.destructive_potential,
               review.consent_sensitivity,review.classification_confidence)
          IS DISTINCT FROM ('manage','selected','high','high','high','high','high')
    ) THEN
        RAISE EXCEPTION 'Persisted Chat.Manage.Chat values differ from the human decision.';
    END IF;
END;
$$;

COMMIT;
