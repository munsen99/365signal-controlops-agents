"""Gated live marketplace adapters.

Default runtime remains mock-only. Importing this package does not enable
a live adapter. `the402` loads only when explicitly listed in
`AEA_ENABLED_ADAPTERS` and `AEA_THE402_ENABLED` is set.
"""

from __future__ import annotations

__all__ = ["THE402_ADAPTER_NAME"]

THE402_ADAPTER_NAME = "the402"
