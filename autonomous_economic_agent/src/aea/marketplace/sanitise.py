"""Wrap untrusted marketplace text. Detect injection. Never execute content.

Preview is truncated and wrapped so naive concatenation cannot override
constitution or policy. Original text is preserved as data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aea.hashing import sha256_hex

PREVIEW_MAX_CHARS = 500
WRAP_OPEN = "[UNTRUSTED_MARKETPLACE_DATA]\n"
WRAP_CLOSE = "\n[/UNTRUSTED_MARKETPLACE_DATA]"

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


def sanitise_marketplace_text(text: str) -> SanitisedText:
    """Return wrapped preview and flags. Does not interpret the text as instructions."""
    original = text if isinstance(text, str) else ""
    cleaned = _strip_controls(original)
    injection = detect_prompt_injection(cleaned)
    truncated = cleaned[:PREVIEW_MAX_CHARS]
    wrapped = f"{WRAP_OPEN}{truncated}{WRAP_CLOSE}"
    flags: list[str] = []
    if injection:
        flags.append("prompt_injection")
    return SanitisedText(
        original=original,
        preview=truncated,
        wrapped=wrapped,
        description_hash=sha256_hex(original.encode("utf-8")),
        flags=tuple(flags),
        prompt_injection=injection,
    )
