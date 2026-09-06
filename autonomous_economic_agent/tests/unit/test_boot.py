"""Profile/constitution boot validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aea import DECLARED_ECONOMIC_TOOLS
from aea.control.boot import BootError, validate_boot

REPO = Path(__file__).resolve().parents[3]
SOUL = REPO / "autonomous_economic_agent" / "constitution" / "SOUL.md"
AGENT = REPO / "agents" / "economic-agent" / "agent.yaml"
PROFILE = REPO / "agents" / "economic-agent" / "runtime" / "config.yaml"
PLUGIN = REPO / "autonomous_economic_agent" / "hermes_plugin" / "plugin.yaml"
RUN_INPUT = REPO / "agents" / "economic-agent" / "templates" / "run-input.yaml"


def test_validate_boot_accepts_canonical_tree() -> None:
    validate_boot(
        soul_path=SOUL,
        agent_yaml=AGENT,
        profile_config=PROFILE,
        plugin_yaml=PLUGIN,
        run_input=RUN_INPUT,
    )


def test_validate_boot_rejects_constitution_mismatch(tmp_path: Path) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text(SOUL.read_text(encoding="utf-8").replace("constitution/v0.1.0", "constitution/v9.9.9"), encoding="utf-8")
    with pytest.raises(BootError, match="constitution version"):
        validate_boot(
            soul_path=soul,
            agent_yaml=AGENT,
            profile_config=PROFILE,
            plugin_yaml=PLUGIN,
        )


def test_validate_boot_rejects_token_in_soul(tmp_path: Path) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text(SOUL.read_text(encoding="utf-8") + "\nAEA_MODEL_TOKEN=leak\n", encoding="utf-8")
    with pytest.raises(BootError, match="AEA_MODEL_TOKEN"):
        validate_boot(
            soul_path=soul,
            agent_yaml=AGENT,
            profile_config=PROFILE,
            plugin_yaml=PLUGIN,
        )


def test_open_question_1_disabled_toolsets_remain() -> None:
    text = PROFILE.read_text(encoding="utf-8")
    assert "file" in text and "terminal" in text and "web" in text and "process" in text
    assert "Do not re-enable terminal" in text


def test_validate_boot_rejects_unrestricted_api_server_toolsets(tmp_path: Path) -> None:
    cfg = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    cfg["platform_toolsets"]["api_server"] = ["hermes-api-server"]
    profile = tmp_path / "config.yaml"
    profile.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    agent_cfg = yaml.safe_load(AGENT.read_text(encoding="utf-8"))
    agent_cfg["tools"]["allow"] = list(DECLARED_ECONOMIC_TOOLS)
    agent = tmp_path / "agent.yaml"
    agent.write_text(yaml.safe_dump(agent_cfg), encoding="utf-8")
    with pytest.raises(BootError, match="platform_toolsets.api_server"):
        validate_boot(
            soul_path=SOUL,
            agent_yaml=agent,
            profile_config=profile,
            plugin_yaml=PLUGIN,
        )
