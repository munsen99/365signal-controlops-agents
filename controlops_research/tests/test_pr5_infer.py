"""Infer adapter contract. No live LM Studio."""

from __future__ import annotations

import json
import threading

import pytest

from controlops_research.runtime.errors import RuntimeFailure
from controlops_research.runtime.http_client import exchange
from controlops_research.runtime.infer import infer
from tests.support import FakeTransport, chat_body, models_body, ready_environ

MODEL = "qwen3.8-27b"
MESSAGES = [{"role": "user", "content": "Reply with the single token: PONG"}]


def _serve(ids: list[str], *, status: int = 200, completion: bytes | None = None, post_status: int = 200):
    completion = chat_body(MODEL) if completion is None else completion

    def handler(method, url, body, timeout):
        if method == "GET":
            return status, models_body(ids)
        return post_status, completion

    return FakeTransport(handler)


def test_forbidden_management_urls_make_no_socket_call():
    transport = FakeTransport(lambda *args: (_ for _ in ()).throw(AssertionError("socket")))
    for path in (
        "/v1/models/load",
        "/api/unload",
        "/v1/models/eject",
        "/v1/models/evict",
    ):
        with pytest.raises(RuntimeFailure) as caught:
            exchange("POST", f"http://127.0.0.1:1234{path}", b"{}", 1, transport=transport)
        assert caught.value.code == "CONFIG_INVALID"
    assert transport.calls == []


def test_infer_posts_the_required_model_id(tmp_path):
    transport = _serve([MODEL, "qwen3.8-27b-obliterated"])
    result = infer(
        MESSAGES, 3, transport=transport, workspace=tmp_path, environ=ready_environ(),
    )
    posts = [call for call in transport.calls if call["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["url"].endswith("/v1/chat/completions")
    assert json.loads(posts[0]["body"])["model"] == MODEL
    assert posts[0]["timeout"] == 3
    assert result.text == "PONG"
    assert result.finish_reason == "stop"
    assert result.model == MODEL


def test_second_infer_while_locked_is_contention(tmp_path):
    started = threading.Event()
    release = threading.Event()

    def handler(method, url, body, timeout):
        if method == "GET":
            return 200, models_body([MODEL])
        started.set()
        assert release.wait(5)
        return 200, chat_body(MODEL)

    transport = FakeTransport(handler)
    errors = []

    def first():
        try:
            infer(MESSAGES, 5, transport=transport, workspace=tmp_path, environ=ready_environ())
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=first)
    worker.start()
    assert started.wait(5)
    with pytest.raises(RuntimeFailure) as caught:
        infer(MESSAGES, 5, transport=transport, workspace=tmp_path, environ=ready_environ())
    assert caught.value.code == "MODEL_CONTENTION"
    release.set()
    worker.join(5)
    assert not worker.is_alive()
    assert errors == []
    posts = [call for call in transport.calls if call["method"] == "POST"]
    assert len(posts) == 1


def test_recorded_urls_are_only_models_get_and_chat_post(tmp_path):
    transport = _serve([MODEL])
    infer(MESSAGES, 2, transport=transport, workspace=tmp_path, environ=ready_environ())
    methods = {(call["method"], call["url"].split("/", 3)[-1]) for call in transport.calls}
    assert methods == {("GET", "v1/models"), ("POST", "v1/chat/completions")}


def test_ready_failure_performs_zero_posts(tmp_path):
    transport = _serve(["qwen3.8-27b-obliterated"])
    with pytest.raises(RuntimeFailure) as caught:
        infer(MESSAGES, 2, transport=transport, workspace=tmp_path, environ=ready_environ())
    assert caught.value.code == "REQUIRED_MODEL_MISSING"
    assert [call["method"] for call in transport.calls] == ["GET"]


def test_non_200_is_endpoint_unavailable(tmp_path):
    transport = _serve([MODEL], post_status=503, completion=b"busy")
    with pytest.raises(RuntimeFailure) as caught:
        infer(MESSAGES, 2, transport=transport, workspace=tmp_path, environ=ready_environ())
    assert caught.value.code == "ENDPOINT_UNAVAILABLE"


def test_empty_choices_and_wrong_echo_are_payload_failures(tmp_path):
    empty = FakeTransport(lambda method, url, body, timeout: (
        (200, models_body([MODEL])) if method == "GET"
        else (200, json.dumps({"model": MODEL, "choices": []}).encode())
    ))
    with pytest.raises(RuntimeFailure) as caught:
        infer(MESSAGES, 2, transport=empty, workspace=tmp_path, environ=ready_environ())
    assert caught.value.code == "MODEL_STATE_INCOMPATIBLE"

    mismatch = FakeTransport(lambda method, url, body, timeout: (
        (200, models_body([MODEL])) if method == "GET"
        else (200, chat_body("other-model"))
    ))
    with pytest.raises(RuntimeFailure) as caught:
        infer(MESSAGES, 2, transport=mismatch, workspace=tmp_path, environ=ready_environ())
    assert caught.value.code == "MODEL_STATE_INCOMPATIBLE"


def test_missing_timeout_and_missing_model_do_not_call_http(tmp_path):
    transport = FakeTransport(lambda *args: (_ for _ in ()).throw(AssertionError("HTTP")))
    with pytest.raises(RuntimeFailure) as caught:
        infer(MESSAGES, 0, transport=transport, workspace=tmp_path, environ=ready_environ())
    assert caught.value.code == "CONFIG_INVALID"
    with pytest.raises(RuntimeFailure) as caught:
        infer(MESSAGES, 2, transport=transport, workspace=tmp_path, environ={})
    assert caught.value.code == "CONFIG_INVALID"
    with pytest.raises(RuntimeFailure) as caught:
        infer(MESSAGES, 2, transport=transport, workspace=tmp_path, environ={"CONTROLOPS_REQUIRED_MODEL": "  "})
    assert caught.value.code == "CONFIG_INVALID"
    assert transport.calls == []


def test_lock_released_after_failed_infer_allows_the_next(tmp_path):
    calls = {"posts": 0}

    def handler(method, url, body, timeout):
        if method == "GET":
            return 200, models_body([MODEL])
        calls["posts"] += 1
        if calls["posts"] == 1:
            return 500, b"no"
        return 200, chat_body(MODEL, text="ok")

    transport = FakeTransport(handler)
    with pytest.raises(RuntimeFailure) as caught:
        infer(MESSAGES, 2, transport=transport, workspace=tmp_path, environ=ready_environ())
    assert caught.value.code == "ENDPOINT_UNAVAILABLE"
    result = infer(MESSAGES, 2, transport=transport, workspace=tmp_path, environ=ready_environ())
    assert result.text == "ok"
    assert result.model == MODEL
