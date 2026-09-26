"""Fail-closed citation verification against immutable PR2 snapshots."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .evidence import (Citation, CitationVerdict, EvidenceError, JsonCatalogue,
                       ReasonCode, SnapshotRef, VERIFIER_VERSION, _now, _identity,
                       _store_citation)
from .snapshot import (SCHEMA_VERSION, ContentContract, SnapshotProblem,
                       extract_visible_text)

_ID = re.compile(r"[0-9a-f]{64}\Z")
_EXTRACTORS = {"plain-text/v1": "text/plain", "html-visible-text/v1": "text/html"}


@dataclass(frozen=True, slots=True)
class _VerifiedSnapshot:
    retrieval_id: str
    metadata: dict
    visible_text: str
    raw_sha256: str
    extraction_sha256: str
    byte_length: int
    character_count: int


def _verdict(retrieval_id: str | None, result: str, code: ReasonCode, *,
             citation_id: str | None = None, snapshot_ref_id: str | None = None,
             excerpt_sha256: str | None = None) -> CitationVerdict:
    safe_id = lambda value: value if type(value) is str and _ID.fullmatch(value) else None
    safe_digest = lambda value: value if type(value) is str and _ID.fullmatch(value) else None
    return CitationVerdict(safe_id(citation_id), safe_id(snapshot_ref_id), safe_id(retrieval_id), result,
                           code, VERIFIER_VERSION, safe_digest(excerpt_sha256))


def _failure(retrieval_id: str | None, code: ReasonCode, **kwargs) -> CitationVerdict:
    result = "indeterminate" if code is ReasonCode.EXTRACTOR_UNKNOWN else "fail"
    return _verdict(retrieval_id, result, code, **kwargs)


def _safe_relative(root: Path, relative: str) -> Path:
    if type(relative) is not str or not relative:
        raise EvidenceError(ReasonCode.SNAPSHOT_MISSING)
    candidate_rel = Path(relative)
    if candidate_rel.is_absolute() or any(part in {"", ".", ".."} for part in candidate_rel.parts):
        raise EvidenceError(ReasonCode.SNAPSHOT_MISSING)
    current = root
    for part in candidate_rel.parts:
        current = current / part
        if current.is_symlink():
            raise EvidenceError(ReasonCode.SNAPSHOT_MISSING)
    return current


def _read_snapshot(store_root: Path, retrieval_id: str) -> _VerifiedSnapshot:
    if not isinstance(store_root, Path) or type(retrieval_id) is not str or not _ID.fullmatch(retrieval_id):
        raise EvidenceError(ReasonCode.SNAPSHOT_MISSING)
    if store_root.is_symlink():
        raise EvidenceError(ReasonCode.SNAPSHOT_MISSING)
    retrieval_rel = Path("retrievals") / retrieval_id
    retrieval_path = _safe_relative(store_root, retrieval_rel.as_posix())
    metadata_path = retrieval_path / "metadata.json"
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise EvidenceError(ReasonCode.SNAPSHOT_MISSING)
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceError(ReasonCode.SNAPSHOT_MISSING) from error
    if type(metadata) is not dict:
        raise EvidenceError(ReasonCode.SNAPSHOT_SCHEMA_UNSUPPORTED)
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError(ReasonCode.SNAPSHOT_SCHEMA_UNSUPPORTED)
    if metadata.get("retrieval_id") != retrieval_id:
        raise EvidenceError(ReasonCode.SNAPSHOT_TAMPERED)
    raw_info = metadata.get("raw")
    extraction = metadata.get("extraction")
    if type(raw_info) is not dict or type(extraction) is not dict:
        raise EvidenceError(ReasonCode.SNAPSHOT_TAMPERED)
    raw_digest = raw_info.get("sha256")
    raw_length = raw_info.get("byte_length")
    if type(raw_digest) is not str or not _ID.fullmatch(raw_digest) or type(raw_length) is not int or raw_length < 0:
        raise EvidenceError(ReasonCode.SNAPSHOT_TAMPERED)
    try:
        raw_path = _safe_relative(store_root, raw_info.get("object_path"))
        raw = raw_path.read_bytes()
    except (EvidenceError, OSError) as error:
        raise EvidenceError(ReasonCode.SNAPSHOT_MISSING) from error
    actual_raw_digest = sha256(raw).hexdigest()
    if len(raw) != raw_length or actual_raw_digest != raw_digest:
        raise EvidenceError(ReasonCode.SNAPSHOT_TAMPERED)
    extractor = extraction.get("version")
    media_type = metadata.get("media_type")
    if type(extractor) is not str or extractor not in _EXTRACTORS:
        raise EvidenceError(ReasonCode.EXTRACTOR_UNKNOWN)
    if type(media_type) is not str or _EXTRACTORS.get(extractor) != media_type:
        raise EvidenceError(ReasonCode.EXTRACTION_MISMATCH)
    try:
        contract = ContentContract(
            media_type=media_type,
            declared_charset=metadata.get("declared_charset"),
            applied_charset=metadata.get("applied_charset"),
            extractor_version=extractor,
        )
        visible = extract_visible_text(raw, contract)
    except (SnapshotProblem, TypeError, ValueError) as error:
        raise EvidenceError(ReasonCode.EXTRACTION_MISMATCH) from error
    visible_bytes = visible.encode("utf-8")
    extraction_digest = extraction.get("sha256")
    if (type(extraction_digest) is not str or not _ID.fullmatch(extraction_digest) or
            sha256(visible_bytes).hexdigest() != extraction_digest or
            type(extraction.get("character_count")) is not int or
            extraction["character_count"] != len(visible) or
            type(extraction.get("byte_length")) is not int or
            extraction["byte_length"] != len(visible_bytes)):
        raise EvidenceError(ReasonCode.EXTRACTION_MISMATCH)
    visible_path_value = extraction.get("path")
    try:
        visible_path = _safe_relative(store_root, visible_path_value)
        stored_visible = visible_path.read_bytes()
    except (EvidenceError, OSError) as error:
        raise EvidenceError(ReasonCode.EXTRACTION_MISMATCH) from error
    if stored_visible != visible_bytes:
        raise EvidenceError(ReasonCode.EXTRACTION_MISMATCH)
    return _VerifiedSnapshot(retrieval_id, metadata, visible, actual_raw_digest,
                             extraction_digest, len(raw), len(visible))


def _span(verified: _VerifiedSnapshot, start_offset: int, end_offset: int,
          quoted_text: str, *, citation_id: str | None = None,
          snapshot_ref_id: str | None = None) -> CitationVerdict:
    if (type(start_offset) is not int or type(end_offset) is not int or
            type(quoted_text) is not str or start_offset < 0 or
            end_offset < start_offset or end_offset > len(verified.visible_text)):
        return _failure(verified.retrieval_id, ReasonCode.SPAN_INVALID,
                        citation_id=citation_id, snapshot_ref_id=snapshot_ref_id)
    actual = verified.visible_text[start_offset:end_offset]
    digest = sha256(actual.encode("utf-8")).hexdigest()
    if actual != quoted_text:
        return _failure(verified.retrieval_id, ReasonCode.QUOTE_MISMATCH,
                        citation_id=citation_id, snapshot_ref_id=snapshot_ref_id,
                        excerpt_sha256=digest)
    return _verdict(verified.retrieval_id, "pass", ReasonCode.SPAN_MATCH,
                    citation_id=citation_id, snapshot_ref_id=snapshot_ref_id,
                    excerpt_sha256=digest)


def verify_span(store_root: Path, retrieval_id: str, start_offset: int,
                end_offset: int, quoted_text: str) -> CitationVerdict:
    """Rehash and re-extract a PR2 retrieval before checking a Python-str span."""
    try:
        verified = _read_snapshot(store_root, retrieval_id)
        return _span(verified, start_offset, end_offset, quoted_text)
    except EvidenceError as error:
        return _failure(retrieval_id if type(retrieval_id) is str else None, error.reason_code)


def _load_ref(catalogue: JsonCatalogue, snapshot_ref_id: str) -> SnapshotRef | None:
    row = catalogue.get("snapshot_ref", "snapshot_ref_id", snapshot_ref_id)
    return SnapshotRef(**row) if row else None


def register_snapshot_ref(store_root: Path, retrieval_id: str, source_id: str,
                          *, catalogue_root: Path) -> SnapshotRef:
    try:
        verified = _read_snapshot(store_root, retrieval_id)
    except EvidenceError as error:
        raise error
    if not JsonCatalogue(catalogue_root).get("source", "source_id", source_id):
        raise EvidenceError(ReasonCode.SOURCE_NOT_FOUND)
    metadata = verified.metadata
    extraction = metadata["extraction"]
    payload = {"source_id": source_id, "retrieval_id": retrieval_id,
               "raw_sha256": verified.raw_sha256,
               "extraction_sha256": verified.extraction_sha256}
    ref_id = _identity(payload)
    catalogue = JsonCatalogue(catalogue_root)
    existing = catalogue.get("snapshot_ref", "snapshot_ref_id", ref_id)
    if existing:
        return SnapshotRef(**existing)
    record = SnapshotRef(
        snapshot_ref_id=ref_id,
        source_id=source_id,
        retrieval_id=retrieval_id,
        raw_sha256=verified.raw_sha256,
        extraction_sha256=verified.extraction_sha256,
        extractor_version=extraction["version"],
        media_type=metadata["media_type"],
        character_count=verified.character_count,
        byte_length=verified.byte_length,
        schema_version=metadata["schema_version"],
        captured_at=metadata["completed_at"],
        registered_at=_now(),
    )
    catalogue.upsert("snapshot_ref", "snapshot_ref_id", asdict(record))
    return record


def _ref_pin_failure(ref: SnapshotRef, verified: _VerifiedSnapshot) -> ReasonCode | None:
    metadata = verified.metadata
    extraction = metadata.get("extraction", {})
    if (verified.raw_sha256 != ref.raw_sha256 or verified.byte_length != ref.byte_length):
        return ReasonCode.SNAPSHOT_TAMPERED
    if (verified.extraction_sha256 != ref.extraction_sha256 or
            verified.character_count != ref.character_count or
            extraction.get("version") != ref.extractor_version or
            metadata.get("media_type") != ref.media_type or
            metadata.get("schema_version") != ref.schema_version):
        return ReasonCode.EXTRACTION_MISMATCH
    return None


def _verify_citation_value(citation: Citation, ref: SnapshotRef,
                           store_root: Path) -> CitationVerdict:
    try:
        verified = _read_snapshot(store_root, ref.retrieval_id)
    except EvidenceError as error:
        return _failure(ref.retrieval_id, error.reason_code,
                        citation_id=citation.citation_id,
                        snapshot_ref_id=ref.snapshot_ref_id)
    pin_failure = _ref_pin_failure(ref, verified)
    if pin_failure is not None:
        return _failure(ref.retrieval_id, pin_failure, citation_id=citation.citation_id,
                        snapshot_ref_id=ref.snapshot_ref_id)
    verdict = _span(verified, citation.start_offset, citation.end_offset,
                    citation.quoted_text, citation_id=citation.citation_id,
                    snapshot_ref_id=ref.snapshot_ref_id)
    if verdict.result == "pass" and verdict.excerpt_sha256 != citation.excerpt_sha256:
        return _failure(ref.retrieval_id, ReasonCode.EXCERPT_HASH_MISMATCH,
                        citation_id=citation.citation_id,
                        snapshot_ref_id=ref.snapshot_ref_id,
                        excerpt_sha256=verdict.excerpt_sha256)
    return verdict


def verify_citation(citation_id: str, *, store_root: Path,
                    catalogue_root: Path) -> CitationVerdict:
    if type(citation_id) is not str or not _ID.fullmatch(citation_id):
        return _failure(None, ReasonCode.CITATION_NOT_FOUND)
    try:
        catalogue = JsonCatalogue(catalogue_root)
        citation_row = catalogue.get("citation", "citation_id", citation_id)
    except EvidenceError as error:
        return _failure(None, error.reason_code, citation_id=citation_id)
    if citation_row is None:
        return _failure(None, ReasonCode.CITATION_NOT_FOUND, citation_id=citation_id)
    try:
        citation_row["reason_code"] = ReasonCode(citation_row["reason_code"])
        citation = Citation(**citation_row)
        ref = _load_ref(catalogue, citation.snapshot_ref_id)
    except (ValueError, TypeError, KeyError) as error:
        return _failure(None, ReasonCode.STORAGE_UNAVAILABLE, citation_id=citation_id)
    if ref is None:
        return _failure(None, ReasonCode.SNAPSHOT_REF_NOT_FOUND,
                        citation_id=citation_id,
                        snapshot_ref_id=citation.snapshot_ref_id)
    return _verify_citation_value(citation, ref, store_root)


def create_citation(snapshot_ref_id: str, start_offset: int, end_offset: int,
                    quoted_text: str, *, store_root: Path,
                    catalogue_root: Path) -> Citation:
    if (type(start_offset) is not int or type(end_offset) is not int or
            type(quoted_text) is not str):
        raise TypeError("offsets must be int and quoted_text must be str")
    catalogue = JsonCatalogue(catalogue_root)
    ref = _load_ref(catalogue, snapshot_ref_id)
    if ref is None:
        raise EvidenceError(ReasonCode.SNAPSHOT_REF_NOT_FOUND)
    identity = {"snapshot_ref_id": snapshot_ref_id, "start_offset": start_offset,
                "end_offset": end_offset, "quoted_text": quoted_text}
    citation_id = _identity(identity)
    existing_row = catalogue.get("citation", "citation_id", citation_id)
    created_at = existing_row["created_at"] if existing_row else _now()
    temporary = Citation(
        citation_id=citation_id, snapshot_ref_id=snapshot_ref_id,
        start_offset=start_offset, end_offset=end_offset, quoted_text=quoted_text,
        excerpt_sha256=sha256(quoted_text.encode("utf-8")).hexdigest(),
        verifier_version=VERIFIER_VERSION, result="indeterminate",
        reason_code=ReasonCode.EXTRACTOR_UNKNOWN, created_at=created_at,
        verified_at=_now(),
    )
    verdict = _verify_citation_value(temporary, ref, store_root)
    citation = Citation(
        citation_id=citation_id, snapshot_ref_id=snapshot_ref_id,
        start_offset=start_offset, end_offset=end_offset, quoted_text=quoted_text,
        excerpt_sha256=sha256(quoted_text.encode("utf-8")).hexdigest(),
        verifier_version=VERIFIER_VERSION, result=verdict.result,
        reason_code=verdict.reason_code, created_at=created_at, verified_at=_now(),
    )
    return _store_citation(catalogue, citation)
