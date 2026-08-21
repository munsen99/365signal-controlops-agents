"""Nine-tool contracts, plugin registration, and extra='forbid'."""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from aea import NINE_TOOLS

REPO = Path(__file__).resolve().parents[3]
PLUGIN_YAML = REPO / "autonomous_economic_agent" / "hermes_plugin" / "plugin.yaml"
PLUGIN_PY = REPO / "autonomous_economic_agent" / "hermes_plugin" / "__init__.py"
AGENT_YAML = REPO / "agents" / "economic-agent" / "agent.yaml"


def test_plugin_yaml_exactly_nine_names() -> None:
    doc = yaml.safe_load(PLUGIN_YAML.read_text(encoding="utf-8"))
    assert doc["provides_tools"] == list(NINE_TOOLS)
    assert len(doc["provides_tools"]) == 9
    assert len(set(doc["provides_tools"])) == 9


def test_agent_yaml_allow_matches_nine() -> None:
    doc = yaml.safe_load(AGENT_YAML.read_text(encoding="utf-8"))
    assert doc["tools"]["allow"] == list(NINE_TOOLS)


def test_plugin_register_only_loops_nine_tools() -> None:
    tree = ast.parse(PLUGIN_PY.read_text(encoding="utf-8"))
    registered: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "register_tool":
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Name):
                        registered.append(kw.value.id)
    # register_tool(name=name, ...) inside `for name in NINE_TOOLS`
    src = PLUGIN_PY.read_text(encoding="utf-8")
    assert "for name in NINE_TOOLS" in src
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
    import importlib.util

    spec = importlib.util.spec_from_file_location("economic_hermes_plugin", PLUGIN_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert tuple(mod.NINE_TOOLS) == NINE_TOOLS
    for name, schema in mod._SCHEMAS.items():
        assert schema["parameters"]["additionalProperties"] is False
        assert schema["name"] == name
    assert set(mod._SCHEMAS) == set(NINE_TOOLS)
    assert mod._SCHEMAS["get_financial_state"]["parameters"]["properties"] == {}
