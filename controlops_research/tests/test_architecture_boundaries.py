"""Static contract for runtime source, not a substitute for runtime isolation.

Extend these checks alongside future capabilities. Docstrings/comments and bare
port integers are permitted; executable string literals are configuration
candidates. Indirect imports/computed configuration require later enforcement.
"""

import ast
from pathlib import Path
import re

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "src" / "controlops_research"
FORBIDDEN_CONFIG = re.compile(
    r"\b(?:economic_app|controlops_admin|aea_run|AEA_MODEL_TOKEN(?:_FILE)?)\b"
    r"|(?:~|/[^\s]*)?/\.config/controlops/economic(?:/|$)"
    r"|\.aea-model-token",
    re.IGNORECASE,
)
FORBIDDEN_ENDPOINT = re.compile(
    r"(?:https?://)?(?:[\w.-]+|\[[\da-f:]+\]):1870[0-5](?!\d)",
    re.IGNORECASE,
)


def boundary_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    violations = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names = [node.module or ""]
        if any(name == "aea" or name.startswith("aea.") for name in names):
            violations.append(f"line {node.lineno}: prohibited aea import")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            if FORBIDDEN_CONFIG.search(node.value) or FORBIDDEN_ENDPOINT.search(node.value):
                violations.append(f"line {node.lineno}: prohibited runtime target/configuration")
    return violations


def test_runtime_source_preserves_architecture_boundaries():
    files = sorted(SOURCE.rglob("*.py"))
    assert files, "Runtime source tree missing or empty"
    violations = [f"{path.relative_to(SOURCE)}: {issue}"
                  for path in files
                  for issue in boundary_violations(path.read_text(encoding="utf-8"))]
    assert not violations, "\n".join(violations)


def test_pr2_network_module_preserves_authority_and_dependency_boundary():
    source = (SOURCE / "fetch.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add(node.module or "")
    assert not imported.intersection({"requests", "httpx", "aiohttp", "urllib.request"})
    assert "from .policy import Decision, ReasonCode, UrlDecision, evaluate_url" in source
    assert "policy_data" not in source
    assert "getproxies" not in source and "urlopen" not in source
    assert "os.environ" not in source and "os.getenv" not in source


@pytest.mark.parametrize("source", [
    "import aea", "import aea.control as control", "from aea import types",
    "from aea.policy import service", "import os, aea",
    *[f'URL = "http://127.0.0.1:{port}"' for port in range(18700, 18706)],
    'URL = "https://localhost:18703/api"', 'HOST = "economic-control:18700"',
    'DSN = "postgresql://economic_app@localhost/research"',
    'DSN = "user=controlops_admin dbname=research"',
    'CONFIG = {"user": "economic_app"}', 'MOUNT = "/run/aea_run"',
    'SECRET = "~/.config/controlops/economic/token"',
    'SECRET = "/home/user/.config/controlops/economic/token"',
    'TOKEN = os.getenv("AEA_MODEL_TOKEN")',
])
def test_rejects_forbidden_dependencies_and_configuration(source):
    assert boundary_violations(source)


@pytest.mark.parametrize("source", [
    'BLOCKED_PORTS = {18700, 18701, 18702, 18703, 18704, 18705}',
    '# Never import aea or connect to http://127.0.0.1:18700\n',
    '"""Reject economic_app, controlops_admin, aea_run and http://127.0.0.1:18700."""',
    'def policy():\n    """Block http://127.0.0.1:18700."""\n    return False',
    'import pathlib\nfrom collections import Counter',
    'NAME = "controlops-research"',
])
def test_permits_documentation_and_blocked_port_integers(source):
    assert boundary_violations(source) == []
