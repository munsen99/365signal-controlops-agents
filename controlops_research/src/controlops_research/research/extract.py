"""Turn captured prefix bytes into bounded plain text."""

from __future__ import annotations

import html
import re

from .allowlist import ALLOWED_MEDIA, MAX_SELECT_CHARS

_TITLE = re.compile(r"(?is)<title\b[^>]*>(.*?)</title>")
_SCRIPT = re.compile(r"(?is)<(script|style)\b[^>]*>.*?</\1>")
_TAG = re.compile(r"(?is)<[^>]+>")
_SPACE = re.compile(r"\s+")


def media_and_charset(content_type: str | None, body: bytes) -> tuple[str | None, str]:
    """Return an allowed media type and charset, or `(None, ...)` when the type is rejected."""
    if content_type is None or not content_type.strip():
        if _looks_like_html(body):
            return "text/html", "utf-8"
        return None, "utf-8"
    parts = [part.strip() for part in content_type.split(";")]
    media = parts[0].lower()
    if media not in ALLOWED_MEDIA:
        return None, "utf-8"
    charset = "utf-8"
    for part in parts[1:]:
        if part.lower().startswith("charset="):
            charset = part.split("=", 1)[1].strip().strip('"').strip("'") or "utf-8"
            break
    return media, charset


def extract_text(body: bytes, media: str, charset: str) -> tuple[str, str, bool]:
    """Return text, title, and whether the text tail was cut."""
    try:
        decoded = body.decode(charset, errors="replace")
    except LookupError:
        decoded = body.decode("utf-8", errors="replace")
    if media == "text/plain":
        text = decoded.strip()
        title = ""
    else:
        title_match = _TITLE.search(decoded)
        title = _plain(title_match.group(1)) if title_match else ""
        without_hidden = _SCRIPT.sub(" ", decoded)
        text = _plain(_TAG.sub(" ", without_hidden))
    truncated = False
    if len(text) > MAX_SELECT_CHARS:
        text = text[:MAX_SELECT_CHARS]
        truncated = True
    return text, title, truncated


def _looks_like_html(body: bytes) -> bool:
    head = body.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def _plain(value: str) -> str:
    return _SPACE.sub(" ", html.unescape(value)).strip()
