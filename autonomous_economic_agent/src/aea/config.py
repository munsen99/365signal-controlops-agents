"""Load policy and destination classification from the filesystem.

Never load policy from model/tool input. Paths come from operator env
or the package ``config/`` directory shipped in this repository.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ConfigDict, Field, field_validator

from aea.hashing import canonical_yaml_hash
from aea.types import AeaBaseModel, WalletPhase, format_amount, parse_unsigned_amount

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = _PACKAGE_ROOT / "config"
DEFAULT_POLICY_PATH = DEFAULT_CONFIG_DIR / "policy.v1.yaml"
DEFAULT_DESTINATIONS_PATH = DEFAULT_CONFIG_DIR / "destinations.yaml"


class StartingTreasury(AeaBaseModel):
    USDC: Decimal
    SOL: Decimal

    @field_validator("USDC", "SOL", mode="before")
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)


class PolicyLimits(AeaBaseModel):
    max_outbound_usdc: Decimal
    max_daily_discretionary_usdc: Decimal
    max_capital_at_risk_usdc: Decimal
    max_job_compute_usdc: Decimal
    max_open_jobs: int = Field(ge=1)
    required_margin_bps: int = Field(ge=0)
    min_payment_probability: float = Field(ge=0, le=1)
    max_job_seconds: int = Field(ge=1)

    @field_validator(
        "max_outbound_usdc",
        "max_daily_discretionary_usdc",
        "max_capital_at_risk_usdc",
        "max_job_compute_usdc",
        mode="before",
    )
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)


class PolicyAssets(AeaBaseModel):
    permitted_treasury: list[Literal["USDC"]]
    fee_asset: Literal["SOL"]
    sol_spend_requires_job: bool
    sol_max_fee_per_tx: Decimal
    sol_usdc_snapshot: Decimal
    sol_usdc_unknown_ceiling: Decimal

    @field_validator(
        "sol_max_fee_per_tx",
        "sol_usdc_snapshot",
        "sol_usdc_unknown_ceiling",
        mode="before",
    )
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)


class CostRates(AeaBaseModel):
    compute_usd_per_1k_tokens_in: Decimal
    compute_usd_per_1k_tokens_out: Decimal
    compute_usd_per_wall_second: Decimal
    compute_floor_usdc: Decimal

    @field_validator(
        "compute_usd_per_1k_tokens_in",
        "compute_usd_per_1k_tokens_out",
        "compute_usd_per_wall_second",
        "compute_floor_usdc",
        mode="before",
    )
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)


class ProhibitedFlags(AeaBaseModel):
    borrow: bool
    leverage: bool
    lend: bool
    speculate: bool
    arbitrary_swaps: bool
    unknown_contracts: bool
    wallet_transfer_without_job: bool
    agent_policy_mutation: bool


class DestinationFileRef(AeaBaseModel):
    allow_unclassified: bool
    file: str


class EmergencyFlags(AeaBaseModel):
    freeze_independent_of_agent: bool
    fail_closed_on_missing_freeze_file: bool
    fail_closed_on_unreadable_freeze_dir: bool


class PolicyDocument(AeaBaseModel):
    policy_version: str
    unit_of_account: Literal["USDC"]
    daily_spend_timezone: Literal["UTC"]
    starting_treasury: StartingTreasury
    limits: PolicyLimits
    assets: PolicyAssets
    cost_rates: CostRates
    prohibited: ProhibitedFlags
    destinations: DestinationFileRef
    idempotency_ttl_seconds: int = Field(ge=1)
    payment_settle_timeout_seconds: int = Field(ge=1)
    wallet_phase: WalletPhase
    emergency: EmergencyFlags


class DestinationEntry(AeaBaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str
    class_: Literal["network_fee", "marketplace_escrow", "unknown"] = Field(alias="class")
    allowed: bool
    max_usdc: Decimal | None = None

    @field_validator("max_usdc", mode="before")
    @classmethod
    def _optional_money(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_unsigned_amount(value)


class DestinationsDocument(AeaBaseModel):
    classifications: list[DestinationEntry]


class LoadedPolicy:
    """Filesystem-backed policy plus destination table and document hash."""

    def __init__(
        self,
        *,
        document: PolicyDocument,
        destinations: DestinationsDocument,
        policy_hash: str,
        policy_path: Path,
        destinations_path: Path,
        raw: dict[str, Any],
    ) -> None:
        self.document = document
        self.destinations = destinations
        self.policy_hash = policy_hash
        self.policy_path = policy_path
        self.destinations_path = destinations_path
        self.raw = raw

    def classify(self, destination: str) -> DestinationEntry:
        for entry in self.destinations.classifications:
            if entry.id == destination:
                return entry
        unknown = next(
            (e for e in self.destinations.classifications if e.id == "unknown"),
            None,
        )
        if unknown is not None:
            return unknown
        return DestinationEntry.model_validate(
            {"id": "unknown", "class": "unknown", "allowed": False}
        )


def _read_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {path}")
    text = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return loaded


def resolve_policy_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    env = os.environ.get("AEA_POLICY_FILE")
    if env:
        return Path(env)
    return DEFAULT_POLICY_PATH


def resolve_destinations_path(path: Path | None = None, *, relative_to: Path | None = None) -> Path:
    if path is not None:
        return path
    env = os.environ.get("AEA_DESTINATIONS_FILE")
    if env:
        return Path(env)
    if relative_to is not None:
        return relative_to
    return DEFAULT_DESTINATIONS_PATH


def load_policy(
    *,
    policy_path: Path | None = None,
    destinations_path: Path | None = None,
) -> LoadedPolicy:
    """Load and validate operator policy from disk. Not from model input."""
    resolved_policy = resolve_policy_path(policy_path)
    raw = _read_mapping(resolved_policy)
    document = PolicyDocument.model_validate(raw)
    dest_name = document.destinations.file
    resolved_dest = resolve_destinations_path(
        destinations_path,
        relative_to=resolved_policy.parent / dest_name,
    )
    dest_raw = _read_mapping(resolved_dest)
    destinations = DestinationsDocument.model_validate(dest_raw)
    if document.destinations.allow_unclassified:
        raise ValueError("allow_unclassified must be false")
    if document.wallet_phase == "C":
        raise ValueError("wallet_phase A/B only; wallet_phase C is reserved for PR14")
    policy_hash = canonical_yaml_hash(raw)
    return LoadedPolicy(
        document=document,
        destinations=destinations,
        policy_hash=policy_hash,
        policy_path=resolved_policy,
        destinations_path=resolved_dest,
        raw=raw,
    )


def money_fields_as_strings(document: PolicyDocument) -> dict[str, str]:
    """Helper for tests: selected limits as 6-decimal strings."""
    limits = document.limits
    return {
        "max_outbound_usdc": format_amount(limits.max_outbound_usdc),
        "max_daily_discretionary_usdc": format_amount(limits.max_daily_discretionary_usdc),
        "sol_usdc_snapshot": format_amount(document.assets.sol_usdc_snapshot),
    }
