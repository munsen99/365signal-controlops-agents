"""Implemented economic-tool contracts, registration, and extra='forbid'."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import yaml

from aea import (
    CALLABLE_MODEL_TOOLS,
    DECLARED_ECONOMIC_TOOLS,
    DECLARED_UNIMPLEMENTED_TOOLS,
    IMPLEMENTED_ECONOMIC_TOOLS,
    NINE_TOOLS,
    READONLY_WEB_TOOLS,
)
from aea.control.freeze import MUTATING_TOOLS, OBSERVE_TOOLS
from aea.control.schemas import TOOL_MODELS

REPO = Path(__file__).resolve().parents[3]
PLUGIN_YAML = REPO / "autonomous_economic_agent" / "hermes_plugin" / "plugin.yaml"
PLUGIN_PY = REPO / "autonomous_economic_agent" / "hermes_plugin" / "__init__.py"
AGENT_YAML = REPO / "agents" / "economic-agent" / "agent.yaml"


def test_plugin_yaml_matches_implemented_tools() -> None:
    doc = yaml.safe_load(PLUGIN_YAML.read_text(encoding="utf-8"))
    assert doc["provides_tools"] == list(CALLABLE_MODEL_TOOLS)
    assert len(doc["provides_tools"]) == 21
    assert len(set(doc["provides_tools"])) == 21
    assert list(IMPLEMENTED_ECONOMIC_TOOLS) == doc["provides_tools"][:19]


def test_agent_yaml_allow_matches_declared_capability_contract() -> None:
    doc = yaml.safe_load(AGENT_YAML.read_text(encoding="utf-8"))
    assert doc["tools"]["allow"] == list(CALLABLE_MODEL_TOOLS)
    assert "web_search" in doc["tools"]["allow"]
    assert "web_extract" in doc["tools"]["allow"]
    assert "browser_automation" in doc["tools"]["deny"]
    assert "computer_use" in doc["tools"]["deny"]
    assert "terminal" in doc["tools"]["deny"]
    assert "email" in doc["tools"]["deny"]
    assert "external_messaging" in doc["tools"]["deny"]
    assert "web_search" not in doc["tools"]["deny"]
    assert "web_extract" not in doc["tools"]["deny"]


def test_plugin_register_only_loops_implemented_tools() -> None:
    tree = ast.parse(PLUGIN_PY.read_text(encoding="utf-8"))
    registered: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "register_tool":
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Name):
                        registered.append(kw.value.id)
    # register_tool(name=name, ...) inside the implemented allow-list loop.
    src = PLUGIN_PY.read_text(encoding="utf-8")
    assert "for name in CALLABLE_MODEL_TOOLS" in src
    assert "override=name in READONLY_WEB_TOOLS" in src
    assert "signer" not in src.lower() or "AEA_SIGNER" not in src
    assert "ctx.register_tool" in src
    assert src.count("ctx.register_tool") == 1


def test_plugin_does_not_import_aea() -> None:
    src = PLUGIN_PY.read_text(encoding="utf-8")
    assert "import aea" not in src
    assert "from aea" not in src


def test_plugin_has_no_generic_http_escape() -> None:
    src = PLUGIN_PY.read_text(encoding="utf-8")
    for needle in ("call_api", "http_request", "execute", "shell", "fetch_url"):
        assert needle not in src
    assert "/v1/tools/" in src


def test_plugin_schemas_forbid_additional_properties() -> None:
    spec = importlib.util.spec_from_file_location("economic_hermes_plugin", PLUGIN_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert tuple(mod.NINE_TOOLS) == NINE_TOOLS
    assert tuple(mod.IMPLEMENTED_ECONOMIC_TOOLS) == IMPLEMENTED_ECONOMIC_TOOLS
    assert tuple(mod.READONLY_WEB_TOOLS) == READONLY_WEB_TOOLS
    assert tuple(mod.CALLABLE_MODEL_TOOLS) == CALLABLE_MODEL_TOOLS
    for name, schema in mod._SCHEMAS.items():
        assert schema["parameters"]["additionalProperties"] is False
        assert schema["name"] == name
    assert set(mod._SCHEMAS) == set(CALLABLE_MODEL_TOOLS)
    assert mod._SCHEMAS["get_financial_state"]["parameters"]["properties"] == {}


def test_plugin_registers_exactly_the_economic_toolset() -> None:
    spec = importlib.util.spec_from_file_location("economic_hermes_plugin_register", PLUGIN_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class Context:
        def __init__(self) -> None:
            self.hooks: list[tuple[str, object]] = []
            self.tools: list[dict] = []

        def register_hook(self, name: str, handler: object) -> None:
            self.hooks.append((name, handler))

        def register_tool(self, **kwargs: object) -> None:
            self.tools.append(kwargs)

    ctx = Context()
    mod.register(ctx)
    assert [item["name"] for item in ctx.tools] == list(CALLABLE_MODEL_TOOLS)
    assert {item["toolset"] for item in ctx.tools} == {"economic"}
    assert not {"project_create", "project_list", "project_switch"} & {
        item["name"] for item in ctx.tools
    }
    assert not {
        "terminal",
        "file",
        "web",
        "browser",
        "browser_automation",
        "computer_use",
        "email",
        "external_messaging",
        "process",
        "code_execution",
    } & {item["name"] for item in ctx.tools}
    assert "web_search" in {item["name"] for item in ctx.tools}
    assert "web_extract" in {item["name"] for item in ctx.tools}
    assert [name for name, _ in ctx.hooks] == ["pre_tool_call"]


def test_all_declared_capabilities_are_implemented() -> None:
    assert DECLARED_ECONOMIC_TOOLS == IMPLEMENTED_ECONOMIC_TOOLS
    assert DECLARED_UNIMPLEMENTED_TOOLS == ()
    assert len(IMPLEMENTED_ECONOMIC_TOOLS) == 19
    assert CALLABLE_MODEL_TOOLS == IMPLEMENTED_ECONOMIC_TOOLS + READONLY_WEB_TOOLS
    assert set(TOOL_MODELS) == set(CALLABLE_MODEL_TOOLS)
    assert MUTATING_TOOLS.isdisjoint(OBSERVE_TOOLS)
    assert MUTATING_TOOLS | OBSERVE_TOOLS == set(CALLABLE_MODEL_TOOLS)


def test_declared_but_unimplemented_capabilities_fail_closed() -> None:
    spec = importlib.util.spec_from_file_location("economic_plugin_fail_closed", PLUGIN_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(DECLARED_UNIMPLEMENTED_TOOLS).isdisjoint(mod._SCHEMAS)
    for name in DECLARED_UNIMPLEMENTED_TOOLS:
        assert mod.on_pre_tool_call(tool_name=name)["action"] == "block"


def test_plugin_resolves_profile_local_model_token_without_active_secret_scope(
    monkeypatch, tmp_path: Path
) -> None:
    profile = tmp_path / "economic-agent"
    plugin = profile / "plugins" / "economic-agent" / "__init__.py"
    plugin.parent.mkdir(parents=True)
    plugin.write_text(PLUGIN_PY.read_text(encoding="utf-8"), encoding="utf-8")
    token_file = profile / ".aea-model-token"
    token_file.write_text("profile-private-token\n", encoding="utf-8")

    secret_scope = types.ModuleType("agent.secret_scope")
    secret_scope.get_secret = lambda name, default="": default
    agent = types.ModuleType("agent")
    agent.secret_scope = secret_scope
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.secret_scope", secret_scope)
    monkeypatch.delenv("AEA_MODEL_TOKEN", raising=False)
    monkeypatch.delenv("AEA_MODEL_TOKEN_FILE", raising=False)

    spec = importlib.util.spec_from_file_location("installed_economic_plugin", plugin)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._model_token() == "profile-private-token"


def test_plugin_profile_local_model_token_rejects_symlink(monkeypatch, tmp_path: Path) -> None:
    profile = tmp_path / "economic-agent"
    plugin = profile / "plugins" / "economic-agent" / "__init__.py"
    plugin.parent.mkdir(parents=True)
    plugin.write_text(PLUGIN_PY.read_text(encoding="utf-8"), encoding="utf-8")
    source = tmp_path / "token"
    source.write_text("must-not-load\n", encoding="utf-8")
    (profile / ".aea-model-token").symlink_to(source)

    secret_scope = types.ModuleType("agent.secret_scope")
    secret_scope.get_secret = lambda name, default="": default
    agent = types.ModuleType("agent")
    agent.secret_scope = secret_scope
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.secret_scope", secret_scope)
    monkeypatch.delenv("AEA_MODEL_TOKEN", raising=False)
    monkeypatch.delenv("AEA_MODEL_TOKEN_FILE", raising=False)

    spec = importlib.util.spec_from_file_location("symlinked_token_plugin", plugin)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._model_token() == ""
