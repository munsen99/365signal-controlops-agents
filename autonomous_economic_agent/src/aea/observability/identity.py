"""Owner wallets vs token mints/contracts. Never display a mint as the owner."""

from __future__ import annotations

from aea.wallet.solana import CANONICAL_MAINNET_USDC_MINT, WRAPPED_SOL_MINT

WELL_KNOWN_SOLANA_MINTS = frozenset(
    {
        WRAPPED_SOL_MINT,
        CANONICAL_MAINNET_USDC_MINT,
    }
)


def is_known_solana_mint(value: str | None, *, configured_mint: str | None = None) -> bool:
    if not value:
        return False
    if configured_mint and value == configured_mint:
        return True
    return value in WELL_KNOWN_SOLANA_MINTS


def solana_owner_wallet(
    *,
    public_wallet: str | None,
    token_mint: str | None = None,
) -> str | None:
    """Return the owner address, or None if the value is a mint/token identity."""
    if not public_wallet:
        return None
    if is_known_solana_mint(public_wallet, configured_mint=token_mint):
        return None
    return public_wallet


def evm_owner_wallet(
    *,
    public_wallet: str | None,
    token_contract: str | None = None,
) -> str | None:
    if not public_wallet:
        return None
    if token_contract and public_wallet.lower() == token_contract.lower():
        return None
    return public_wallet
