"""Compose presence, read-only discovery, and intelligence. No financial actions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aea.marketplace.discovery import ReadOnlyDiscoveryClient, probe_public_board
from aea.marketplace.intelligence import (
    ClassifiedOpportunity,
    ConcentrationReport,
    MarketObservation,
    OpportunityClass,
    classify_board,
    concentration,
)
from aea.marketplace.presence import ServiceProfile, default_service_profile
from aea.marketplace.protocol import MarketplaceError


def scan_observations(
    observations_by_market: dict[str, list[MarketObservation]],
    *,
    profile: ServiceProfile | None = None,
) -> dict[str, Any]:
    profile = profile or default_service_profile()
    classified: list[ClassifiedOpportunity] = []
    concentrations: dict[str, ConcentrationReport] = {}
    for market, rows in observations_by_market.items():
        if rows:
            classified.extend(classify_board(rows, profile))
        else:
            classified.extend(
                [
                    item.model_copy(
                        update={
                            "observation": item.observation.model_copy(update={"marketplace": market, "source": "empty_board"})
                        }
                    )
                    for item in classify_board([], profile)
                ]
            )
        concentrations[market] = concentration(rows, marketplace=market)
    counts: dict[str, int] = {}
    for item in classified:
        counts[item.classification.value] = counts.get(item.classification.value, 0) + 1
    eligible = [item for item in classified if item.classification == OpportunityClass.ELIGIBLE]
    return {
        "profile": profile.model_dump(mode="json"),
        "classified": [item.model_dump(mode="json") for item in classified],
        "concentrations": {name: report.model_dump(mode="json") for name, report in concentrations.items()},
        "classification_counts": counts,
        "eligible_count": len(eligible),
        "capital_bearing_actions": [],
        "wallet_authority_expansion": False,
        "pr16_started": False,
    }


def probe_markets(
    markets: tuple[str, ...] = ("the402", "moltjobs", "workpnp", "hober", "bothire"),
    *,
    client: ReadOnlyDiscoveryClient | None = None,
    now: datetime | None = None,
) -> dict[str, list[MarketObservation]]:
    now = now or datetime.now(timezone.utc)
    owns = client is None
    client = client or ReadOnlyDiscoveryClient()
    out: dict[str, list[MarketObservation]] = {}
    try:
        for market in markets:
            try:
                out[market] = probe_public_board(client, market, now=now)
            except MarketplaceError as exc:
                reason = exc.message if exc.message and exc.message != exc.code else "public_probe_failed"
                out[market] = [
                    MarketObservation(
                        marketplace=market,
                        observed_at=now,
                        source=f"discovery_blocked:{exc.code}",
                        ineligibility_reason=str(reason)[:200],
                        vendor_clarification_required=True,
                    )
                ]
    finally:
        if owns:
            client.close()
    return out
