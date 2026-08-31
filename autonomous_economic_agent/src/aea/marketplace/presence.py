"""Bounded AEA service advertisement. Not a wallet grant and not a bid."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_serializer, field_validator, model_validator

from aea.types import AeaBaseModel, format_amount, parse_unsigned_amount

ALLOWED_CAPABILITIES = frozenset(
    {
        "text_summarization",
        "classification",
        "structured_extraction",
        "public_data_transformation",
        "supplied_material_research",
        "text_only_transform",
        "text_code_review",
    }
)
ALLOWED_OUTPUTS = frozenset({"text", "json", "markdown"})
ALLOWED_ASSETS = frozenset({"USDC"})
ALLOWED_CHAINS = frozenset({"base", "solana"})


class SettlementRail(AeaBaseModel):
    asset: Literal["USDC"]
    chain: Literal["base", "solana"]


class ServiceProfile(AeaBaseModel):
    """Structured presence record. Security flags are pinned closed."""

    agent: Literal["econo"] = "econo"
    capabilities: list[str] = Field(min_length=1, max_length=16)
    outputs: list[str] = Field(min_length=1, max_length=8)
    settlement: list[SettlementRail] = Field(min_length=1, max_length=4)
    minimum_net_reward_usd: Decimal
    maximum_capital_at_risk_usd: Decimal
    public_hosting_supported: Literal[False] = False
    external_accounts_required: Literal[False] = False
    human_operator_required: Literal[True] = True
    requires_policy_approval: Literal[True] = True
    custody_delegation: Literal[False] = False
    arbitrary_signing: Literal[False] = False
    restrictions: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("minimum_net_reward_usd", "maximum_capital_at_risk_usd", mode="before")
    @classmethod
    def _money(cls, value: object) -> Decimal:
        return parse_unsigned_amount(value)

    @field_serializer("minimum_net_reward_usd", "maximum_capital_at_risk_usd")
    def _dump_money(self, value: Decimal) -> str:
        return format_amount(value)

    @field_validator("capabilities")
    @classmethod
    def _caps(cls, value: list[str]) -> list[str]:
        unknown = [item for item in value if item not in ALLOWED_CAPABILITIES]
        if unknown:
            raise ValueError("capability is outside the AEA envelope")
        return list(dict.fromkeys(value))

    @field_validator("outputs")
    @classmethod
    def _outs(cls, value: list[str]) -> list[str]:
        unknown = [item for item in value if item not in ALLOWED_OUTPUTS]
        if unknown:
            raise ValueError("output type is outside the AEA envelope")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _bounds(self) -> "ServiceProfile":
        if self.minimum_net_reward_usd <= 0:
            raise ValueError("minimum_net_reward_usd must be positive")
        if self.maximum_capital_at_risk_usd < self.minimum_net_reward_usd:
            raise ValueError("maximum_capital_at_risk_usd below minimum reward")
        if self.custody_delegation or self.arbitrary_signing:
            raise ValueError("advertisement cannot claim wallet authority")
        if self.public_hosting_supported or not self.requires_policy_approval:
            raise ValueError("advertisement cannot bypass policy or hosting limits")
        return self


DEFAULT_RESTRICTIONS: tuple[str, ...] = (
    "no_custody_delegation",
    "no_private_key_sharing",
    "no_arbitrary_wallet_authority",
    "no_public_hosting",
    "no_authenticated_third_party_accounts",
    "jobs_subject_to_policy_evaluation",
)


def default_service_profile() -> ServiceProfile:
    return ServiceProfile(
        capabilities=[
            "text_summarization",
            "classification",
            "structured_extraction",
            "public_data_transformation",
            "supplied_material_research",
            "text_only_transform",
            "text_code_review",
        ],
        outputs=["text", "json", "markdown"],
        settlement=[
            SettlementRail(asset="USDC", chain="base"),
            SettlementRail(asset="USDC", chain="solana"),
        ],
        minimum_net_reward_usd="2.000000",
        maximum_capital_at_risk_usd="20.000000",
        restrictions=list(DEFAULT_RESTRICTIONS),
    )
