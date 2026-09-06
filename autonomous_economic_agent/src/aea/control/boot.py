"""Startup validation for constitution/profile/plugin identity."""

from __future__ import annotations

from pathlib import Path

import yaml

from aea import (
    AGENT_ID,
    CONSTITUTION_VERSION,
    CALLABLE_MODEL_TOOLS,
    POLICY_VERSION,
)

_SECRET_NEEDLES = (
    "AEA_MODEL_TOKEN",
    "AEA_CONTROL_TOKEN",
    "AEA_SIGNER_TOKEN",
    "AEA_SIGNER_HMAC_KEY",
    "AEA_WALLET_DEBIT_TOKEN",
    "AEA_WALLET_CREDIT_TOKEN",
    "AEA_SUPERVISOR_TOKEN",
    "AEA_MARKETPLACE_TOKEN",
    "Bearer ",
)


class BootError(RuntimeError):
    """Profile/constitution/plugin failed startup validation."""


def validate_boot(
    *,
    soul_path: Path,
    agent_yaml: Path,
    profile_config: Path,
    plugin_yaml: Path,
    run_input: Path | None = None,
    expected_agent_id: str = AGENT_ID,
    expected_constitution: str = CONSTITUTION_VERSION,
) -> None:
    soul = soul_path.read_text(encoding="utf-8")
    if expected_constitution not in soul:
        raise BootError("SOUL.md constitution version mismatch")
    if f"Agent ID: {expected_agent_id}" not in soul and f"agent_id: {expected_agent_id}" not in soul:
        if expected_agent_id not in soul:
            raise BootError("SOUL.md agent identity mismatch")
    _forbid_secrets(soul_path, soul)

    agent = yaml.safe_load(agent_yaml.read_text(encoding="utf-8"))
    if agent["agent"]["agent_id"] != expected_agent_id:
        raise BootError("agent.yaml agent_id mismatch")
    if agent["identity"]["constitution_version"] != expected_constitution:
        raise BootError("agent.yaml constitution version mismatch")
    if list(agent["tools"]["allow"]) != list(CALLABLE_MODEL_TOOLS):
        raise BootError("agent.yaml tools.allow does not match callable model tools")
    _forbid_secrets(agent_yaml, agent_yaml.read_text(encoding="utf-8"))

    cfg_text = profile_config.read_text(encoding="utf-8")
    cfg = yaml.safe_load(cfg_text)
    disabled = set(cfg["agent"]["disabled_toolsets"])
    required = {"file", "terminal", "web", "process", "delegation", "memory", "cronjob"}
    if not required <= disabled:
        raise BootError("profile config missing required disabled_toolsets")
    if cfg["plugins"]["enabled"] != ["economic-agent"]:
        raise BootError("profile must enable only economic-agent")
    platform_toolsets = cfg.get("platform_toolsets", {})
    for platform in ("cli", "api_server"):
        if platform_toolsets.get(platform) != ["economic"]:
            raise BootError(f"profile platform_toolsets.{platform} must be [economic]")
    _forbid_secrets(profile_config, cfg_text)

    plugin = yaml.safe_load(plugin_yaml.read_text(encoding="utf-8"))
    if plugin.get("name") != "economic-agent":
        raise BootError("plugin.yaml name mismatch")
    if list(plugin.get("provides_tools") or []) != list(CALLABLE_MODEL_TOOLS):
        raise BootError("plugin.yaml must provide the economic tools plus read-only web research")
    _forbid_secrets(plugin_yaml, plugin_yaml.read_text(encoding="utf-8"))

    if run_input is not None:
        _forbid_secrets(run_input, run_input.read_text(encoding="utf-8"))

    # Policy version is operator config, not constitution, but must remain Phase A.
    if POLICY_VERSION != "policy/v0.1.0":
        raise BootError("unexpected policy version constant")


def _forbid_secrets(path: Path, text: str) -> None:
    for needle in _SECRET_NEEDLES:
        if needle in text:
            raise BootError(f"{path.name} must not contain {needle}")
