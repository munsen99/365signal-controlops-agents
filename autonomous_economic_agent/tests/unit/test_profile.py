"""Hermes profile, agent identity, run-input, and compose symlink."""

from __future__ import annotations

from pathlib import Path

import yaml

from aea import NINE_TOOLS

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = REPO_ROOT / "agents" / "economic-agent"
PROFILE = AGENT_DIR / "runtime" / "config.yaml"
AGENT_YAML = AGENT_DIR / "agent.yaml"
RUN_INPUT = AGENT_DIR / "templates" / "run-input.yaml"
COMPOSE_LINK = REPO_ROOT / "ops" / "compose.economic.yaml"
COMPOSE_CANONICAL = REPO_ROOT / "autonomous_economic_agent" / "ops" / "compose.economic.yaml"

REQUIRED_DISABLED = {"file", "terminal", "web", "process"}

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
    assert cfg["platform_toolsets"]["cli"] == ["economic"]
    assert cfg["plugins"]["enabled"] == ["economic-agent"]
    profile_text = PROFILE.read_text(encoding="utf-8")
    assert "AEA_MODEL_TOKEN" not in profile_text
    assert "AEA_SIGNER_HMAC_KEY" not in profile_text
    assert "AEA_SIGNER_TOKEN" not in profile_text
    assert "Bearer" not in profile_text


def test_agent_yaml_nine_tools_only() -> None:
    doc = yaml.safe_load(AGENT_YAML.read_text(encoding="utf-8"))
    assert doc["tools"]["allow"] == list(NINE_TOOLS)
    assert "terminal" in doc["tools"]["deny"]
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
    assert "find_jobs" in data["instructions"]
    assert "Do not invent job IDs" in data["instructions"]


def test_compose_symlink_points_at_canonical_file() -> None:
    assert COMPOSE_LINK.is_symlink()
    assert COMPOSE_LINK.resolve() == COMPOSE_CANONICAL.resolve()
    text = COMPOSE_CANONICAL.read_text(encoding="utf-8")
    assert "name: controlops-economic" in text
    assert "live wallet" in text.lower() or "Do not attach a live wallet" in text
    assert "solders" not in text
    assert "solana" not in text.lower() or "No Solana" in text or "until gated" in text
