"""Policy YAML, schema, and loader (wallet phase A only)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from decimal import Decimal

from aea.config import PolicyDocument, load_policy

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "autonomous_economic_agent" / "config"
POLICY_PATH = CONFIG_DIR / "policy.v1.yaml"
SCHEMA_PATH = CONFIG_DIR / "policy.schema.yaml"


def test_default_policy_loads_phase_a() -> None:
    loaded = load_policy()
    assert loaded.document.wallet_phase == "A"
    assert loaded.document.unit_of_account == "USDC"
    assert loaded.document.limits.max_outbound_usdc == Decimal("1.000000")
    assert loaded.document.limits.max_job_seconds == 120
    assert str(loaded.document.assets.sol_usdc_snapshot) in {"150.000000", "150"}
    assert loaded.document.cost_rates.compute_floor_usdc is not None
    assert loaded.document.destinations.allow_unclassified is False
    assert loaded.policy_hash
    assert len(loaded.policy_hash) == 64
    mock_escrow = loaded.classify("mock:counterparty:mkt-escrow")
    assert mock_escrow.allowed is True
    unknown = loaded.classify("solana:not-listed")
    assert unknown.allowed is False
    assert unknown.class_ == "unknown"


def test_policy_matches_json_schema() -> None:
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    instance = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(instance)


def test_policy_schema_rejects_extra_top_level_key() -> None:
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    instance = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    instance["force"] = True
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(instance)


def test_policy_document_forbids_extra_fields() -> None:
    raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    raw["force"] = True
    with pytest.raises(ValidationError):
        PolicyDocument.model_validate(raw)


def test_load_policy_accepts_phase_c_for_live_backend(tmp_path: Path) -> None:
    raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    raw["wallet_phase"] = "C"
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    dest = tmp_path / "destinations.yaml"
    dest.write_text((CONFIG_DIR / "destinations.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    raw["destinations"]["file"] = "destinations.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    loaded = load_policy(policy_path=path, destinations_path=dest)
    assert loaded.document.wallet_phase == "C"


def test_no_solana_or_solders_import() -> None:
    import aea
    import aea.config
    import aea.hashing
    import aea.types

    for module in (aea, aea.config, aea.hashing, aea.types):
        assert "solana" not in module.__dict__
        assert "solders" not in module.__dict__
