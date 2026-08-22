"""Policy HTTP process. ASGI on 127.0.0.1:18701. Wraps the pure engine.

Auth: POST /v1/evaluate and POST /v1/execute-payment require
AEA_CONTROL_TOKEN. AEA_MODEL_TOKEN is FORBIDDEN. GET /health is
unauthenticated. Policy is the HMAC caller of the signer (M0 §4.4 / §11).
No wallet debit credential. No LLM. No Solana.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from hmac import compare_digest
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from aea.config import LoadedPolicy, load_policy
from aea.payment.schemas import ExecutePaymentRequest
from aea.policy.engine import evaluate
from aea.policy.reasons import HttpCode
from aea.policy.signer_client import PolicySignerClient
from aea.signer.backend import ApprovedRequest
from aea.signer.freeze import inspect_freeze
from aea.types import PolicyInput, PolicyOutput, format_amount

POLICY_PORT = 18701
POLICY_HOST = "127.0.0.1"

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


def _read_token(env_name: str, file_env: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    path = os.environ.get(file_env)
    if path:
        return Path(path).read_text(encoding="utf-8").rstrip("\n")
    return None


def freeze_from_path(freeze_path: Path | None, *, fail_closed_unreadable_dir: bool) -> bool:
    """FREEZE file present ⇒ frozen. Missing file + readable dir ⇒ not frozen.

    Unreadable/missing freeze directory ⇒ frozen when fail-closed.
    """
    if freeze_path is None:
        return False
    directory = freeze_path if freeze_path.is_dir() else freeze_path.parent
    freeze_file = freeze_path / "FREEZE" if freeze_path.is_dir() else freeze_path
    try:
        if not directory.exists() or not os.access(directory, os.R_OK | os.X_OK):
            return bool(fail_closed_unreadable_dir)
        return freeze_file.is_file()
    except OSError:
        return bool(fail_closed_unreadable_dir)


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")


async def _read_body(receive: Receive) -> bytes:
    chunks = bytearray()
    more = True
    while more:
        message = await receive()
        chunks.extend(message.get("body", b""))
        more = bool(message.get("more_body"))
    return bytes(chunks)


async def _send_json(
    send: Send,
    *,
    status: int,
    payload: dict[str, Any],
) -> None:
    body = _json_bytes(payload)
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
    if raw is None:
        return None
    prefix = "Bearer "
    if not raw.startswith(prefix):
        return None
    token = raw[len(prefix) :].strip()
    return token or None


def _envelope(output: PolicyOutput) -> tuple[int, dict[str, Any]]:
    body = output.model_dump(mode="json")
    if output.decision == "approved":
        body["ok"] = True
        body["code"] = HttpCode.OK
        return 200, body
    body["ok"] = False
    body["code"] = HttpCode.POLICY_REJECTED
    return 200, body


class PolicyService:
    """ASGI app wrapping evaluate()."""

    def __init__(
        self,
        *,
        control_token: str,
        loaded: LoadedPolicy,
        model_token: str | None = None,
        freeze_path: Path | None = None,
        now: datetime | None = None,
        db_frozen_reader: Callable[[], Any] | None = None,
        signer_client: PolicySignerClient | None = None,
        phase_b_context: dict[str, str] | None = None,
        debit_token: str | None = None,
    ) -> None:
        if not control_token:
            raise ValueError("control_token is required")
        if debit_token:
            raise ValueError("policy must not hold wallet debit credentials")
        self._control_token = control_token
        self._model_token = model_token
        self._loaded = loaded
        self._freeze_path = freeze_path
        self._now = now
        self._db_frozen_reader = db_frozen_reader
        self._signer_client = signer_client
        self._phase_b_context = phase_b_context

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        headers = _header_map(scope)
        if method == "GET" and path == "/health":
            await _send_json(send, status=200, payload={"ok": True, "code": HttpCode.OK})
            return
        if method == "POST" and path == "/v1/evaluate":
            await self._evaluate(headers, receive, send)
            return
        if method == "POST" and path == "/v1/execute-payment":
            await self._execute_payment(headers, receive, send)
            return
        await _send_json(
            send,
            status=404,
            payload={"ok": False, "code": HttpCode.NOT_FOUND},
        )

    def _authorize(self, headers: dict[str, str]) -> HttpCode | None:
        token = _bearer(headers)
        if token is None:
            return HttpCode.UNAUTHENTICATED
        if compare_digest(token, self._control_token):
            return None
        if self._model_token and compare_digest(token, self._model_token):
            return HttpCode.FORBIDDEN
        return HttpCode.UNAUTHENTICATED

    async def _evaluate(self, headers: dict[str, str], receive: Receive, send: Send) -> None:
        denied = self._authorize(headers)
        if denied is HttpCode.UNAUTHENTICATED:
            await _send_json(
                send,
                status=401,
                payload={"ok": False, "code": HttpCode.UNAUTHENTICATED},
            )
            return
        if denied is HttpCode.FORBIDDEN:
            await _send_json(
                send,
                status=403,
                payload={"ok": False, "code": HttpCode.FORBIDDEN},
            )
            return
        raw = await _read_body(receive)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
            )
            return
        if not isinstance(payload, dict):
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
            )
            return
        try:
            inp = PolicyInput.model_validate(payload)
        except ValidationError:
            await _send_json(
                send,
                status=400,
                payload={"ok": False, "code": HttpCode.VALIDATION_ERROR},
            )
            return
        output = self._run_engine(inp)
        status, body = _envelope(output)
        await _send_json(send, status=status, payload=body)

    def _run_engine(self, inp: PolicyInput) -> PolicyOutput:
        if self._freeze_is_frozen():
            inp = inp.model_copy(update={"frozen": True})
        dest = self._loaded.classify(inp.destination)
        now = self._now or datetime.now(timezone.utc)
        return evaluate(
            inp,
            self._loaded.document,
            effective_policy_hash=self._loaded.policy_hash,
            now=now,
            destination=dest,
        )

    async def _execute_payment(self, headers: dict[str, str], receive: Receive, send: Send) -> None:
        denied = self._authorize(headers)
        if denied is HttpCode.UNAUTHENTICATED:
            await _send_json(
                send, status=401, payload={"ok": False, "code": HttpCode.UNAUTHENTICATED}
            )
            return
        if denied is HttpCode.FORBIDDEN:
            await _send_json(
                send, status=403, payload={"ok": False, "code": HttpCode.FORBIDDEN}
            )
            return
        raw = await _read_body(receive)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            await _send_json(
                send, status=400, payload={"ok": False, "code": HttpCode.VALIDATION_ERROR}
            )
            return
        if not isinstance(payload, dict):
            await _send_json(
                send, status=400, payload={"ok": False, "code": HttpCode.VALIDATION_ERROR}
            )
            return
        try:
            req = ExecutePaymentRequest.model_validate(payload)
        except ValidationError:
            await _send_json(
                send, status=400, payload={"ok": False, "code": HttpCode.VALIDATION_ERROR}
            )
            return
        output = self._run_engine(req)
        if output.decision != "approved" or output.approved_amount is None:
            status, body = _envelope(output)
            body["request_id"] = str(req.request_id)
            body["tx_id"] = None
            await _send_json(send, status=status, payload=body)
            return
        if self._signer_client is None:
            await _send_json(
                send,
                status=200,
                payload={
                    "ok": False,
                    "code": HttpCode.SIGNER_UNAVAILABLE,
                    "decision": "approved",
                    "request_id": str(req.request_id),
                    "tx_id": None,
                    "reason_code": HttpCode.SIGNER_UNAVAILABLE,
                },
            )
            return
        if req.job_id is None:
            await _send_json(
                send,
                status=200,
                payload={
                    "ok": False,
                    "code": HttpCode.VALIDATION_ERROR,
                    "decision": "approved",
                    "request_id": str(req.request_id),
                    "reason_code": "NO_JOB_PURPOSE",
                },
            )
            return
        approved_body = {
                "request_id": str(req.request_id),
                "amount": format_amount(req.amount),
                "asset": req.asset,
                "destination": req.destination,
                "purpose": req.purpose,
                "job_id": str(req.job_id),
                "policy_version": output.policy_version,
                "policy_hash": output.policy_hash,
                "approved_amount": format_amount(output.approved_amount),
                "approved_at": req.approved_at.isoformat(),
                "correlation_id": str(output.correlation_id),
            }
        if self._loaded.document.wallet_phase in {"B", "C"}:
            if self._phase_b_context is None:
                await _send_json(send, status=200, payload={"ok": False,
                    "code": HttpCode.SIGNER_UNAVAILABLE, "decision": "approved",
                    "request_id": str(req.request_id), "reason_code": "PHASE_B_CONFIG_MISSING"})
                return
            from decimal import Decimal
            base = req.amount * (Decimal(10) ** int(self._phase_b_context["decimals"]))
            if base != base.to_integral_value():
                await _send_json(send, status=400, payload={"ok": False, "code": HttpCode.VALIDATION_ERROR})
                return
            context_key = "phase_c_context" if self._loaded.document.wallet_phase == "C" else "phase_b_context"
            approved_body[context_key] = {**self._phase_b_context, "amount_base_units": int(base)}
        approved = ApprovedRequest.model_validate(approved_body)
        signed = await self._signer_client.sign(approved)
        body = {
            "ok": signed.ok,
            "code": signed.code if not signed.ok else HttpCode.OK,
            "decision": "approved",
            "reason_code": signed.reason_code if not signed.ok else None,
            "request_id": str(req.request_id),
            "tx_id": signed.tx_id,
            "canonical_hash": signed.canonical_hash,
            "policy_version": output.policy_version,
            "policy_hash": output.policy_hash,
            "approved_amount": format_amount(output.approved_amount),
            "replay": signed.replay,
            "fee_lamports": signed.fee_lamports,
            "correlation_id": str(output.correlation_id),
        }
        await _send_json(send, status=200, payload=body)

    def _freeze_is_frozen(self) -> bool:
        db_kw: dict[str, Any] = {}
        if self._db_frozen_reader is not None:
            try:
                db_kw["db_frozen"] = self._db_frozen_reader()
            except Exception:
                db_kw["db_frozen"] = None
        if self._freeze_path is not None:
            return inspect_freeze(self._freeze_path, **db_kw).frozen
        if "db_frozen" in db_kw:
            value = db_kw["db_frozen"]
            if value is None or not isinstance(value, bool):
                return True
            return bool(value)
        return freeze_from_path(
            self._freeze_path,
            fail_closed_unreadable_dir=self._loaded.document.emergency.fail_closed_on_unreadable_freeze_dir,
        )


def create_app(
    *,
    control_token: str,
    loaded: LoadedPolicy,
    model_token: str | None = None,
    freeze_path: Path | None = None,
    now: datetime | None = None,
    db_frozen_reader: Callable[[], Any] | None = None,
    signer_client: PolicySignerClient | None = None,
    phase_b_context: dict[str, str] | None = None,
) -> PolicyService:
    return PolicyService(
        control_token=control_token,
        loaded=loaded,
        model_token=model_token,
        freeze_path=freeze_path,
        now=now,
        db_frozen_reader=db_frozen_reader,
        signer_client=signer_client,
        phase_b_context=phase_b_context,
    )


def create_app_from_env() -> PolicyService:
    control = _read_token("AEA_CONTROL_TOKEN", "AEA_CONTROL_TOKEN_FILE")
    if not control:
        raise ValueError("AEA_CONTROL_TOKEN or AEA_CONTROL_TOKEN_FILE is required")
    model = _read_token("AEA_MODEL_TOKEN", "AEA_MODEL_TOKEN_FILE")
    freeze_raw = os.environ.get("AEA_FREEZE_PATH")
    freeze_path = Path(freeze_raw) if freeze_raw else None
    hmac_key = _read_token("AEA_SIGNER_HMAC_KEY", "AEA_SIGNER_HMAC_KEY_FILE")
    signer_token = _read_token("AEA_SIGNER_TOKEN", "AEA_SIGNER_TOKEN_FILE")
    signer_client = None
    if hmac_key and signer_token:
        signer_client = PolicySignerClient(
            hmac_key=hmac_key,
            signer_token=signer_token,
            signer_sock=os.environ.get("AEA_SIGNER_SOCK"),
        )
    loaded = load_policy()
    phase_b_context = None
    if loaded.document.wallet_phase in {"B", "C"}:
        from solders.pubkey import Pubkey
        from spl.token.instructions import get_associated_token_address
        names = ("AEA_SOLANA_NETWORK", "AEA_SOLANA_PUBLIC_WALLET", "AEA_SOLANA_TOKEN_MINT",
                 "AEA_SOLANA_SOURCE_TOKEN_ACCOUNT", "AEA_SOLANA_DESTINATION_OWNER")
        values = {name: os.environ.get(name) for name in names}
        if any(not value for value in values.values()):
            raise ValueError("Solana public transaction context is incomplete")
        mint = Pubkey.from_string(str(values["AEA_SOLANA_TOKEN_MINT"]))
        owner = Pubkey.from_string(str(values["AEA_SOLANA_DESTINATION_OWNER"]))
        phase_b_context = {
            "network": str(values["AEA_SOLANA_NETWORK"]),
            "payer": str(values["AEA_SOLANA_PUBLIC_WALLET"]),
            "source_mint": str(mint),
            "source_token_account": str(values["AEA_SOLANA_SOURCE_TOKEN_ACCOUNT"]),
            "destination_owner": str(owner),
            "destination_token_account": str(get_associated_token_address(owner, mint)),
            "decimals": os.environ.get("AEA_SOLANA_TOKEN_DECIMALS", "6"),
        }
    return create_app(
        control_token=control,
        loaded=loaded,
        model_token=model,
        freeze_path=freeze_path,
        signer_client=signer_client,
        phase_b_context=phase_b_context,
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        create_app_from_env(),
        host=POLICY_HOST,
        port=POLICY_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
