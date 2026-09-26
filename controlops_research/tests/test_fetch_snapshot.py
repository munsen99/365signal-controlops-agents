"""PR2 controlled-fetch, snapshot and extraction acceptance tests."""

from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timezone
from hashlib import sha256
import ast
import json
from pathlib import Path
import socket

import pytest

import controlops_research.fetch as fetch
from controlops_research.fetch import (FailureStage, FetchFailure, FetchFailureCode,
                                       FetchSuccess, ResolvedAddress)
from controlops_research.snapshot import (ContentContract, SnapshotProblem,
                                          SnapshotStore, extract_visible_text,
                                          parse_content_contract)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "fetch"
PUBLIC = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443))
PRIVATE = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.1", 443))


class Clock:
    def __init__(self):
        self.value = 10.0

    def __call__(self):
        return self.value


class ScriptResponse:
    def __init__(self, status=200, headers=(), body=b"", clock=None, advance_on_end=0):
        self.status = status
        self.headers = tuple(headers)
        self.body = body
        self.offset = 0
        self.closed = False
        self.clock = clock
        self.advance_on_end = advance_on_end

    def read(self, size):
        chunk = self.body[self.offset:self.offset + size]
        self.offset += len(chunk)
        if not chunk and self.clock:
            self.clock.value += self.advance_on_end
        return chunk

    def close(self):
        self.closed = True

    def settimeout(self, timeout):
        assert 0 < timeout <= fetch.READ_TIMEOUT


class ScriptTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, decision, addresses, deadline, clock):
        self.calls.append((decision, addresses, deadline))
        return self.responses.pop(0), addresses[0].address


def resolver(host, port, timeout):
    assert port == 443 and timeout <= 3
    return [PUBLIC]


def fixed_now():
    return datetime(2026, 9, 26, 12, 0, 0, 123456, tzinfo=timezone.utc)


def run_fetch(tmp_path, responses, **kwargs):
    transport = ScriptTransport(responses)
    result = fetch._fetch_snapshot("https://cloudflare.com/source", tmp_path,
                                   resolver=resolver, transport=transport,
                                   clock=kwargs.pop("clock", Clock()), now=fixed_now,
                                   **kwargs)
    return result, transport


def test_plain_fetch_preserves_raw_hash_and_complete_metadata(tmp_path):
    raw = (FIXTURES / "plain-utf8.txt").read_bytes()
    response = ScriptResponse(headers=(("Content-Type", "text/plain; charset=utf-8"),
                                       ("Content-Length", str(len(raw)))), body=raw)
    result, transport = run_fetch(tmp_path, [response])
    assert isinstance(result, FetchSuccess)
    assert result.raw_sha256 == sha256(raw).hexdigest()
    assert result.raw_byte_length == len(raw)
    metadata = json.loads((tmp_path / result.metadata_path).read_text())
    assert metadata["schema_version"] == "controlops-retrieval-record/v1.0.0"
    assert metadata["initial_policy_decision"]["decision"] == "ACCEPT"
    assert metadata["resolution_events"][0]["selected_address"] == "8.8.8.8"
    assert metadata["raw"]["sha256"] == result.raw_sha256
    assert (tmp_path / metadata["raw"]["object_path"]).read_bytes() == raw
    assert (tmp_path / result.visible_text_path).read_bytes() == raw
    assert transport.calls[0][1] == (ResolvedAddress(socket.AF_INET, "8.8.8.8"),)


def test_raw_binary_octets_are_preserved_before_text_derivation(tmp_path):
    raw = b"alpha\x00omega\n"
    result, _ = run_fetch(tmp_path, [ScriptResponse(200, (("Content-Type", "text/plain"),), raw)])
    assert isinstance(result, FetchSuccess)
    metadata = json.loads((tmp_path / result.metadata_path).read_text())
    assert (tmp_path / metadata["raw"]["object_path"]).read_bytes() == raw
    assert (tmp_path / result.visible_text_path).read_bytes() == raw


@pytest.mark.parametrize("url,code", [
    ("https://127.0.0.1/", FetchFailureCode.URL_REJECTED),
    ("http://cloudflare.com/", FetchFailureCode.URL_REVIEW_REQUIRED),
    (None, FetchFailureCode.URL_REJECTED),
])
def test_nonaccepted_url_never_reaches_storage_or_network(tmp_path, url, code):
    calls = []
    result = fetch._fetch_snapshot(url, tmp_path / "missing",
                                   resolver=lambda *args: calls.append(args),
                                   transport=ScriptTransport([]), clock=Clock(), now=fixed_now)
    assert isinstance(result, FetchFailure) and result.code is code
    assert calls == [] and not (tmp_path / "missing").exists()
    assert not hasattr(result, "original_url")
    assert result.policy_decision is None
    assert url is None or url not in repr(result)
    assert url is None or url not in repr(asdict(result))


def test_policy_unavailable_fails_before_io(tmp_path, monkeypatch):
    decision = fetch.evaluate_url("https://cloudflare.com/")
    monkeypatch.setattr(fetch, "evaluate_url", lambda value: decision.__class__(
        decision.original_url, fetch.Decision.REJECT, fetch.ReasonCode.POLICY_UNAVAILABLE,
        None, None, None, None, None, "unavailable", None))
    root = tmp_path / "missing"
    result = fetch.fetch_snapshot("https://cloudflare.com/", root)
    assert result.code is FetchFailureCode.POLICY_UNAVAILABLE
    assert not root.exists()


def test_mixed_public_private_dns_fails_closed_without_transport(tmp_path):
    transport = ScriptTransport([])
    result = fetch._fetch_snapshot("https://cloudflare.com/", tmp_path,
        resolver=lambda *args: [PUBLIC, PRIVATE], transport=transport, clock=Clock(), now=fixed_now)
    assert result.code is FetchFailureCode.RESOLVED_DESTINATION_PROHIBITED
    assert transport.calls == []


def test_redirect_is_rechecked_and_recorded(tmp_path):
    first = ScriptResponse(302, (("Location", "/final"),))
    second = ScriptResponse(200, (("Content-Type", "text/plain"),), b"done")
    result, transport = run_fetch(tmp_path, [first, second])
    assert isinstance(result, FetchSuccess) and len(transport.calls) == 2
    metadata = json.loads((tmp_path / result.metadata_path).read_text())
    assert metadata["redirect_chain"][0]["target_url"] == "https://cloudflare.com/final"
    assert metadata["redirect_chain"][0]["policy_decision"]["decision"] == "ACCEPT"


@pytest.mark.parametrize("location,code", [
    ("https://127.0.0.1/", FetchFailureCode.REDIRECT_TARGET_REJECTED),
    ("http://cloudflare.com/", FetchFailureCode.REDIRECT_TARGET_REVIEW_REQUIRED),
    ("/source", FetchFailureCode.REDIRECT_LOOP),
])
def test_redirect_cannot_bypass_policy(tmp_path, location, code):
    result, _ = run_fetch(tmp_path, [ScriptResponse(302, (("Location", location),))])
    assert result.code is code and result.stage is FailureStage.REDIRECT


def test_redirect_limit_and_location_contract(tmp_path):
    responses = [ScriptResponse(302, (("Location", f"/{n}"),)) for n in range(1, 7)]
    result, transport = run_fetch(tmp_path, responses)
    assert result.code is FetchFailureCode.REDIRECT_LIMIT_EXCEEDED
    assert len(transport.calls) == 6
    for headers in ((), (("Location", ""),), (("Location", "/a"), ("Location", "/b"))):
        result, _ = run_fetch(tmp_path / str(len(headers)), [ScriptResponse(302, headers)])
        assert result.code is FetchFailureCode.REDIRECT_LOCATION_INVALID


@pytest.mark.parametrize("status", [201, 204, 300, 304, 400, 500])
def test_only_status_200_is_final_success(tmp_path, status):
    result, _ = run_fetch(tmp_path, [ScriptResponse(status)])
    assert result.code is FetchFailureCode.HTTP_STATUS_NOT_ACCEPTED


def test_html_extraction_matches_fixture():
    raw = (FIXTURES / "page.html").read_bytes()
    contract = parse_content_contract((("Content-Type", "TEXT/HTML; charset=UTF8"),), raw)
    assert extract_visible_text(raw, contract) == (FIXTURES / "page-visible.txt").read_text().rstrip("\n")
    assert contract.extractor_version == "html-visible-text/v1"
    hidden_void = b"<div hidden>secret<br>still secret</div><p>shown</p>"
    assert extract_visible_text(hidden_void, ContentContract(
        "text/html", None, "utf-8", "html-visible-text/v1")) == "shown"


@pytest.mark.parametrize("header,body,applied", [
    ("text/plain", "café".encode(), "utf-8"),
    ("text/plain; charset=utf8", b"\xef\xbb\xbfhello", "utf-8-sig"),
    ("text/plain; charset=us-ascii", b"hello", "us-ascii"),
])
def test_charset_contract(header, body, applied):
    contract = parse_content_contract((("Content-Type", header),), body)
    assert contract.applied_charset == applied
    assert extract_visible_text(body, contract) in {"café", "hello"}


@pytest.mark.parametrize("headers,body,code", [
    ((('Content-Type', 'application/pdf'),), b'x', 'UNSUPPORTED_CONTENT_TYPE'),
    ((('Content-Type', 'text/plain; charset=latin-1'),), b'x', 'UNSUPPORTED_CHARSET'),
    ((('Content-Type', 'text/plain'), ('Content-Encoding', 'gzip')), b'x', 'UNSUPPORTED_CONTENT_ENCODING'),
    ((('Content-Type', 'text/plain'),), b'\xff', 'MALFORMED_TEXT'),
    ((('Content-Type', 'text/plain'), ('Content-Type', 'text/html')), b'x', 'RESPONSE_HEADERS_INVALID'),
])
def test_content_failures(tmp_path, headers, body, code):
    result, _ = run_fetch(tmp_path, [ScriptResponse(200, headers, body)])
    assert result.code.value == code


def test_empty_response_is_success(tmp_path):
    result, _ = run_fetch(tmp_path, [ScriptResponse(200, (("Content-Type", "text/plain"),
                                                          ("Content-Length", "0")), b"")])
    assert isinstance(result, FetchSuccess)
    assert result.raw_sha256 == sha256(b"").hexdigest()
    assert (tmp_path / result.visible_text_path).read_bytes() == b""


def test_size_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "RAW_LIMIT", 4)
    ok, _ = run_fetch(tmp_path / "ok", [ScriptResponse(200, (("Content-Type", "text/plain"),), b"1234")])
    too_big, _ = run_fetch(tmp_path / "big", [ScriptResponse(200, (("Content-Type", "text/plain"),), b"12345")])
    declared, _ = run_fetch(tmp_path / "declared", [ScriptResponse(200, (
        ("Content-Type", "text/plain"), ("Content-Length", "5")), b"")])
    assert isinstance(ok, FetchSuccess)
    assert too_big.code is declared.code is FetchFailureCode.RESPONSE_TOO_LARGE


@pytest.mark.parametrize("stage", [FailureStage.DNS, FailureStage.CONNECT, FailureStage.TLS,
                                    FailureStage.REDIRECT, FailureStage.HTTP, FailureStage.READ])
def test_network_deadline_code_retains_active_stage(tmp_path, stage):
    class DeadlineTransport:
        def request(self, *args):
            raise fetch._FetchProblem(FetchFailureCode.NETWORK_DEADLINE_EXCEEDED, stage)
    if stage is FailureStage.DNS:
        clock = Clock()
        def late_resolver(*args):
            clock.value += 31
            raise TimeoutError
        result = fetch._fetch_snapshot("https://cloudflare.com/", tmp_path,
            resolver=late_resolver, transport=ScriptTransport([]), clock=clock, now=fixed_now)
    else:
        result = fetch._fetch_snapshot("https://cloudflare.com/", tmp_path,
            resolver=resolver, transport=DeadlineTransport(), clock=Clock(), now=fixed_now)
    assert result.code is FetchFailureCode.NETWORK_DEADLINE_EXCEEDED
    assert result.stage is stage


def test_deadline_after_final_byte_is_not_consulted_during_extraction(tmp_path, monkeypatch):
    clock = Clock()
    original = fetch.extract_visible_text
    def late_extract(raw, contract):
        clock.value += 100
        return original(raw, contract)
    monkeypatch.setattr(fetch, "extract_visible_text", late_extract)
    result, _ = run_fetch(tmp_path, [ScriptResponse(200, (("Content-Type", "text/plain"),
        ("Content-Length", "2")), b"ok")], clock=clock)
    assert isinstance(result, FetchSuccess)


def test_late_persistence_has_storage_failure_not_network_deadline(tmp_path, monkeypatch):
    clock = Clock()
    def fail_publish(self, *args, **kwargs):
        clock.value += 100
        raise SnapshotProblem("SNAPSHOT_PERSISTENCE_FAILED", "STORAGE")
    monkeypatch.setattr(SnapshotStore, "publish", fail_publish)
    result, _ = run_fetch(tmp_path, [ScriptResponse(200, (("Content-Type", "text/plain"),
        ("Content-Length", "2")), b"ok")], clock=clock)
    assert result.code is FetchFailureCode.SNAPSHOT_PERSISTENCE_FAILED


def test_dns_timeout_and_malformed_results(tmp_path):
    def timeout(*args): raise TimeoutError
    result = fetch._fetch_snapshot("https://cloudflare.com/", tmp_path / "timeout",
        resolver=timeout, transport=ScriptTransport([]), clock=Clock(), now=fixed_now)
    assert result.code is FetchFailureCode.DNS_TIMEOUT
    result = fetch._fetch_snapshot("https://cloudflare.com/", tmp_path / "bad",
        resolver=lambda *args: [(999, 1, 1, "", ("x", 443))],
        transport=ScriptTransport([]), clock=Clock(), now=fixed_now)
    assert result.code is FetchFailureCode.DNS_NO_ADDRESS


def test_operational_failure_does_not_retain_canonical_or_original_url(tmp_path):
    url = "https://cloudflare.com/private?token=secret"
    result = fetch._fetch_snapshot(url, tmp_path / "dns-failure",
        resolver=lambda *args: (_ for _ in ()).throw(OSError("resolver detail")),
        transport=ScriptTransport([]), clock=Clock(), now=fixed_now)
    assert result.code is FetchFailureCode.DNS_FAILED
    assert not hasattr(result, "original_url")
    assert result.policy_decision is None
    assert url not in repr(result) and "secret" not in repr(result)
    assert url not in repr(asdict(result)) and "secret" not in repr(asdict(result))


@pytest.mark.parametrize("polls,expect_timeout", [(True, False), (False, True)])
def test_bounded_resolver_worker_is_reaped(monkeypatch, polls, expect_timeout):
    events = []
    class Connection:
        def poll(self, timeout): events.append(("poll", timeout)); return polls
        def recv(self): return True, [PUBLIC]
        def close(self): events.append("close")
    class Child:
        def close(self): events.append("child-close")
    class Process:
        alive = True
        def start(self): events.append("start")
        def join(self, timeout=None): events.append(("join", timeout)); self.alive = False
        def is_alive(self): return self.alive
        def terminate(self): events.append("terminate")
        def kill(self): events.append("kill"); self.alive = False
    class Context:
        def Pipe(self, duplex): return Connection(), Child()
        def Process(self, **kwargs): return Process()
    monkeypatch.setattr(fetch.multiprocessing, "get_context", lambda method: Context())
    if expect_timeout:
        with pytest.raises(TimeoutError): fetch._bounded_resolver("cloudflare.com", 443, 3)
        assert "terminate" in events
    else:
        assert fetch._bounded_resolver("cloudflare.com", 443, 3) == [PUBLIC]
    assert any(item[0] == "join" for item in events if isinstance(item, tuple))


@pytest.mark.parametrize("code,stage", [
    (FetchFailureCode.CONNECT_TIMEOUT, FailureStage.CONNECT),
    (FetchFailureCode.CONNECT_FAILED, FailureStage.CONNECT),
    (FetchFailureCode.TLS_FAILED, FailureStage.TLS),
    (FetchFailureCode.READ_TIMEOUT, FailureStage.HTTP),
])
def test_transport_failure_semantics(tmp_path, code, stage):
    class FailingTransport:
        def request(self, *args):
            raise fetch._FetchProblem(code, stage)
    result = fetch._fetch_snapshot("https://cloudflare.com/", tmp_path,
        resolver=resolver, transport=FailingTransport(), clock=Clock(), now=fixed_now)
    assert result.code is code and result.stage is stage


def test_body_read_inactivity_timeout(tmp_path):
    class TimeoutResponse(ScriptResponse):
        def read(self, size):
            raise socket.timeout
    result, _ = run_fetch(tmp_path, [TimeoutResponse(200, (("Content-Type", "text/plain"),))])
    assert result.code is FetchFailureCode.READ_TIMEOUT and result.stage is FailureStage.READ


def test_storage_rejects_symlink_root(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    root = tmp_path / "root"
    root.symlink_to(target, target_is_directory=True)
    result, _ = run_fetch(root, [ScriptResponse(200, (("Content-Type", "text/plain"),), b"ok")])
    assert result.code is FetchFailureCode.STORAGE_UNAVAILABLE


def test_result_contract_is_immutable_and_not_truthy(tmp_path):
    result, _ = run_fetch(tmp_path, [ScriptResponse(200, (("Content-Type", "text/plain"),), b"ok")])
    with pytest.raises(TypeError): bool(result)
    with pytest.raises(FrozenInstanceError): result.raw_sha256 = "changed"
    failure = FetchFailure(FetchFailureCode.URL_REJECTED, FailureStage.POLICY, "x", None,
                           None)
    assert "secret" not in repr(failure)
    assert "secret" not in repr(asdict(failure))
    with pytest.raises(TypeError): bool(failure)


def test_repeat_snapshot_is_idempotent_and_reextracts_identically(tmp_path):
    raw = (FIXTURES / "page.html").read_bytes()
    headers = (("Content-Type", "text/html; charset=utf-8"),)
    first, _ = run_fetch(tmp_path, [ScriptResponse(200, headers, raw)])
    second, _ = run_fetch(tmp_path, [ScriptResponse(200, headers, raw)])
    assert isinstance(first, FetchSuccess) and first.retrieval_id == second.retrieval_id
    metadata = json.loads((tmp_path / first.metadata_path).read_text())
    stored_raw = (tmp_path / metadata["raw"]["object_path"]).read_bytes()
    contract = ContentContract(metadata["media_type"], metadata["declared_charset"],
                               metadata["applied_charset"], metadata["extraction"]["version"])
    regenerated = extract_visible_text(stored_raw, contract).encode()
    assert sha256(regenerated).hexdigest() == metadata["extraction"]["sha256"]
    assert regenerated == (tmp_path / first.visible_text_path).read_bytes()


def test_runtime_has_no_proxy_model_database_or_policy_table_shortcuts():
    for name in ("fetch.py", "snapshot.py"):
        source = (ROOT / "src" / "controlops_research" / name).read_text()
        tree = ast.parse(source)
        text = source.lower()
        assert "getproxies" not in text and "authorization:" not in text and "cookie:" not in text
        assert "openai" not in text and "postgres" not in text and "is_private" not in text
        assert not any(isinstance(node, ast.ImportFrom) and node.module == "policy_data"
                       for node in ast.walk(tree))


def test_production_connector_pins_numeric_address_and_preserves_host_and_sni(monkeypatch):
    events = {}
    class RawSocket:
        def settimeout(self, value): events.setdefault("timeouts", []).append(value)
        def connect(self, address): events["connect"] = address
        def close(self): events["raw_closed"] = True
    class TLSSocket:
        def settimeout(self, value): events.setdefault("tls_timeouts", []).append(value)
        def sendall(self, value): events["request"] = value
        def close(self): events["tls_closed"] = True
    class Context:
        minimum_version = None
        def wrap_socket(self, stream, server_hostname):
            events["sni"] = server_hostname
            events["minimum"] = self.minimum_version
            return TLSSocket()
    class HTTPResponse:
        status = 200
        def __init__(self, stream): events["http_stream"] = stream
        def begin(self): pass
        def getheaders(self): return [("Content-Type", "text/plain")]
        def read(self, size): return b""
        def close(self): pass
    monkeypatch.setattr(fetch.socket, "socket", lambda *args: RawSocket())
    monkeypatch.setattr(fetch.socket, "getaddrinfo", lambda *args: pytest.fail("second DNS lookup"))
    monkeypatch.setattr(fetch.ssl, "create_default_context", lambda: Context())
    monkeypatch.setattr(fetch.http.client, "HTTPResponse", HTTPResponse)
    decision = fetch.evaluate_url("https://cloudflare.com/a?q=1")
    response, selected = fetch._PinnedTransport().request(
        decision, (ResolvedAddress(socket.AF_INET, "8.8.8.8"),), 40, Clock())
    assert selected == "8.8.8.8" and events["connect"] == ("8.8.8.8", 443)
    assert events["sni"] == "cloudflare.com"
    assert events["minimum"] is fetch.ssl.TLSVersion.TLSv1_2
    request = events["request"].decode("ascii")
    assert request.startswith("GET /a?q=1 HTTP/1.1\r\nHost: cloudflare.com\r\n")
    assert "Accept-Encoding: identity\r\n" in request
    assert "Authorization:" not in request and "Cookie:" not in request
    response.close()


def test_fixture_manifest_hashes():
    manifest = json.loads((FIXTURES / "responses.json").read_text())
    for name, digest in manifest["fixtures"].items():
        assert sha256((FIXTURES / name).read_bytes()).hexdigest() == digest
