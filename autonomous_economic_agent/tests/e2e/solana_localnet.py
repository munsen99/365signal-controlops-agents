"""Genuine PR13 local-validator acceptance harness.

Operator/test infrastructure only. The harness holds policy/control authority,
never key material, and reaches the signer exclusively over its Unix socket.
Database setup is transaction-scoped and rolled back after evidence capture.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from solders.pubkey import Pubkey
from spl.token.instructions import get_associated_token_address

from aea.config import load_policy
from aea.control.schemas import RequestPaymentRequest
from aea.ledger.service import LedgerService
from aea.payment.service import PaymentOrchestrator, policy_execute_via_asgi
from aea.payment.schemas import ExecutePaymentRequest
from aea.policy.service import create_app as create_policy_app
from aea.policy.signer_client import PolicySignerClient
from aea.types import format_amount
from aea.wallet.solana import SolanaConfig, SolanaWallet


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required localnet setting: {name}")
    return value


def read_secret(path_name: str) -> str:
    return Path(required(path_name)).read_text(encoding="utf-8").rstrip("\n")


def run_async(awaitable):
    return asyncio.run(awaitable)


def wallet_balances(wallet: SolanaWallet, config: SolanaConfig) -> dict[str, Decimal]:
    return run_async(wallet.balances(config))


def rpc(method: str, params: list[Any]) -> Any:
    response = httpx.post(required("AEA_SOLANA_RPC_URL"), json={
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }, timeout=20)
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise RuntimeError(f"localnet RPC {method} failed")
    return body["result"]


def parsed_transfer(signature: str) -> dict[str, Any]:
    result = rpc("getTransaction", [signature, {
        "encoding": "jsonParsed", "commitment": required("AEA_SOLANA_COMMITMENT"),
        "maxSupportedTransactionVersion": 0,
    }])
    if not result:
        raise RuntimeError("confirmed transaction lookup returned no result")
    instructions = result["transaction"]["message"]["instructions"]
    matches = [item["parsed"] for item in instructions
               if isinstance(item, dict) and item.get("program") == "spl-token"
               and isinstance(item.get("parsed"), dict)
               and item["parsed"].get("type") == "transferChecked"]
    if len(matches) != 1:
        raise RuntimeError("transaction must contain exactly one transferChecked instruction")
    status = rpc("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])["value"][0]
    return {"slot": result["slot"], "fee_lamports": result["meta"]["fee"],
            "error": result["meta"]["err"], "confirmation_status": status["confirmationStatus"],
            "instruction": matches[0]}


def token_balance(account: str, commitment: str) -> Decimal:
    value = rpc("getTokenAccountBalance", [account, {"commitment": commitment}])["value"]
    return Decimal(value["amount"]) / (Decimal(10) ** int(value["decimals"]))


def configure_database(conn: psycopg.Connection, *, policy, balances: dict[str, Decimal], job_id: UUID) -> None:
    conn.execute("TRUNCATE economic.audit_events, economic.decisions, economic.revenues, economic.economic_costs, economic.payment_requests, economic.jobs, economic.opportunities CASCADE")
    conn.execute("UPDATE economic.policy_versions SET is_current = false")
    conn.execute("""
        INSERT INTO economic.policy_versions
            (policy_version, policy_document, policy_hash, effective_from, created_by, is_current)
        VALUES (%s, %s, %s, now(), 'operator-pr13-localnet', true)
        ON CONFLICT (policy_version) DO UPDATE SET
            policy_document=excluded.policy_document, policy_hash=excluded.policy_hash,
            effective_from=excluded.effective_from, created_by=excluded.created_by, is_current=true
    """, (policy.document.policy_version, Jsonb(policy.raw), policy.policy_hash))
    for asset in ("USDC", "SOL"):
        conn.execute("""
            INSERT INTO economic.agent_accounts (agent_id, asset, opening_balance, current_balance)
            VALUES ('economic-agent', %s, %s, %s)
            ON CONFLICT (agent_id, asset) DO UPDATE SET
                opening_balance=excluded.opening_balance, current_balance=excluded.current_balance,
                updated_at=now()
        """, (asset, balances[asset], balances[asset]))
    conn.execute("UPDATE economic.supervisor_state SET frozen=false, signer_enabled=true, loop_enabled=true, updated_at=now(), updated_by='operator-pr13-localnet' WHERE singleton")
    opportunity_id = uuid4()
    conn.execute("""
        INSERT INTO economic.opportunities
            (opportunity_id, agent_id, source, external_reference, description_hash,
             expected_revenue, expected_cost, expected_margin, expected_revenue_asset,
             decision, policy_version)
        VALUES (%s, 'economic-agent', 'solana-localnet', %s, %s,
                1, 0, 1, 'USDC', 'accepted', %s)
    """, (opportunity_id, f"pr13-{opportunity_id}", "a" * 64, policy.document.policy_version))
    conn.execute("""
        INSERT INTO economic.jobs
            (job_id, opportunity_id, agent_id, status, expected_revenue, policy_version)
        VALUES (%s, %s, 'economic-agent', 'accepted', 1, %s)
    """, (job_id, opportunity_id, policy.document.policy_version))


def policy_body_for_pending(ledger: LedgerService, policy, req: RequestPaymentRequest,
                            pending: dict[str, Any], balances: dict[str, Decimal]) -> dict[str, Any]:
    dest = policy.classify(req.destination)
    return ExecutePaymentRequest.model_validate({
        "amount": format_amount(req.amount), "asset": req.asset,
        "destination": req.destination, "destination_class": dest.class_,
        "destination_allowed": dest.allowed, "job_id": str(req.job_id),
        "purpose": req.purpose, "daily_spend_usdc": format_amount(ledger.daily_spend_usdc()),
        "outstanding_exposure_usdc": format_amount(
            ledger.outstanding_exposure_usdc(excluding_request_id=pending["request_id"])),
        "wallet_balances": {key: format_amount(value) for key, value in balances.items()},
        "policy_version": policy.document.policy_version, "policy_hash": policy.policy_hash,
        "frozen": False, "signer_enabled": True, "wallet_phase": "B",
        "correlation_id": str(pending["correlation_id"]), "request_id": str(pending["request_id"]),
        "approved_at": pending["requested_at"].isoformat(), "expected_return_usdc": "1.000000",
    }).model_dump(mode="json")


def main() -> None:
    policy = load_policy(policy_path=Path(required("AEA_POLICY_FILE")),
                         destinations_path=Path(required("AEA_DESTINATIONS_FILE")))
    mint = Pubkey.from_string(required("AEA_SOLANA_TOKEN_MINT"))
    destination_owner = Pubkey.from_string(required("AEA_SOLANA_DESTINATION_OWNER"))
    destination_account = str(get_associated_token_address(destination_owner, mint))
    config = SolanaConfig.model_validate({
        "wallet_phase": "B", "network": "localnet", "rpc_url": required("AEA_SOLANA_RPC_URL"),
        "public_wallet": required("AEA_SOLANA_PUBLIC_WALLET"), "token_mint": str(mint),
        "token_decimals": 6, "source_token_account": required("AEA_SOLANA_SOURCE_TOKEN_ACCOUNT"),
        "commitment": required("AEA_SOLANA_COMMITMENT"), "confirmation_timeout_seconds": 30,
    })
    wallet = SolanaWallet()
    run_async(wallet.validate(config))
    before = wallet_balances(wallet, config)
    destination_before = token_balance(destination_account, config.commitment)
    control_token = "operator-pr13-local-control"
    signer_client = PolicySignerClient(hmac_key=read_secret("AEA_SIGNER_HMAC_KEY_FILE"),
        signer_token=read_secret("AEA_SIGNER_TOKEN_FILE"), signer_sock=required("AEA_SIGNER_SOCK"))
    phase_b_context = {
        "network": "localnet", "payer": config.public_wallet, "source_mint": config.token_mint,
        "source_token_account": config.source_token_account,
        "destination_owner": str(destination_owner), "destination_token_account": destination_account,
        "decimals": "6",
    }
    policy_app = create_policy_app(control_token=control_token, loaded=policy,
        freeze_path=Path(required("AEA_FREEZE_PATH")), signer_client=signer_client,
        phase_b_context=phase_b_context)
    policy_execute = policy_execute_via_asgi(policy_app, control_token)

    admin_password = Path(required("AEA_POSTGRES_ADMIN_PASSWORD_FILE")).read_text(encoding="utf-8").rstrip("\n")
    conn = psycopg.connect(host="127.0.0.1", port=5432, dbname="controlops",
                           user="controlops_admin", password=admin_password)
    conn.row_factory = dict_row
    job_id = uuid4()
    try:
        configure_database(conn, policy=policy, balances=before, job_id=job_id)
        conn.execute("SET LOCAL ROLE economic_app")
        conn.execute("SET LOCAL search_path TO economic")
        ledger = LedgerService(conn, policy=policy)
        orchestrator = PaymentOrchestrator(ledger=ledger, policy=policy,
            policy_execute=policy_execute, wallet_balances=lambda: wallet_balances(wallet, config),
            control_token=control_token)

        primary = RequestPaymentRequest.model_validate({"amount": "0.125000", "asset": "USDC",
            "destination": required("AEA_SOLANA_DESTINATION_ID"), "purpose": "pr13_localnet_acceptance",
            "job_id": str(job_id), "idempotency_key": "pr13-local-primary",
            "expected_return": {"amount": "1.000000", "asset": "USDC"}})
        primary_result = orchestrator.request(primary, correlation_id=uuid4(), frozen=False,
                                               signer_enabled=True, loop_enabled=True)
        if not primary_result.get("ok"):
            raise RuntimeError(f"primary payment failed: {primary_result.get('code')}")
        primary_signature = str(primary_result["transaction_reference"])
        primary_chain = parsed_transfer(primary_signature)
        after_primary = wallet_balances(wallet, config)
        destination_after_primary = token_balance(destination_account, config.commitment)
        replay_result = orchestrator.request(primary, correlation_id=uuid4(), frozen=False,
                                              signer_enabled=True, loop_enabled=True)

        uncertain = RequestPaymentRequest.model_validate({"amount": "0.062500", "asset": "USDC",
            "destination": required("AEA_SOLANA_DESTINATION_ID"), "purpose": "pr13_response_loss_recovery",
            "job_id": str(job_id), "idempotency_key": "pr13-local-uncertain",
            "expected_return": {"amount": "1.000000", "asset": "USDC"}})
        correlation_id = uuid4()
        pending = ledger.create_payment_request(__import__("aea.ledger.models", fromlist=["PaymentCreate"]).PaymentCreate.model_validate({
            "job_id": str(job_id), "amount": format_amount(uncertain.amount), "asset": "USDC",
            "destination": uncertain.destination, "purpose": uncertain.purpose,
            "policy_version": policy.document.policy_version, "correlation_id": str(correlation_id),
            "idempotency_key": uncertain.idempotency_key,
            "idempotency_ttl_seconds": policy.document.idempotency_ttl_seconds,
        }))
        lost_response = policy_execute(policy_body_for_pending(
            ledger, policy, uncertain, pending, wallet_balances(wallet, config)))
        if not lost_response.get("ok"):
            raise RuntimeError("response-loss submission did not reach signer")
        uncertain_signature = str(lost_response["tx_id"])
        # Deliberately discard the successful result before ledger settlement.
        del lost_response
        recovered = orchestrator.request(uncertain, correlation_id=correlation_id, frozen=False,
                                         signer_enabled=True, loop_enabled=True)
        if not recovered.get("ok") or recovered.get("transaction_reference") != uncertain_signature:
            raise RuntimeError("uncertain outcome recovery failed")
        uncertain_chain = parsed_transfer(uncertain_signature)
        final_balances = wallet_balances(wallet, config)
        destination_final = token_balance(destination_account, config.commitment)
        reconciliation = ledger.reconcile_with_wallet(final_balances)
        if not reconciliation["ok"]:
            raise RuntimeError("localnet wallet/ledger reconciliation failed")

        def assert_instruction(chain: dict[str, Any], amount_base_units: str) -> None:
            info = chain["instruction"]["info"]
            if chain["error"] is not None or info["source"] != config.source_token_account:
                raise RuntimeError("source/error mismatch in chain evidence")
            if info["destination"] != destination_account or info["mint"] != config.token_mint:
                raise RuntimeError("destination/mint mismatch in chain evidence")
            token = info["tokenAmount"]
            if token["amount"] != amount_base_units or token["decimals"] != 6:
                raise RuntimeError("amount/decimals mismatch in chain evidence")
        assert_instruction(primary_chain, "125000")
        assert_instruction(uncertain_chain, "62500")
        if before["USDC"] - final_balances["USDC"] != Decimal("0.187500"):
            raise RuntimeError("token delta is not exactly the two approved transfers")
        if destination_final - destination_before != Decimal("0.187500"):
            raise RuntimeError("destination delta is not exactly the two approved transfers")
        if before["SOL"] - final_balances["SOL"] != Decimal("0.00001000"):
            raise RuntimeError("fee reserve delta does not equal two observed fees")

        rows = conn.execute("SELECT cost_id, category, amount, asset, usdc_equivalent, payment_request_id FROM economic.economic_costs ORDER BY cost_id").fetchall()
        payments = conn.execute("SELECT request_id, amount, transaction_reference, canonical_hash FROM economic.payment_requests ORDER BY requested_at").fetchall()
        evidence = {
            "run_id": required("AEA_SOLANA_RUN_ID"), "result": "PASS", "network": "localnet",
            "validator_version": rpc("getVersion", [])["solana-core"],
            "genesis_hash": rpc("getGenesisHash", []), "rpc_endpoint": config.sanitized_rpc_endpoint(),
            "public_wallet": config.public_wallet, "test_token_mint": config.token_mint,
            "test_value_not_real_usdc": True, "source_token_account": config.source_token_account,
            "destination_owner": str(destination_owner), "destination_token_account": destination_account,
            "policy_version": policy.document.policy_version, "policy_hash": policy.policy_hash,
            "authority_chain": ["Policy", "HMAC approval", "isolated Unix-socket signer",
                "SPL transfer_checked", "local Solana validator"],
            "canonical_context_bound_fields": sorted([*phase_b_context, "amount_base_units"]),
            "confirmation": config.commitment,
            "primary": {"amount": "0.125000", "base_units": 125000,
                "policy_decision": primary_result.get("policy_decision"),
                "signature": primary_signature, "chain": primary_chain,
                "replay_code": replay_result.get("code"), "replay_signature": replay_result.get("transaction_reference")},
            "uncertain_response_loss": {"amount": "0.062500", "base_units": 62500,
                "policy_decision": recovered.get("policy_decision"),
                "signature": uncertain_signature, "chain": uncertain_chain,
                "recovered_signature": recovered.get("transaction_reference"),
                "one_signature": recovered.get("transaction_reference") == uncertain_signature},
            "balances": {"before": {k: str(v) for k, v in before.items()},
                "after_primary": {k: str(v) for k, v in after_primary.items()},
                "final": {k: str(v) for k, v in final_balances.items()},
                "destination_before_token": str(destination_before),
                "destination_after_primary_token": str(destination_after_primary),
                "destination_final_token": str(destination_final)},
            "fees": {"primary_lamports": primary_chain["fee_lamports"],
                "uncertain_lamports": uncertain_chain["fee_lamports"],
                "total_sol": "0.00001000", "sol_usdc_snapshot": "150.000000"},
            "ledger": {"payments": [{k: str(v) if v is not None else None for k, v in row.items()} for row in payments],
                "costs": [{k: str(v) if v is not None else None for k, v in row.items()} for row in rows]},
            "reconciliation": reconciliation,
            "security": {"signer_socket_only": True, "harness_loaded_private_key": False,
                "wallet_read_can_sign": False, "mainnet": False, "arbitrary_signing": False},
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        output = Path(required("AEA_SOLANA_EVIDENCE_FILE"))
        output.parent.mkdir(parents=True, exist_ok=False)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        print(json.dumps({"result": "PASS", "signature": primary_signature,
                          "uncertain_signature": uncertain_signature,
                          "reconciliation": reconciliation["code"]}))
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    main()
