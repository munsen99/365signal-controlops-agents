"""Controlled HTTPS acquisition after authoritative PR1 URL decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import http.client
from ipaddress import IPv4Address, IPv6Address
import multiprocessing
import os
from pathlib import Path
import re
import socket
import ssl
import time
from typing import Callable, Protocol
from urllib.parse import urljoin, urlsplit

from .policy import Decision, ReasonCode, UrlDecision, evaluate_url
from .snapshot import (RAW_LIMIT, SCHEMA_VERSION, SnapshotProblem, SnapshotStore,
                       extract_visible_text, parse_content_contract)

__all__ = ["FailureStage", "FetchFailure", "FetchFailureCode", "FetchResult",
           "FetchSuccess", "fetch_snapshot"]

FETCH_POLICY_VERSION = "controlops-fetch/v1.0.0"
DNS_TIMEOUT = 3.0
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 10.0
NETWORK_DEADLINE = 30.0
MAX_REDIRECTS = 5
READ_CHUNK = 65_536
_REDIRECTS = frozenset({301, 302, 303, 307, 308})


class FailureStage(StrEnum):
    POLICY = "POLICY"
    STORAGE = "STORAGE"
    DNS = "DNS"
    CONNECT = "CONNECT"
    TLS = "TLS"
    REDIRECT = "REDIRECT"
    HTTP = "HTTP"
    READ = "READ"
    CONTENT = "CONTENT"
    EXTRACT = "EXTRACT"


class FetchFailureCode(StrEnum):
    POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"
    URL_REJECTED = "URL_REJECTED"
    URL_REVIEW_REQUIRED = "URL_REVIEW_REQUIRED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    DNS_TIMEOUT = "DNS_TIMEOUT"
    DNS_FAILED = "DNS_FAILED"
    DNS_NO_ADDRESS = "DNS_NO_ADDRESS"
    RESOLVED_DESTINATION_PROHIBITED = "RESOLVED_DESTINATION_PROHIBITED"
    CONNECT_TIMEOUT = "CONNECT_TIMEOUT"
    CONNECT_FAILED = "CONNECT_FAILED"
    TLS_FAILED = "TLS_FAILED"
    REDIRECT_LOCATION_INVALID = "REDIRECT_LOCATION_INVALID"
    REDIRECT_TARGET_REJECTED = "REDIRECT_TARGET_REJECTED"
    REDIRECT_TARGET_REVIEW_REQUIRED = "REDIRECT_TARGET_REVIEW_REQUIRED"
    REDIRECT_LOOP = "REDIRECT_LOOP"
    REDIRECT_LIMIT_EXCEEDED = "REDIRECT_LIMIT_EXCEEDED"
    HTTP_STATUS_NOT_ACCEPTED = "HTTP_STATUS_NOT_ACCEPTED"
    RESPONSE_HEADERS_INVALID = "RESPONSE_HEADERS_INVALID"
    READ_TIMEOUT = "READ_TIMEOUT"
    READ_FAILED = "READ_FAILED"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    UNSUPPORTED_CONTENT_TYPE = "UNSUPPORTED_CONTENT_TYPE"
    UNSUPPORTED_CONTENT_ENCODING = "UNSUPPORTED_CONTENT_ENCODING"
    UNSUPPORTED_CHARSET = "UNSUPPORTED_CHARSET"
    MALFORMED_TEXT = "MALFORMED_TEXT"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    EXTRACTED_TEXT_TOO_LARGE = "EXTRACTED_TEXT_TOO_LARGE"
    SNAPSHOT_PERSISTENCE_FAILED = "SNAPSHOT_PERSISTENCE_FAILED"
    NETWORK_DEADLINE_EXCEEDED = "NETWORK_DEADLINE_EXCEEDED"


_MESSAGES = {code: code.value.replace("_", " ").capitalize() + "." for code in FetchFailureCode}


@dataclass(frozen=True, slots=True)
class FetchSuccess:
    retrieval_id: str
    final_url: str
    raw_sha256: str
    raw_byte_length: int
    metadata_path: str
    visible_text_path: str

    def __bool__(self) -> bool:
        raise TypeError("FetchResult has no truth value")


@dataclass(frozen=True, slots=True)
class FetchFailure:
    code: FetchFailureCode
    stage: FailureStage
    explanation: str
    hop_index: int | None
    policy_decision: UrlDecision | None

    def __bool__(self) -> bool:
        raise TypeError("FetchResult has no truth value")


FetchResult = FetchSuccess | FetchFailure


@dataclass(frozen=True, slots=True)
class ResolvedAddress:
    family: int
    address: str


class Response(Protocol):
    status: int
    headers: tuple[tuple[str, str], ...]
    def read(self, size: int) -> bytes: ...
    def settimeout(self, timeout: float) -> None: ...
    def close(self) -> None: ...


class Transport(Protocol):
    def request(self, decision: UrlDecision, addresses: tuple[ResolvedAddress, ...],
                deadline: float, clock: Callable[[], float]) -> tuple[Response, str]: ...


class _FetchProblem(Exception):
    def __init__(self, code: FetchFailureCode, stage: FailureStage,
                 decision: UrlDecision | None = None, hop: int | None = None):
        super().__init__(code)
        self.code, self.stage, self.decision, self.hop = code, stage, decision, hop


class _HTTPResponse:
    def __init__(self, response: http.client.HTTPResponse, stream: ssl.SSLSocket):
        self._response, self._stream = response, stream
        self.status = response.status
        self.headers = tuple(response.getheaders())

    def read(self, size: int) -> bytes:
        return self._response.read(size)

    def settimeout(self, timeout: float) -> None:
        self._stream.settimeout(timeout)

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._stream.close()


def _remaining(deadline: float, clock: Callable[[], float], stage: FailureStage) -> float:
    remaining = deadline - clock()
    if remaining <= 0:
        raise _FetchProblem(FetchFailureCode.NETWORK_DEADLINE_EXCEEDED, stage)
    return remaining


class _PinnedTransport:
    def request(self, decision: UrlDecision, addresses: tuple[ResolvedAddress, ...],
                deadline: float, clock: Callable[[], float]) -> tuple[Response, str]:
        parts = urlsplit(decision.canonical_url)
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        host_header = f"[{decision.host}]" if decision.host_kind == "ipv6" else decision.host
        request = (f"GET {target} HTTP/1.1\r\nHost: {host_header}\r\n"
                   "User-Agent: ControlOps-Research-Fetch/1.0\r\n"
                   "Accept: text/html, text/plain;q=0.9\r\n"
                   "Accept-Encoding: identity\r\nConnection: close\r\n\r\n").encode("ascii")
        saw_timeout = False
        saw_tls = False
        for item in addresses:
            stream = None
            try:
                timeout = min(CONNECT_TIMEOUT, _remaining(deadline, clock, FailureStage.CONNECT))
                stream = socket.socket(item.family, socket.SOCK_STREAM)
                stream.settimeout(timeout)
                sockaddr = (item.address, 443) if item.family == socket.AF_INET else (item.address, 443, 0, 0)
                stream.connect(sockaddr)
            except _FetchProblem:
                if stream is not None:
                    stream.close()
                raise
            except (socket.timeout, TimeoutError):
                saw_timeout = True
                stream.close()
                stream = None
            except OSError:
                stream.close()
                stream = None
            if stream is None:
                continue
            try:
                context = ssl.create_default_context()
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                stream.settimeout(min(CONNECT_TIMEOUT, _remaining(deadline, clock, FailureStage.TLS)))
                tls = context.wrap_socket(stream, server_hostname=decision.host)
                stream = None
            except _FetchProblem:
                if stream is not None:
                    stream.close()
                raise
            except (ssl.SSLError, OSError, socket.timeout, TimeoutError):
                saw_tls = True
                if stream is not None:
                    stream.close()
                continue
            try:
                tls.settimeout(min(READ_TIMEOUT, _remaining(deadline, clock, FailureStage.HTTP)))
                tls.sendall(request)
                response = http.client.HTTPResponse(tls)
                response.begin()
                return _HTTPResponse(response, tls), item.address
            except _FetchProblem:
                tls.close()
                raise
            except (socket.timeout, TimeoutError) as error:
                tls.close()
                if clock() >= deadline:
                    raise _FetchProblem(FetchFailureCode.NETWORK_DEADLINE_EXCEEDED,
                                        FailureStage.HTTP) from error
                raise _FetchProblem(FetchFailureCode.READ_TIMEOUT, FailureStage.HTTP) from error
            except (OSError, http.client.HTTPException) as error:
                tls.close()
                raise _FetchProblem(FetchFailureCode.READ_FAILED, FailureStage.HTTP) from error
        if clock() >= deadline:
            raise _FetchProblem(FetchFailureCode.NETWORK_DEADLINE_EXCEEDED, FailureStage.CONNECT)
        if saw_tls:
            raise _FetchProblem(FetchFailureCode.TLS_FAILED, FailureStage.TLS)
        if saw_timeout:
            raise _FetchProblem(FetchFailureCode.CONNECT_TIMEOUT, FailureStage.CONNECT)
        raise _FetchProblem(FetchFailureCode.CONNECT_FAILED, FailureStage.CONNECT)


def _resolver_worker(connection, host: str, port: int) -> None:
    try:
        values = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        connection.send((True, values))
    except BaseException:
        connection.send((False, None))
    finally:
        connection.close()


def _bounded_resolver(host: str, port: int, timeout: float):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_resolver_worker, args=(child, host, port), daemon=True)
    process.start()
    child.close()
    try:
        if not parent.poll(timeout):
            process.terminate()
            process.join(0.2)
            if process.is_alive():
                process.kill()
                process.join()
            raise TimeoutError
        ok, values = parent.recv()
        process.join()
        if not ok:
            raise OSError
        return values
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
            process.join()


def _decision_dict(decision: UrlDecision) -> dict:
    return asdict(decision)


def _policy_gate(value: object, *, redirect: bool = False) -> UrlDecision:
    decision = evaluate_url(value)
    if (decision.decision is Decision.ACCEPT and
            decision.reason_code is ReasonCode.PUBLIC_URL_CANDIDATE and
            decision.policy_version == "controlops-public-url/v1.0.0" and
            decision.canonical_url is not None and decision.host is not None and
            decision.effective_port == 443):
        return decision
    if redirect:
        code = (FetchFailureCode.REDIRECT_TARGET_REVIEW_REQUIRED
                if decision.decision is Decision.REVIEW
                else FetchFailureCode.REDIRECT_TARGET_REJECTED)
        raise _FetchProblem(code, FailureStage.REDIRECT, decision)
    if decision.reason_code is ReasonCode.POLICY_UNAVAILABLE:
        code = FetchFailureCode.POLICY_UNAVAILABLE
    elif decision.decision is Decision.REVIEW:
        code = FetchFailureCode.URL_REVIEW_REQUIRED
    else:
        code = FetchFailureCode.URL_REJECTED
    raise _FetchProblem(code, FailureStage.POLICY, decision)


def _addresses(decision: UrlDecision, resolver, deadline: float, clock, hop: int):
    if decision.host_kind in {"ipv4", "ipv6"}:
        raw_values = [(socket.AF_INET if decision.host_kind == "ipv4" else socket.AF_INET6,
                       socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                       (decision.host, 443) if decision.host_kind == "ipv4"
                       else (decision.host, 443, 0, 0))]
    else:
        timeout = min(DNS_TIMEOUT, _remaining(deadline, clock, FailureStage.DNS))
        try:
            raw_values = resolver(decision.host, 443, timeout)
        except TimeoutError as error:
            if clock() >= deadline:
                raise _FetchProblem(FetchFailureCode.NETWORK_DEADLINE_EXCEEDED,
                                    FailureStage.DNS, hop=hop) from error
            raise _FetchProblem(FetchFailureCode.DNS_TIMEOUT, FailureStage.DNS, hop=hop) from error
        except Exception as error:
            raise _FetchProblem(FetchFailureCode.DNS_FAILED, FailureStage.DNS, hop=hop) from error
    parsed: set[tuple[int, int, str]] = set()
    try:
        for family, socktype, proto, canonname, sockaddr in raw_values:
            if family not in (socket.AF_INET, socket.AF_INET6) or socktype != socket.SOCK_STREAM:
                continue
            if proto not in (0, socket.IPPROTO_TCP) or canonname:
                raise ValueError
            if family == socket.AF_INET6 and (len(sockaddr) < 4 or sockaddr[3] != 0 or "%" in sockaddr[0]):
                raise ValueError
            address = IPv4Address(sockaddr[0]) if family == socket.AF_INET else IPv6Address(sockaddr[0])
            text = address.compressed
            if family == socket.AF_INET6 and "." in text:
                raise ValueError
            parsed.add((0 if family == socket.AF_INET else 1, family, text))
    except (ValueError, TypeError, IndexError) as error:
        raise _FetchProblem(FetchFailureCode.DNS_FAILED, FailureStage.DNS, hop=hop) from error
    if not parsed:
        raise _FetchProblem(FetchFailureCode.DNS_NO_ADDRESS, FailureStage.DNS, hop=hop)
    addresses = tuple(ResolvedAddress(family, text) for _, family, text in
                      sorted(parsed, key=lambda x: (x[0], int(IPv4Address(x[2])) if x[1] == socket.AF_INET else int(IPv6Address(x[2])))))
    decisions = []
    for item in addresses:
        literal = f"https://{item.address}/" if item.family == socket.AF_INET else f"https://[{item.address}]/"
        checked = evaluate_url(literal)
        decisions.append(_decision_dict(checked))
        if (checked.decision is not Decision.ACCEPT or
                checked.policy_version != decision.policy_version):
            raise _FetchProblem(FetchFailureCode.RESOLVED_DESTINATION_PROHIBITED,
                                FailureStage.DNS, checked, hop)
    return addresses, decisions


def _single_header(headers: tuple[tuple[str, str], ...], name: str) -> str | None:
    values = [value for key, value in headers if key.lower() == name]
    if len(values) > 1:
        raise _FetchProblem(FetchFailureCode.RESPONSE_HEADERS_INVALID, FailureStage.HTTP)
    return values[0] if values else None


def _timestamp(now: Callable[[], datetime]) -> str:
    value = now().astimezone(timezone.utc)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _fetch_snapshot(value: object, snapshot_root: Path, *, resolver=_bounded_resolver,
                    transport: Transport | None = None, clock=time.monotonic,
                    now=lambda: datetime.now(timezone.utc)) -> FetchResult:
    store: SnapshotStore | None = None
    decision: UrlDecision | None = None
    hop = 0
    try:
        decision = _policy_gate(value)
        store = SnapshotStore(snapshot_root)
        raw_path = store.begin()
        started_at = _timestamp(now)
        deadline = clock() + NETWORK_DEADLINE
        transport = transport or _PinnedTransport()
        current = decision
        visited = {current.canonical_url}
        redirects: list[dict] = []
        resolutions: list[dict] = []
        while True:
            addresses, address_decisions = _addresses(current, resolver, deadline, clock, hop)
            response, selected = transport.request(current, addresses, deadline, clock)
            resolutions.append({
                "canonical_url": current.canonical_url, "host": current.host,
                "port": 443, "addresses": [x.address for x in addresses],
                "address_decisions": address_decisions, "selected_address": selected,
            })
            try:
                if response.status in _REDIRECTS:
                    if len(redirects) >= MAX_REDIRECTS:
                        raise _FetchProblem(FetchFailureCode.REDIRECT_LIMIT_EXCEEDED,
                                            FailureStage.REDIRECT, current, hop)
                    locations = [v for k, v in response.headers if k.lower() == "location"]
                    if len(locations) != 1 or not locations[0]:
                        raise _FetchProblem(FetchFailureCode.REDIRECT_LOCATION_INVALID,
                                            FailureStage.REDIRECT, current, hop)
                    target_value = urljoin(current.canonical_url, locations[0])
                    try:
                        target = _policy_gate(target_value, redirect=True)
                    except _FetchProblem as error:
                        raise _FetchProblem(error.code, error.stage, error.decision, hop) from error
                    if target.canonical_url in visited:
                        raise _FetchProblem(FetchFailureCode.REDIRECT_LOOP,
                                            FailureStage.REDIRECT, target, hop)
                    redirects.append({"hop": hop, "source_url": current.canonical_url,
                                      "status": response.status, "location": locations[0],
                                      "target_url": target.canonical_url,
                                      "policy_decision": _decision_dict(target)})
                    visited.add(target.canonical_url)
                    current = target
                    hop += 1
                    continue
                if response.status != 200:
                    raise _FetchProblem(FetchFailureCode.HTTP_STATUS_NOT_ACCEPTED,
                                        FailureStage.HTTP, current, hop)
                length_header = _single_header(response.headers, "content-length")
                if length_header is not None:
                    if not re.fullmatch(r"0|[1-9][0-9]*", length_header.strip()):
                        raise _FetchProblem(FetchFailureCode.RESPONSE_HEADERS_INVALID,
                                            FailureStage.HTTP, current, hop)
                    declared_length = int(length_header)
                    if declared_length > RAW_LIMIT:
                        raise _FetchProblem(FetchFailureCode.RESPONSE_TOO_LARGE,
                                            FailureStage.READ, current, hop)
                else:
                    declared_length = None
                digest = sha256()
                total = 0
                with raw_path.open("wb") as output:
                    os.chmod(raw_path, 0o600)
                    while True:
                        remaining = _remaining(deadline, clock, FailureStage.READ)
                        if hasattr(response, "settimeout"):
                            response.settimeout(min(READ_TIMEOUT, remaining))
                        try:
                            chunk = response.read(min(READ_CHUNK, RAW_LIMIT + 1 - total))
                        except (socket.timeout, TimeoutError) as error:
                            if clock() >= deadline:
                                raise _FetchProblem(FetchFailureCode.NETWORK_DEADLINE_EXCEEDED,
                                                    FailureStage.READ, current, hop) from error
                            raise _FetchProblem(FetchFailureCode.READ_TIMEOUT,
                                                FailureStage.READ, current, hop) from error
                        except Exception as error:
                            raise _FetchProblem(FetchFailureCode.READ_FAILED,
                                                FailureStage.READ, current, hop) from error
                        if clock() >= deadline:
                            raise _FetchProblem(FetchFailureCode.NETWORK_DEADLINE_EXCEEDED,
                                                FailureStage.READ, current, hop)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > RAW_LIMIT:
                            raise _FetchProblem(FetchFailureCode.RESPONSE_TOO_LARGE,
                                                FailureStage.READ, current, hop)
                        output.write(chunk)
                        digest.update(chunk)
                        if declared_length is not None and total == declared_length:
                            break
                    output.flush()
                    os.fsync(output.fileno())
                if declared_length is not None and total != declared_length:
                    raise _FetchProblem(FetchFailureCode.READ_FAILED,
                                        FailureStage.READ, current, hop)
                raw_digest = digest.hexdigest()
                break
            finally:
                response.close()
        raw = raw_path.read_bytes()
        try:
            contract = parse_content_contract(response.headers, raw)
            visible = extract_visible_text(raw, contract)
        except SnapshotProblem as error:
            raise _FetchProblem(FetchFailureCode(error.code), FailureStage(error.stage), current, hop) from error
        completed_at = _timestamp(now)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "fetch_policy_version": FETCH_POLICY_VERSION,
            "requested_url": value,
            "initial_policy_decision": _decision_dict(decision),
            "final_url": current.canonical_url,
            "redirect_chain": redirects,
            "resolution_events": resolutions,
            "started_at": started_at,
            "completed_at": completed_at,
            "http_status": 200,
            "media_type": contract.media_type,
            "declared_charset": contract.declared_charset,
            "applied_charset": contract.applied_charset,
            "content_encoding": "identity",
            "extraction": {"version": contract.extractor_version},
        }
        try:
            stored = store.publish(raw_path, raw_digest, total, visible, metadata)
        except SnapshotProblem as error:
            raise _FetchProblem(FetchFailureCode(error.code), FailureStage(error.stage), current, hop) from error
        return FetchSuccess(stored.retrieval_id, current.canonical_url, raw_digest, total,
                            stored.metadata_path, stored.visible_text_path)
    except SnapshotProblem as error:
        problem = _FetchProblem(FetchFailureCode(error.code), FailureStage(error.stage), decision, hop)
    except _FetchProblem as error:
        problem = error
    finally:
        if store is not None:
            store.cleanup()
    return FetchFailure(problem.code, problem.stage, _MESSAGES[problem.code],
                        problem.hop if problem.hop is not None else hop,
                        None)


def fetch_snapshot(value: object, snapshot_root: Path) -> FetchResult:
    """Retrieve and persist one PR1-accepted HTTPS source under fixed controls."""
    return _fetch_snapshot(value, snapshot_root)
