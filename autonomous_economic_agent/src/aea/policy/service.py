"""Policy HTTP process. ASGI on 127.0.0.1:18701. Wraps the pure engine.

Auth: POST /v1/evaluate requires AEA_CONTROL_TOKEN. AEA_MODEL_TOKEN is
FORBIDDEN. GET /health is unauthenticated. No LLM, wallet, Solana, signer,
or supervisor clients.
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
from aea.policy.engine import evaluate
from aea.policy.reasons import HttpCode
from aea.signer.freeze import inspect_freeze
from aea.types import PolicyInput, PolicyOutput

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
    ) -> None:
        if not control_token:
            raise ValueError("control_token is required")
        self._control_token = control_token
        self._model_token = model_token
        self._loaded = loaded
        self._freeze_path = freeze_path
        self._now = now
        self._db_frozen_reader = db_frozen_reader

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
        if self._freeze_is_frozen():
            inp = inp.model_copy(update={"frozen": True})
        dest = self._loaded.classify(inp.destination)
        now = self._now or datetime.now(timezone.utc)
        output = evaluate(
            inp,
            self._loaded.document,
            effective_policy_hash=self._loaded.policy_hash,
            now=now,
            destination=dest,
        )
        status, body = _envelope(output)
        await _send_json(send, status=status, payload=body)

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
) -> PolicyService:
    return PolicyService(
        control_token=control_token,
        loaded=loaded,
        model_token=model_token,
        freeze_path=freeze_path,
        now=now,
        db_frozen_reader=db_frozen_reader,
    )


def create_app_from_env() -> PolicyService:
    control = _read_token("AEA_CONTROL_TOKEN", "AEA_CONTROL_TOKEN_FILE")
    if not control:
        raise ValueError("AEA_CONTROL_TOKEN or AEA_CONTROL_TOKEN_FILE is required")
    model = _read_token("AEA_MODEL_TOKEN", "AEA_MODEL_TOKEN_FILE")
    freeze_raw = os.environ.get("AEA_FREEZE_PATH")
    freeze_path = Path(freeze_raw) if freeze_raw else None
    return create_app(
        control_token=control,
        loaded=load_policy(),
        model_token=model,
        freeze_path=freeze_path,
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
