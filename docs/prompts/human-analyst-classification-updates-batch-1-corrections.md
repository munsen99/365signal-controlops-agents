# Human Analyst Classification Updates — Batch 1 Corrections

Apply the following exact human analyst decisions to:

```text
reviewer_kind = analyst
reviewer_identifier = jon_bruce
review_round = 1
```

Do not reinterpret or alter these values.

## 1. AppRoleAssignment.ReadWrite.All — Application

```text
capability = manage
access_level = all
privilege_level = critical
data_sensitivity = moderate
destructive_potential = critical
consent_sensitivity = critical
classification_confidence = high
```

## 2. AuditLog.Read.All — Delegated

```text
capability = read
access_level = all
privilege_level = high
data_sensitivity = high
destructive_potential = none
consent_sensitivity = high
classification_confidence = high
```

## 3. DeviceLocalCredential.Read.All — Application

```text
capability = read
access_level = all
privilege_level = critical
data_sensitivity = restricted
destructive_potential = critical
consent_sensitivity = high
classification_confidence = high
```

## 4. Directory.AccessAsUser.All — Delegated

```text
capability = read
access_level = all
privilege_level = high
data_sensitivity = moderate
destructive_potential = moderate
consent_sensitivity = high
classification_confidence = high
```

## 5. Sites.Selected — Application

```text
capability = unknown
access_level = selected
privilege_level = unknown
data_sensitivity = moderate
destructive_potential = unknown
consent_sensitivity = moderate
classification_confidence = medium
```

The original instruction supplied `consent_sensitivity = medium`. The human
analyst subsequently corrected that value to the controlled value `moderate`.
All other values remained exactly as originally supplied.

## 6. Teamwork.Migrate.All — Application

```text
capability = write
access_level = all
privilege_level = critical
data_sensitivity = high
destructive_potential = high
consent_sensitivity = high
classification_confidence = high
```

## 7. User.Read — Delegated

```text
capability = read
access_level = owned
privilege_level = low
data_sensitivity = low
destructive_potential = none
consent_sensitivity = low
classification_confidence = high
```

## Important

These are explicit human analyst decisions.

Codex must:

- apply only these field changes;
- not reclassify them;
- not modify domain assignments;
- not modify review status unless separately instructed;
- not change any Codex review rows;
- not change unrelated analyst rows;
- preserve review IDs and created timestamps;
- update `updated_at` only where values actually change;
- validate all seven rows after persistence;
- make the migration idempotent;
- create no disagreements or adjudications;
- not commit or push.
