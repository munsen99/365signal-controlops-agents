"""Load only enabled marketplace adapters. M1: mock."""

from __future__ import annotations

import os

from aea.marketplace.mock import MockMarketplace
from aea.marketplace.protocol import MarketplaceAdapter, MarketplaceError
from aea.policy.reasons import HttpCode

M1_ADAPTERS = frozenset({"mock"})


def enabled_adapter_names() -> tuple[str, ...]:
    raw = os.environ.get("AEA_ENABLED_ADAPTERS", "mock")
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not names:
        names = ("mock",)
    disallowed = [n for n in names if n not in M1_ADAPTERS]
    if disallowed:
        raise MarketplaceError(
            HttpCode.VALIDATION_ERROR,
            "live adapters are not enabled in M1",
        )
    return names


def get_adapter(name: str = "mock", **kwargs: object) -> MarketplaceAdapter:
    if name not in enabled_adapter_names():
        raise MarketplaceError(HttpCode.NOT_FOUND, f"adapter {name} is not enabled")
    if name != "mock":
        raise MarketplaceError(HttpCode.NOT_FOUND, "only mock is implemented")
    return MockMarketplace(**kwargs)
