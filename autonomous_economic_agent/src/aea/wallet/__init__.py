"""Phase A mock wallet. No Solana, no keys, no signer."""

from aea.wallet.mock import MockWallet
from aea.wallet.protocol import WalletBackend, WalletError, WalletTx

__all__ = ["MockWallet", "WalletBackend", "WalletError", "WalletTx"]
