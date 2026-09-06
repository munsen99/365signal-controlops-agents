"""HTTP client for POST /v1/tools/{name}. Model token only.

Used by the Hermes plugin runtime and the Gate A driver. There is no
control-token constructor. The token is never placed on the returned payload.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

from aea import AGENT_ID, CONSTITUTION_VERSION, CALLABLE_MODEL_TOOLS, __version__
from aea.policy.reasons import HttpCode

DEFAULT_CONTROL_URL = "http://127.0.0.1:18700"

_SECRET_PARTS = (
    "token",
    "secret",
    "password",
    "hmac",
    "authorization",
    "private_key",
    "seed",
    "mnemonic",
    "bearer",
)


class ToolClientError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _scrub(value: Any, *, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            low = str(key).lower()
            if any(part in low for part in _SECRET_PARTS):
                continue
            if isinstance(item, str) and item in secrets:
                continue
            out[key] = _scrub(item, secrets=secrets)
        return out
    if isinstance(value, list):
        return [_scrub(item, secrets=secrets) for item in value]
    if isinstance(value, str) and value in secrets:
        return "[redacted]"
    return value


class ToolClient:
    """POST /v1/tools/<name> with AEA_MODEL_TOKEN. No other scopes."""

    def __init__(
        self,
        *,
        model_token: str,
        base_url: str = DEFAULT_CONTROL_URL,
        agent_id: str = AGENT_ID,
        constitution_version: str = CONSTITUTION_VERSION,
        timeout: float = 30.0,
    ) -> None:
        if not model_token:
            raise ValueError("model_token is required")
        self._model_token = model_token
        self._base_url = base_url.rstrip("/")
        self._agent_id = agent_id
        self._constitution_version = constitution_version
        self._timeout = timeout

    def call(
        self,
        name: str,
        body: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        if name not in CALLABLE_MODEL_TOOLS:
            raise ToolClientError(HttpCode.FORBIDDEN, f"tool {name} is not permitted")
        cid = correlation_id or str(uuid4())
        headers = {
            "Authorization": f"Bearer {self._model_token}",
            "X-AEA-Agent-Id": self._agent_id,
            "X-AEA-Agent-Version": __version__,
            "X-AEA-Constitution-Version": self._constitution_version,
            "X-AEA-Correlation-Id": cid,
            "Content-Type": "application/json",
        }
        payload = dict(body or {})
        key = idempotency_key or payload.get("idempotency_key")
        if key:
            headers["X-AEA-Idempotency-Key"] = str(key)
        try:
            response = httpx.post(
                f"{self._base_url}/v1/tools/{name}",
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise ToolClientError(HttpCode.NETWORK_FAILURE, "control plane unreachable") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise ToolClientError(HttpCode.INTERNAL_ERROR, "malformed control response") from exc
        if not isinstance(data, dict):
            raise ToolClientError(HttpCode.INTERNAL_ERROR, "malformed control response")
        scrubbed = _scrub(data, secrets=(self._model_token,))
        if not isinstance(scrubbed, dict):
            raise ToolClientError(HttpCode.INTERNAL_ERROR, "malformed control response")
        return scrubbed
