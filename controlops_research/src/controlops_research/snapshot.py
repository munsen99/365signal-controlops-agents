"""Deterministic raw-snapshot persistence and text extraction for PR2."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import Message
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

RAW_LIMIT = 8_388_608
TEXT_LIMIT = 8_388_608
SCHEMA_VERSION = "controlops-retrieval-record/v1.0.0"


class SnapshotProblem(Exception):
    """Internal, closed failure signal translated by the fetch boundary."""

    def __init__(self, code: str, stage: str):
        super().__init__(code)
        self.code = code
        self.stage = stage


@dataclass(frozen=True, slots=True)
class ContentContract:
    media_type: str
    declared_charset: str | None
    applied_charset: str
    extractor_version: str


@dataclass(frozen=True, slots=True)
class StoredSnapshot:
    retrieval_id: str
    metadata_path: str
    visible_text_path: str


_BLOCKS = frozenset({
    "br", "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr",
    "section", "article", "header", "footer", "main", "nav", "aside",
    "blockquote", "pre", "title",
})
_EXCLUDED = frozenset({"script", "style", "template", "noscript"})
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input",
                   "link", "meta", "param", "source", "track", "wbr"})


class _VisibleHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.excluded: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self.excluded:
            if tag not in _VOID:
                self.excluded.append(tag)
            return
        if tag in _EXCLUDED:
            self.excluded.append(tag)
            return
        if self.hidden_depth:
            if tag not in _VOID:
                self.hidden_depth += 1
            return
        if any(name.lower() == "hidden" for name, _ in attrs):
            self.hidden_depth = 1
            return
        if tag in _BLOCKS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.excluded and not self.hidden_depth and tag.lower() in _BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.excluded:
            self.excluded.pop()
            return
        if self.hidden_depth:
            self.hidden_depth -= 1
            return
        if tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.excluded and not self.hidden_depth:
            self.parts.append(data)

    def result(self) -> str:
        if self.excluded or self.hidden_depth:
            raise SnapshotProblem("EXTRACTION_FAILED", "EXTRACT")
        lines = []
        for line in "".join(self.parts).splitlines():
            normalized = " ".join(line.split())
            if normalized:
                lines.append(normalized)
        return "\n".join(lines)


def parse_content_contract(headers: tuple[tuple[str, str], ...], raw: bytes) -> ContentContract:
    grouped: dict[str, list[str]] = {}
    for name, value in headers:
        grouped.setdefault(name.lower(), []).append(value)
    for name in ("content-type", "content-length", "content-encoding"):
        if len(grouped.get(name, ())) > 1:
            raise SnapshotProblem("RESPONSE_HEADERS_INVALID", "HTTP")
    encodings = grouped.get("content-encoding", [])
    if encodings and encodings[0].strip().lower() != "identity":
        raise SnapshotProblem("UNSUPPORTED_CONTENT_ENCODING", "CONTENT")
    values = grouped.get("content-type", [])
    if len(values) != 1:
        raise SnapshotProblem("UNSUPPORTED_CONTENT_TYPE", "CONTENT")
    message = Message()
    message["content-type"] = values[0]
    media_type = message.get_content_type().lower()
    if media_type not in {"text/plain", "text/html"}:
        raise SnapshotProblem("UNSUPPORTED_CONTENT_TYPE", "CONTENT")
    params = message.get_params(header="content-type", unquote=True) or []
    if any(key.lower() != "charset" for key, _ in params[1:]) or sum(
        key.lower() == "charset" for key, _ in params[1:]
    ) > 1:
        raise SnapshotProblem("UNSUPPORTED_CONTENT_TYPE", "CONTENT")
    declared = message.get_param("charset", header="content-type")
    if declared is not None:
        declared = declared.strip().lower()
        normalized = {"utf-8": "utf-8", "utf8": "utf-8", "us-ascii": "us-ascii"}.get(declared)
        if normalized is None:
            raise SnapshotProblem("UNSUPPORTED_CHARSET", "CONTENT")
        declared = normalized
    applied = declared or "utf-8"
    if raw.startswith(b"\xef\xbb\xbf"):
        if applied != "utf-8":
            raise SnapshotProblem("MALFORMED_TEXT", "CONTENT")
        applied = "utf-8-sig"
    return ContentContract(
        media_type, declared, applied,
        "plain-text/v1" if media_type == "text/plain" else "html-visible-text/v1",
    )


def extract_visible_text(raw: bytes, contract: ContentContract) -> str:
    try:
        text = raw.decode(contract.applied_charset, errors="strict")
    except (UnicodeDecodeError, LookupError) as error:
        raise SnapshotProblem("MALFORMED_TEXT", "CONTENT") from error
    if contract.media_type == "text/html":
        try:
            parser = _VisibleHTML()
            parser.feed(text)
            parser.close()
            text = parser.result()
        except SnapshotProblem:
            raise
        except Exception as error:
            raise SnapshotProblem("EXTRACTION_FAILED", "EXTRACT") from error
    if len(text.encode("utf-8")) > TEXT_LIMIT:
        raise SnapshotProblem("EXTRACTED_TEXT_TOO_LARGE", "EXTRACT")
    return text


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")


class SnapshotStore:
    """Private, symlink-resistant store rooted only at the caller path."""

    def __init__(self, root: Path):
        if not isinstance(root, Path):
            raise SnapshotProblem("STORAGE_UNAVAILABLE", "STORAGE")
        self.root = root
        self.stage: Path | None = None

    @staticmethod
    def _reject_symlink(path: Path) -> None:
        if path.is_symlink():
            raise SnapshotProblem("STORAGE_UNAVAILABLE", "STORAGE")

    def _private_dir(self, path: Path) -> None:
        self._reject_symlink(path)
        path.mkdir(mode=0o700, exist_ok=True)
        self._reject_symlink(path)
        os.chmod(path, 0o700)

    def begin(self) -> Path:
        try:
            self._reject_symlink(self.root)
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._reject_symlink(self.root)
            os.chmod(self.root, 0o700)
            staging = self.root / ".staging"
            self._private_dir(staging)
            self.stage = Path(tempfile.mkdtemp(prefix="fetch-", dir=staging))
            os.chmod(self.stage, 0o700)
            return self.stage / "body.bin"
        except SnapshotProblem:
            raise
        except OSError as error:
            raise SnapshotProblem("STORAGE_UNAVAILABLE", "STORAGE") from error

    def cleanup(self) -> None:
        if self.stage is not None:
            shutil.rmtree(self.stage, ignore_errors=True)
            self.stage = None

    def publish(self, raw_path: Path, raw_digest: str, raw_length: int,
                visible_text: str, metadata_base: dict[str, Any]) -> StoredSnapshot:
        if self.stage is None:
            raise SnapshotProblem("SNAPSHOT_PERSISTENCE_FAILED", "STORAGE")
        try:
            object_rel = Path("objects") / "sha256" / raw_digest[:2] / raw_digest / "body.bin"
            object_path = self.root / object_rel
            for directory in (self.root / "objects", self.root / "objects" / "sha256",
                              self.root / "objects" / "sha256" / raw_digest[:2],
                              object_path.parent):
                self._private_dir(directory)
            if object_path.exists() or object_path.is_symlink():
                self._reject_symlink(object_path)
                existing = object_path.read_bytes()
                if len(existing) != raw_length or sha256(existing).hexdigest() != raw_digest:
                    raise SnapshotProblem("SNAPSHOT_PERSISTENCE_FAILED", "STORAGE")
            else:
                os.link(raw_path, object_path)
                os.chmod(object_path, 0o600)

            visible = visible_text.encode("utf-8")
            identity_metadata = json.loads(json.dumps(metadata_base))
            identity_metadata["raw"] = {"byte_length": raw_length, "sha256": raw_digest}
            identity_metadata["extraction"] = {
                **identity_metadata["extraction"],
                "character_count": len(visible_text), "byte_length": len(visible),
                "sha256": sha256(visible).hexdigest(),
            }
            retrieval_id = sha256(canonical_json(identity_metadata)).hexdigest()
            retrieval_rel = Path("retrievals") / retrieval_id
            visible_rel = retrieval_rel / "visible-text.txt"
            metadata_rel = retrieval_rel / "metadata.json"
            metadata = {
                **identity_metadata,
                "retrieval_id": retrieval_id,
                "raw": {**identity_metadata["raw"], "object_path": object_rel.as_posix()},
                "extraction": {**identity_metadata["extraction"], "path": visible_rel.as_posix()},
            }
            record_stage = self.stage / "record"
            record_stage.mkdir(mode=0o700)
            visible_path = record_stage / "visible-text.txt"
            metadata_path = record_stage / "metadata.json"
            visible_path.write_bytes(visible)
            metadata_bytes = canonical_json(metadata)
            metadata_path.write_bytes(metadata_bytes)
            for path in (visible_path, metadata_path):
                os.chmod(path, 0o600)
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
            retrievals = self.root / "retrievals"
            self._private_dir(retrievals)
            final = self.root / retrieval_rel
            if final.exists() or final.is_symlink():
                self._reject_symlink(final)
                if ((final / "metadata.json").read_bytes() != metadata_bytes or
                        (final / "visible-text.txt").read_bytes() != visible):
                    raise SnapshotProblem("SNAPSHOT_PERSISTENCE_FAILED", "STORAGE")
            else:
                os.replace(record_stage, final)
            self.cleanup()
            return StoredSnapshot(retrieval_id, metadata_rel.as_posix(), visible_rel.as_posix())
        except SnapshotProblem:
            raise
        except OSError as error:
            raise SnapshotProblem("SNAPSHOT_PERSISTENCE_FAILED", "STORAGE") from error
