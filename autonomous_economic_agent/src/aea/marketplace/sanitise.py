"""Wrap untrusted marketplace text. Detect injection. Never execute content.

Preview is truncated and wrapped so naive concatenation cannot override
constitution or policy. Original text is preserved as data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aea.hashing import sha256_hex

PREVIEW_MAX_CHARS = 500
WEB_PREVIEW_MAX_CHARS = 8000
WRAP_OPEN = "[UNTRUSTED_MARKETPLACE_DATA]\n"
WRAP_CLOSE = "\n[/UNTRUSTED_MARKETPLACE_DATA]"
WEB_WRAP_OPEN = "[UNTRUSTED_WEB_DATA]\n"
WEB_WRAP_CLOSE = "\n[/UNTRUSTED_WEB_DATA]"
HOSTILE_CONTENT = "HOSTILE_CONTENT"

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bignore\b.{0,40}\bconstitution\b", re.I),
    re.compile(r"\bignore\b.{0,40}\bpolicy\b", re.I),
    re.compile(r"\bsend\s+all\s+USDC\b", re.I),
    re.compile(r"\bdisable\b.{0,40}\bsupervisor\b", re.I),
    re.compile(r"\bunfreeze\b", re.I),
    re.compile(r"\breveal\b.{0,40}\b(secret|token|key|seed)\b", re.I),
    re.compile(r"\bAEA_(WALLET_DEBIT|SIGNER|SIGNER_HMAC|SUPERVISOR)_", re.I),
    re.compile(r"\bforce\s*=\s*true\b", re.I),
    re.compile(r"\bbypass\b.{0,20}\bpolicy\b", re.I),
)


@dataclass(frozen=True)
class SanitisedText:
    original: str
    preview: str
    wrapped: str
    description_hash: str
    flags: tuple[str, ...]
    prompt_injection: bool


def _strip_controls(text: str) -> str:
    return "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)


def detect_prompt_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def _sanitise(text: str, *, limit: int, wrap_open: str, wrap_close: str) -> SanitisedText:
    original = text if isinstance(text, str) else ""
    cleaned = _strip_controls(original)
    injection = detect_prompt_injection(cleaned)
    truncated = cleaned[:limit]
    wrapped = f"{wrap_open}{truncated}{wrap_close}"
    flags: list[str] = []
    if injection:
        flags.append("prompt_injection")
        flags.append(HOSTILE_CONTENT)
    return SanitisedText(
        original=original,
        preview=truncated,
        wrapped=wrapped,
        description_hash=sha256_hex(original.encode("utf-8")),
        flags=tuple(flags),
        prompt_injection=injection,
    )


def sanitise_marketplace_text(text: str) -> SanitisedText:
    """Return wrapped preview and flags. Does not interpret the text as instructions."""
    return _sanitise(text, limit=PREVIEW_MAX_CHARS, wrap_open=WRAP_OPEN, wrap_close=WRAP_CLOSE)


def sanitise_web_text(text: str, *, max_chars: int = WEB_PREVIEW_MAX_CHARS) -> SanitisedText:
    """Wrap public web content. Retrieved instructions remain data."""
    return _sanitise(text, limit=max_chars, wrap_open=WEB_WRAP_OPEN, wrap_close=WEB_WRAP_CLOSE)
