"""Isolated Phase A mock signer. Sole wallet-debit caller.

No Solana, no LLM, no marketplace, no wallet credit authority.
"""

from aea.signer.backend import (
    ApprovedRequest,
    SignRequest,
    SignResult,
    SignerBackend,
    canonical_approved_hash,
    compute_request_hmac,
    verify_request_hmac,
)
from aea.signer.freeze import FreezeInspection, inspect_freeze
from aea.signer.mock import MockSigner

__all__ = [
    "ApprovedRequest",
    "FreezeInspection",
    "MockSigner",
    "SignRequest",
    "SignResult",
    "SignerBackend",
    "canonical_approved_hash",
    "compute_request_hmac",
    "inspect_freeze",
    "verify_request_hmac",
]
