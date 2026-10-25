"""Single infer verb. Host POST /v1/chat/completions while the model lock is held."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

from .config import LMSTUDIO_BASE
from .errors import RuntimeFailure
from .http_client import Transport, exchange
from .lock import ModelLock
from .probe import LMStudioProbe


@dataclass(frozen=True)
class InferResult:
    text: str
    finish_reason: str | None
    model: str


def infer(
    messages: list[dict[str, str]],
    timeout: float,
    *,
    transport: Transport | None = None,
    workspace: Path | None = None,
    environ: Mapping[str, str] | None = None,
    base: str = LMSTUDIO_BASE,
) -> InferResult:
    """Readiness, then one locked chat completion. No retry and no fallback model."""
    _require_timeout(timeout)
    _validate_messages(messages)
    model = LMStudioProbe(transport=transport, base=base, environ=environ).require_ready()
    body = json.dumps({"model": model, "messages": messages}).encode("utf-8")
    url = f"{base.rstrip('/')}/v1/chat/completions"
    with ModelLock(workspace):
        status, payload = exchange("POST", url, body, timeout, transport=transport)
    if status != 200:
        raise RuntimeFailure("ENDPOINT_UNAVAILABLE", f"HTTP {status}")
    return _parse_completion(payload, model)


def _require_timeout(timeout: float) -> None:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise RuntimeFailure("CONFIG_INVALID", "timeout is required")


def _validate_messages(messages: list[dict[str, str]]) -> None:
    if not isinstance(messages, list) or not messages:
        raise RuntimeFailure("CONFIG_INVALID", "messages are required")
    for message in messages:
        if not isinstance(message, dict):
            raise RuntimeFailure("CONFIG_INVALID", "message shape")
        if not isinstance(message.get("role"), str) or not isinstance(message.get("content"), str):
            raise RuntimeFailure("CONFIG_INVALID", "message shape")


def _parse_completion(payload: bytes, expected_model: str) -> InferResult:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "chat body is not JSON") from error
    if not isinstance(document, dict):
        raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "chat body is not an object")
    echoed = document.get("model")
    if echoed != expected_model:
        raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "response model id differs")
    choices = document.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "choices are empty")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "choice shape")
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "message content shape")
    finish = choice.get("finish_reason")
    if finish is not None and not isinstance(finish, str):
        raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "finish reason shape")
    return InferResult(text=message["content"], finish_reason=finish, model=echoed)
