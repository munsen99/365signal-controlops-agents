"""Canonical JSON/YAML encoding and SHA-256 helpers.

Canonical JSON: UTF-8, sorted keys, no whitespace, Decimal amounts as
fixed-point strings. Used for tool bodies and signer request hashes.
Canonical YAML: UTF-8, LF, mappings emitted with sorted keys. Used for
policy document hashes (M0 §5.1).
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

import yaml


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "hex") and callable(value.hex) and not isinstance(value, (bytes, bytearray)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"not JSON canonicalisable: {type(value)!r}")


def canonical_json_bytes(obj: Any) -> bytes:
    """UTF-8 JSON, keys sorted, no whitespace."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_hash(obj: Any) -> str:
    return sha256_hex(canonical_json_bytes(obj))


def _sort_yaml(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sort_yaml(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_sort_yaml(item) for item in value]
    return value


def canonical_yaml_bytes(obj: Any) -> bytes:
    """UTF-8 YAML with LF newlines and sorted mapping keys."""
    dumped = yaml.safe_dump(
        _sort_yaml(obj),
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
        width=10_000,
    )
    return dumped.replace("\r\n", "\n").encode("utf-8")


def canonical_yaml_hash(obj: Any) -> str:
    return sha256_hex(canonical_yaml_bytes(obj))
