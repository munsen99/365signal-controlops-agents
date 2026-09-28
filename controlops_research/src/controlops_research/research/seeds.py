"""Canonicalise and deduplicate operator seed URLs. This is not discovery."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from .allowlist import MAX_SEED_URLS


def canonical_seed(url: str) -> str:
    """Lower-case the scheme and host, drop the fragment, and keep path and query."""
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower().rstrip(".") if parsed.hostname else ""
    if parsed.port is not None:
        netloc = f"{host}:{parsed.port}" if host else parsed.netloc
    else:
        netloc = host
        if scheme == "http":
            scheme = "https"
    if parsed.username is not None:
        auth = parsed.username
        if parsed.password is not None:
            auth = f"{auth}:{parsed.password}"
        netloc = f"{auth}@{netloc}"
    return urlunsplit((scheme, netloc, parsed.path, parsed.query, ""))


def prepare_seeds(raw_urls: list[str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]], str | None]:
    """Return unique `(raw, canonical)` pairs, duplicates, and a failure code."""
    if not raw_urls:
        return [], [], "CONFIG_INVALID"
    unique: list[tuple[str, str]] = []
    duplicates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in raw_urls:
        canonical = canonical_seed(raw)
        if canonical in seen:
            duplicates.append((raw, canonical))
            continue
        seen.add(canonical)
        unique.append((raw, canonical))
    if not unique or len(unique) > MAX_SEED_URLS:
        return unique, duplicates, "CONFIG_INVALID"
    return unique, duplicates, None
