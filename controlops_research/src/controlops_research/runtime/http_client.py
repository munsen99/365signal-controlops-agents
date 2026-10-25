"""The only LM Studio HTTP client. GET /v1/models and POST /v1/chat/completions."""

from __future__ import annotations

import http.client
from typing import Protocol
from urllib.parse import urlsplit

from .errors import RuntimeFailure

_FORBIDDEN_PATH_TOKENS = ("load", "unload", "eject", "evict")
_ALLOWED = {
    ("GET", "/v1/models"),
    ("POST", "/v1/chat/completions"),
}


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, bytes]:
        """Perform one HTTP request and return status plus body."""


class UrllibTransport:
    """Production transport. Talks only to the URL `exchange` has already allowed."""

    def request(
        self,
        method: str,
        url: str,
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, bytes]:
        parts = urlsplit(url)
        if parts.scheme != "http" or not parts.hostname or parts.port is None:
            raise RuntimeFailure("CONFIG_INVALID", "LM Studio URL is not a fixed http endpoint")
        connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
        try:
            headers = {"Content-Type": "application/json"} if body is not None else {}
            connection.request(method, parts.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            return response.status, payload
        finally:
            connection.close()


def assert_allowed(method: str, url: str) -> None:
    """Refuse management verbs and every path other than the two allowed calls."""
    path = urlsplit(url).path
    lowered = path.lower()
    if any(token in lowered for token in _FORBIDDEN_PATH_TOKENS):
        raise RuntimeFailure("CONFIG_INVALID", "LM Studio management URL is refused")
    if (method, path) not in _ALLOWED:
        raise RuntimeFailure("CONFIG_INVALID", "LM Studio URL is not an allowed verb")


def exchange(
    method: str,
    url: str,
    body: bytes | None,
    timeout: float,
    *,
    transport: Transport | None = None,
) -> tuple[int, bytes]:
    """Send one allowed request. The socket is not opened for a refused URL."""
    assert_allowed(method, url)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise RuntimeFailure("CONFIG_INVALID", "timeout is required")
    client = transport if transport is not None else UrllibTransport()
    try:
        return client.request(method, url, body, float(timeout))
    except (OSError, http.client.HTTPException, TimeoutError) as error:
        raise RuntimeFailure("ENDPOINT_UNAVAILABLE", "LM Studio request failed") from error
