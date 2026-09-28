"""Write one run directory. Paths stay under runtime/runs."""

from __future__ import annotations

import json
from pathlib import Path

from .retrieve import Candidate


def question_document(question: str, seed_urls: list[str], canonical_seed_urls: list[str] | None = None) -> dict:
    document = {"question": question, "seed_urls": list(seed_urls)}
    if canonical_seed_urls is not None:
        document["canonical_seed_urls"] = list(canonical_seed_urls)
    return document


def write_question(run_dir: Path, question: str, seed_urls: list[str], canonical_seed_urls: list[str] | None = None) -> None:
    _yaml(run_dir / "question.yaml", question_document(question, seed_urls, canonical_seed_urls))


def write_selection(run_dir: Path, document: dict) -> None:
    (run_dir / "selection.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def write_candidates(run_dir: Path, candidates: list[Candidate]) -> None:
    evidence = run_dir / "evidence"
    evidence.mkdir(exist_ok=True)
    for candidate in candidates:
        if candidate.body:
            (evidence / f"{candidate.candidate_id}.bin").write_bytes(candidate.body)
    payload = {"candidates": [candidate.public() for candidate in candidates]}
    (run_dir / "candidate-evidence.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_finding(run_dir: Path, finding: dict) -> None:
    _yaml(run_dir / "finding.yaml", finding)


def write_integrity(run_dir: Path, result: dict) -> None:
    (run_dir / "evidence-integrity.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def write_run(run_dir: Path, document: dict) -> None:
    allowed = ("run_id", "started_at", "completed_at", "model", "status")
    payload = {key: document[key] for key in allowed}
    (run_dir / "run.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_packet(run_dir: Path, name: str, document: dict) -> None:
    folder = run_dir / "packets"
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _yaml(path: Path, document: dict) -> None:
    path.write_text(_dump(document) + "\n", encoding="utf-8")


def _dump(value, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(_dump(item, indent + 1))
            else:
                lines.append(f"{pad}{key}: {_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(_dump(item, indent + 1))
            else:
                lines.append(f"{pad}- {_scalar(item)}")
        return "\n".join(lines)
    return f"{pad}{_scalar(value)}"


def _scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return json.dumps(value, ensure_ascii=False)
