"""Deterministic fakes for PR5-R. These tests do not contact LM Studio."""

from __future__ import annotations

import json
from collections.abc import Callable


class FakeTransport:
    def __init__(self, handler: Callable[..., tuple[int, bytes]]) -> None:
        self.handler = handler
        self.calls: list[dict] = []

    def request(self, method: str, url: str, body: bytes | None, timeout: float):
        self.calls.append({"method": method, "url": url, "body": body, "timeout": timeout})
        return self.handler(method, url, body, timeout)


def models_body(ids: list[str]) -> bytes:
    return json.dumps({
        "object": "list",
        "data": [{"id": model_id, "object": "model", "owned_by": "test"} for model_id in ids],
    }).encode("utf-8")


def chat_body(model: str, text: str = "PONG", finish: str | None = "stop") -> bytes:
    return json.dumps({
        "model": model,
        "choices": [{
            "message": {"role": "assistant", "content": text},
            "finish_reason": finish,
        }],
    }).encode("utf-8")


def ready_environ(model: str = "qwen3.8-27b") -> dict[str, str]:
    return {"CONTROLOPS_REQUIRED_MODEL": model}
