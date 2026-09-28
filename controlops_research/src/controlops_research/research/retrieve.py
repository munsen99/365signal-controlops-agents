"""Host retrieval with an allowlist check before every request."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import http.client
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from .allowlist import (
    MAX_BYTES_PER_SOURCE,
    MAX_REDIRECT_HOPS,
    MAX_RETRIEVE,
    RETRIEVE_TIMEOUT_S,
    is_aka,
    is_allowlisted,
    may_request,
)
from .extract import extract_text, media_and_charset

REDIRECTS = frozenset({301, 302, 303, 307, 308})


@dataclass
class Candidate:
    candidate_id: str
    seed_url: str
    url: str
    canonical_url: str
    title: str
    retrieved_at: str
    http_status: int
    content_type: str
    redirect_hops: list[str]
    content_hash: str | None
    text: str
    truncated: bool
    usable: bool
    skip_reason: str | None
    body: bytes = field(default=b"", repr=False)

    def public(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "seed_url": self.seed_url,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "retrieved_at": self.retrieved_at,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "redirect_hops": list(self.redirect_hops),
            "content_hash": self.content_hash,
            "text": self.text,
            "truncated": self.truncated,
            "usable": self.usable,
            "skip_reason": self.skip_reason,
        }


class PageResponse(Protocol):
    status: int

    def header(self, name: str) -> str | None:
        """Return one response header."""

    def read(self, amount: int) -> bytes:
        """Return at most `amount` bytes."""

    def close(self) -> None:
        """Release the response."""


class HttpTransport(Protocol):
    def get(self, url: str, timeout: float) -> PageResponse:
        """Request one URL. The caller decides whether a redirect is followed."""


class _LibResponse:
    def __init__(self, connection: http.client.HTTPConnection, response: http.client.HTTPResponse) -> None:
        self._connection = connection
        self._response = response
        self.status = response.status

    def header(self, name: str) -> str | None:
        return self._response.getheader(name)

    def read(self, amount: int) -> bytes:
        return self._response.read(amount)

    def close(self) -> None:
        self._response.close()
        self._connection.close()


class HostHttp:
    """Production transport. It does not follow redirects by itself."""

    def get(self, url: str, timeout: float) -> PageResponse:
        parsed = urlsplit(url)
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=timeout)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        try:
            connection.request("GET", path, headers={
                "User-Agent": "ControlOps-Research-PR6A/1.0",
                "Accept-Encoding": "identity",
            })
            return _LibResponse(connection, connection.getresponse())
        except Exception:
            connection.close()
            raise


def retrieve_seeds(
    seeds: list[tuple[str, str, str]],
    transport: HttpTransport,
    *,
    timeout: float = RETRIEVE_TIMEOUT_S,
) -> list[Candidate]:
    """Retrieve `(candidate_id, raw, canonical)` triples. The caller applies the cap."""
    return [_retrieve_one(candidate_id, raw, canonical, transport, timeout) for candidate_id, raw, canonical in seeds]


def _retrieve_one(candidate_id: str, raw: str, canonical: str, transport: HttpTransport, timeout: float) -> Candidate:
    requested: list[str] = []
    follows = 0
    current = canonical
    while True:
        if not may_request(current):
            reason = "OFF_ALLOWLIST" if not requested else "REDIRECT_HOP_DENIED"
            shown = current if not requested else raw
            return _skipped(candidate_id, raw, canonical, shown, requested, reason)
        try:
            response = transport.get(current, timeout)
        except TimeoutError:
            return _skipped(candidate_id, raw, canonical, raw, requested + [current], "TIMEOUT")
        except OSError:
            return _skipped(candidate_id, raw, canonical, raw, requested + [current], "HTTP_ERROR")
        requested.append(current)
        try:
            try:
                if response.status in REDIRECTS:
                    if follows >= MAX_REDIRECT_HOPS:
                        return _skipped(candidate_id, raw, canonical, raw, requested, "REDIRECT_CAP")
                    location = response.header("location") or response.header("Location")
                    if not location:
                        return _skipped(candidate_id, raw, canonical, raw, requested, "REDIRECT_HOP_DENIED")
                    nxt = urljoin(current, location.strip())
                    if not may_request(nxt):
                        return _skipped(candidate_id, raw, canonical, raw, requested, "REDIRECT_HOP_DENIED")
                    follows += 1
                    current = nxt
                    continue
                if response.status != 200:
                    return _skipped(candidate_id, raw, canonical, current, requested, "HTTP_ERROR", response.status)
                return _capture(candidate_id, raw, canonical, current, requested, response)
            except TimeoutError:
                return _skipped(candidate_id, raw, canonical, current, requested, "TIMEOUT")
            except OSError:
                return _skipped(candidate_id, raw, canonical, current, requested, "HTTP_ERROR")
        finally:
            response.close()


def _capture(candidate_id: str, raw: str, canonical: str, url: str, hops: list[str], response: PageResponse) -> Candidate:
    if not is_allowlisted(url) or is_aka(url):
        return _skipped(candidate_id, raw, canonical, url, hops, "OFF_ALLOWLIST", response.status)
    content_type = response.header("content-type") or response.header("Content-Type")
    if content_type is not None and content_type.strip():
        media, _charset = media_and_charset(content_type, b"")
        if media is None:
            return _skipped(candidate_id, raw, canonical, url, hops, "CONTENT_TYPE", response.status, content_type)
    body, byte_truncated = _read_capped(response)
    media, charset = media_and_charset(content_type, body)
    if media is None:
        return _skipped(candidate_id, raw, canonical, url, hops, "CONTENT_TYPE", response.status, content_type or "")
    if not body:
        return _skipped(candidate_id, raw, canonical, url, hops, "EMPTY_BODY", response.status, media)
    text, title, text_truncated = extract_text(body, media, charset)
    if not text:
        return _skipped(candidate_id, raw, canonical, url, hops, "EMPTY_BODY", response.status, media)
    return Candidate(
        candidate_id=candidate_id,
        seed_url=raw,
        url=url,
        canonical_url=canonical,
        title=title,
        retrieved_at=_now(),
        http_status=response.status,
        content_type=media,
        redirect_hops=list(hops),
        content_hash=hashlib.sha256(body).hexdigest(),
        text=text,
        truncated=byte_truncated or text_truncated,
        usable=response.status == 200,
        skip_reason=None,
        body=body,
    )


def _read_capped(response: PageResponse) -> tuple[bytes, bool]:
    chunks = []
    total = 0
    while total < MAX_BYTES_PER_SOURCE:
        chunk = response.read(min(8192, MAX_BYTES_PER_SOURCE - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    body = b"".join(chunks)
    header = response.header("content-length") or response.header("Content-Length")
    if header is not None and header.strip().isdigit():
        return body, int(header.strip()) > len(body)
    return body, len(body) == MAX_BYTES_PER_SOURCE


def duplicate_candidate(candidate_id: str, raw: str, canonical: str) -> Candidate:
    return _skipped(candidate_id, raw, canonical, "", [], "DUPLICATE_SEED")


def _skipped(
    candidate_id: str,
    raw: str,
    canonical: str,
    url: str,
    hops: list[str],
    reason: str,
    status: int = 0,
    content_type: str = "",
) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        seed_url=raw,
        url=url,
        canonical_url=canonical,
        title="",
        retrieved_at=_now(),
        http_status=status,
        content_type=content_type,
        redirect_hops=list(hops),
        content_hash=None,
        text="",
        truncated=False,
        usable=False,
        skip_reason=reason,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
