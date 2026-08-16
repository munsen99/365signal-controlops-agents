#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import lancedb
import requests
import sys
from pathlib import Path

RAG_ROOT = Path("/mnt/Storage/AI/RAG/MultimodalIngest")
sys.path.insert(0, str(RAG_ROOT))
sys.path.insert(0, str(RAG_ROOT / "scripts"))

from scripts.common.embeddings import embed_text


CATALOG_URL = "https://learn.microsoft.com/api/catalog/"
DEFAULT_TABLE = "msft_learn_catalog_nomic_v1"
DEFAULT_MODEL = "nomic-ai/nomic-embed-text-v1.5"


def clean_url(url: str | None) -> str | None:
    """Remove tracking query strings while preserving the canonical path."""
    if not url:
        return None

    parts = urlsplit(url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            "",
            "",
        )
    )


def as_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item) for item in value if item is not None]

    return [str(value)]


def build_embedding_text(
    *,
    content_type: str,
    title: str,
    summary: str,
    products: list[str],
    roles: list[str],
    subjects: list[str],
    levels: list[str],
) -> str:
    sections = [
        f"Content type: {content_type}",
        f"Title: {title}",
        f"Summary: {summary}",
    ]

    if products:
        sections.append(f"Products: {', '.join(products)}")

    if subjects:
        sections.append(f"Subjects: {', '.join(subjects)}")

    if roles:
        sections.append(f"Roles: {', '.join(roles)}")

    if levels:
        sections.append(f"Levels: {', '.join(levels)}")

    return "\n".join(sections)


def fetch_catalog(locale: str) -> dict[str, Any]:
    response = requests.get(
        CATALOG_URL,
        params={"locale": locale},
        headers={
            "Accept": "application/json",
            "User-Agent": "365signal-controlops-msft-validator/0.1",
        },
        timeout=(10, 120),
    )

    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError("Microsoft Learn returned a non-object JSON response")

    return payload


def normalise_records(
    payload: dict[str, Any],
    *,
    locale: str,
    retrieved_at: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    collections = {
        "modules": "module",
        "learningPaths": "learning_path",
    }

    for collection_name, content_type in collections.items():
        items = payload.get(collection_name, [])

        if not isinstance(items, list):
            print(
                f"Warning: {collection_name} was not a list; skipping",
                file=sys.stderr,
            )
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            uid = str(item.get("uid") or "").strip()
            title = str(item.get("title") or "").strip()

            if not uid or not title:
                continue

            summary = str(item.get("summary") or "").strip()
            products = as_list(item.get("products"))
            roles = as_list(item.get("roles"))
            subjects = as_list(item.get("subjects"))
            levels = as_list(item.get("levels"))

            canonical_url = clean_url(item.get("url"))
            original_url = item.get("url")

            text = build_embedding_text(
                content_type=content_type,
                title=title,
                summary=summary,
                products=products,
                roles=roles,
                subjects=subjects,
                levels=levels,
            )

            records.append(
                {
                    "id": uid,
                    "uid": uid,
                    "source_type": "microsoft_learn_catalog",
                    "content_type": content_type,
                    "evidence_classification": "discovery_index",
                    "locale": locale,
                    "title": title,
                    "summary": summary,
                    "text": text,
                    "url": canonical_url,
                    "catalog_url": original_url,
                    "last_modified": item.get("last_modified"),
                    "products": products,
                    "roles": roles,
                    "subjects": subjects,
                    "levels": levels,
                    "retrieved_at": retrieved_at,
                    "raw_json": json.dumps(
                        item,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )

    return records


def embed_records(
    records: list[dict[str, Any]],
    model_name: str,
) -> list[dict[str, Any]]:
    for index, record in enumerate(records, start=1):
        record["vector"] = embed_text(record["text"])

        if index % 100 == 0:
            print(f"Embedded {index}/{len(records)}")

    return records


def write_table(
    records: list[dict[str, Any]],
    *,
    db_uri: str,
    table_name: str,
    overwrite: bool,
) -> None:
    db = lancedb.connect(db_uri)

    existing_tables = set(db.list_tables())

    if table_name in existing_tables and not overwrite:
        table = db.open_table(table_name)

        # Replace existing rows with the same IDs, then append the new versions.
        ids = [record["id"] for record in records]

        batch_size = 250

        for offset in range(0, len(ids), batch_size):
            batch = ids[offset : offset + batch_size]
            quoted = ", ".join(
                "'" + value.replace("'", "''") + "'"
                for value in batch
            )
            table.delete(f"id IN ({quoted})")

        table.add(records)
    else:
        mode = "overwrite" if overwrite else "create"
        table = db.create_table(
            table_name,
            data=records,
            mode=mode,
        )

    print(f"Table: {table_name}")
    print(f"Database: {db_uri}")
    print(f"Rows ingested: {len(records)}")
    print(table.schema)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Microsoft Learn catalogue data into LanceDB."
    )

    parser.add_argument(
        "--db-uri",
        default=os.environ.get("LANCEDB_URI"),
        help="LanceDB URI or filesystem path. Defaults to LANCEDB_URI.",
    )

    parser.add_argument(
        "--table",
        default=DEFAULT_TABLE,
    )

    parser.add_argument(
        "--locale",
        default="en-us",
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the table rather than updating matching records.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.db_uri:
        print(
            "Error: supply --db-uri or set LANCEDB_URI.",
            file=sys.stderr,
        )
        return 2

    retrieved_at = datetime.now(timezone.utc).isoformat()

    print(f"Retrieving {CATALOG_URL}")
    payload = fetch_catalog(args.locale)

    records = normalise_records(
        payload,
        locale=args.locale,
        retrieved_at=retrieved_at,
    )

    if not records:
        print("Error: no catalogue records were found.", file=sys.stderr)
        return 1

    module_count = sum(
        record["content_type"] == "module"
        for record in records
    )

    path_count = sum(
        record["content_type"] == "learning_path"
        for record in records
    )

    print(f"Modules found: {module_count}")
    print(f"Learning paths found: {path_count}")

    records = embed_records(records, args.model)

    write_table(
        records,
        db_uri=args.db_uri,
        table_name=args.table,
        overwrite=args.overwrite,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
