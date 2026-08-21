"""In-memory Phase A mock wallet. No chain, no keys, no revenue booking."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Lock
from uuid import uuid4

from aea.types import format_amount
from aea.wallet.protocol import (
    CONFLICT,
    IDEMPOTENCY_CONFLICT,
    INSUFFICIENT_FUNDS,
    NETWORK_FAILURE,
    PROHIBITED_TOKEN,
    TX_ID_RE,
    UNSUPPORTED_WALLET_PHASE,
    FaultName,
    WalletError,
    WalletTx,
    fingerprint,
)

_ASSETS = ("USDC", "SOL")


def new_tx_id() -> str:
    return "mocktx_" + uuid4().hex


class MockWallet:
    """Deterministic mock balances and txs. SOL is a fee reserve, not revenue."""

    def __init__(
        self,
        *,
        phase: str = "A",
        opening: dict[str, Decimal] | None = None,
        snapshot_path: Path | None = None,
    ) -> None:
        if phase != "A":
            raise WalletError(UNSUPPORTED_WALLET_PHASE, "Phase A mock wallet only")
        self._phase = phase
        self._lock = Lock()
        self._fault: FaultName = "none"
        self._faults_enabled = False
        self._snapshot_path = snapshot_path
        self._balances: dict[str, Decimal] = {
            "USDC": Decimal("0"),
            "SOL": Decimal("0"),
        }
        if opening:
            for asset, amount in opening.items():
                if asset not in _ASSETS:
                    raise WalletError(PROHIBITED_TOKEN, f"unsupported asset {asset}")
                self._balances[asset] = amount
        self._txs: dict[str, WalletTx] = {}
        self._by_key: dict[str, str] = {}
        self._prints: dict[str, tuple[str, str, str, str, str]] = {}
        if snapshot_path is not None and snapshot_path.is_file():
            self._load_snapshot()

    def enable_faults(self) -> None:
        """Test-only. Production wallets never enable this."""
        with self._lock:
            self._faults_enabled = True

    def set_fault(self, fault: FaultName) -> None:
        if fault not in {
            "none",
            "insufficient_funds",
            "network",
            "timeout",
            "reject",
        }:
            raise WalletError("VALIDATION_ERROR", f"unknown fault {fault}")
        with self._lock:
            if not self._faults_enabled:
                return
            self._fault = fault

    def get_balances(self) -> dict[str, Decimal]:
        with self._lock:
            return {k: v for k, v in self._balances.items()}

    def get_tx(self, tx_id: str) -> WalletTx | None:
        with self._lock:
            return self._txs.get(tx_id)

    def credit(
        self,
        *,
        asset: str,
        amount: Decimal,
        tx_id: str,
        reason: str,
        idempotency_key: str,
    ) -> WalletTx:
        return self._apply(
            direction="credit",
            asset=asset,
            amount=amount,
            tx_id=tx_id,
            reason=reason,
            idempotency_key=idempotency_key,
            destination=None,
        )

    def debit(
        self,
        *,
        asset: str,
        amount: Decimal,
        destination: str,
        tx_id: str,
        reason: str,
        idempotency_key: str,
    ) -> WalletTx:
        if not destination.strip():
            raise WalletError("VALIDATION_ERROR", "destination is required")
        return self._apply(
            direction="debit",
            asset=asset,
            amount=amount,
            tx_id=tx_id,
            reason=reason,
            idempotency_key=idempotency_key,
            destination=destination,
        )

    def _apply(
        self,
        *,
        direction: str,
        asset: str,
        amount: Decimal,
        tx_id: str,
        reason: str,
        idempotency_key: str,
        destination: str | None,
    ) -> WalletTx:
        if asset not in _ASSETS:
            raise WalletError(PROHIBITED_TOKEN, f"unsupported asset {asset}")
        if amount <= 0:
            raise WalletError("VALIDATION_ERROR", "amount must be positive")
        if not TX_ID_RE.fullmatch(tx_id):
            raise WalletError("VALIDATION_ERROR", "invalid tx_id")
        print_key = fingerprint(
            direction=direction,
            asset=asset,
            amount=amount,
            reason=reason,
            destination=destination,
        )
        with self._lock:
            self._raise_fault()
            existing_id = self._by_key.get(idempotency_key)
            if existing_id is not None:
                if self._prints[idempotency_key] != print_key:
                    raise WalletError(
                        IDEMPOTENCY_CONFLICT,
                        "idempotency key reused with a different body",
                    )
                return self._txs[existing_id]
            if tx_id in self._txs:
                raise WalletError(CONFLICT, "duplicate transaction id")
            if direction == "debit":
                if self._balances[asset] < amount:
                    raise WalletError(INSUFFICIENT_FUNDS, "insufficient funds")
                self._balances[asset] -= amount
            else:
                self._balances[asset] += amount
            tx = WalletTx.model_validate(
                {
                    "tx_id": tx_id,
                    "asset": asset,
                    "amount": format_amount(amount),
                    "direction": direction,
                    "reason": reason,
                    "idempotency_key": idempotency_key,
                    "destination": destination,
                    "status": "settled",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            self._txs[tx_id] = tx
            self._by_key[idempotency_key] = tx_id
            self._prints[idempotency_key] = print_key
            self._write_snapshot()
            return tx

    def _raise_fault(self) -> None:
        if self._fault == "none":
            return
        if self._fault == "insufficient_funds":
            raise WalletError(INSUFFICIENT_FUNDS, "fault injected")
        if self._fault in {"network", "timeout"}:
            raise WalletError(NETWORK_FAILURE, f"fault injected: {self._fault}")
        if self._fault == "reject":
            raise WalletError(CONFLICT, "fault injected: reject")

    def _load_snapshot(self) -> None:
        assert self._snapshot_path is not None
        raw = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
        for asset in _ASSETS:
            if asset in raw.get("balances", {}):
                self._balances[asset] = Decimal(str(raw["balances"][asset]))
        for item in raw.get("txs", []):
            tx = WalletTx.model_validate(item)
            self._txs[tx.tx_id] = tx
            self._by_key[tx.idempotency_key] = tx.tx_id
            self._prints[tx.idempotency_key] = fingerprint(
                direction=tx.direction,
                asset=tx.asset,
                amount=tx.amount,
                reason=tx.reason,
                destination=tx.destination,
            )

    def _write_snapshot(self) -> None:
        if self._snapshot_path is None:
            return
        payload = {
            "balances": {k: format_amount(v) for k, v in self._balances.items()},
            "txs": [tx.model_dump(mode="json") for tx in self._txs.values()],
        }
        self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
