"""Canonical encoding helpers used by policy hashing."""

from __future__ import annotations

from aea.hashing import canonical_json_hash, canonical_yaml_hash


def test_canonical_json_is_order_independent() -> None:
    a = canonical_json_hash({"b": "1", "a": "2"})
    b = canonical_json_hash({"a": "2", "b": "1"})
    assert a == b
    assert len(a) == 64


def test_canonical_yaml_hash_stable() -> None:
    h1 = canonical_yaml_hash({"policy_version": "policy/v0.1.0", "wallet_phase": "A"})
    h2 = canonical_yaml_hash({"wallet_phase": "A", "policy_version": "policy/v0.1.0"})
    assert h1 == h2
