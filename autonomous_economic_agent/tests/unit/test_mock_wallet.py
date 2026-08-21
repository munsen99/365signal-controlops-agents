"""Phase A MockWallet unit tests. No HTTP, no chain."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aea.wallet.mock import MockWallet, new_tx_id
from aea.wallet.protocol import WalletError


def _wallet() -> MockWallet:
    return MockWallet(
        phase="A",
        opening={"USDC": Decimal("20"), "SOL": Decimal("0.05")},
    )


def test_phase_b_rejected() -> None:
    with pytest.raises(WalletError) as exc:
        MockWallet(phase="B")
    assert exc.value.code == "UNSUPPORTED_WALLET_PHASE"


def test_opening_balances() -> None:
    wallet = _wallet()
    balances = wallet.get_balances()
    assert balances["USDC"] == Decimal("20")
    assert balances["SOL"] == Decimal("0.05")


def test_credit_and_debit_usdc() -> None:
    wallet = _wallet()
    credit = wallet.credit(
        asset="USDC",
        amount=Decimal("0.500000"),
        tx_id=new_tx_id(),
        reason="marketplace_settlement",
        idempotency_key="mkt-settle:job-1",
    )
    assert credit.tx_id.startswith("mocktx_")
    assert len(credit.tx_id) == len("mocktx_") + 32
    assert wallet.get_balances()["USDC"] == Decimal("20.5")
    debit = wallet.debit(
        asset="USDC",
        amount=Decimal("0.050000"),
        destination="mock:counterparty:mkt-escrow",
        tx_id=new_tx_id(),
        reason="marketplace_acceptance_fee",
        idempotency_key="pay:job-1:fee",
    )
    assert debit.direction == "debit"
    assert wallet.get_balances()["USDC"] == Decimal("20.45")


def test_sol_credit_is_not_usdc_and_not_revenue() -> None:
    wallet = _wallet()
    usdc_before = wallet.get_balances()["USDC"]
    wallet.credit(
        asset="SOL",
        amount=Decimal("0.010000"),
        tx_id=new_tx_id(),
        reason="fee_reserve",
        idempotency_key="seed:sol-topup",
    )
    assert wallet.get_balances()["USDC"] == usdc_before
    assert wallet.get_balances()["SOL"] == Decimal("0.06")
    assert not hasattr(wallet, "revenues")


def test_idempotent_credit_does_not_double() -> None:
    wallet = _wallet()
    tx_id = new_tx_id()
    first = wallet.credit(
        asset="USDC",
        amount=Decimal("1"),
        tx_id=tx_id,
        reason="opening_capital",
        idempotency_key="seed:usdc",
    )
    second = wallet.credit(
        asset="USDC",
        amount=Decimal("1"),
        tx_id=tx_id,
        reason="opening_capital",
        idempotency_key="seed:usdc",
    )
    assert first.tx_id == second.tx_id
    assert wallet.get_balances()["USDC"] == Decimal("21")


def test_idempotency_conflict_different_body() -> None:
    wallet = _wallet()
    wallet.credit(
        asset="USDC",
        amount=Decimal("1"),
        tx_id=new_tx_id(),
        reason="opening_capital",
        idempotency_key="seed:usdc",
    )
    with pytest.raises(WalletError) as exc:
        wallet.credit(
            asset="USDC",
            amount=Decimal("2"),
            tx_id=new_tx_id(),
            reason="opening_capital",
            idempotency_key="seed:usdc",
        )
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    assert wallet.get_balances()["USDC"] == Decimal("21")


def test_duplicate_tx_id() -> None:
    wallet = _wallet()
    tx_id = new_tx_id()
    wallet.credit(
        asset="USDC",
        amount=Decimal("1"),
        tx_id=tx_id,
        reason="opening_capital",
        idempotency_key="seed:usdc-1",
    )
    with pytest.raises(WalletError) as exc:
        wallet.credit(
            asset="USDC",
            amount=Decimal("1"),
            tx_id=tx_id,
            reason="opening_capital",
            idempotency_key="seed:usdc-2",
        )
    assert exc.value.code == "CONFLICT"


def test_insufficient_funds_no_partial_debit() -> None:
    wallet = _wallet()
    before = wallet.get_balances()["USDC"]
    with pytest.raises(WalletError) as exc:
        wallet.debit(
            asset="USDC",
            amount=Decimal("21"),
            destination="mock:counterparty:mkt-escrow",
            tx_id=new_tx_id(),
            reason="fee",
            idempotency_key="pay:too-big",
        )
    assert exc.value.code == "INSUFFICIENT_FUNDS"
    assert wallet.get_balances()["USDC"] == before
    assert wallet.get_tx("does-not-exist") is None


def test_invalid_asset() -> None:
    wallet = _wallet()
    with pytest.raises(WalletError) as exc:
        wallet.credit(
            asset="BONK",
            amount=Decimal("1"),
            tx_id=new_tx_id(),
            reason="x",
            idempotency_key="bad-asset-01",
        )
    assert exc.value.code == "PROHIBITED_TOKEN"


def test_set_fault_has_no_effect_until_enabled() -> None:
    wallet = _wallet()
    wallet.set_fault("insufficient_funds")
    tx = wallet.debit(
        asset="USDC",
        amount=Decimal("0.01"),
        destination="mock:fee_payer",
        tx_id=new_tx_id(),
        reason="fee",
        idempotency_key="fault-disabled-01",
    )
    assert tx.status == "settled"
    assert wallet.get_balances()["USDC"] == Decimal("19.99")


def test_fault_insufficient_funds_even_when_funded() -> None:
    wallet = _wallet()
    wallet.enable_faults()
    wallet.set_fault("insufficient_funds")
    with pytest.raises(WalletError) as exc:
        wallet.debit(
            asset="USDC",
            amount=Decimal("0.01"),
            destination="mock:fee_payer",
            tx_id=new_tx_id(),
            reason="fee",
            idempotency_key="fault-debit-01",
        )
    assert exc.value.code == "INSUFFICIENT_FUNDS"
    assert wallet.get_balances()["USDC"] == Decimal("20")


def test_no_solana_import() -> None:
    import aea.wallet.mock as mock
    import aea.wallet.protocol as protocol

    assert "solana" not in mock.__dict__
    assert "solders" not in protocol.__dict__
