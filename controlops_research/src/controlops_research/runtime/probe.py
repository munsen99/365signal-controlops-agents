"""Host-side LM Studio readiness. This module does not run inside the jail."""

from __future__ import annotations

import json
from collections.abc import Mapping

from .config import LMSTUDIO_BASE, PROBE_TIMEOUT_SECONDS, required_model
from .errors import RuntimeFailure
from .http_client import Transport, exchange


class LMStudioProbe:
    """GET /v1/models on the host and require the exact configured id."""

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        base: str = LMSTUDIO_BASE,
        environ: Mapping[str, str] | None = None,
        timeout: float = PROBE_TIMEOUT_SECONDS,
    ) -> None:
        self.transport = transport
        self.base = base.rstrip("/")
        self.environ = environ
        self.timeout = timeout

    def require_ready(self) -> str:
        model = required_model(self.environ)
        status, payload = exchange(
            "GET",
            f"{self.base}/v1/models",
            None,
            self.timeout,
            transport=self.transport,
        )
        if status != 200:
            raise RuntimeFailure("ENDPOINT_UNAVAILABLE", f"HTTP {status}")
        return _require_exact_id(payload, model)


def _require_exact_id(payload: bytes, model: str) -> str:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "models body is not JSON") from error
    if not isinstance(document, dict):
        raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "models body is not an object")
    rows = document.get("data")
    if not isinstance(rows, list):
        raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "models data is not a list")
    found = False
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise RuntimeFailure("MODEL_STATE_INCOMPATIBLE", "model row shape")
        if row["id"] == model:
            found = True
    if not found:
        raise RuntimeFailure("REQUIRED_MODEL_MISSING", model)
    return model
