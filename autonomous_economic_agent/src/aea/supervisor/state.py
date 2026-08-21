"""Supervisor-owned freeze/signer/loop state.

Postgres mutations use role economic_supervisor only. The in-memory store
exists for tests that do not need a live database.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from aea import AGENT_ID
from aea.hashing import canonical_json_hash


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scrub(value: Any) -> Any:
    secret_parts = (
        "token",
        "secret",
        "password",
        "hmac",
        "private_key",
        "seed",
        "mnemonic",
        "authorization",
        "bearer",
    )
    if isinstance(value, dict):
        return {
            k: _scrub(v)
            for k, v in value.items()
            if not any(part in str(k).lower() for part in secret_parts)
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


@dataclass(frozen=True)
class SupervisorState:
    frozen: bool = False
    signer_enabled: bool = True
    loop_enabled: bool = True
    updated_at: datetime | None = None
    updated_by: str = "operator"

    def as_dict(self) -> dict[str, Any]:
        return {
            "frozen": self.frozen,
            "signer_enabled": self.signer_enabled,
            "loop_enabled": self.loop_enabled,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updated_by": self.updated_by,
        }


@dataclass(frozen=True)
class IdempotencyRecord:
    idempotency_key: str
    request_hash: str
    event_type: str
    result: dict[str, Any]


@dataclass(frozen=True)
class IncidentRow:
    incident_id: UUID
    severity: str
    kind: str
    message: str
    correlation_id: UUID | None
    created_at: datetime


class SupervisorStore(Protocol):
    def load(self) -> SupervisorState | None: ...

    def save(self, state: SupervisorState, *, actor: str) -> SupervisorState: ...

    def lookup_idempotency(self, key: str) -> IdempotencyRecord | None: ...

    def remember_idempotency(self, record: IdempotencyRecord) -> None: ...

    def write_audit(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        correlation_id: UUID | None = None,
    ) -> None: ...

    def write_incident(
        self,
        *,
        severity: str,
        kind: str,
        message: str,
        correlation_id: UUID | None = None,
    ) -> IncidentRow: ...


@dataclass
class MemorySupervisorStore:
    """Process-local store. Not used in production."""

    _state: SupervisorState = field(default_factory=SupervisorState)
    _idem: dict[str, IdempotencyRecord] = field(default_factory=dict)
    _audits: list[dict[str, Any]] = field(default_factory=list)
    _incidents: list[IncidentRow] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)
    missing: bool = False

    def load(self) -> SupervisorState | None:
        if self.missing:
            return None
        with self._lock:
            return self._state

    def save(self, state: SupervisorState, *, actor: str) -> SupervisorState:
        if self.missing:
            raise RuntimeError("unreadable_db")
        stored = replace(state, updated_at=_now(), updated_by=actor)
        with self._lock:
            self._state = stored
        return stored

    def lookup_idempotency(self, key: str) -> IdempotencyRecord | None:
        with self._lock:
            return self._idem.get(key)

    def remember_idempotency(self, record: IdempotencyRecord) -> None:
        with self._lock:
            self._idem[record.idempotency_key] = record

    def write_audit(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        correlation_id: UUID | None = None,
    ) -> None:
        clean = _scrub(payload)
        with self._lock:
            self._audits.append(
                {
                    "event_type": event_type,
                    "payload": clean,
                    "payload_hash": canonical_json_hash(clean),
                    "correlation_id": correlation_id,
                    "created_at": _now(),
                }
            )

    def write_incident(
        self,
        *,
        severity: str,
        kind: str,
        message: str,
        correlation_id: UUID | None = None,
    ) -> IncidentRow:
        row = IncidentRow(
            incident_id=uuid4(),
            severity=severity,
            kind=kind,
            message=message,
            correlation_id=correlation_id,
            created_at=_now(),
        )
        with self._lock:
            self._incidents.append(row)
        return row


class PostgresSupervisorStore:
    """Mutations as the current role. Caller must be economic_supervisor."""

    def __init__(self, conn: Any, *, agent_id: str = AGENT_ID) -> None:
        if conn is None:
            raise ValueError("database connection is required")
        self._conn = conn
        self._agent_id = agent_id

    def load(self) -> SupervisorState | None:
        row = self._conn.execute(
            """
            SELECT frozen, signer_enabled, loop_enabled, updated_at, updated_by
              FROM supervisor_state
             WHERE singleton
            """
        ).fetchone()
        if row is None:
            return None
        return _row_to_state(row)

    def save(self, state: SupervisorState, *, actor: str) -> SupervisorState:
        current = self._conn.execute(
            """
            SELECT frozen, signer_enabled, loop_enabled, updated_at, updated_by
              FROM supervisor_state
             WHERE singleton
             FOR UPDATE
            """
        ).fetchone()
        if current is None:
            inserted = self._conn.execute(
                """
                INSERT INTO supervisor_state (
                    singleton, frozen, signer_enabled, loop_enabled, updated_by
                ) VALUES (true, %s, %s, %s, %s)
                RETURNING frozen, signer_enabled, loop_enabled, updated_at, updated_by
                """,
                (state.frozen, state.signer_enabled, state.loop_enabled, actor),
            ).fetchone()
            if inserted is None:
                raise RuntimeError("unreadable_db")
            return _row_to_state(inserted)
        updated = self._conn.execute(
            """
            UPDATE supervisor_state
               SET frozen = %s,
                   signer_enabled = %s,
                   loop_enabled = %s,
                   updated_at = now(),
                   updated_by = %s
             WHERE singleton
         RETURNING frozen, signer_enabled, loop_enabled, updated_at, updated_by
            """,
            (state.frozen, state.signer_enabled, state.loop_enabled, actor),
        ).fetchone()
        if updated is None:
            raise RuntimeError("unreadable_db")
        return _row_to_state(updated)

    def lookup_idempotency(self, key: str) -> IdempotencyRecord | None:
        row = self._conn.execute(
            """
            SELECT event_type, payload
              FROM audit_events
             WHERE event_type LIKE 'supervisor.%%'
               AND payload->>'idempotency_key' = %s
             ORDER BY created_at ASC
             LIMIT 1
            """,
            (key,),
        ).fetchone()
        if row is None:
            return None
        payload = row["payload"] if isinstance(row["payload"], dict) else {}
        request_hash = payload.get("request_hash")
        result = payload.get("result")
        if not isinstance(request_hash, str) or not isinstance(result, dict):
            return None
        return IdempotencyRecord(
            idempotency_key=key,
            request_hash=request_hash,
            event_type=row["event_type"],
            result=result,
        )

    def remember_idempotency(self, record: IdempotencyRecord) -> None:
        # Durable copy lives in the audit row written alongside the mutation.
        return None

    def write_audit(
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

    def write_incident(
        self,
        *,
        severity: str,
        kind: str,
        message: str,
        correlation_id: UUID | None = None,
    ) -> IncidentRow:
        row = self._conn.execute(
            """
            INSERT INTO incidents (severity, kind, message, correlation_id)
            VALUES (%s, %s, %s, %s)
            RETURNING incident_id, severity, kind, message, correlation_id, created_at
            """,
            (severity, kind, message, correlation_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("unreadable_db")
        return IncidentRow(
            incident_id=row["incident_id"],
            severity=row["severity"],
            kind=row["kind"],
            message=row["message"],
            correlation_id=row["correlation_id"],
            created_at=row["created_at"],
        )


def _row_to_state(row: Any) -> SupervisorState:
    if isinstance(row, dict):
        frozen = row["frozen"]
        signer_enabled = row["signer_enabled"]
        loop_enabled = row["loop_enabled"]
        updated_at = row["updated_at"]
        updated_by = row["updated_by"]
    else:
        frozen, signer_enabled, loop_enabled, updated_at, updated_by = row
    return SupervisorState(
        frozen=bool(frozen),
        signer_enabled=bool(signer_enabled),
        loop_enabled=bool(loop_enabled),
        updated_at=updated_at,
        updated_by=str(updated_by),
    )
