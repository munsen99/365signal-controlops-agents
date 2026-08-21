"""Pure supervisor monitors. Never unfreeze. Fail closed on unreadable input."""

from __future__ import annotations

from decimal import Decimal

from aea.supervisor.monitors import MonitorSnapshot, evaluate_monitors


def _healthy(**overrides) -> MonitorSnapshot:
    body = {
        "usdc": Decimal("20"),
        "token_balances": {"USDC": Decimal("20"), "SOL": Decimal("0.05")},
        "daily_spend_usdc": Decimal("0"),
        "daily_cap_usdc": Decimal("3"),
        "capital_at_risk_usdc": Decimal("0"),
        "max_capital_at_risk_usdc": Decimal("5"),
        "failed_txs_10m": 0,
        "policy_rejections_10m": 0,
        "policy_tamper": False,
        "unusual_destination": False,
        "ledger_wallet_mismatch": False,
        "compute_usdc_10m": Decimal("0.001"),
        "max_job_compute_usdc": Decimal("0.5"),
        "job_failures": 0,
        "job_total": 1,
        "control_healthy": True,
        "fake_payment_count": 0,
    }
    body.update(overrides)
    return MonitorSnapshot(**body)


def test_healthy_snapshot_does_not_freeze() -> None:
    decision = evaluate_monitors(_healthy())
    assert decision.freeze_spend is False
    assert decision.disable_signer is False
    assert decision.stop_loop is False
    assert decision.incidents == ()


def test_single_compute_mark_does_not_false_freeze() -> None:
    decision = evaluate_monitors(_healthy(compute_usdc_10m=Decimal("0.001")))
    assert decision.freeze_spend is False


def test_unreadable_balances_fail_closed() -> None:
    decision = evaluate_monitors(_healthy(usdc=None, token_balances=None))
    assert decision.freeze_spend is True


def test_unexpected_token_freezes() -> None:
    decision = evaluate_monitors(
        _healthy(token_balances={"USDC": Decimal("20"), "BONK": Decimal("1")})
    )
    assert decision.freeze_spend is True


def test_daily_spend_warn_then_cap_freeze() -> None:
    warn = evaluate_monitors(_healthy(daily_spend_usdc=Decimal("2.8")))
    assert warn.freeze_spend is False
    assert any(i.kind == "DAILY_SPEND_WARN" for i in warn.incidents)
    cap = evaluate_monitors(_healthy(daily_spend_usdc=Decimal("3")))
    assert cap.freeze_spend is True


def test_capital_at_risk_and_mismatch_freeze() -> None:
    car = evaluate_monitors(_healthy(capital_at_risk_usdc=Decimal("5.1")))
    assert car.freeze_spend is True
    mismatch = evaluate_monitors(_healthy(ledger_wallet_mismatch=True))
    assert mismatch.freeze_spend is True
    assert any(i.kind == "WALLET_LEDGER_MISMATCH" for i in mismatch.incidents)


def test_failed_txs_disable_signer() -> None:
    decision = evaluate_monitors(_healthy(failed_txs_10m=3))
    assert decision.disable_signer is True


def test_policy_tamper_freezes() -> None:
    decision = evaluate_monitors(
        _healthy(policy_rejections_10m=5, policy_tamper=True)
    )
    assert decision.freeze_spend is True


def test_control_unhealthy_stops_loop_does_not_unfreeze() -> None:
    decision = evaluate_monitors(_healthy(control_healthy=False))
    assert decision.stop_loop is True
    assert decision.freeze_spend is False


def test_repeated_fake_payment_freezes() -> None:
    decision = evaluate_monitors(_healthy(fake_payment_count=2))
    assert decision.freeze_spend is True


def test_compute_velocity_freezes() -> None:
    decision = evaluate_monitors(_healthy(compute_usdc_10m=Decimal("1.1")))
    assert decision.freeze_spend is True


def test_never_sets_unfreeze() -> None:
    decision = evaluate_monitors(MonitorSnapshot())
    assert not hasattr(decision, "unfreeze")
    assert decision.freeze_spend is True
