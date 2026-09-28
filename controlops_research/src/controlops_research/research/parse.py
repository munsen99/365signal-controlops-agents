"""Parse one infer response. There is no repair retry."""

from __future__ import annotations

import json


class ModelOutputInvalid(Exception):
    """The adapter returned text that is not the required JSON object."""


def parse_selection(raw: str) -> dict:
    document = _object(raw)
    values = document.get("selected_ids")
    rationale = document.get("rationale")
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise ModelOutputInvalid("selected_ids")
    if not isinstance(rationale, str):
        raise ModelOutputInvalid("rationale")
    if set(document) - {"selected_ids", "rationale", "model"}:
        raise ModelOutputInvalid("keys")
    return {"selected_ids": values, "rationale": rationale}


def parse_draft(raw: str) -> dict:
    document = _object(raw)
    status = document.get("status")
    finding = document.get("finding")
    evidence_ids = document.get("evidence_ids")
    rationale = document.get("rationale")
    if status not in {"supported", "insufficient"}:
        raise ModelOutputInvalid("status")
    if not isinstance(finding, str) or not isinstance(rationale, str):
        raise ModelOutputInvalid("text")
    if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
        raise ModelOutputInvalid("evidence_ids")
    if set(document) - {"status", "finding", "evidence_ids", "rationale", "model"}:
        raise ModelOutputInvalid("keys")
    return {
        "status": status,
        "finding": finding,
        "evidence_ids": evidence_ids,
        "rationale": rationale,
    }


def _object(raw: str) -> dict:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ModelOutputInvalid("json") from error
    if not isinstance(document, dict):
        raise ModelOutputInvalid("object")
    return document
