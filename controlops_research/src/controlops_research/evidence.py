"""Filesystem JSON catalogue for research provenance records (PR3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

from .snapshot import canonical_json

CATALOGUE_SCHEMA_VERSION = "controlops-research-catalogue/v1.0.0"
VERIFIER_VERSION = "controlops-citation-verify/v1.0.0"
_ID = re.compile(r"[0-9a-f]{64}\Z")


class ReasonCode(StrEnum):
    SPAN_MATCH = "SPAN_MATCH"
    SNAPSHOT_MISSING = "SNAPSHOT_MISSING"
    SNAPSHOT_SCHEMA_UNSUPPORTED = "SNAPSHOT_SCHEMA_UNSUPPORTED"
    SNAPSHOT_TAMPERED = "SNAPSHOT_TAMPERED"
    EXTRACTION_MISMATCH = "EXTRACTION_MISMATCH"
    EXTRACTOR_UNKNOWN = "EXTRACTOR_UNKNOWN"
    SPAN_INVALID = "SPAN_INVALID"
    QUOTE_MISMATCH = "QUOTE_MISMATCH"
    EXCERPT_HASH_MISMATCH = "EXCERPT_HASH_MISMATCH"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    SNAPSHOT_REF_NOT_FOUND = "SNAPSHOT_REF_NOT_FOUND"
    CITATION_NOT_FOUND = "CITATION_NOT_FOUND"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    SCHEMA_FORBIDDEN = "SCHEMA_FORBIDDEN"


_EXPLANATIONS = {
    ReasonCode.SPAN_MATCH: "The quotation exactly matches the verified snapshot span.",
    ReasonCode.SNAPSHOT_MISSING: "The referenced snapshot is missing or unavailable.",
    ReasonCode.SNAPSHOT_SCHEMA_UNSUPPORTED: "The snapshot schema is unsupported.",
    ReasonCode.SNAPSHOT_TAMPERED: "The authoritative raw snapshot failed integrity checks.",
    ReasonCode.EXTRACTION_MISMATCH: "The deterministic extraction does not match the stored representation.",
    ReasonCode.EXTRACTOR_UNKNOWN: "The snapshot extractor version is not supported.",
    ReasonCode.SPAN_INVALID: "The citation offsets are outside the visible-text representation.",
    ReasonCode.QUOTE_MISMATCH: "The quotation does not exactly match the requested span.",
    ReasonCode.EXCERPT_HASH_MISMATCH: "The persisted excerpt digest does not match the verified span.",
    ReasonCode.SOURCE_NOT_FOUND: "The logical source is not registered.",
    ReasonCode.SOURCE_CONFLICT: "The source key is already registered with a different locator.",
    ReasonCode.SNAPSHOT_REF_NOT_FOUND: "The snapshot reference is not registered.",
    ReasonCode.CITATION_NOT_FOUND: "The citation is not registered.",
    ReasonCode.STORAGE_UNAVAILABLE: "The provenance catalogue or snapshot storage is unavailable.",
    ReasonCode.SCHEMA_FORBIDDEN: "The requested catalogue schema is unsupported or forbidden.",
}


class EvidenceError(Exception):
    """A catalogue operation failed with one of the closed reason codes."""

    def __init__(self, reason_code: ReasonCode):
        self.reason_code = reason_code
        super().__init__(_EXPLANATIONS[reason_code])


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    source_key: str
    locator: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class SnapshotRef:
    snapshot_ref_id: str
    source_id: str
    retrieval_id: str
    raw_sha256: str
    extraction_sha256: str
    extractor_version: str
    media_type: str
    character_count: int
    byte_length: int
    schema_version: str
    captured_at: str
    registered_at: str


@dataclass(frozen=True, slots=True)
class Citation:
    citation_id: str
    snapshot_ref_id: str
    start_offset: int
    end_offset: int
    quoted_text: str
    excerpt_sha256: str | None
    verifier_version: str
    result: str
    reason_code: ReasonCode
    created_at: str
    verified_at: str


@dataclass(frozen=True, slots=True)
class CitationVerdict:
    citation_id: str | None
    snapshot_ref_id: str | None
    retrieval_id: str | None
    result: str
    reason_code: ReasonCode
    verifier_version: str
    excerpt_sha256: str | None

    def __post_init__(self) -> None:
        if self.result not in {"pass", "fail", "indeterminate"}:
            raise ValueError("result must be pass, fail, or indeterminate")

    def __bool__(self) -> bool:
        raise TypeError("Compare CitationVerdict.result explicitly")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _identity(payload: dict) -> str:
    return sha256(canonical_json(payload)).hexdigest()


def _as_reason(value: str) -> ReasonCode:
    return ReasonCode(value)


class JsonCatalogue:
    """Reload-on-operation JSON catalogue rooted at a caller-selected directory."""

    filename = "catalogue.json"

    def __init__(self, root: Path):
        if not isinstance(root, Path):
            raise TypeError("catalogue_root must be pathlib.Path")
        self.root = root
        self.path = root / self.filename

    @staticmethod
    def _reject_link(path: Path) -> None:
        if path.is_symlink():
            raise EvidenceError(ReasonCode.STORAGE_UNAVAILABLE)

    def _read(self) -> dict:
        try:
            self._reject_link(self.root)
            self._reject_link(self.path)
            if not self.path.exists():
                return {"schema_version": CATALOGUE_SCHEMA_VERSION,
                        "research": {"source": [], "snapshot_ref": [], "citation": []}}
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != CATALOGUE_SCHEMA_VERSION:
                raise EvidenceError(ReasonCode.SCHEMA_FORBIDDEN)
            if any(name in payload for name in ("evidence", "economic")):
                raise EvidenceError(ReasonCode.SCHEMA_FORBIDDEN)
            research = payload.get("research")
            if not isinstance(research, dict) or set(research) != {"source", "snapshot_ref", "citation"}:
                raise EvidenceError(ReasonCode.STORAGE_UNAVAILABLE)
            if any(type(research[name]) is not list or any(type(row) is not dict for row in research[name])
                   for name in research):
                raise EvidenceError(ReasonCode.STORAGE_UNAVAILABLE)
            return payload
        except EvidenceError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise EvidenceError(ReasonCode.STORAGE_UNAVAILABLE) from error

    def _write(self, payload: dict) -> None:
        try:
            self._reject_link(self.root)
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._reject_link(self.root)
            os.chmod(self.root, 0o700)
            self._reject_link(self.path)
            fd, temporary = tempfile.mkstemp(prefix=".catalogue-", suffix=".tmp", dir=self.root)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(canonical_json(payload))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                directory_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        except EvidenceError:
            raise
        except OSError as error:
            raise EvidenceError(ReasonCode.STORAGE_UNAVAILABLE) from error

    def rows(self, table: str) -> list[dict]:
        if table not in {"source", "snapshot_ref", "citation"}:
            raise EvidenceError(ReasonCode.SCHEMA_FORBIDDEN)
        return list(self._read()["research"][table])

    def upsert(self, table: str, key: str, record: dict) -> None:
        payload = self._read()
        rows = payload["research"][table]
        for index, row in enumerate(rows):
            if row.get(key) == record[key]:
                rows[index] = record
                break
        else:
            rows.append(record)
        self._write(payload)

    def get(self, table: str, key: str, value: str):
        return next((row for row in self.rows(table) if row.get(key) == value), None)


def load_source(source_id: str, *, catalogue_root: Path) -> Source | None:
    row = JsonCatalogue(catalogue_root).get("source", "source_id", source_id)
    return Source(**row) if row else None


def load_snapshot_ref(snapshot_ref_id: str, *, catalogue_root: Path) -> SnapshotRef | None:
    row = JsonCatalogue(catalogue_root).get("snapshot_ref", "snapshot_ref_id", snapshot_ref_id)
    return SnapshotRef(**row) if row else None


def load_citation(citation_id: str, *, catalogue_root: Path) -> Citation | None:
    row = JsonCatalogue(catalogue_root).get("citation", "citation_id", citation_id)
    if not row:
        return None
    row["reason_code"] = _as_reason(row["reason_code"])
    return Citation(**row)


def register_source(source_key: str, *, locator: str | None = None,
                    catalogue_root: Path) -> Source:
    if type(source_key) is not str or type(locator) not in (str, type(None)):
        raise TypeError("source_key must be str and locator must be str or None")
    catalogue = JsonCatalogue(catalogue_root)
    source_id = _identity({"source_key": source_key, "locator": locator})
    for row in catalogue.rows("source"):
        if row["source_key"] == source_key:
            if row["locator"] != locator:
                raise EvidenceError(ReasonCode.SOURCE_CONFLICT)
            return Source(**row)
    source = Source(source_id, source_key, locator, _now())
    catalogue.upsert("source", "source_id", asdict(source))
    return source


def _store_citation(catalogue: JsonCatalogue, citation: Citation) -> Citation:
    row = asdict(citation)
    row["reason_code"] = citation.reason_code.value
    catalogue.upsert("citation", "citation_id", row)
    return citation


# Verification lives in its own module; these lazy entry points keep the
# public evidence-plane API together without introducing an import cycle.
def register_snapshot_ref(store_root: Path, retrieval_id: str, source_id: str,
                          *, catalogue_root: Path) -> SnapshotRef:
    from .verify import register_snapshot_ref as register
    return register(store_root, retrieval_id, source_id, catalogue_root=catalogue_root)


def create_citation(snapshot_ref_id: str, start_offset: int, end_offset: int,
                    quoted_text: str, *, store_root: Path,
                    catalogue_root: Path) -> Citation:
    from .verify import create_citation as create
    return create(snapshot_ref_id, start_offset, end_offset, quoted_text,
                  store_root=store_root, catalogue_root=catalogue_root)


def verify_span(store_root: Path, retrieval_id: str, start_offset: int,
                end_offset: int, quoted_text: str) -> CitationVerdict:
    from .verify import verify_span as verify
    return verify(store_root, retrieval_id, start_offset, end_offset, quoted_text)


def verify_citation(citation_id: str, *, store_root: Path,
                    catalogue_root: Path) -> CitationVerdict:
    from .verify import verify_citation as verify
    return verify(citation_id, store_root=store_root, catalogue_root=catalogue_root)
