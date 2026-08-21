"""Non-economic LM Studio compatibility probes for Gate B.

This sends no economic tool calls and holds no economic credentials.  It
validates the OpenAI-compatible message wire shape before each request.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import httpx

from autonomous_economic_agent.hermes_plugin import NINE_TOOLS, _SCHEMAS

MODEL = "lmstudio-community/qwen3.6-35b-a3b"
ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"


def valid_content(content: Any) -> bool:
    return isinstance(content, str) or (
        isinstance(content, list)
        and all(isinstance(part, dict) and isinstance(part.get("type"), str) for part in content)
    )


def validate_messages(messages: list[dict[str, Any]]) -> None:
    for index, message in enumerate(messages):
        if not valid_content(message.get("content")):
            raise ValueError(
                f"message {index} ({message.get('role')}) has invalid content type "
                f"{type(message.get('content')).__name__}"
            )


def request_body(*, with_tools: bool) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are a compatibility probe. Do not call tools."},
        {
            "role": "user",
            "content": "Reply exactly TOOL_SCHEMAS_OK." if with_tools else "Reply exactly HERMES_READY.",
        },
    ]
    validate_messages(messages)
    body: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 65536,
        "reasoning_effort": "medium",
    }
    if with_tools:
        body["tools"] = [
            {"type": "function", "function": _SCHEMAS[name]} for name in NINE_TOOLS
        ]
    return body


def run_probe(*, with_tools: bool) -> dict[str, Any]:
    body = request_body(with_tools=with_tools)
    response = httpx.post(ENDPOINT, json=body, timeout=180.0)
    response.raise_for_status()
    payload = response.json()
    message = payload["choices"][0]["message"]
    return {
        "ok": True,
        "model_requested": MODEL,
        "model_returned": payload.get("model"),
        "tool_schema_count": len(body.get("tools", [])),
        "response_content_type": type(message.get("content")).__name__,
        "finish_reason": payload["choices"][0].get("finish_reason"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-tools", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_probe(with_tools=args.with_tools), sort_keys=True))


if __name__ == "__main__":
    main()
