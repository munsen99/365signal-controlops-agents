"""PR3 JSON provenance and deterministic citation verification tests."""

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from controlops_research.evidence import (CATALOGUE_SCHEMA_VERSION, CitationVerdict,
    EvidenceError, JsonCatalogue, ReasonCode, create_citation, load_citation,
    load_snapshot_ref, load_source, register_snapshot_ref, register_source,
    verify_citation, verify_span)
from controlops_research.policy import evaluate_url
from controlops_research.snapshot import (SCHEMA_VERSION, ContentContract, SnapshotStore,
    canonical_json, extract_visible_text)

ROOT = Path(__file__).resolve().parents[1]
FETCH_FIXTURES = ROOT / "tests" / "fixtures" / "fetch"
MANIFEST = json.loads((ROOT / "tests" / "fixtures" / "evidence" / "manifest.json").read_text())


def _stamp():
    return "2026-09-26T12:34:56.123456Z"


def publish_fixture(store_root: Path, raw: bytes, media: str, visible_override: str | None = None):
    version = "plain-text/v1" if media == "text/plain" else "html-visible-text/v1"
    contract = ContentContract(media, None, "utf-8", version)
    visible = extract_visible_text(raw, contract)
    if visible_override is not None:
        assert visible == visible_override
    store = SnapshotStore(store_root)
    raw_path = store.begin()
    raw_path.write_bytes(raw)
    os.chmod(raw_path, 0o600)
    digest = sha256(raw).hexdigest()
    metadata_base = {
        "schema_version": SCHEMA_VERSION,
        "fetch_policy_version": "controlops-fetch/v1.0.0",
        "requested_url": "https://cloudflare.com/fixture",
        "initial_policy_decision": asdict(evaluate_url("https://cloudflare.com/fixture")),
        "final_url": "https://cloudflare.com/fixture",
        "redirect_chain": [],
        "resolution_events": [],
        "started_at": _stamp(),
        "completed_at": _stamp(),
        "http_status": 200,
        "media_type": media,
        "declared_charset": None,
        "applied_charset": "utf-8",
        "content_encoding": "identity",
        "extraction": {"version": version},
    }
    try:
        return store.publish(raw_path, digest, len(raw), visible, metadata_base), visible
    finally:
        store.cleanup()


def source_and_ref(store_root, catalogue_root, source_key="learn-docs", locator="https://learn.microsoft.com/topic"):
    source = register_source(source_key, locator=locator, catalogue_root=catalogue_root)
    plain = (FETCH_FIXTURES / "plain-utf8.txt").read_bytes()
    stored, _ = publish_fixture(store_root, plain, "text/plain")
    ref = register_snapshot_ref(store_root, stored.retrieval_id, source.source_id,
                                catalogue_root=catalogue_root)
    return source, stored, ref


def test_source_persists_and_reregistration_is_idempotent(tmp_path):
    root = tmp_path / "catalogue"
    first = register_source("learn-docs", locator="https://learn.microsoft.com/",
                            catalogue_root=root)
    second = register_source("learn-docs", locator="https://learn.microsoft.com/",
                             catalogue_root=root)
    assert first.source_id == second.source_id
    assert load_source(first.source_id, catalogue_root=root) == first
    payload = json.loads((root / "catalogue.json").read_text())
    assert payload["schema_version"] == CATALOGUE_SCHEMA_VERSION
    assert len(payload["research"]["source"]) == 1


def test_source_locator_conflict_fails_without_overwrite(tmp_path):
    root = tmp_path / "catalogue"
    source = register_source("same-key", locator="https://one.example/", catalogue_root=root)
    with pytest.raises(EvidenceError) as error:
        register_source("same-key", locator="https://two.example/", catalogue_root=root)
    assert error.value.reason_code is ReasonCode.SOURCE_CONFLICT
    assert load_source(source.source_id, catalogue_root=root).locator == "https://one.example/"


def test_snapshot_ref_pins_match_pr2_and_store_no_content(tmp_path):
    source, stored, ref = source_and_ref(tmp_path / "store", tmp_path / "catalogue")
    metadata = json.loads((tmp_path / "store" / stored.metadata_path).read_text())
    raw = (tmp_path / "store" / metadata["raw"]["object_path"]).read_bytes()
    visible = (tmp_path / "store" / stored.visible_text_path).read_bytes()
    assert ref.raw_sha256 == sha256(raw).hexdigest()
    assert ref.extraction_sha256 == sha256(visible).hexdigest()
    assert not hasattr(ref, "content") and not hasattr(ref, "visible_text")
    record = asdict(ref)
    assert raw.decode("utf-8") not in json.dumps(record)
    assert visible.decode("utf-8") not in json.dumps(record)
    assert load_snapshot_ref(ref.snapshot_ref_id, catalogue_root=tmp_path / "catalogue") == ref
    assert source.source_id == ref.source_id


def test_exact_span_passes_and_altered_quote_fails(tmp_path):
    _, stored, _ = source_and_ref(tmp_path / "store", tmp_path / "catalogue")
    visible = (FETCH_FIXTURES / "plain-utf8.txt").read_text()
    verdict = verify_span(tmp_path / "store", stored.retrieval_id, 0, 15,
                          visible[0:15])
    assert (verdict.result, verdict.reason_code) == ("pass", ReasonCode.SPAN_MATCH)
    altered = verify_span(tmp_path / "store", stored.retrieval_id, 0, 15, "changed quote")
    assert (altered.result, altered.reason_code) == ("fail", ReasonCode.QUOTE_MISMATCH)


@pytest.mark.parametrize("start,end,quote", [(-1, 0, ""), (4, 3, ""), (0, 1000, "")])
def test_invalid_spans_fail(tmp_path, start, end, quote):
    _, stored, _ = source_and_ref(tmp_path / "store", tmp_path / "catalogue")
    verdict = verify_span(tmp_path / "store", stored.retrieval_id, start, end, quote)
    assert (verdict.result, verdict.reason_code) == ("fail", ReasonCode.SPAN_INVALID)


def test_sql_contract_creates_only_research_schema_and_three_tables():
    sql = (ROOT / "src" / "controlops_research" / "research_schema.sql").read_text().lower()
    assert re.findall(r"create\s+schema\s+if\s+not\s+exists\s+([a-z_]+)", sql) == ["research"]
    assert set(re.findall(r"create\s+table\s+if\s+not\s+exists\s+research\.([a-z_]+)", sql)) == {
        "source", "snapshot_ref", "citation"}
    assert not re.search(r"create\s+schema\s+(?:evidence|economic)\b", sql)
    assert not re.search(r"create\s+table\s+[^;]*\bevidence\b", sql)
    assert not re.search(r"economic_app|controlops_admin|aea_run|body_bin|source_content|raw_content", sql)


def test_snapshot_a_citation_remains_bound_after_snapshot_b(tmp_path):
    store_root, catalogue_root = tmp_path / "store", tmp_path / "catalogue"
    source = register_source("same-source", locator=None, catalogue_root=catalogue_root)
    raw_a = (FETCH_FIXTURES / "plain-utf8.txt").read_bytes()
    saved_a, visible_a = publish_fixture(store_root, raw_a, "text/plain")
    ref_a = register_snapshot_ref(store_root, saved_a.retrieval_id, source.source_id,
                                  catalogue_root=catalogue_root)
    citation = create_citation(ref_a.snapshot_ref_id, 0, 15, visible_a[:15],
                               store_root=store_root, catalogue_root=catalogue_root)
    raw_b = b"Different document bytes."
    saved_b, _ = publish_fixture(store_root, raw_b, "text/plain")
    ref_b = register_snapshot_ref(store_root, saved_b.retrieval_id, source.source_id,
                                  catalogue_root=catalogue_root)
    assert ref_a.retrieval_id != ref_b.retrieval_id
    assert verify_citation(citation.citation_id, store_root=store_root,
                           catalogue_root=catalogue_root).reason_code is ReasonCode.SPAN_MATCH


def _catalogue_citation(root, citation_id):
    path = root / "catalogue.json"
    payload = json.loads(path.read_text())
    return payload, payload["research"]["citation"][next(
        i for i, row in enumerate(payload["research"]["citation"])
        if row["citation_id"] == citation_id)]


def test_raw_tamper_invalidates_later_citation_verification(tmp_path):
    store, catalogue = tmp_path / "store", tmp_path / "catalogue"
    _, saved, ref = source_and_ref(store, catalogue)
    citation = create_citation(ref.snapshot_ref_id, 0, 15, "ControlOps café",
                               store_root=store, catalogue_root=catalogue)
    metadata = json.loads((store / saved.metadata_path).read_text())
    (store / metadata["raw"]["object_path"]).write_bytes(b"tampered")
    result = verify_citation(citation.citation_id, store_root=store, catalogue_root=catalogue)
    assert (result.result, result.reason_code) == ("fail", ReasonCode.SNAPSHOT_TAMPERED)


def test_visible_text_tamper_invalidates_later_verification(tmp_path):
    store, catalogue = tmp_path / "store", tmp_path / "catalogue"
    _, saved, ref = source_and_ref(store, catalogue)
    citation = create_citation(ref.snapshot_ref_id, 0, 15, "ControlOps café",
                               store_root=store, catalogue_root=catalogue)
    (store / saved.visible_text_path).write_text("edited visible text")
    result = verify_citation(citation.citation_id, store_root=store, catalogue_root=catalogue)
    assert (result.result, result.reason_code) == ("fail", ReasonCode.EXTRACTION_MISMATCH)


def test_missing_retrieval_is_closed_failure(tmp_path):
    result = verify_span(tmp_path / "store", "a" * 64, 0, 0, "")
    assert (result.result, result.reason_code) == ("fail", ReasonCode.SNAPSHOT_MISSING)


def test_empty_document_accepts_empty_span(tmp_path):
    store = tmp_path / "store"
    saved, visible = publish_fixture(store, (FETCH_FIXTURES / "empty.txt").read_bytes(),
                                     "text/plain")
    assert visible == ""
    result = verify_span(store, saved.retrieval_id, 0, 0, "")
    assert (result.result, result.reason_code, result.excerpt_sha256) == (
        "pass", ReasonCode.SPAN_MATCH, sha256(b"").hexdigest())


def test_html_offsets_use_extracted_visible_text(tmp_path):
    store = tmp_path / "store"
    raw = (FETCH_FIXTURES / "page.html").read_bytes()
    saved, visible = publish_fixture(store, raw, "text/html")
    expected_visible = (FETCH_FIXTURES / "page-visible.txt").read_text().removesuffix("\n")
    span = next(item for item in MANIFEST["spans"] if item["kind"] == "html")
    assert visible == expected_visible == span["visible_text"]
    result = verify_span(store, saved.retrieval_id, span["start_offset"],
                         span["end_offset"], span["quoted_text"])
    assert (result.result, result.reason_code) == ("pass", ReasonCode.SPAN_MATCH)
    assert "<p>" not in visible and span["end_offset"] < len(raw)


def test_unicode_offsets_are_python_str_indices(tmp_path):
    span = next(item for item in MANIFEST["spans"] if item["kind"] == "unicode")
    store = tmp_path / "store"
    raw = span["visible_text"].encode("utf-8")
    saved, visible = publish_fixture(store, raw, "text/plain", span["visible_text"])
    assert len(visible[:span["start_offset"]].encode("utf-8")) != span["start_offset"]
    result = verify_span(store, saved.retrieval_id, span["start_offset"],
                         span["end_offset"], span["quoted_text"])
    assert result.reason_code is ReasonCode.SPAN_MATCH
    assert result.excerpt_sha256 == span["excerpt_sha256"]


def test_excerpt_digest_tamper_is_detected(tmp_path):
    store, catalogue = tmp_path / "store", tmp_path / "catalogue"
    _, _, ref = source_and_ref(store, catalogue)
    citation = create_citation(ref.snapshot_ref_id, 0, 15, "ControlOps café",
                               store_root=store, catalogue_root=catalogue)
    payload = json.loads((catalogue / "catalogue.json").read_text())
    row = payload["research"]["citation"][0]
    row["excerpt_sha256"] = "0" * 64
    (catalogue / "catalogue.json").write_bytes(canonical_json(payload))
    result = verify_citation(citation.citation_id, store_root=store, catalogue_root=catalogue)
    assert (result.result, result.reason_code) == ("fail", ReasonCode.EXCERPT_HASH_MISMATCH)


@pytest.mark.parametrize("result", ["pass", "fail", "indeterminate"])
def test_verdict_is_frozen_not_truthy_and_repr_has_no_quote_or_locator(result):
    verdict = CitationVerdict("a" * 64, "b" * 64, "c" * 64, result,
                              ReasonCode.SPAN_MATCH, "controlops-citation-verify/v1.0.0",
                              "d" * 64)
    assert "https://" not in repr(verdict) and "visible text" not in repr(verdict)
    with pytest.raises(TypeError): bool(verdict)


def test_catalogue_quote_alone_cannot_verify_citation(tmp_path):
    store, catalogue = tmp_path / "store", tmp_path / "catalogue"
    _, _, ref = source_and_ref(store, catalogue)
    citation = create_citation(ref.snapshot_ref_id, 0, 15, "ControlOps café",
                               store_root=store, catalogue_root=catalogue)
    payload = json.loads((catalogue / "catalogue.json").read_text())
    payload["research"]["citation"][0]["result"] = "pass"
    (catalogue / "catalogue.json").write_bytes(canonical_json(payload))
    result = verify_citation(citation.citation_id, store_root=tmp_path / "missing-store",
                             catalogue_root=catalogue)
    assert (result.result, result.reason_code) == ("fail", ReasonCode.SNAPSHOT_MISSING)


def test_catalogue_reload_in_separate_process(tmp_path):
    store, catalogue = tmp_path / "store", tmp_path / "catalogue"
    _, _, ref = source_and_ref(store, catalogue)
    citation = create_citation(ref.snapshot_ref_id, 0, 15, "ControlOps café",
                               store_root=store, catalogue_root=catalogue)
    code = (
        "import sys; from pathlib import Path; "
        "from controlops_research.evidence import verify_citation; "
        "v=verify_citation(sys.argv[1],store_root=Path(sys.argv[2]),"
        "catalogue_root=Path(sys.argv[3])); "
        "print(v.result + ':' + v.reason_code.value)"
    )
    run = subprocess.run([sys.executable, "-c", code, citation.citation_id,
                          str(store), str(catalogue)], cwd=tmp_path,
                         env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                         capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "pass:SPAN_MATCH"


def test_catalogue_schema_forbidden_fails_closed(tmp_path):
    root = tmp_path / "catalogue"
    root.mkdir()
    (root / "catalogue.json").write_text('{"schema_version":"wrong","research":{}}')
    with pytest.raises(EvidenceError) as error:
        register_source("x", catalogue_root=root)
    assert error.value.reason_code is ReasonCode.SCHEMA_FORBIDDEN


def test_symlink_store_and_catalogue_roots_are_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    store_link, catalogue_link = tmp_path / "store-link", tmp_path / "catalogue-link"
    store_link.symlink_to(target, target_is_directory=True)
    catalogue_link.symlink_to(target, target_is_directory=True)
    verdict = verify_span(store_link, "a" * 64, 0, 0, "")
    assert verdict.reason_code is ReasonCode.SNAPSHOT_MISSING
    with pytest.raises(EvidenceError) as error:
        register_source("x", catalogue_root=catalogue_link)
    assert error.value.reason_code is ReasonCode.STORAGE_UNAVAILABLE


def test_manifest_plain_fixture_span_matches():
    span = next(item for item in MANIFEST["spans"] if item["kind"] == "plain")
    plain = (FETCH_FIXTURES / "plain-utf8.txt").read_text()
    assert plain[span["start_offset"]:span["end_offset"]] == span["quoted_text"]
    assert sha256(span["quoted_text"].encode()).hexdigest() == span["excerpt_sha256"]
