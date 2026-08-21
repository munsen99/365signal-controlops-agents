"""Independent supervisor ASGI on 127.0.0.1:18703.

POST /v1/admin/* accepts AEA_SUPERVISOR_TOKEN only. The model, Hermes
plugin, control facade, wallet, marketplace, and signer HMAC/bearer
cannot mutate supervisor state. GET /health is the unauthenticated
read-only status surface (M0 auth matrix).

Holds no wallet debit/credit token and no AEA_SIGNER_HMAC_KEY.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from hmac import compare_digest
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError

from aea.hashing import canonical_json_hash
from aea.policy.reasons import HttpCode
from aea.signer.freeze import inspect_freeze
from aea.supervisor.freeze_file import (
    FreezeFileError,
    remove_freeze_file,
    write_freeze_file,
)
from aea.supervisor.monitors import (
    POLL_INTERVAL_SECONDS,
    MonitorDecision,
    MonitorSnapshot,
    evaluate_monitors,
)
from aea.supervisor.schemas import (
    EnableSignerRequest,
    IncidentCreateRequest,
    PermitLoopRequest,
    RELAXING_CONFIRM,
    SupervisorMutationRequest,
    UnfreezeRequest,
)
from aea.supervisor.state import (
    IdempotencyRecord,
    MemorySupervisorStore,
    SupervisorState,
    SupervisorStore,
)

SUPERVISOR_HOST = "127.0.0.1"
SUPERVISOR_PORT = 18703

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

ADMIN_ROUTES = {
    "/v1/admin/freeze-spend": "freeze-spend",
    "/v1/admin/unfreeze": "unfreeze",
    "/v1/admin/disable-signer": "disable-signer",
    "/v1/admin/enable-signer": "enable-signer",
    "/v1/admin/stop-agent": "stop-agent",
    "/v1/admin/permit-loop": "permit-loop",
    "/v1/admin/incidents": "incidents",
}

_RESTRICTIVE = frozenset({"freeze-spend", "disable-signer", "stop-agent"})
_RELAXING = frozenset({"unfreeze", "enable-signer", "permit-loop"})
_REQUEST_MODELS = {
    "unfreeze": UnfreezeRequest,
    "enable-signer": EnableSignerRequest,
    "permit-loop": PermitLoopRequest,
    "incidents": IncidentCreateRequest,
}
_RELAX_HARD_FAIL = frozenset(
    {
        "missing_path",
        "missing_dir",
        "unreadable",
        "symlink",
        "malformed",
        "unreadable_db",
        "malformed_db",
        "inconsistent",
    }
)

_FORBIDDEN_SPEND_ENV = (
    "AEA_WALLET_DEBIT_TOKEN",
    "AEA_WALLET_DEBIT_TOKEN_FILE",
    "AEA_WALLET_CREDIT_TOKEN",
    "AEA_WALLET_CREDIT_TOKEN_FILE",
    "AEA_SIGNER_HMAC_KEY",
    "AEA_SIGNER_HMAC_KEY_FILE",
)

_SECRET_NEEDLES = (
    "private_key",
    "seed_phrase",
    "seed phrase",
    "mnemonic",
    "wallet_debit",
    "AEA_WALLET_DEBIT_TOKEN",
    "AEA_SIGNER_TOKEN",
    "AEA_SIGNER_HMAC_KEY",
    "AEA_SUPERVISOR_TOKEN",
    "BEGIN ",
)


class SignerAdminPort:
    """Optional synchronous caller of signer disable/enable."""

    def disable(self) -> None:  # pragma: no cover - protocol
        raise NotImplementedError

    def enable(self) -> None:  # pragma: no cover - protocol
        raise NotImplementedError


class CallableSignerAdmin(SignerAdminPort):
    def __init__(
        self,
        *,
        disable: Callable[[], Any] | None = None,
        enable: Callable[[], Any] | None = None,
    ) -> None:
        self._disable = disable
        self._enable = enable

    def disable(self) -> None:
        if self._disable is None:
            return
        self._disable()

    def enable(self) -> None:
        if self._enable is None:
            return
        self._enable()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_token(env_name: str, file_env: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    path = os.environ.get(file_env)
    if path:
        return Path(path).read_text(encoding="utf-8").rstrip("\n")
    return None


def assert_no_spend_secrets() -> None:
    for name in _FORBIDDEN_SPEND_ENV:
        if os.environ.get(name):
            raise ValueError(f"supervisor must not hold {name}")


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")


def _scrub(payload: dict[str, Any], *, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    blocked = {s.lower() for s in secrets}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        low = key.lower()
        if any(p in low for p in ("token", "secret", "password", "hmac", "authorization", "bearer")):
            continue
        if isinstance(value, str) and value in secrets:
            continue
        if isinstance(value, str) and value.lower() in blocked:
            continue
        if isinstance(value, str) and any(n in value for n in _SECRET_NEEDLES):
            continue
        out[key] = value
    return out


async def _read_body(receive: Receive) -> bytes:
    chunks = bytearray()
    more = True
    while more:
        message = await receive()
        chunks.extend(message.get("body", b""))
        more = bool(message.get("more_body"))
    return bytes(chunks)


async def _send_json(
    send: Send, *, status: int, payload: dict[str, Any], secrets: tuple[str, ...] = ()
) -> None:
    body = _json_bytes(_scrub(payload, secrets=secrets))
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _header_map(scope: Scope) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        headers[key.decode("latin1").lower()] = value.decode("latin1")
    return headers


def _bearer(headers: dict[str, str]) -> str | None:
    raw = headers.get("authorization")
    if raw is None or not raw.startswith("Bearer "):
        return None
    token = raw[len("Bearer ") :].strip()
    return token or None


def _status_for(code: str) -> int:
    return {
        HttpCode.UNAUTHENTICATED: 401,
        HttpCode.FORBIDDEN: 403,
        HttpCode.VALIDATION_ERROR: 400,
        HttpCode.NOT_FOUND: 404,
        HttpCode.IDEMPOTENCY_CONFLICT: 409,
        HttpCode.CONFLICT: 409,
        HttpCode.NETWORK_FAILURE: 503,
        HttpCode.INTERNAL_ERROR: 500,
        HttpCode.AGENT_FROZEN: 200,
        HttpCode.SIGNER_DISABLED: 200,
    }.get(code, 200)


def _fail_closed_state() -> SupervisorState:
    return SupervisorState(
        frozen=True,
        signer_enabled=False,
        loop_enabled=False,
        updated_at=_now(),
        updated_by="fail-closed",
    )


class SupervisorService:
    """ASGI supervisor. Independent safety authority."""

    def __init__(
        self,
        *,
        supervisor_token: str,
        freeze_path: Path | str | None,
        store: SupervisorStore,
        model_token: str | None = None,
        control_token: str | None = None,
        signer_token: str | None = None,
        hmac_key: str | None = None,
        debit_token: str | None = None,
        credit_token: str | None = None,
        marketplace_token: str | None = None,
        wallet_read_token: str | None = None,
        signer_admin: SignerAdminPort | None = None,
    ) -> None:
        if not supervisor_token:
            raise ValueError("supervisor_token is required")
        if hmac_key or debit_token or credit_token:
            raise ValueError("supervisor must not hold wallet debit/credit or signer HMAC")
        self._supervisor = supervisor_token
        self._freeze_path = freeze_path
        self._store = store
        self._model = model_token
        self._control = control_token
        self._signer = signer_token
        self._marketplace = marketplace_token
        self._wallet_read = wallet_read_token
        self._signer_admin = signer_admin
        self._lock = Lock()

    def _secrets(self) -> tuple[str, ...]:
        return tuple(
            t
            for t in (
                self._supervisor,
                self._model,
                self._control,
                self._signer,
                self._marketplace,
                self._wallet_read,
            )
            if t
        )

    def _classify(self, token: str | None) -> HttpCode | None:
        if token is None:
            return HttpCode.UNAUTHENTICATED
        if compare_digest(token, self._supervisor):
            return None
        known = [
            t
            for t in (
                self._model,
                self._control,
                self._signer,
                self._marketplace,
                self._wallet_read,
            )
            if t
        ]
        for other in known:
            if compare_digest(token, other):
                return HttpCode.FORBIDDEN
        return HttpCode.UNAUTHENTICATED

    def _load_or_closed(self) -> SupervisorState:
        try:
            loaded = self._store.load()
        except Exception:
            return _fail_closed_state()
        if loaded is None:
            return _fail_closed_state()
        return loaded

    def _relaxing_blocked(self) -> str | None:
        """Refuse safety-relaxing actions unless file+DB state is readable and consistent."""
        try:
            loaded = self._store.load()
        except Exception:
            return "unreadable_db"
        if loaded is None:
            return "unreadable_db"
        frozen = getattr(loaded, "frozen", None)
        signer_enabled = getattr(loaded, "signer_enabled", None)
        loop_enabled = getattr(loaded, "loop_enabled", None)
        if not isinstance(frozen, bool) or not isinstance(signer_enabled, bool) or not isinstance(loop_enabled, bool):
            return "malformed_db"
        inspection = inspect_freeze(self._freeze_path, db_frozen=frozen)
        if inspection.detail in _RELAX_HARD_FAIL:
            return inspection.detail
        return None

    def inspect_effective(self) -> dict[str, Any]:
        db_state: SupervisorState | None
        try:
            db_state = self._store.load()
        except Exception:
            db_state = None
        db_frozen: Any
        if db_state is None:
            db_frozen = None
        else:
            db_frozen = bool(db_state.frozen)
        inspection = inspect_freeze(self._freeze_path, db_frozen=db_frozen)
        signer_enabled = False if db_state is None else bool(db_state.signer_enabled)
        loop_enabled = False if db_state is None else bool(db_state.loop_enabled)
        if inspection.frozen:
            # File/DB disagreement or unreadable freeze is already fail-closed.
            pass
        return {
            "frozen": bool(inspection.frozen),
            "signer_enabled": signer_enabled,
            "loop_enabled": loop_enabled,
            "file_detail": inspection.detail,
            "db_frozen": db_frozen,
            "updated_at": db_state.updated_at.isoformat() if db_state and db_state.updated_at else None,
            "updated_by": db_state.updated_by if db_state else "fail-closed",
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        headers = _header_map(scope)
        if method == "GET" and path in {"/health", "/v1/status"}:
            snap = self.inspect_effective()
            await _send_json(
                send,
                status=200,
                payload={
                    "ok": True,
                    "code": HttpCode.OK,
                    "frozen": snap["frozen"],
                    "signer_enabled": snap["signer_enabled"],
                    "loop_enabled": snap["loop_enabled"],
                    "detail": snap["file_detail"],
                    "updated_at": snap["updated_at"],
                    "updated_by": snap["updated_by"],
                    "poll_interval_seconds": POLL_INTERVAL_SECONDS,
                },
                secrets=self._secrets(),
            )
            return
        if method == "POST" and path in ADMIN_ROUTES:
            await self._admin(ADMIN_ROUTES[path], headers, receive, send)
            return
        await _send_json(
            send,
            status=404,
            payload={"ok": False, "code": HttpCode.NOT_FOUND},
            secrets=self._secrets(),
        )

    async def _admin(
        self,
        action: str,
        headers: dict[str, str],
        receive: Receive,
        send: Send,
    ) -> None:
        denied = self._classify(_bearer(headers))
        if denied:
            await _send_json(
                send,
                status=_status_for(denied),
                payload={"ok": False, "code": denied},
                secrets=self._secrets(),
            )
            return
        raw = await _read_body(receive)
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                secrets=self._secrets(),
            )
            return
        if not isinstance(payload, dict):
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                secrets=self._secrets(),
            )
            return
        model_cls = _REQUEST_MODELS.get(action, SupervisorMutationRequest)
        try:
            req = model_cls.model_validate(payload)
        except ValidationError:
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
                secrets=self._secrets(),
            )
            return
        correlation_raw = headers.get("x-aea-correlation-id")
        try:
            correlation_id = UUID(correlation_raw) if correlation_raw else uuid4()
        except ValueError:
            correlation_id = uuid4()
        dumped = req.model_dump(mode="json")
        request_hash = canonical_json_hash(dumped)
        try:
            result = await self._mutate(
                action,
                req,
                request_hash=request_hash,
                correlation_id=correlation_id,
            )
        except FreezeFileError:
            await _send_json(
                send,
                status=200,
                payload={"ok": False, "code": HttpCode.AGENT_FROZEN, "detail": "freeze_file"},
                secrets=self._secrets(),
            )
            return
        except RuntimeError as exc:
            code = HttpCode.SIGNER_DISABLED if "signer" in str(exc) else HttpCode.INTERNAL_ERROR
            if "unreadable" in str(exc):
                code = HttpCode.AGENT_FROZEN
            await _send_json(
                send,
                status=_status_for(code),
                payload={"ok": False, "code": code},
                secrets=self._secrets(),
            )
            return
        await _send_json(
            send,
            status=_status_for(str(result.get("code") or HttpCode.OK)),
            payload=result,
            secrets=self._secrets(),
        )

    async def _mutate(
        self,
        action: str,
        req: Any,
        *,
        request_hash: str,
        correlation_id: UUID,
    ) -> dict[str, Any]:
        with self._lock:
            prior = self._store.lookup_idempotency(req.idempotency_key)
            if prior is not None:
                if prior.request_hash != request_hash or prior.event_type != f"supervisor.{action}":
                    return {"ok": False, "code": HttpCode.IDEMPOTENCY_CONFLICT}
                replay = dict(prior.result)
                replay["code"] = HttpCode.IDEMPOTENT_REPLAY
                replay["ok"] = True
                return replay

            if action == "incidents":
                result = self._write_incident(req, correlation_id=correlation_id)
            else:
                result = self._apply_transition(
                    action,
                    req,
                    correlation_id=correlation_id,
                    request_hash=request_hash,
                )
            if result.get("ok") is True:
                stored = {k: v for k, v in result.items() if k != "code"}
                stored["code"] = HttpCode.OK
                record = IdempotencyRecord(
                    idempotency_key=req.idempotency_key,
                    request_hash=request_hash,
                    event_type=f"supervisor.{action}",
                    result=stored,
                )
                self._store.remember_idempotency(record)
            return result

    def _write_incident(self, req: IncidentCreateRequest, *, correlation_id: UUID) -> dict[str, Any]:
        row = self._store.write_incident(
            severity=req.severity,
            kind=req.kind,
            message=req.message,
            correlation_id=req.correlation_id or correlation_id,
        )
        payload = {
            "action": "incidents",
            "severity": req.severity,
            "kind": req.kind,
            "message": req.message,
            "reason": req.reason,
            "actor": req.actor,
            "source": req.source,
            "idempotency_key": req.idempotency_key,
            "incident_id": str(row.incident_id),
            "request_hash": canonical_json_hash(req.model_dump(mode="json")),
            "result": {"ok": True, "incident_id": str(row.incident_id)},
        }
        self._store.write_audit(
            "supervisor.incidents",
            payload,
            correlation_id=req.correlation_id or correlation_id,
        )
        return {
            "ok": True,
            "code": HttpCode.OK,
            "incident_id": str(row.incident_id),
            "severity": req.severity,
            "kind": req.kind,
        }

    def _apply_transition(
        self,
        action: str,
        req: SupervisorMutationRequest,
        *,
        correlation_id: UUID,
        request_hash: str,
    ) -> dict[str, Any]:
        if action in _RELAXING:
            expected = RELAXING_CONFIRM[action]
            if getattr(req, "confirm", None) != expected:
                return {"ok": False, "code": HttpCode.VALIDATION_ERROR}
            blocked = self._relaxing_blocked()
            if blocked is not None:
                return {
                    "ok": False,
                    "code": HttpCode.AGENT_FROZEN,
                    "detail": blocked,
                }

        previous = self._load_or_closed()

        nxt = SupervisorState(
            frozen=previous.frozen,
            signer_enabled=previous.signer_enabled,
            loop_enabled=previous.loop_enabled,
            updated_by=req.actor,
        )
        if action == "freeze-spend":
            nxt = SupervisorState(
                frozen=True,
                signer_enabled=previous.signer_enabled,
                loop_enabled=previous.loop_enabled,
                updated_by=req.actor,
            )
            self._write_freeze_file(req)
            saved = self._persist(nxt, actor=req.actor, relaxing=False)
        elif action == "unfreeze":
            saved = self._unfreeze(previous, actor=req.actor)
        elif action == "disable-signer":
            nxt = SupervisorState(
                frozen=previous.frozen,
                signer_enabled=False,
                loop_enabled=previous.loop_enabled,
                updated_by=req.actor,
            )
            saved = self._persist(nxt, actor=req.actor, relaxing=False)
            self._propagate_signer(action)
        elif action == "enable-signer":
            self._propagate_signer(action)
            nxt = SupervisorState(
                frozen=previous.frozen,
                signer_enabled=True,
                loop_enabled=previous.loop_enabled,
                updated_by=req.actor,
            )
            try:
                saved = self._persist(nxt, actor=req.actor, relaxing=True)
            except Exception:
                if self._signer_admin is not None:
                    try:
                        self._signer_admin.disable()
                    except Exception:
                        pass
                raise
        elif action == "stop-agent":
            nxt = SupervisorState(
                frozen=previous.frozen,
                signer_enabled=previous.signer_enabled,
                loop_enabled=False,
                updated_by=req.actor,
            )
            saved = self._persist(nxt, actor=req.actor, relaxing=False)
        elif action == "permit-loop":
            nxt = SupervisorState(
                frozen=previous.frozen,
                signer_enabled=previous.signer_enabled,
                loop_enabled=True,
                updated_by=req.actor,
            )
            saved = self._persist(nxt, actor=req.actor, relaxing=True)
        else:
            return {"ok": False, "code": HttpCode.NOT_FOUND}

        effective = self.inspect_effective()
        result = {
            "ok": True,
            "code": HttpCode.OK,
            "action": action,
            "previous": previous.as_dict(),
            "new": saved.as_dict(),
            "frozen": effective["frozen"],
            "signer_enabled": effective["signer_enabled"],
            "loop_enabled": effective["loop_enabled"],
            "reason": req.reason,
            "actor": req.actor,
            "source": req.source,
            "correlation_id": str(correlation_id),
        }
        audit_payload = {
            "action": action,
            "previous": previous.as_dict(),
            "new": saved.as_dict(),
            "reason": req.reason,
            "actor": req.actor,
            "source": req.source,
            "idempotency_key": req.idempotency_key,
            "request_hash": request_hash,
            "result": {
                "frozen": result["frozen"],
                "signer_enabled": result["signer_enabled"],
                "loop_enabled": result["loop_enabled"],
            },
        }
        audit_payload["result"] = {
            k: result[k]
            for k in (
                "ok",
                "action",
                "previous",
                "new",
                "frozen",
                "signer_enabled",
                "loop_enabled",
                "reason",
                "actor",
                "source",
                "correlation_id",
            )
            if k in result
        }
        self._store.write_audit(
            f"supervisor.{action}",
            audit_payload,
            correlation_id=correlation_id,
        )
        if action in _RESTRICTIVE:
            self._store.write_incident(
                severity="critical",
                kind=action,
                message=req.reason,
                correlation_id=correlation_id,
            )
        return result

    def _persist(self, nxt: SupervisorState, *, actor: str, relaxing: bool) -> SupervisorState:
        try:
            current = self._store.load()
        except Exception as exc:
            raise RuntimeError("unreadable_db") from exc
        if current is None and relaxing:
            raise RuntimeError("unreadable_db")
        try:
            return self._store.save(nxt, actor=actor)
        except Exception as exc:
            raise RuntimeError("unreadable_db") from exc

    def _write_freeze_file(self, req: SupervisorMutationRequest) -> None:
        write_freeze_file(
            self._freeze_path,
            {
                "frozen": True,
                "reason": req.reason,
                "actor": req.actor,
                "source": req.source,
                "at": _now().isoformat(),
            },
        )

    def _unfreeze(self, previous: SupervisorState, *, actor: str) -> SupervisorState:
        # Restrictive until both file and DB are cleared. File first would
        # leave DB frozen (OR still frozen). DB-first would leave file frozen.
        # Clear file, then DB; if DB fails, rewrite the file.
        try:
            remove_freeze_file(self._freeze_path)
        except FreezeFileError:
            raise
        nxt = SupervisorState(
            frozen=False,
            signer_enabled=previous.signer_enabled,
            loop_enabled=previous.loop_enabled,
            updated_by=actor,
        )
        try:
            return self._persist(nxt, actor=actor, relaxing=True)
        except Exception:
            try:
                write_freeze_file(
                    self._freeze_path,
                    {
                        "frozen": True,
                        "reason": "unfreeze_db_failed",
                        "actor": actor,
                        "source": "supervisor",
                        "at": _now().isoformat(),
                    },
                )
            except FreezeFileError:
                pass
            raise RuntimeError("unreadable_db")

    def _propagate_signer(self, action: str) -> None:
        if self._signer_admin is None:
            return
        # Authoritative state is already persisted. Signer in-memory flag is
        # a cache; failure here leaves the more restrictive DB/file state.
        try:
            if action == "disable-signer":
                self._signer_admin.disable()
            elif action == "enable-signer":
                self._signer_admin.enable()
        except Exception:
            if action == "enable-signer":
                raise RuntimeError("signer_unavailable")

    def apply_monitor_decision(
        self,
        decision: MonitorDecision,
        *,
        actor: str = "monitor",
        reason: str = "monitor signal",
    ) -> None:
        """Apply restrictive monitor actions. Never unfreezes."""
        dummy = SupervisorMutationRequest.model_validate(
            {
                "reason": reason,
                "actor": actor,
                "source": "monitor",
                "idempotency_key": f"monitor-{uuid4().hex[:12]}",
            }
        )
        with self._lock:
            if decision.freeze_spend:
                self._apply_transition(
                    "freeze-spend",
                    dummy,
                    correlation_id=uuid4(),
                    request_hash=canonical_json_hash({"monitor": "freeze-spend", "reason": reason}),
                )
            if decision.disable_signer:
                self._apply_transition(
                    "disable-signer",
                    dummy,
                    correlation_id=uuid4(),
                    request_hash=canonical_json_hash({"monitor": "disable-signer", "reason": reason}),
                )
            if decision.stop_loop:
                self._apply_transition(
                    "stop-agent",
                    dummy,
                    correlation_id=uuid4(),
                    request_hash=canonical_json_hash({"monitor": "stop-agent", "reason": reason}),
                )
            for incident in decision.incidents:
                self._store.write_incident(
                    severity=incident.severity,
                    kind=incident.kind,
                    message=incident.message,
                )

    def evaluate_and_apply(self, snapshot: MonitorSnapshot) -> MonitorDecision:
        decision = evaluate_monitors(snapshot)
        self.apply_monitor_decision(decision)
        return decision


def create_app(
    *,
    supervisor_token: str,
    freeze_path: Path | str | None,
    store: SupervisorStore | None = None,
    model_token: str | None = None,
    control_token: str | None = None,
    signer_token: str | None = None,
    marketplace_token: str | None = None,
    wallet_read_token: str | None = None,
    signer_admin: SignerAdminPort | None = None,
    hmac_key: str | None = None,
    debit_token: str | None = None,
    credit_token: str | None = None,
) -> SupervisorService:
    return SupervisorService(
        supervisor_token=supervisor_token,
        freeze_path=freeze_path,
        store=store or MemorySupervisorStore(),
        model_token=model_token,
        control_token=control_token,
        signer_token=signer_token,
        hmac_key=hmac_key,
        debit_token=debit_token,
        credit_token=credit_token,
        marketplace_token=marketplace_token,
        wallet_read_token=wallet_read_token,
        signer_admin=signer_admin,
    )


def create_app_from_env() -> SupervisorService:
    assert_no_spend_secrets()
    token = _read_token("AEA_SUPERVISOR_TOKEN", "AEA_SUPERVISOR_TOKEN_FILE")
    if not token:
        raise ValueError("AEA_SUPERVISOR_TOKEN is required")
    freeze_raw = os.environ.get("AEA_FREEZE_PATH")
    if not freeze_raw:
        raise ValueError("AEA_FREEZE_PATH is required")
    from psycopg.rows import dict_row

    from aea.ledger.db import connect

    conn = connect(role="economic_supervisor")
    conn.row_factory = dict_row
    from aea.supervisor.state import PostgresSupervisorStore

    return create_app(
        supervisor_token=token,
        freeze_path=freeze_raw,
        store=PostgresSupervisorStore(conn),
        model_token=_read_token("AEA_MODEL_TOKEN", "AEA_MODEL_TOKEN_FILE"),
        control_token=_read_token("AEA_CONTROL_TOKEN", "AEA_CONTROL_TOKEN_FILE"),
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        create_app_from_env(),
        host=SUPERVISOR_HOST,
        port=SUPERVISOR_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
