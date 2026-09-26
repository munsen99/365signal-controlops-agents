"""Dashboard plugin is read-only and cannot reach signer/debit capability."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import types
from pathlib import Path
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_API = ROOT / "dashboard_plugin" / "dashboard" / "plugin_api.py"
PLUGIN_JS = ROOT / "dashboard_plugin" / "dashboard" / "dist" / "index.js"
PLUGIN_SANITIZE = ROOT / "dashboard_plugin" / "dashboard" / "sanitize.js"
MANIFEST = ROOT / "dashboard_plugin" / "dashboard" / "manifest.json"


def _load_plugin_api():
    if "fastapi" not in sys.modules:
        fake = types.ModuleType("fastapi")

        class APIRouter:
            def __init__(self) -> None:
                self.routes: list[tuple[str, str]] = []

            def get(self, path: str):
                def deco(fn):
                    self.routes.append(("GET", path))
                    return fn

                return deco

        fake.APIRouter = APIRouter
        responses = types.ModuleType("fastapi.responses")

        class JSONResponse:
            def __init__(self, content, status_code=200):
                self.body = content
                self.status_code = status_code

        responses.JSONResponse = JSONResponse
        fake.responses = responses
        sys.modules["fastapi"] = fake
        sys.modules["fastapi.responses"] = responses
    spec = importlib.util.spec_from_file_location("aea_dashboard_plugin_api", PLUGIN_API)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_manifest_is_observability_only() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["name"] == "aea"
    assert data["label"] == "Economic Agent"
    assert data["tab"]["path"] == "/aea"
    assert data["api"] == "plugin_api.py"


def test_plugin_api_declares_only_get_status() -> None:
    tree = ast.parse(PLUGIN_API.read_text(encoding="utf-8"))
    methods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(target, ast.Attribute) and target.attr.lower() in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "api_route",
                }:
                    methods.append(target.attr.lower())
    assert methods == ["get"]
    source = PLUGIN_API.read_text(encoding="utf-8")
    for needle in (
        "AEA_SIGNER_TOKEN",
        "AEA_WALLET_DEBIT_TOKEN",
        "AEA_SIGNER_HMAC_KEY",
        "AEA_SUPERVISOR_TOKEN",
        "AEA_MODEL_TOKEN",
        "@router.post",
        "@router.put",
        "@router.delete",
        "@router.patch",
    ):
        assert needle not in source
    assert "FORBIDDEN_PATH_PARTS" in source
    assert 'method="GET"' in source or "method='GET'" in source


def test_js_never_renders_html_or_calls_signer() -> None:
    js = PLUGIN_JS.read_text(encoding="utf-8")
    for needle in (
        "innerHTML",
        "dangerouslySetInnerHTML",
        "document.write",
        "eval(",
        "/v1/sign",
        "/v1/wallet/debit",
        "/v1/admin/",
        "unfreeze",
        "enable-signer",
    ):
        assert needle not in js
    assert "visibilitychange" in js
    assert "8000" in js
    assert "safeText" in js
    assert "OBSERVATION DEGRADED" in js
    assert "last-known" in js.lower() or "Last-known" in js
    assert "context_id" in js


def test_sanitize_js_strips_tags() -> None:
    text = PLUGIN_SANITIZE.read_text(encoding="utf-8")
    assert "TAG_RE" in text
    assert "safeDisplayText" in text
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        return
    result = subprocess.run(
        [node, "--test", str(ROOT / "dashboard_plugin" / "dashboard" / "sanitize.test.mjs")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_plugin_fetch_is_get_only_and_loopback(monkeypatch) -> None:
    mod = _load_plugin_api()
    monkeypatch.setenv("AEA_OBSERVABILITY_TOKEN", "obs-token")
    monkeypatch.setenv("AEA_CONTROL_URL", "http://127.0.0.1:18700")
    seen: dict[str, str] = {}

    class DummyResp:
        status = 200

        def read(self) -> bytes:
            return b'{"ok":true,"agent":{"state":"idle"},"recent_events":[]}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=0):
        seen["method"] = request.get_method()
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return DummyResp()

    monkeypatch.setattr(mod, "urlopen", fake_urlopen)
    status, body = mod.fetch_observability_status()
    assert status == 200
    assert seen["method"] == "GET"
    assert seen["url"].endswith("/observability/status")
    assert "sign" not in seen["url"]
    assert seen["timeout"] == mod.REQUEST_TIMEOUT_SECONDS
    assert body["ok"] is True


def test_plugin_rejects_non_loopback_control(monkeypatch) -> None:
    mod = _load_plugin_api()
    monkeypatch.setenv("AEA_OBSERVABILITY_TOKEN", "obs-token")
    monkeypatch.setenv("AEA_CONTROL_URL", "http://evil.example:18700")
    status, body = mod.fetch_observability_status()
    assert status == 503
    assert body["agent"]["state"] == "offline"


def test_plugin_timeout_is_stale_offline(monkeypatch) -> None:
    mod = _load_plugin_api()
    monkeypatch.setenv("AEA_OBSERVABILITY_TOKEN", "obs-token")
    monkeypatch.setenv("AEA_CONTROL_URL", "http://127.0.0.1:18700")

    def boom(request, timeout=0):
        raise URLError("timed out")

    monkeypatch.setattr(mod, "urlopen", boom)
    status, body = mod.fetch_observability_status()
    assert status == 504
    assert body["code"] == "TIMEOUT"
    assert body["agent"]["state"] == "offline"
    assert body["agent"]["health"] != "healthy"


def test_plugin_cannot_target_signer_path() -> None:
    mod = _load_plugin_api()
    try:
        mod._assert_read_only_target("http://127.0.0.1:18702/v1/sign")
        raise AssertionError("signer path must be rejected")
    except ValueError:
        pass
    try:
        mod._assert_read_only_target("http://127.0.0.1:18704/v1/wallet/debit")
        raise AssertionError("debit path must be rejected")
    except ValueError:
        pass
