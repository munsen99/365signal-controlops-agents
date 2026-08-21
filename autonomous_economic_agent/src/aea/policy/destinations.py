"""Destination classification rules. Unclassified and unknown are deny.

Per-destination max_usdc is an amount cap, not a classification deny.
It is enforced in limits.check_outbound (M0 §10.4 step 7) so a $1.000001
payment is MAX_OUTBOUND_EXCEEDED, not PROHIBITED_DESTINATION. Enforcement
is min(policy.max_outbound_usdc, dest.max_usdc) — never weaker than either cap.
"""

from __future__ import annotations

from aea.config import DestinationEntry, PolicyDocument
from aea.policy.reasons import ReasonCode
from aea.types import PolicyInput


def check_destination(
    inp: PolicyInput,
    policy: PolicyDocument,
    *,
    destination: DestinationEntry | None = None,
) -> str | None:
    if policy.destinations.allow_unclassified:
        return ReasonCode.PROHIBITED_DESTINATION
    if not inp.destination_allowed:
        return ReasonCode.PROHIBITED_DESTINATION
    if inp.destination_class == "unknown":
        return ReasonCode.PROHIBITED_DESTINATION
    if not inp.destination.strip():
        return ReasonCode.PROHIBITED_DESTINATION
    if destination is not None:
        if destination.id != inp.destination and destination.id != "unknown":
            return ReasonCode.PROHIBITED_DESTINATION
        if not destination.allowed or destination.class_ == "unknown":
            return ReasonCode.PROHIBITED_DESTINATION
        if inp.destination_class != destination.class_:
            return ReasonCode.PROHIBITED_DESTINATION
    return None


def classify_fail_closed(entry: DestinationEntry | None) -> tuple[str, bool]:
    """Return (class, allowed) for an unknown lookup."""
    if entry is None:
        return ("unknown", False)
    if not entry.allowed:
        return (entry.class_, False)
    return (entry.class_, True)
