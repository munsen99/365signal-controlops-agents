"""Hermes profile, agent identity, run-input, and compose symlink."""

from __future__ import annotations

from pathlib import Path

import yaml

from aea import (
    CALLABLE_MODEL_TOOLS,
    DECLARED_UNIMPLEMENTED_TOOLS,
    IMPLEMENTED_ECONOMIC_TOOLS,
    NINE_TOOLS,
    READONLY_WEB_TOOLS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = REPO_ROOT / "agents" / "economic-agent"
PROFILE = AGENT_DIR / "runtime" / "config.yaml"
AGENT_YAML = AGENT_DIR / "agent.yaml"
RUN_INPUT = AGENT_DIR / "templates" / "run-input.yaml"
COMPOSE_LINK = REPO_ROOT / "ops" / "compose.economic.yaml"
COMPOSE_CANONICAL = REPO_ROOT / "autonomous_economic_agent" / "ops" / "compose.economic.yaml"
ECONOMIC_CLI = REPO_ROOT / "scripts" / "economic"

REQUIRED_DISABLED = {"file", "terminal", "process"}

FORBIDDEN_IN_RUN_INPUT = (
    "mock:job:",
    "profitable-summary",
    "unprofitable-research",
    "external_reference",
    "AEA_MODEL_TOKEN",
    "AEA_SIGNER_HMAC_KEY",
    "AEA_SIGNER_TOKEN",
    "opportunity_id",
    "expected_revenue",
)


def test_disabled_toolsets_include_file_terminal_web_process() -> None:
    cfg = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    disabled = set(cfg["agent"]["disabled_toolsets"])
    assert REQUIRED_DISABLED <= disabled
    assert "web" not in disabled
    assert "search" not in disabled
    assert "browser" not in disabled
    assert cfg["platform_toolsets"]["cli"] == ["economic"]
    assert cfg["platform_toolsets"]["api_server"] == ["economic"]
    assert (cfg.get("plugins") or {}).get("entries", {}).get("economic-agent", {}).get(
        "allow_tool_override"
    ) is True
    assert cfg["plugins"]["enabled"] == ["economic-agent"]
    profile_text = PROFILE.read_text(encoding="utf-8")
    assert "AEA_MODEL_TOKEN" not in profile_text
    assert "AEA_SIGNER_HMAC_KEY" not in profile_text
    assert "AEA_SIGNER_TOKEN" not in profile_text
    assert "Bearer" not in profile_text


def test_profile_installer_pins_tui_and_uses_portable_plugin_copy() -> None:
    text = ECONOMIC_CLI.read_text(encoding="utf-8")
    assert "HERMES_TUI_TOOLSETS=economic" in text
    assert "AEA_MODEL_TOKEN_FILE=/opt/data/profiles/economic-agent/.aea-model-token" in text
    assert "install -m 0600 \"${AEA_DIR}/hermes_plugin/plugin.yaml\"" in text
    assert "ln -sfn /workspace/autonomous_economic_agent/hermes_plugin" not in text


def test_agent_yaml_declares_authoritative_capabilities() -> None:
    doc = yaml.safe_load(AGENT_YAML.read_text(encoding="utf-8"))
    assert doc["tools"]["allow"] == list(CALLABLE_MODEL_TOOLS)
    assert DECLARED_UNIMPLEMENTED_TOOLS == ()
    assert set(READONLY_WEB_TOOLS).isdisjoint(IMPLEMENTED_ECONOMIC_TOOLS)
    assert "terminal" in doc["tools"]["deny"]
    assert "browser_automation" in doc["tools"]["deny"]
    assert "computer_use" in doc["tools"]["deny"]
    assert "email" in doc["tools"]["deny"]
    assert "external_messaging" in doc["tools"]["deny"]
    assert "signer" in doc["tools"]["deny"]
    assert doc["security"]["wallet_key_access"] is False
    assert doc["execution_policy"]["policy_engine_is_final_spend_control"] is True
    assert doc["runtime"]["human_review_required"] is False
    # execution_policy is a sibling of security, not nested (do not copy validator indent bug)
    assert "execution_policy" not in doc["security"]
    assert "max_tool_calls" in doc["execution_policy"]


def test_run_input_has_no_job_selection_hints() -> None:
    text = RUN_INPUT.read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in FORBIDDEN_IN_RUN_INPUT:
        assert needle.lower() not in lowered
    data = yaml.safe_load(text)
    assert data["agent_id"] == "economic-agent"
    assert "autonomous economic work cycle" in data["instructions"]
    assert "available tools" in data["instructions"]
    for tool in NINE_TOOLS:
        assert tool not in data["instructions"]


def test_validator_profile_is_unchanged() -> None:
    validator = REPO_ROOT / "agents" / "controlops-msft-validator" / "agent.yaml"
    doc = yaml.safe_load(validator.read_text(encoding="utf-8"))
    assert doc["agent"]["agent_id"] == "controlops-msft-validator"
    assert "terminal" in doc["tools"]["allow"]
    assert "web_search" in doc["tools"]["allow"]
    assert "find_jobs" not in doc["tools"]["allow"]


def test_compose_symlink_points_at_canonical_file() -> None:
    assert COMPOSE_LINK.is_symlink()
    assert COMPOSE_LINK.resolve() == COMPOSE_CANONICAL.resolve()
    text = COMPOSE_CANONICAL.read_text(encoding="utf-8")
    assert "name: controlops-economic" in text
    assert "live wallet" in text.lower() or "Do not attach a live wallet" in text
    assert "solders" not in text
    assert "solana" not in text.lower() or "No Solana" in text or "until gated" in text
