"""Microsoft evidence hosts for PR6A. aka.ms is a redirect hop only."""

from __future__ import annotations

from urllib.parse import urlsplit

ALLOWED_HOSTS = frozenset({
    "learn.microsoft.com",
    "microsoft.com",
    "www.microsoft.com",
    "support.microsoft.com",
    "techcommunity.microsoft.com",
    "azure.microsoft.com",
    "adoption.microsoft.com",
})
AKA_HOST = "aka.ms"

MAX_SEED_URLS = 8
MAX_RETRIEVE = 5
MAX_REDIRECT_HOPS = 5
MAX_BYTES_PER_SOURCE = 200_000
RETRIEVE_TIMEOUT_S = 20
INFER_TIMEOUT_S = 180
MAX_SELECT_CHARS = 12_000

ALLOWED_MEDIA = frozenset({
    "text/html",
    "application/xhtml+xml",
    "text/plain",
})


def hostname(url: str) -> str | None:
    """Return the lower-case host of a plain HTTPS URL, or None when it is unusable."""
    if not isinstance(url, str) or not url or any(char in url for char in " \t\r\n"):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https":
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    host = parsed.hostname
    if not host:
        return None
    if parsed.port not in (None, 443):
        return None
    return host.lower().rstrip(".")


def is_allowlisted(url: str) -> bool:
    return hostname(url) in ALLOWED_HOSTS


def is_aka(url: str) -> bool:
    return hostname(url) == AKA_HOST


def may_request(url: str) -> bool:
    """A hop may be requested when it is evidence or an aka.ms redirect."""
    return is_allowlisted(url) or is_aka(url)
