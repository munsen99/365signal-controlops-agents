"""Deterministic allow-list serialization and secret/HTML filtering.

Unknown must never become healthy. Marketplace text is untrusted display data.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

from aea.observability.schemas import ObservabilityStatus

RECENT_EVENTS_LIMIT = 20
DISPLAY_TEXT_MAX = 240

_SECRET_KEY_PARTS = (
    "private_key",
    "privatekey",
    "seed_phrase",
    "seedphrase",
    "mnemonic",
    "hmac",
    "password",
    "secret",
    "authorization",
    "bearer",
    "api_key",
    "apikey",
    "api_token",
    "access_token",
    "model_token",
    "control_token",
    "observability_token",
    "supervisor_token",
    "signer_token",
    "debit_token",
    "rpc_url",
    "rpc_credential",
    "signed_tx",
    "raw_tx",
    "raw_signed",
    "webhook_secret",
    "signer_key",
    "keypair",
)

_SECRET_VALUE_RE = re.compile(
    r"(AEA_(MODEL|CONTROL|SIGNER|SUPERVISOR|WALLET_DEBIT|WALLET_CREDIT|SIGNER_HMAC|OBSERVABILITY)_TOKEN"
    r"|AEA_SIGNER_HMAC_KEY"
    r"|BEGIN (EC |RSA |OPENSSH )?PRIVATE KEY"
    r"|Bearer\s+[A-Za-z0-9._\-]{8,})",
    re.I,
)

_TAG_RE = re.compile(r"<[^>]*>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def safe_display_text(value: object, *, max_len: int = DISPLAY_TEXT_MAX) -> str:
    """Strip tags/controls, escape HTML, truncate. Never execute content."""
    text = "" if value is None else str(value)
    text = _CONTROL_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _TAG_RE.sub("", text)
    text = html.escape(text, quote=True)
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def _key_blocked(key: str) -> bool:
    low = str(key).lower().replace("-", "_")
    return any(part in low for part in _SECRET_KEY_PARTS)


def filter_secrets(value: Any, *, secrets: tuple[str, ...] = ()) -> Any:
    """Drop secret-shaped keys and exact secret values. Allow-list is still required."""
    blocked = tuple(s for s in secrets if s)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _key_blocked(str(key)):
                continue
            cleaned = filter_secrets(item, secrets=blocked)
            if isinstance(cleaned, str) and (
                cleaned in blocked or _SECRET_VALUE_RE.search(cleaned)
            ):
                continue
            out[str(key)] = cleaned
        return out
    if isinstance(value, list):
        return [filter_secrets(item, secrets=blocked) for item in value]
    if isinstance(value, str):
        if value in blocked or _SECRET_VALUE_RE.search(value):
            return "[redacted]"
        return value
    return value


def serialize_status(status: ObservabilityStatus, *, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    """Allow-list dump through the DTO, then secret-filter nested strings."""
    dumped = status.model_dump(mode="json")
    dumped = filter_secrets(dumped, secrets=secrets)
    # Re-validate so extra keys cannot sneak through filtering reconstitutions.
    ObservabilityStatus.model_validate(dumped)
    events = dumped.get("recent_events") or []
    if len(events) > RECENT_EVENTS_LIMIT:
        dumped["recent_events"] = events[:RECENT_EVENTS_LIMIT]
    return dumped


def isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()
