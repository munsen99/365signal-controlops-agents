"""Deterministic economic ledger service. economic_app DML only.

Does not hold wallet debit/credit tokens, signer tokens, or HMAC keys.
Does not mutate supervisor freeze/policy/constitution rows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from aea import AGENT_ID, POLICY_VERSION
from aea.config import LoadedPolicy, load_policy
from aea.hashing import canonical_json_hash
from aea.ledger.errors import LedgerError
from aea.ledger.models import (
    AuditWrite,
    ChainEvidenceCreate,
    CostCreate,
    DecisionCreate,
    JobAccept,
    JobTransition,
    OpportunityCreate,
    PaymentCreate,
    PaymentDecisionWrite,
    PaymentSettle,
    RevenueCreate,
    TransferCreate,
)
from aea.ledger.transitions import (
    APP_TRANSFER_CLASSES,
    OPEN_JOB_STATUSES,
    SEED_TRANSFER_CLASSES,
    ensure_transition,
)
from aea.policy.reasons import HttpCode, ReasonCode
from aea.types import format_amount, format_asset_amount

_SECRET_PARTS = (
    "token",
    "secret",
    "password",
    "hmac",
    "private_key",
    "seed",
    "mnemonic",
    "authorization",
)
_COST_IDEM_PREFIX = "idem:"
_TRANSFER_IDEM_PREFIX = "idem:"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _scrub(v)
            for k, v in value.items()
            if not any(part in str(k).lower() for part in _SECRET_PARTS)
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _dec(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def usdc_equivalent(
    *,
    amount: Decimal,
    asset: str,
    snapshot: Decimal | None,
    ceiling: Decimal,
) -> Decimal:
    """Snapshot SOL→USDC at insert. Never zero-hide. Never revalue later."""
    if asset == "USDC":
        return amount
    if snapshot is None:
        return amount * ceiling
    return amount * snapshot


class LedgerService:
    """Application ledger over schema ``economic`` as role ``economic_app``."""

    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        policy: LoadedPolicy,
        agent_id: str = AGENT_ID,
    ) -> None:
        if conn is None:
            raise ValueError("database connection is required")
        self._conn = conn
        self._conn.row_factory = dict_row
        self._policy = policy
        self._agent_id = agent_id

    @classmethod
    def from_env(cls, *, policy: LoadedPolicy | None = None) -> "LedgerService":
        """Open an economic_app connection. Caller must commit/close."""
        from aea.ledger.db import connect

        return cls(connect(), policy=policy or load_policy())

    def _savepoint(self, fn):  # type: ignore[no-untyped-def]
        name = "aea_" + uuid4().hex
        self._conn.execute(f"SAVEPOINT {name}")
        try:
            result = fn()
            self._conn.execute(f"RELEASE SAVEPOINT {name}")
            return result
        except LedgerError:
            self._conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
            raise
        except ForeignKeyViolation as exc:
            self._conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
            raise LedgerError(HttpCode.NOT_FOUND, "referenced row missing") from exc
        except UniqueViolation as exc:
            self._conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
            raise LedgerError(HttpCode.CONFLICT, "duplicate economic identifier") from exc
        except Exception:
            self._conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
            raise

    def _audit(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        correlation_id: UUID | None = None,
    ) -> None:
        clean = _scrub(payload)
        self._conn.execute(
            """
            INSERT INTO audit_events (agent_id, event_type, correlation_id, payload, payload_hash)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                self._agent_id,
                event_type,
                correlation_id,
                Jsonb(clean),
                canonical_json_hash(clean),
            ),
        )

    def _account(self, asset: str, *, for_update: bool = False) -> dict[str, Any]:
        sql = """
            SELECT account_id, agent_id, asset, opening_balance, current_balance, updated_at
              FROM agent_accounts
             WHERE agent_id = %s AND asset = %s
        """
        if for_update:
            sql += " FOR UPDATE"
        row = self._conn.execute(sql, (self._agent_id, asset)).fetchone()
        if row is None:
            raise LedgerError(HttpCode.NOT_FOUND, f"no {asset} account")
        return row

    def _adjust_balance(self, asset: str, delta: Decimal) -> Decimal:
        row = self._account(asset, for_update=True)
        current = _dec(row["current_balance"])
        nxt = current + delta
        if nxt < 0:
            raise LedgerError(ReasonCode.INSUFFICIENT_FUNDS, "ledger cash would go negative")
        updated = self._conn.execute(
            """
            UPDATE agent_accounts
               SET current_balance = %s, updated_at = now()
             WHERE agent_id = %s AND asset = %s
         RETURNING current_balance
            """,
            (nxt, self._agent_id, asset),
        ).fetchone()
        if updated is None:
            raise LedgerError(HttpCode.INTERNAL_ERROR, "balance update failed")
        return _dec(updated["current_balance"])

    def get_accounts(self) -> dict[str, dict[str, str]]:
        rows = self._conn.execute(
            """
            SELECT asset, opening_balance, current_balance
              FROM agent_accounts
             WHERE agent_id = %s
            """,
            (self._agent_id,),
        ).fetchall()
        return {
            r["asset"]: {
                "opening_balance": format_amount(_dec(r["opening_balance"])),
                "current_balance": format_amount(_dec(r["current_balance"])),
            }
            for r in rows
        }

    def get_financial_state(self) -> dict[str, Any]:
        accounts = self.get_accounts()
        usdc = accounts.get("USDC", {"opening_balance": "0.000000", "current_balance": "0.000000"})
        sol = accounts.get("SOL", {"opening_balance": "0.000000", "current_balance": "0.000000"})
        pnl = self._conn.execute(
            """
            SELECT revenue_usdc, cost_usdc, realised_pnl_usdc
              FROM v_cumulative_realised_pnl
             WHERE agent_id = %s
            """,
            (self._agent_id,),
        ).fetchone()
        car = self._conn.execute("SELECT * FROM v_capital_at_risk").fetchone()
        flags = self.supervisor_flags()
        policy_row = self._conn.execute(
            "SELECT policy_version FROM policy_versions WHERE is_current"
        ).fetchone()
        daily = self.daily_spend_usdc()
        open_jobs = self._conn.execute(
            """
            SELECT count(*) AS n FROM jobs
             WHERE agent_id = %s AND status = ANY(%s)
            """,
            (self._agent_id, list(OPEN_JOB_STATUSES)),
        ).fetchone()
        limits = self._policy.document.limits
        daily_remaining = limits.max_daily_discretionary_usdc - daily
        if daily_remaining < 0:
            daily_remaining = Decimal("0")
        car_usdc = _dec(car["approved_unsettled_outflow"]) if car else Decimal("0")
        car_remaining = limits.max_capital_at_risk_usdc - car_usdc
        if car_remaining < 0:
            car_remaining = Decimal("0")
        return {
            "ok": True,
            "agent_id": self._agent_id,
            "policy_version": policy_row["policy_version"] if policy_row else POLICY_VERSION,
            "wallet_phase": self._policy.document.wallet_phase,
            "frozen": flags["frozen"],
            "signer_enabled": flags["signer_enabled"],
            "loop_enabled": flags["loop_enabled"],
            "balances": {
                "USDC": usdc["current_balance"],
                "SOL": sol["current_balance"],
            },
            "opening_usdc": usdc["opening_balance"],
            "realised_pnl_usdc": format_amount(_dec(pnl["realised_pnl_usdc"])) if pnl else "0.000000",
            "revenue_usdc": format_amount(_dec(pnl["revenue_usdc"])) if pnl else "0.000000",
            "cost_usdc": format_amount(_dec(pnl["cost_usdc"])) if pnl else "0.000000",
            "daily_spend_usdc": format_amount(daily),
            "daily_remaining_usdc": format_amount(daily_remaining),
            "capital_at_risk_usdc": format_amount(car_usdc),
            "capital_at_risk_remaining_usdc": format_amount(car_remaining),
            "max_outbound_usdc": format_amount(limits.max_outbound_usdc),
            "open_jobs": int(open_jobs["n"]) if open_jobs else 0,
            "unit_of_account": "USDC",
        }

    def supervisor_flags(self) -> dict[str, bool]:
        """Fail closed when the singleton row is missing or unreadable."""
        try:
            row = self._conn.execute(
                """
                SELECT frozen, signer_enabled, loop_enabled
                  FROM supervisor_state
                 WHERE singleton
                """
            ).fetchone()
        except Exception:
            return {
                "frozen": True,
                "signer_enabled": False,
                "loop_enabled": False,
                "readable": False,
            }
        if row is None:
            return {
                "frozen": True,
                "signer_enabled": False,
                "loop_enabled": False,
                "readable": False,
            }
        return {
            "frozen": bool(row["frozen"]),
            "signer_enabled": bool(row["signer_enabled"]),
            "loop_enabled": bool(row["loop_enabled"]),
            "readable": True,
        }

    def _require_unfrozen(self) -> None:
        flags = self.supervisor_flags()
        if flags["frozen"] or not flags["readable"]:
            raise LedgerError(HttpCode.AGENT_FROZEN, "economic activity is frozen")

    def outstanding_exposure_usdc(self, *, excluding_request_id: UUID | None = None) -> Decimal:
        """M0 capital-at-risk: approved USDC outflow not yet settled.

        Matches ``v_capital_at_risk.approved_unsettled_outflow``. The model
        cannot supply this figure. ``excluding_request_id`` drops the row
        under evaluation so recovery does not double-count it.
        """
        row = self._conn.execute(
            """
            SELECT COALESCE(SUM(pr.amount), 0) AS exposure
              FROM payment_requests pr
             WHERE pr.asset = 'USDC'
               AND pr.policy_decision = 'approved'
               AND pr.transaction_reference IS NULL
               AND (%s::uuid IS NULL OR pr.request_id <> %s)
            """,
            (excluding_request_id, excluding_request_id),
        ).fetchone()
        if row is None:
            raise LedgerError(HttpCode.INTERNAL_ERROR, "capital at risk unreadable")
        return _dec(row["exposure"])

    def cash_cost_count(self, request_id: UUID) -> int:
        row = self._conn.execute(
            """
            SELECT count(*) AS n FROM economic_costs
             WHERE payment_request_id = %s
            """,
            (request_id,),
        ).fetchone()
        return int(row["n"]) if row else 0

    def daily_spend_usdc(self) -> Decimal:
        row = self._conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS spent
              FROM payment_requests
             WHERE policy_decision = 'approved'
               AND transaction_reference IS NOT NULL
               AND asset = 'USDC'
               AND requested_at >= (date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
            """
        ).fetchone()
        return _dec(row["spent"]) if row else Decimal("0")

    def record_opportunity(self, req: OpportunityCreate) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            existing = self._conn.execute(
                """
                SELECT * FROM opportunities
                 WHERE source = %s AND external_reference = %s
                """,
                (req.source, req.external_reference),
            ).fetchone()
            body = {
                "source": req.source,
                "external_reference": req.external_reference,
                "description_hash": req.description_hash,
                "expected_revenue": format_amount(req.expected_revenue),
                "expected_cost": format_amount(req.expected_cost),
            }
            if existing is not None:
                prev = {
                    "source": existing["source"],
                    "external_reference": existing["external_reference"],
                    "description_hash": existing["description_hash"],
                    "expected_revenue": format_amount(_dec(existing["expected_revenue"])),
                    "expected_cost": format_amount(_dec(existing["expected_cost"])),
                }
                if prev != body:
                    raise LedgerError(HttpCode.IDEMPOTENCY_CONFLICT)
                out = dict(existing)
                out["replay"] = True
                return out
            row = self._conn.execute(
                """
                INSERT INTO opportunities (
                    agent_id, source, external_reference, description_hash, artefact_uri,
                    expected_revenue, expected_cost, expected_margin, expected_revenue_asset,
                    decision, policy_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'discovered', %s)
                RETURNING *
                """,
                (
                    self._agent_id,
                    req.source,
                    req.external_reference,
                    req.description_hash,
                    req.artefact_uri,
                    req.expected_revenue,
                    req.expected_cost,
                    req.expected_revenue - req.expected_cost,
                    req.expected_revenue_asset,
                    req.policy_version,
                ),
            ).fetchone()
            self._audit(
                "opportunity_recorded",
                {"opportunity_id": str(row["opportunity_id"]), **body},
            )
            out = dict(row)
            out["replay"] = False
            return out

        return self._savepoint(inner)

    def set_opportunity_decision(
        self, opportunity_id: UUID, decision: str, *, reason: str | None = None
    ) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            row = self._conn.execute(
                "SELECT * FROM opportunities WHERE opportunity_id = %s FOR UPDATE",
                (opportunity_id,),
            ).fetchone()
            if row is None:
                raise LedgerError(HttpCode.NOT_FOUND, "opportunity not found")
            ensure_transition("opportunity", row["decision"], decision)
            if row["decision"] == decision:
                return dict(row)
            updated = self._conn.execute(
                """
                UPDATE opportunities
                   SET decision = %s, decision_reason = %s
                 WHERE opportunity_id = %s
             RETURNING *
                """,
                (decision, reason, opportunity_id),
            ).fetchone()
            self._audit(
                "opportunity_decision",
                {
                    "opportunity_id": str(opportunity_id),
                    "from": row["decision"],
                    "to": decision,
                },
            )
            return dict(updated)

        return self._savepoint(inner)

    def accept_job(self, req: JobAccept) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            existing = self._conn.execute(
                "SELECT * FROM jobs WHERE opportunity_id = %s",
                (req.opportunity_id,),
            ).fetchone()
            if existing is not None:
                if format_amount(_dec(existing["expected_revenue"])) != format_amount(req.expected_revenue):
                    raise LedgerError(HttpCode.IDEMPOTENCY_CONFLICT)
                out = dict(existing)
                out["replay"] = True
                return out
            self._require_unfrozen()
            opp = self.set_opportunity_decision(req.opportunity_id, "accepted")
            if format_amount(_dec(opp["expected_revenue"])) != format_amount(req.expected_revenue):
                raise LedgerError(HttpCode.CONFLICT, "expected_revenue does not match opportunity")
            row = self._conn.execute(
                """
                INSERT INTO jobs (
                    opportunity_id, agent_id, status, expected_revenue, policy_version
                ) VALUES (%s, %s, 'accepted', %s, %s)
                RETURNING *
                """,
                (
                    req.opportunity_id,
                    self._agent_id,
                    req.expected_revenue,
                    req.policy_version,
                ),
            ).fetchone()
            self._audit(
                "job_accepted",
                {"job_id": str(row["job_id"]), "opportunity_id": str(req.opportunity_id)},
            )
            out = dict(row)
            out["replay"] = False
            return out

        return self._savepoint(inner)

    def get_job(self, job_id: UUID) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,)).fetchone()
        if row is None:
            raise LedgerError(HttpCode.NOT_FOUND, "job not found")
        return dict(row)

    def get_opportunity(self, opportunity_id: UUID) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM opportunities WHERE opportunity_id = %s",
            (opportunity_id,),
        ).fetchone()
        if row is None:
            raise LedgerError(HttpCode.NOT_FOUND, "opportunity not found")
        return dict(row)

    def get_job_bundle(self, job_id: UUID) -> dict[str, Any]:
        row = self._conn.execute(
            """
            SELECT j.*, o.external_reference, o.expected_revenue AS opp_revenue,
                   o.expected_cost AS opp_cost, o.source, o.description_hash
              FROM jobs j
              JOIN opportunities o ON o.opportunity_id = j.opportunity_id
             WHERE j.job_id = %s
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            raise LedgerError(HttpCode.NOT_FOUND, "job not found")
        return dict(row)

    def count_open_jobs(self) -> int:
        row = self._conn.execute(
            """
            SELECT count(*) AS n FROM jobs
             WHERE agent_id = %s AND status = ANY(%s)
            """,
            (self._agent_id, list(OPEN_JOB_STATUSES)),
        ).fetchone()
        return int(row["n"]) if row else 0

    def get_payment_by_idempotency(self, key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM payment_requests WHERE idempotency_key = %s",
            (key,),
        ).fetchone()
        return dict(row) if row else None

    def history_payment_rate(self, *, source: str, limit: int = 50) -> float | None:
        rows = self._conn.execute(
            """
            SELECT j.status,
                   EXISTS (
                       SELECT 1 FROM revenues r
                        WHERE r.job_id = j.job_id AND r.verified
                   ) AS paid
              FROM jobs j
              JOIN opportunities o ON o.opportunity_id = j.opportunity_id
             WHERE o.source = %s
               AND j.status IN ('completed', 'failed')
             ORDER BY j.accepted_at DESC NULLS LAST
             LIMIT %s
            """,
            (source, limit),
        ).fetchall()
        if len(rows) < 4:
            return None
        completed = sum(1 for r in rows if r["status"] == "completed" and r["paid"])
        denom = max(1, len(rows))
        return completed / denom

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def transition_job(self, req: JobTransition) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE job_id = %s FOR UPDATE",
                (req.job_id,),
            ).fetchone()
            if row is None:
                raise LedgerError(HttpCode.NOT_FOUND, "job not found")
            ensure_transition("job", row["status"], req.status)
            if row["status"] == req.status:
                if req.deliverable_hash and row["deliverable_hash"] not in (None, req.deliverable_hash):
                    raise LedgerError(HttpCode.IDEMPOTENCY_CONFLICT)
                out = dict(row)
                out["replay"] = True
                return out
            self._require_unfrozen()
            submitted_at = row["submitted_at"]
            completed_at = row["completed_at"]
            if req.status == "submitted":
                submitted_at = _now()
            if req.status == "completed":
                completed_at = _now()
            deliverable = req.deliverable_hash or row["deliverable_hash"]
            updated = self._conn.execute(
                """
                UPDATE jobs
                   SET status = %s,
                       submitted_at = %s,
                       completed_at = %s,
                       deliverable_hash = %s
                 WHERE job_id = %s
             RETURNING *
                """,
                (req.status, submitted_at, completed_at, deliverable, req.job_id),
            ).fetchone()
            self._audit(
                "job_transition",
                {"job_id": str(req.job_id), "from": row["status"], "to": req.status},
            )
            out = dict(updated)
            out["replay"] = False
            return out

        return self._savepoint(inner)

    def record_cost(self, req: CostCreate) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            marker = _COST_IDEM_PREFIX + req.idempotency_key
            existing = self._conn.execute(
                "SELECT * FROM economic_costs WHERE evidence_reference = %s",
                (marker,),
            ).fetchone()
            print_key = {
                "job_id": str(req.job_id) if req.job_id else None,
                "category": req.category,
                "amount": format_amount(req.amount),
                "asset": req.asset,
                "payment_request_id": str(req.payment_request_id) if req.payment_request_id else None,
            }
            if existing is not None:
                prev = {
                    "job_id": str(existing["job_id"]) if existing["job_id"] else None,
                    "category": existing["category"],
                    "amount": format_amount(_dec(existing["amount"])),
                    "asset": existing["asset"],
                    "payment_request_id": (
                        str(existing["payment_request_id"]) if existing["payment_request_id"] else None
                    ),
                }
                if prev != print_key:
                    raise LedgerError(HttpCode.IDEMPOTENCY_CONFLICT)
                out = dict(existing)
                out["replay"] = True
                return out
            self._require_unfrozen()
            cash = req.payment_request_id is not None
            if cash:
                pay = self._conn.execute(
                    "SELECT * FROM payment_requests WHERE request_id = %s FOR UPDATE",
                    (req.payment_request_id,),
                ).fetchone()
                if pay is None:
                    raise LedgerError(HttpCode.NOT_FOUND, "payment request not found")
                if pay["policy_decision"] != "approved" or pay["transaction_reference"] is None:
                    raise LedgerError(HttpCode.CONFLICT, "cash cost requires settled payment request")
            if req.asset == "ETH":
                if self._policy.document.evm is None:
                    raise LedgerError(HttpCode.VALIDATION_ERROR, "ETH cost requires EVM policy rate evidence")
                snapshot = self._policy.document.evm.native_fee_usdc_snapshot
                ceiling = snapshot
            else:
                snapshot = self._policy.document.assets.sol_usdc_snapshot
                ceiling = self._policy.document.assets.sol_usdc_unknown_ceiling
            equiv = usdc_equivalent(
                amount=req.amount, asset=req.asset, snapshot=snapshot, ceiling=ceiling
            )
            row = self._conn.execute(
                """
                INSERT INTO economic_costs (
                    job_id, category, amount, asset, usdc_equivalent,
                    evidence_reference, correlation_id, payment_request_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    req.job_id,
                    req.category,
                    req.amount,
                    req.asset,
                    equiv,
                    marker,
                    req.correlation_id,
                    req.payment_request_id,
                ),
            ).fetchone()
            if cash:
                self._adjust_balance(req.asset, -req.amount)
            self._audit(
                "cost_recorded",
                {
                    "cost_id": str(row["cost_id"]),
                    "cash": cash,
                    **print_key,
                    "usdc_equivalent": format_amount(equiv),
                    "caller_evidence": req.evidence_reference,
                },
                correlation_id=req.correlation_id,
            )
            out = dict(row)
            out["replay"] = False
            return out

        return self._savepoint(inner)

    def record_chain_evidence(self, req: ChainEvidenceCreate) -> dict[str, Any]:
        """Persist verified chain-specific fields exactly once; never interprets a hash as settlement."""
        def inner() -> dict[str, Any]:
            existing = self._conn.execute(
                "SELECT * FROM chain_transaction_evidence WHERE payment_request_id = %s",
                (req.payment_request_id,),
            ).fetchone()
            fingerprint = req.model_dump(mode="python")
            if existing is not None:
                prior = {key: existing[key] for key in fingerprint}
                for key in ("chain_id", "block_number", "gas_used", "effective_gas_price_wei", "fee_wei"):
                    prior[key] = int(prior[key])
                prior["fee_usdc_snapshot"] = format_amount(_dec(prior["fee_usdc_snapshot"]))
                if prior != fingerprint:
                    raise LedgerError(HttpCode.IDEMPOTENCY_CONFLICT)
                return {**dict(existing), "replay": True}
            row = self._conn.execute(
                """INSERT INTO chain_transaction_evidence
                   (payment_request_id, rail, network, chain_id, transaction_hash, block_number,
                    token_contract, gas_used, effective_gas_price_wei, fee_wei,
                    fee_usdc_snapshot, fee_rate_source, fee_rate_observed_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (req.payment_request_id, req.rail, req.network, req.chain_id, req.transaction_hash.lower(),
                 req.block_number, req.token_contract, req.gas_used,
                 req.effective_gas_price_wei, req.fee_wei, req.fee_usdc_snapshot,
                 req.fee_rate_source, req.fee_rate_observed_at),
            ).fetchone()
            return {**dict(row), "replay": False}
        return self._savepoint(inner)

    def record_verified_revenue(self, req: RevenueCreate) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            if not req.verified:
                raise LedgerError(HttpCode.FAKE_PAYMENT, "unverified payment is not revenue")
            if req.asset != "USDC":
                raise LedgerError(ReasonCode.PROHIBITED_TOKEN, "revenue must be USDC")
            if not req.transaction_reference.strip():
                raise LedgerError(HttpCode.FAKE_PAYMENT, "settlement evidence required")
            existing = self._conn.execute(
                "SELECT * FROM revenues WHERE transaction_reference = %s",
                (req.transaction_reference,),
            ).fetchone()
            print_key = {
                "job_id": str(req.job_id),
                "amount": format_amount(req.amount),
                "asset": req.asset,
                "transaction_reference": req.transaction_reference,
            }
            if existing is not None:
                prev = {
                    "job_id": str(existing["job_id"]),
                    "amount": format_amount(_dec(existing["amount"])),
                    "asset": existing["asset"],
                    "transaction_reference": existing["transaction_reference"],
                }
                if prev != print_key:
                    raise LedgerError(HttpCode.CONFLICT, "transaction_reference already booked")
                out = dict(existing)
                out["replay"] = True
                return out
            self._require_unfrozen()
            job = self._conn.execute(
                "SELECT * FROM jobs WHERE job_id = %s FOR UPDATE",
                (req.job_id,),
            ).fetchone()
            if job is None:
                raise LedgerError(HttpCode.NOT_FOUND, "job not found")
            if job["status"] not in {"submitted", "completed"}:
                raise LedgerError(HttpCode.CONFLICT, "revenue requires a submitted job")
            row = self._conn.execute(
                """
                INSERT INTO revenues (
                    job_id, amount, asset, payer_reference, transaction_reference, verified
                ) VALUES (%s, %s, %s, %s, %s, true)
                RETURNING *
                """,
                (
                    req.job_id,
                    req.amount,
                    req.asset,
                    req.payer_reference,
                    req.transaction_reference,
                ),
            ).fetchone()
            new_realised = _dec(job["realised_revenue"]) + req.amount
            completed_at = job["completed_at"] or _now()
            self._conn.execute(
                """
                UPDATE jobs
                   SET realised_revenue = %s,
                       status = 'completed',
                       completed_at = %s
                 WHERE job_id = %s
                """,
                (new_realised, completed_at, req.job_id),
            )
            self._adjust_balance("USDC", req.amount)
            self._audit(
                "revenue_verified",
                {"revenue_id": str(row["revenue_id"]), **print_key},
            )
            out = dict(row)
            out["replay"] = False
            return out

        return self._savepoint(inner)

    def record_transfer(self, req: TransferCreate) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            if req.classification in SEED_TRANSFER_CLASSES:
                raise LedgerError(HttpCode.FORBIDDEN, "opening-capital history is operator-owned")
            if req.classification not in APP_TRANSFER_CLASSES:
                raise LedgerError(HttpCode.VALIDATION_ERROR, "unsupported transfer classification")
            if req.classification in {"operator_top_up", "refund", "not_revenue"} and req.direction != "in":
                raise LedgerError(HttpCode.VALIDATION_ERROR, "inbound classification requires direction in")
            if req.classification == "operator_withdrawal" and req.direction != "out":
                raise LedgerError(HttpCode.VALIDATION_ERROR, "withdrawal requires direction out")
            marker = req.transaction_reference or (_TRANSFER_IDEM_PREFIX + req.idempotency_key)
            existing = self._conn.execute(
                "SELECT * FROM transfers WHERE transaction_reference = %s",
                (marker,),
            ).fetchone()
            print_key = {
                "asset": req.asset,
                "amount": format_amount(req.amount),
                "direction": req.direction,
                "classification": req.classification,
            }
            if existing is not None:
                prev = {
                    "asset": existing["asset"],
                    "amount": format_amount(_dec(existing["amount"])),
                    "direction": existing["direction"],
                    "classification": existing["classification"],
                }
                if prev != print_key:
                    raise LedgerError(HttpCode.IDEMPOTENCY_CONFLICT)
                out = dict(existing)
                out["replay"] = True
                return out
            account = self._account(req.asset, for_update=True)
            row = self._conn.execute(
                """
                INSERT INTO transfers (
                    account_id, direction, amount, asset, classification, transaction_reference
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    account["account_id"],
                    req.direction,
                    req.amount,
                    req.asset,
                    req.classification,
                    marker,
                ),
            ).fetchone()
            delta = req.amount if req.direction == "in" else -req.amount
            self._adjust_balance(req.asset, delta)
            self._audit("transfer_recorded", {"transfer_id": str(row["transfer_id"]), **print_key})
            out = dict(row)
            out["replay"] = False
            return out

        return self._savepoint(inner)

    def create_payment_request(self, req: PaymentCreate) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            existing = self._conn.execute(
                "SELECT * FROM payment_requests WHERE idempotency_key = %s",
                (req.idempotency_key,),
            ).fetchone()
            print_key = {
                "job_id": str(req.job_id),
                "amount": format_amount(req.amount),
                "asset": req.asset,
                "destination": req.destination,
                "purpose": req.purpose,
            }
            if existing is not None:
                prev = {
                    "job_id": str(existing["job_id"]) if existing["job_id"] else None,
                    "amount": format_amount(_dec(existing["amount"])),
                    "asset": existing["asset"],
                    "destination": existing["destination"],
                    "purpose": existing["purpose"],
                }
                if prev != print_key:
                    raise LedgerError(HttpCode.IDEMPOTENCY_CONFLICT)
                out = dict(existing)
                out["replay"] = True
                return out
            self._require_unfrozen()
            dup = self._conn.execute(
                """
                SELECT request_id FROM payment_requests
                 WHERE job_id = %s AND asset = %s AND destination = %s AND amount = %s
                   AND policy_decision IN ('pending', 'approved')
                   AND requested_at >= now() - (%s * interval '1 second')
                   AND idempotency_key <> %s
                 LIMIT 1
                """,
                (
                    req.job_id,
                    req.asset,
                    req.destination,
                    req.amount,
                    req.idempotency_ttl_seconds,
                    req.idempotency_key,
                ),
            ).fetchone()
            if dup is not None:
                raise LedgerError(HttpCode.DUPLICATE_PAYMENT)
            job = self._conn.execute(
                "SELECT job_id FROM jobs WHERE job_id = %s", (req.job_id,)
            ).fetchone()
            if job is None:
                raise LedgerError(HttpCode.NOT_FOUND, "job not found")
            row = self._conn.execute(
                """
                INSERT INTO payment_requests (
                    job_id, amount, asset, destination, purpose, policy_decision,
                    policy_version, idempotency_key, correlation_id
                ) VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s)
                RETURNING *
                """,
                (
                    req.job_id,
                    req.amount,
                    req.asset,
                    req.destination,
                    req.purpose,
                    req.policy_version,
                    req.idempotency_key,
                    req.correlation_id,
                ),
            ).fetchone()
            self._audit(
                "payment_request_created",
                {"request_id": str(row["request_id"]), **print_key},
                correlation_id=req.correlation_id,
            )
            out = dict(row)
            out["replay"] = False
            return out

        return self._savepoint(inner)

    def decide_payment_request(self, req: PaymentDecisionWrite) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            row = self._conn.execute(
                "SELECT * FROM payment_requests WHERE request_id = %s FOR UPDATE",
                (req.request_id,),
            ).fetchone()
            if row is None:
                raise LedgerError(HttpCode.NOT_FOUND, "payment request not found")
            ensure_transition("payment", row["policy_decision"], req.decision)
            if row["policy_decision"] == req.decision:
                out = dict(row)
                out["replay"] = True
                return out
            approved_amount = req.approved_amount if req.decision == "approved" else None
            if req.decision == "approved":
                if approved_amount is None:
                    approved_amount = _dec(row["amount"])
                if format_amount(approved_amount) != format_amount(_dec(row["amount"])):
                    raise LedgerError(ReasonCode.AMOUNT_MISMATCH)
            updated = self._conn.execute(
                """
                UPDATE payment_requests
                   SET policy_decision = %s,
                       reason_code = %s,
                       rejection_reason = %s,
                       approved_amount = %s,
                       approved_at = CASE WHEN %s = 'approved' THEN now() ELSE approved_at END,
                       canonical_hash = COALESCE(%s, canonical_hash)
                 WHERE request_id = %s
             RETURNING *
                """,
                (
                    req.decision,
                    req.reason_code,
                    req.rejection_reason,
                    approved_amount,
                    req.decision,
                    req.canonical_hash,
                    req.request_id,
                ),
            ).fetchone()
            self._audit(
                "payment_request_decided",
                {
                    "request_id": str(req.request_id),
                    "decision": req.decision,
                    "reason_code": req.reason_code,
                },
            )
            out = dict(updated)
            out["replay"] = False
            return out

        return self._savepoint(inner)

    def settle_payment_request(self, req: PaymentSettle) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            row = self._conn.execute(
                "SELECT * FROM payment_requests WHERE request_id = %s FOR UPDATE",
                (req.request_id,),
            ).fetchone()
            if row is None:
                raise LedgerError(HttpCode.NOT_FOUND, "payment request not found")
            if row["policy_decision"] != "approved":
                raise LedgerError(HttpCode.CONFLICT, "only approved requests can settle")
            if row["transaction_reference"] is not None:
                if row["transaction_reference"] != req.transaction_reference:
                    raise LedgerError(HttpCode.CONFLICT, "settled payment cannot change reference")
                out = dict(row)
                out["replay"] = True
                return out
            updated = self._conn.execute(
                """
                UPDATE payment_requests
                   SET transaction_reference = %s
                 WHERE request_id = %s
             RETURNING *
                """,
                (req.transaction_reference, req.request_id),
            ).fetchone()
            self._audit(
                "payment_request_settled",
                {
                    "request_id": str(req.request_id),
                    "transaction_reference": req.transaction_reference,
                },
            )
            out = dict(updated)
            out["replay"] = False
            return out

        return self._savepoint(inner)

    def record_decision(self, req: DecisionCreate) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            existing = self._conn.execute(
                "SELECT * FROM decisions WHERE idempotency_key = %s",
                (req.idempotency_key,),
            ).fetchone()
            print_key = {
                "decision_type": req.decision_type,
                "decision": req.decision,
                "reasoning_summary": req.reasoning_summary,
                "job_id": str(req.job_id) if req.job_id else None,
                "opportunity_id": str(req.opportunity_id) if req.opportunity_id else None,
            }
            if existing is not None:
                prev = {
                    "decision_type": existing["decision_type"],
                    "decision": existing["decision"],
                    "reasoning_summary": existing["reasoning_summary"],
                    "job_id": str(existing["job_id"]) if existing["job_id"] else None,
                    "opportunity_id": (
                        str(existing["opportunity_id"]) if existing["opportunity_id"] else None
                    ),
                }
                if prev != print_key:
                    raise LedgerError(HttpCode.IDEMPOTENCY_CONFLICT)
                out = dict(existing)
                out["replay"] = True
                return out
            row = self._conn.execute(
                """
                INSERT INTO decisions (
                    job_id, opportunity_id, decision_type, input_summary, input_hash,
                    reasoning_summary, decision, expected_value, confidence,
                    policy_version, constitution_version, idempotency_key
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    req.job_id,
                    req.opportunity_id,
                    req.decision_type,
                    req.input_summary,
                    req.input_hash,
                    req.reasoning_summary,
                    req.decision,
                    req.expected_value,
                    req.confidence,
                    req.policy_version,
                    req.constitution_version,
                    req.idempotency_key,
                ),
            ).fetchone()
            self._audit("decision_recorded", {"decision_id": str(row["decision_id"]), **print_key})
            out = dict(row)
            out["replay"] = False
            return out

        return self._savepoint(inner)

    def write_audit(self, req: AuditWrite) -> dict[str, Any]:
        def inner() -> dict[str, Any]:
            self._audit(req.event_type, req.payload, correlation_id=req.correlation_id)
            row = self._conn.execute(
                """
                SELECT * FROM audit_events
                 WHERE agent_id = %s
                 ORDER BY created_at DESC
                 LIMIT 1
                """,
                (self._agent_id,),
            ).fetchone()
            return dict(row)

        return self._savepoint(inner)

    def realised_pnl_by_job(self, job_id: UUID) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM v_realised_pnl_by_job WHERE job_id = %s",
            (job_id,),
        ).fetchone()
        if row is None:
            raise LedgerError(HttpCode.NOT_FOUND, "job not found")
        return {
            "job_id": row["job_id"],
            "status": row["status"],
            "realised_revenue_usdc": format_amount(_dec(row["realised_revenue_usdc"])),
            "realised_cost_usdc": format_amount(_dec(row["realised_cost_usdc"])),
            "realised_pnl_usdc": format_amount(_dec(row["realised_pnl_usdc"])),
        }

    def ledger_reconciliation(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT agent_id, asset, opening_balance, ledger_balance,
                   reconstructed_balance, delta
              FROM v_balance_reconciliation
             WHERE agent_id = %s
             ORDER BY asset
            """,
            (self._agent_id,),
        ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "agent_id": r["agent_id"],
                    "asset": r["asset"],
                    "opening_balance": format_amount(_dec(r["opening_balance"])),
                    "ledger_balance": format_amount(_dec(r["ledger_balance"])),
                    "reconstructed_balance": format_amount(_dec(r["reconstructed_balance"])),
                    "delta": format_amount(_dec(r["delta"])),
                }
            )
        return out

    def reconcile_with_wallet(self, wallet_balances: dict[str, Decimal]) -> dict[str, Any]:
        """Compare wallet to ledger. Never writes a 'fix'."""
        rows = self.ledger_reconciliation()
        mismatches: list[dict[str, str]] = []
        for row in rows:
            asset = row["asset"]
            ledger = _dec(row["ledger_balance"])
            reconstructed = _dec(row["reconstructed_balance"])
            wallet = wallet_balances.get(asset)
            if wallet is None:
                mismatches.append(
                    {"asset": asset, "reason": "wallet_missing", "ledger": row["ledger_balance"]}
                )
                continue
            if format_asset_amount(wallet, asset) != format_asset_amount(ledger, asset):
                mismatches.append(
                    {
                        "asset": asset,
                        "reason": "wallet_ledger_mismatch",
                        "wallet": format_asset_amount(wallet, asset),
                        "ledger": format_asset_amount(ledger, asset),
                    }
                )
            if _dec(row["delta"]) != Decimal("0"):
                mismatches.append(
                    {
                        "asset": asset,
                        "reason": "ledger_internal_delta",
                        "delta": row["delta"],
                        "reconstructed": format_amount(reconstructed),
                        "ledger": format_amount(ledger),
                    }
                )
        ok = not mismatches
        return {
            "ok": ok,
            "code": HttpCode.OK if ok else HttpCode.WALLET_LEDGER_MISMATCH,
            "rows": rows,
            "mismatches": mismatches,
        }

    def get_payment_request(self, request_id: UUID) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM payment_requests WHERE request_id = %s",
            (request_id,),
        ).fetchone()
        if row is None:
            raise LedgerError(HttpCode.NOT_FOUND)
        return dict(row)
