"""Referential integrity of cited evidence. This is not an entailment judge."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .retrieve import Candidate


def check_integrity(
    candidates: list[Candidate],
    evidence_ids: list[str],
    status: str,
    evidence_dir: Path,
    selected_ids: list[str],
) -> dict:
    """Return PASS or INTEGRITY_FAILED. Callers force insufficient on failure."""
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    chosen = set(selected_ids)
    errors: list[str] = []
    if status == "supported" and not evidence_ids:
        errors.append("supported requires evidence_ids")
    for evidence_id in evidence_ids:
        if status != "insufficient" and evidence_id not in chosen:
            errors.append(f"{evidence_id} was not selected")
        candidate = by_id.get(evidence_id)
        if candidate is None:
            errors.append(f"unknown id {evidence_id}")
            continue
        if candidate.usable is not True:
            errors.append(f"{evidence_id} is not usable")
        if candidate.http_status != 200:
            errors.append(f"{evidence_id} http_status")
        path = evidence_dir / f"{evidence_id}.bin"
        if candidate.content_hash is None or not path.is_file():
            errors.append(f"{evidence_id} bytes missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != candidate.content_hash:
            errors.append(f"{evidence_id} hash mismatch")
        if not candidate.text:
            errors.append(f"{evidence_id} empty text")
    if errors:
        return {"result": "INTEGRITY_FAILED", "errors": errors}
    return {"result": "PASS", "errors": []}
