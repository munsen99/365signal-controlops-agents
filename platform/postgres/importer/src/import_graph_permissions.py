#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


SOURCE_PROPERTIES = {
    "appRoles": "Application",
    "oauth2PermissionScopes": "Delegated",
    "resourceSpecificApplicationPermissions": "RSC",
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def classify_access(permission_name: str) -> str:
    name = permission_name.casefold()

    if "readwriteandconsent" in name:
        return "Consent-Grant"
    if "readwrite" in name or "read.update" in name:
        return "ReadWrite"
    if ".manage" in name or name.startswith("manage"):
        return "Manage"
    if ".selected" in name:
        return "Read-Selected"
    if "readbasic" in name or "readlimited" in name:
        return "Read-Limited"
    if ".read" in name or name.startswith("read"):
        return "Read"
    if permission_name in {"openid", "profile", "email", "offline_access"}:
        return "Authentication"

    return "Unknown"


def unwrap_graph_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Expected the Graph export to contain a JSON object.")

    if "value" in payload:
        values = payload["value"]
        if not isinstance(values, list) or not values:
            raise ValueError("The Graph response contains no service principal records.")
        if len(values) > 1:
            raise ValueError(
                f"Expected one Microsoft Graph service principal; received {len(values)}."
            )
        record = values[0]
    else:
        record = payload

    if not isinstance(record, dict):
        raise ValueError("The service principal record is not a JSON object.")

    if record.get("appId") != "00000003-0000-0000-c000-000000000000":
        raise ValueError(
            "The exported object is not the Microsoft Graph service principal."
        )

    return record


def flatten_permissions(service_principal: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for source_property, permission_type in SOURCE_PROPERTIES.items():
        values = service_principal.get(source_property) or []

        if not isinstance(values, list):
            raise ValueError(f"{source_property} is not an array.")

        for raw in values:
            if not isinstance(raw, dict):
                continue

            permission_name = raw.get("value") or raw.get("displayName")
            if not permission_name:
                continue

            records.append(
                {
                    "external_id": raw.get("id"),
                    "permission_name": permission_name,
                    "permission_type": permission_type,
                    "display_name": raw.get("displayName"),
                    "description": (
                        raw.get("description")
                        or raw.get("adminConsentDescription")
                        or raw.get("userConsentDescription")
                    ),
                    "access_class": classify_access(permission_name),
                    "admin_consent_required": (
                        True
                        if permission_type == "Application"
                        else raw.get("type") == "Admin"
                    ),
                    "is_enabled": bool(raw.get("isEnabled", True)),
                    "source_property": source_property,
                    "source_hash": sha256_json(raw),
                    "raw_payload": raw,
                }
            )

    return records


def connection_string() -> str:
    return (
        f"host={os.getenv('POSTGRES_HOST', '127.0.0.1')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'controlops')} "
        f"user={os.getenv('POSTGRES_USER', 'controlops_admin')} "
        f"password={os.environ['POSTGRES_PASSWORD']}"
    )


def import_catalogue(input_path: Path, collector_version: str) -> None:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    service_principal = unwrap_graph_response(payload)
    permissions = flatten_permissions(service_principal)
    payload_hash = sha256_json(payload)
    now = datetime.now(timezone.utc)

    added = 0
    changed = 0
    unchanged = 0
    retired = 0

    with psycopg.connect(connection_string()) as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ss.source_system_id, i.interface_id
                    FROM catalogue.source_system ss
                    JOIN catalogue.interface i
                      ON i.source_system_id = ss.source_system_id
                    WHERE ss.source_code = 'MSGRAPH'
                      AND i.interface_code = 'MSGRAPH_V1'
                    """
                )
                source = cursor.fetchone()

                if not source:
                    raise RuntimeError(
                        "MSGRAPH source/interface seed records were not found."
                    )

                source_system_id, interface_id = source

                cursor.execute(
                    """
                    INSERT INTO operations.catalogue_import_run (
                        source_system_id,
                        interface_id,
                        started_at,
                        collector_version,
                        source_version,
                        status,
                        records_received,
                        payload_hash
                    )
                    VALUES (%s, %s, %s, %s, %s, 'running', %s, %s)
                    RETURNING import_run_id
                    """,
                    (
                        source_system_id,
                        interface_id,
                        now,
                        collector_version,
                        "v1.0",
                        len(permissions),
                        payload_hash,
                    ),
                )
                import_run_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                    INSERT INTO raw.catalogue_snapshot (
                        import_run_id,
                        source_uri,
                        retrieved_at,
                        payload,
                        payload_hash
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        import_run_id,
                        (
                            "https://graph.microsoft.com/v1.0/"
                            "servicePrincipals(appId="
                            "'00000003-0000-0000-c000-000000000000')"
                        ),
                        now,
                        Jsonb(payload),
                        payload_hash,
                    ),
                )

                observed_keys: set[tuple[str, str]] = set()

                for permission in permissions:
                    key = (
                        permission["permission_type"],
                        permission["permission_name"],
                    )
                    observed_keys.add(key)

                    cursor.execute(
                        """
                        SELECT permission_definition_id, source_hash
                        FROM catalogue.permission_definition
                        WHERE interface_id = %s
                          AND permission_type = %s
                          AND permission_name = %s
                          AND is_current = true
                        """,
                        (
                            interface_id,
                            permission["permission_type"],
                            permission["permission_name"],
                        ),
                    )
                    current = cursor.fetchone()

                    if current and current[1] == permission["source_hash"]:
                        unchanged += 1
                        continue

                    if current:
                        cursor.execute(
                            """
                            UPDATE catalogue.permission_definition
                            SET valid_to = %s,
                                is_current = false
                            WHERE permission_definition_id = %s
                            """,
                            (now, current[0]),
                        )
                        changed += 1
                    else:
                        added += 1

                    cursor.execute(
                        """
                        INSERT INTO catalogue.permission_definition (
                            interface_id,
                            external_id,
                            permission_name,
                            permission_type,
                            display_name,
                            description,
                            access_class,
                            admin_consent_required,
                            is_enabled,
                            source_property,
                            valid_from,
                            is_current,
                            source_hash,
                            raw_payload
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, true, %s, %s
                        )
                        """,
                        (
                            interface_id,
                            permission["external_id"],
                            permission["permission_name"],
                            permission["permission_type"],
                            permission["display_name"],
                            permission["description"],
                            permission["access_class"],
                            permission["admin_consent_required"],
                            permission["is_enabled"],
                            permission["source_property"],
                            now,
                            permission["source_hash"],
                            Jsonb(permission["raw_payload"]),
                        ),
                    )

                cursor.execute(
                    """
                    SELECT permission_definition_id,
                           permission_type,
                           permission_name
                    FROM catalogue.permission_definition
                    WHERE interface_id = %s
                      AND is_current = true
                    """,
                    (interface_id,),
                )

                for permission_id, permission_type, permission_name in cursor.fetchall():
                    if (permission_type, permission_name) not in observed_keys:
                        cursor.execute(
                            """
                            UPDATE catalogue.permission_definition
                            SET valid_to = %s,
                                is_current = false,
                                is_enabled = false
                            WHERE permission_definition_id = %s
                            """,
                            (now, permission_id),
                        )
                        retired += 1

                cursor.execute(
                    """
                    UPDATE operations.catalogue_import_run
                    SET completed_at = %s,
                        status = 'success',
                        records_added = %s,
                        records_changed = %s,
                        records_retired = %s
                    WHERE import_run_id = %s
                    """,
                    (now, added, changed, retired, import_run_id),
                )

    print(f"Import run: {import_run_id}")
    print(f"Permissions received: {len(permissions)}")
    print(f"Added: {added}")
    print(f"Changed: {changed}")
    print(f"Unchanged: {unchanged}")
    print(f"Retired: {retired}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Microsoft Graph permission definitions into ControlOps."
    )
    parser.add_argument("input_file", type=Path)
    parser.add_argument("--collector-version", default="0.1.0")
    args = parser.parse_args()

    if not args.input_file.is_file():
        print(f"Input file not found: {args.input_file}", file=sys.stderr)
        return 1

    try:
        import_catalogue(args.input_file, args.collector_version)
    except Exception as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
