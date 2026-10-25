#!/usr/bin/env python3
"""365Signal event-level duplicate detection, v0.3."""
import argparse
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit

from research_memory import canonical_url

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "research.db"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for",
    "from", "in", "into", "is", "of", "on", "or",
    "the", "to", "with", "your", "new", "latest",
    "microsoft", "security", "update", "announces",
    "announced", "blog"
}

def tokens(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}

def similarity(a, b):
    x, y = tokens(a), tokens(b)
    if not x or not y:
        return 0.0
    jaccard = len(x & y) / len(x | y)
    ordered = SequenceMatcher(
        None, " ".join(sorted(x)), " ".join(sorted(y))
    ).ratio()
    return round(0.7 * jaccard + 0.3 * ordered, 4)

def connection():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def date_distance(a, b):
    if not a or not b:
        return None
    try:
        return abs((date.fromisoformat(a[:10]) -
                    date.fromisoformat(b[:10])).days)
    except ValueError:
        return None

def check(url, title, product="", published=None):
    url = canonical_url(url)
    results = []

    with connection() as con:
        exact = con.execute("""
            SELECT e.event_id, e.title, e.canonical_url
            FROM research_events e
            WHERE e.canonical_url = ?
            UNION
            SELECT e.event_id, e.title, e.canonical_url
            FROM research_sources s
            JOIN research_events e ON e.event_id = s.event_id
            WHERE s.source_url = ?
        """, (url, url)).fetchone()

        if exact:
            return {
                "classification": "exact_duplicate",
                "event": dict(exact),
                "candidates": []
            }

        rows = con.execute("""
            SELECT event_id, title, product, published_at,
                   canonical_url
            FROM research_events
        """).fetchall()

        for row in rows:
            score = similarity(title, row["title"])
            same_product = bool(
                product and row["product"] and
                product.strip().casefold() ==
                row["product"].strip().casefold()
            )
            distance = date_distance(published, row["published_at"])

            # Only compare events from a plausible time window.
            # Unknown dates remain candidates but get no date bonus.
            if distance is not None and distance > 30:
                continue

            # Product is corroborating evidence, not proof.
            # Date proximity adds only a small bonus.
            adjusted = min(
                1.0,
                score +
                (0.04 if same_product else 0.0) +
                (0.03 if distance is not None and distance <= 7 else 0.0)
            )

            if adjusted >= 0.55:
                results.append({
                    "event_id": row["event_id"],
                    "title": row["title"],
                    "canonical_url": row["canonical_url"],
                    "similarity": round(adjusted, 4),
                    "published_at": row["published_at"],
                    "same_product": same_product,
                    "date_distance_days": distance
                })

    results.sort(key=lambda x: x["similarity"], reverse=True)

    return {
        "classification": (
            "possible_duplicate" if results else "no_match"
        ),
        "candidates": results[:5],
        "note": "Similarity is advisory, not confirmation of event identity."
    }

def attach_source(event_id, url, source):
    url = canonical_url(url)
    timestamp = datetime.now(timezone.utc).isoformat()

    with connection() as con:
        event = con.execute(
            "SELECT event_id FROM research_events WHERE event_id=?",
            (event_id,)
        ).fetchone()
        if not event:
            raise ValueError("Unknown event_id")

        conflict = con.execute("""
            SELECT event_id FROM research_events
            WHERE canonical_url=?
            UNION
            SELECT event_id FROM research_sources
            WHERE source_url=?
        """, (url, url)).fetchone()

        if conflict and conflict["event_id"] != event_id:
            raise ValueError(
                "Source URL already belongs to a different event"
            )

        con.execute("""
            INSERT OR IGNORE INTO research_sources
            (event_id, source_url, source_name, retrieved_at)
            VALUES (?, ?, ?, ?)
        """, (event_id, url, source, timestamp))

    return {
        "status": "source_attached_or_already_present",
        "event_id": event_id,
        "source_url": url
    }

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check")
    c.add_argument("--url", required=True)
    c.add_argument("--title", required=True)
    c.add_argument("--product", default="")
    c.add_argument("--published")

    a = sub.add_parser("attach-source")
    a.add_argument("--event-id", required=True)
    a.add_argument("--url", required=True)
    a.add_argument("--source", required=True)
    a.add_argument("--confirmed-same-event", action="store_true",
                   required=True)

    args = p.parse_args()

    try:
        if args.command == "check":
            result = check(
                args.url, args.title,
                args.product, args.published
            )
        else:
            result = attach_source(
                args.event_id, args.url, args.source
            )
        print(json.dumps(result, indent=2))
    except (ValueError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(1)

if __name__ == "__main__":
    main()
