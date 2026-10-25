#!/usr/bin/env python3
import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "data" / "research.db"

def now():
    return datetime.now(timezone.utc).isoformat()

def canonical_url(url):
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("A valid HTTP(S) source URL is required")
    query = urlencode(sorted(
        (k, v) for k, v in parse_qsl(parts.query)
        if not k.lower().startswith("utm_")
        and k.lower() not in ("fbclid", "gclid")
    ))
    return urlunsplit((
        "https",
        parts.netloc.lower(),
        parts.path.rstrip("/") or "/",
        query,
        ""
    ))

def event_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:24]

def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute("PRAGMA foreign_keys=ON")
    db.row_factory = sqlite3.Row
    return db

def output(data):
    print(json.dumps(data, indent=2))

def check_duplicate(url):
    url = canonical_url(url)
    with connect() as db:
        row = db.execute(
            "SELECT * FROM research_events WHERE canonical_url=?",
            (url,)
        ).fetchone()
    return {
        "duplicate": row is not None,
        "event": dict(row) if row else None
    }

def record_event(args):
    url = canonical_url(args.url)
    eid = event_id(url)
    timestamp = now()

    with connect() as db:
        existing = db.execute(
            "SELECT event_id FROM research_events WHERE canonical_url=?",
            (url,)
        ).fetchone()

        if existing:
            db.execute(
                "UPDATE research_events SET last_seen_at=? WHERE event_id=?",
                (timestamp, existing["event_id"])
            )
            eid = existing["event_id"]
            status = "existing"
        else:
            db.execute("""
                INSERT INTO research_events
                (event_id, canonical_url, title, product,
                 published_at, first_seen_at, last_seen_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'discovered')
            """, (
                eid, url, args.title, args.product,
                args.published, timestamp, timestamp
            ))
            status = "created"

        db.execute("""
            INSERT OR IGNORE INTO research_sources
            (event_id, source_url, source_name, retrieved_at)
            VALUES (?, ?, ?, ?)
        """, (eid, url, args.source, timestamp))

    return {"status": status, "event_id": eid, "url": url}

def record_decision(args):
    # Component validation is handled by calculate_score().
    # No manually supplied weighted score is accepted.

    timestamp = now()
    with connect() as db:
        event = db.execute(
            "SELECT event_id FROM research_events WHERE event_id=?",
            (args.event_id,)
        ).fetchone()
        if not event:
            raise ValueError("Unknown event_id")

        db.execute("""
            INSERT OR IGNORE INTO research_runs
            (run_id, started_at, status)
            VALUES (?, ?, 'running')
        """, (args.run_id, timestamp))

        score = calculate_score(
            args.technical, args.risk, args.architecture,
            args.relevance, args.novelty
        )

        db.execute("""
            INSERT INTO research_decisions
            (run_id, event_id, score, rationale, decision, decided_at,
             technical, risk, architecture, relevance, novelty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            args.run_id, args.event_id, score,
            args.rationale, args.decision, timestamp,
            args.technical, args.risk, args.architecture,
            args.relevance, args.novelty
        ))

    return {"status": "recorded", "run_id": args.run_id}

def calculate_score(technical, risk, architecture,
                    relevance, novelty):
    weights = {
        "technical": 0.25,
        "risk": 0.25,
        "architecture": 0.25,
        "relevance": 0.15,
        "novelty": 0.10
    }

    scores = {
        "technical": technical,
        "risk": risk,
        "architecture": architecture,
        "relevance": relevance,
        "novelty": novelty
    }

    for name, value in scores.items():
        if not 0 <= value <= 5:
            raise ValueError(
                f"{name} must be between 0 and 5"
            )

    return round(
        sum(scores[k] * weights[k] for k in weights),
        3
    )

def main():
    parser = argparse.ArgumentParser(description="365Signal Research Memory")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("record-event")
    add.add_argument("--url", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--product", default="")
    add.add_argument("--published", default=None)
    add.add_argument("--source", default="")

    dup = sub.add_parser("check-duplicate")
    dup.add_argument("--url", required=True)

    decision = sub.add_parser("record-decision")
    decision.add_argument("--run-id", required=True)
    decision.add_argument("--event-id", required=True)
    for component in ("technical", "risk", "architecture", "relevance", "novelty"):
        decision.add_argument(
            f"--{component}", type=float, required=True
        )
    decision.add_argument("--decision", required=True,
                          choices=["selected", "rejected", "deferred"])
    decision.add_argument("--rationale", required=True)

    args = parser.parse_args()

    try:
        if args.command == "record-event":
            output(record_event(args))
        elif args.command == "check-duplicate":
            output(check_duplicate(args.url))
        elif args.command == "record-decision":
            output(record_decision(args))
    except (ValueError, sqlite3.Error) as exc:
        output({"error": str(exc)})
        raise SystemExit(1)

if __name__ == "__main__":
    main()
