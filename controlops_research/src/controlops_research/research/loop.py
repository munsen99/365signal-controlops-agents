"""Seeded research loop. Discovery is not part of PR6A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
import uuid

from controlops_research.runtime.config import WORKSPACE, required_model
from controlops_research.runtime.errors import RuntimeFailure
from controlops_research.runtime.infer import infer as runtime_infer

from .allowlist import INFER_TIMEOUT_S, MAX_RETRIEVE
from .artefacts import (
    write_candidates,
    write_finding,
    write_integrity,
    write_packet,
    write_question,
    write_run,
    write_selection,
)
from .integrity import check_integrity
from .packets import draft_messages, selection_messages
from .parse import ModelOutputInvalid, parse_draft, parse_selection
from .retrieve import HostHttp, duplicate_candidate, retrieve_seeds
from .seeds import prepare_seeds


@dataclass(frozen=True)
class RunResult:
    run_dir: Path
    status: str
    code: str | None
    finding_status: str | None
    model: str | None


def run_research(
    question: str,
    seed_urls: list[str],
    *,
    workspace: Path | None = None,
    http=None,
    infer_fn=None,
    infer_transport=None,
    environ=None,
) -> RunResult:
    """Run one seeded question. `infer_fn` defaults to the PR5-R adapter."""
    started = _now()
    run_id = uuid.uuid4().hex
    run_dir = (workspace or WORKSPACE) / "runtime" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_seeds = list(seed_urls) if isinstance(seed_urls, list) else []
    write_question(run_dir, question if isinstance(question, str) else "", raw_seeds)
    code = _input_code(question, seed_urls)
    if code is not None:
        return _fail(run_dir, run_id, started, None, code)
    unique, duplicates, seed_code = prepare_seeds(seed_urls)
    write_question(run_dir, question, raw_seeds, [canonical for _raw, canonical in unique])
    if seed_code is not None:
        return _fail(run_dir, run_id, started, None, seed_code)
    try:
        model_id = required_model(environ)
    except RuntimeFailure as error:
        return _fail(run_dir, run_id, started, None, error.code)

    transport = http if http is not None else HostHttp()
    candidates = _collect_candidates(unique, duplicates, transport)
    write_candidates(run_dir, candidates)
    usable = [candidate for candidate in candidates if candidate.usable]
    if not usable:
        return _fail(run_dir, run_id, started, model_id, "NO_USABLE_CANDIDATES")

    caller = infer_fn if infer_fn is not None else runtime_infer
    try:
        selected, select_result = _infer_json(
            caller, selection_messages(question, usable), parse_selection, run_dir, "select.json",
            workspace, environ, infer_transport,
        )
    except RuntimeFailure as error:
        return _fail(run_dir, run_id, started, model_id, error.code)
    except ModelOutputInvalid:
        return _fail(run_dir, run_id, started, model_id, "MODEL_OUTPUT_INVALID")
    if select_result.model != model_id:
        return _fail(run_dir, run_id, started, model_id, "MODEL_STATE_INCOMPATIBLE")
    kept, dropped = _filter_selection(selected["selected_ids"], usable)
    write_selection(run_dir, {
        "question": question,
        "selected_ids": kept,
        "rationale": selected["rationale"],
        "model": select_result.model,
        "dropped_ids": dropped,
    })
    chosen = [candidate for candidate in usable if candidate.candidate_id in set(kept)]

    try:
        draft, draft_result = _infer_json(
            caller, draft_messages(question, chosen, kept), parse_draft, run_dir, "draft.json",
            workspace, environ, infer_transport,
        )
    except RuntimeFailure as error:
        return _fail(run_dir, run_id, started, model_id, error.code)
    except ModelOutputInvalid:
        return _fail(run_dir, run_id, started, model_id, "MODEL_OUTPUT_INVALID")
    if draft_result.model != model_id:
        return _fail(run_dir, run_id, started, model_id, "MODEL_STATE_INCOMPATIBLE")

    finding = {
        "question": question,
        "status": draft["status"],
        "finding": draft["finding"],
        "evidence_ids": draft["evidence_ids"],
        "rationale": draft["rationale"],
        "model": draft_result.model,
    }
    integrity = check_integrity(
        candidates, finding["evidence_ids"], finding["status"], run_dir / "evidence", kept,
    )
    if integrity["result"] == "INTEGRITY_FAILED" or not kept:
        finding["status"] = "insufficient"
    write_integrity(run_dir, integrity)
    write_finding(run_dir, finding)
    write_run(run_dir, _record(run_id, started, finding["model"], "completed"))
    return RunResult(run_dir, "completed", None, finding["status"], finding["model"])


def _infer_json(caller, messages, parser, run_dir: Path, packet_name: str, workspace, environ, infer_transport):
    started = time.perf_counter()
    kwargs = {"workspace": workspace, "environ": environ}
    if infer_transport is not None:
        kwargs["transport"] = infer_transport
    result = caller(messages, INFER_TIMEOUT_S, **kwargs)
    elapsed = time.perf_counter() - started
    write_packet(run_dir, packet_name, {
        "messages": messages,
        "raw": result.text,
        "model": result.model,
        "finish_reason": result.finish_reason,
        "elapsed_s": elapsed,
    })
    return parser(result.text), result


def _collect_candidates(unique, duplicates, transport):
    grouped: dict[str, list[str]] = {}
    for raw, canonical in duplicates:
        grouped.setdefault(canonical, []).append(raw)
    to_fetch = unique[:MAX_RETRIEVE]
    fetched = retrieve_seeds(
        [(f"E{index}", raw, canonical) for index, (raw, canonical) in enumerate(to_fetch, start=1)],
        transport,
    )
    by_id = {candidate.candidate_id: candidate for candidate in fetched}
    ordered = []
    extra_index = len(fetched) + 1
    for index, (_raw, canonical) in enumerate(to_fetch, start=1):
        ordered.append(by_id[f"E{index}"])
        for extra in grouped.get(canonical, []):
            ordered.append(duplicate_candidate(f"E{extra_index}", extra, canonical))
            extra_index += 1
    return ordered


def _filter_selection(selected_ids: list[str], usable) -> tuple[list[str], list[str]]:
    allowed = {candidate.candidate_id for candidate in usable}
    kept = []
    dropped = []
    for evidence_id in selected_ids:
        if evidence_id in allowed and evidence_id not in kept:
            kept.append(evidence_id)
        else:
            dropped.append(evidence_id)
    return kept, dropped


def _input_code(question: str, seed_urls: list[str]) -> str | None:
    if not isinstance(question, str) or not question.strip():
        return "CONFIG_INVALID"
    if not isinstance(seed_urls, list) or any(not isinstance(item, str) or not item.strip() for item in seed_urls):
        return "CONFIG_INVALID"
    return None


def _fail(run_dir: Path, run_id: str, started: str, model: str | None, code: str) -> RunResult:
    write_run(run_dir, _record(run_id, started, model, "failed"))
    return RunResult(run_dir, "failed", code, None, model)


def _record(run_id: str, started: str, model: str | None, status: str) -> dict:
    return {
        "run_id": run_id,
        "started_at": started,
        "completed_at": _now(),
        "model": model,
        "status": status,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
