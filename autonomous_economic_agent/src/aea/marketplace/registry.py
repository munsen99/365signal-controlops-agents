"""Load only enabled marketplace adapters. Default: mock."""

from __future__ import annotations

import os

from aea.marketplace.mock import MockMarketplace
from aea.marketplace.protocol import MarketplaceAdapter, MarketplaceError
from aea.policy.reasons import HttpCode

M1_ADAPTERS = frozenset({"mock"})
GATED_LIVE_ADAPTERS = frozenset({"the402"})
KNOWN_ADAPTERS = M1_ADAPTERS | GATED_LIVE_ADAPTERS


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def the402_is_enabled() -> bool:
    return _flag("AEA_THE402_ENABLED")


def enabled_adapter_names() -> tuple[str, ...]:
    raw = os.environ.get("AEA_ENABLED_ADAPTERS", "mock")
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not names:
        names = ("mock",)
    unknown = [n for n in names if n not in KNOWN_ADAPTERS]
    if unknown:
        raise MarketplaceError(
            HttpCode.VALIDATION_ERROR,
            "live adapters are not enabled in M1",
        )
    gated = [n for n in names if n in GATED_LIVE_ADAPTERS]
    if gated and not the402_is_enabled():
        raise MarketplaceError(
            HttpCode.VALIDATION_ERROR,
            "the402 adapter is disabled by default",
        )
    return names


def get_adapter(name: str = "mock", **kwargs: object) -> MarketplaceAdapter:
    if name not in enabled_adapter_names():
        raise MarketplaceError(HttpCode.NOT_FOUND, f"adapter {name} is not enabled")
    if name == "mock":
        return MockMarketplace(**kwargs)
    if name == "the402":
        from aea.marketplace.live.the402 import The402Adapter

        return The402Adapter.from_env(**kwargs)
    raise MarketplaceError(HttpCode.NOT_FOUND, "only mock is implemented")
