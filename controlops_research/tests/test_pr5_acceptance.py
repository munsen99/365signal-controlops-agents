"""Jail, readiness, lock, and doctor checks. No live LM Studio."""

from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

import pytest

from controlops_research.runtime.config import required_model
from controlops_research.runtime.doctor import doctor
from controlops_research.runtime.errors import RuntimeFailure
from controlops_research.runtime.jail import bwrap_argv, exec_command
from controlops_research.runtime.probe import LMStudioProbe
from tests.support import FakeTransport, models_body, ready_environ

MODEL = "qwen3.8-27b"
SRC = Path(__file__).resolve().parents[1] / "src"


def test_unset_and_empty_required_model_is_config_invalid():
    with pytest.raises(RuntimeFailure) as caught:
        required_model({})
    assert caught.value.code == "CONFIG_INVALID"
    with pytest.raises(RuntimeFailure) as caught:
        required_model({"CONTROLOPS_REQUIRED_MODEL": ""})
    assert caught.value.code == "CONFIG_INVALID"


def test_share_net_env_cannot_change_jail_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLOPS_ALLOW_SHARED_NET", "1")
    argv = bwrap_argv(tmp_path, ["/usr/bin/true"])
    assert "--unshare-all" in argv
    assert "--share-net" not in argv
    assert os.environ["CONTROLOPS_ALLOW_SHARED_NET"] == "1"


def test_argv_binds_only_the_four_runtime_directories(tmp_path):
    argv = bwrap_argv(tmp_path, ["/usr/bin/true"])
    binds = [(argv[index + 1], argv[index + 2]) for index, token in enumerate(argv) if token == "--bind"]
    assert binds == [
        (str(tmp_path / "runtime" / name), f"/opt/data/workspace/runtime/{name}")
        for name in ("locks", "tmp", "out", "runs")
    ]
    assert argv.count("--ro-bind") == 1
    assert argv[argv.index("--ro-bind") + 1:argv.index("--ro-bind") + 3] == ["/usr", "/usr"]
    assert "/v1/models" not in argv
    assert "--share-net" not in argv


def test_exact_id_matches_and_near_match_does_not(tmp_path):
    exact = FakeTransport(lambda *args: (200, models_body([MODEL, "qwen3.8-27b-obliterated"])))
    probe = LMStudioProbe(transport=exact, environ=ready_environ())
    assert probe.require_ready() == MODEL

    near = FakeTransport(lambda *args: (200, models_body(["qwen3.8-27b-obliterated"])))
    with pytest.raises(RuntimeFailure) as caught:
        LMStudioProbe(transport=near, environ=ready_environ()).require_ready()
    assert caught.value.code == "REQUIRED_MODEL_MISSING"


def test_readiness_does_not_build_a_jail(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("bwrap was invoked")

    monkeypatch.setattr(subprocess, "run", explode)
    transport = FakeTransport(lambda *args: (200, models_body([MODEL])))
    assert LMStudioProbe(transport=transport, environ=ready_environ()).require_ready() == MODEL
    assert [call["method"] for call in transport.calls] == ["GET"]


def test_doctor_down_exits_nonzero_and_does_not_post(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/bwrap")

    def handler(method, url, body, timeout):
        if method == "POST":
            raise AssertionError("POST")
        raise OSError("connection refused")

    transport = FakeTransport(handler)
    assert doctor(transport=transport, environ=ready_environ(), workspace=tmp_path) == 1
    assert [call["method"] for call in transport.calls] == ["GET"]


def test_doctor_rejects_unknown_cli(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env.pop("CONTROLOPS_REQUIRED_MODEL", None)
    result = subprocess.run(
        [sys.executable, "-m", "controlops_research.runtime", "infer"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == "CONFIG_INVALID"


def test_missing_bwrap_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "controlops_research.runtime.jail.shutil.which",
        lambda name: None,
    )
    with pytest.raises(RuntimeFailure) as caught:
        exec_command(["/usr/bin/true"], workspace=tmp_path)
    assert caught.value.code == "BWRAP_NOT_AVAILABLE"


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bubblewrap is not installed")
def test_docker_socket_and_prohibited_paths_are_absent(tmp_path):
    script = r"""
set -- \
  /root \
  /home \
  /home/proteu5 \
  /home/proteu5/AI/Hermes/hermes-agent \
  /run/docker.sock \
  /var/run/docker.sock \
  /etc/shadow \
  /etc/ssh \
  /mnt/Storage \
  /dev/nvidia0 \
  /dev/nvidiactl \
  /dev/dri \
  /dev/kfd \
  /opt/data/workspace/controlops_research
for path in "$@"; do
  if [ -e "$path" ]; then
    printf 'PRESENT %s\n' "$path"
  else
    printf 'ABSENT %s\n' "$path"
  fi
done
"""
    completed = exec_command(["/usr/bin/bash", "-c", script], workspace=tmp_path, timeout=20)
    assert completed.returncode == 0, completed.stderr
    lines = [line for line in completed.stdout.splitlines() if line.startswith(("PRESENT ", "ABSENT "))]
    assert lines
    assert all(line.startswith("ABSENT ") for line in lines), completed.stdout


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bubblewrap is not installed")
def test_jail_writes_only_inside_the_four_runtime_binds(tmp_path):
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("keep", encoding="utf-8")
    marker = "pr5r-write-probe"
    script = f"""
for name in locks tmp out runs; do
  printf 'x' > "/opt/data/workspace/runtime/$name/{marker}" || printf 'WRITE_FAIL %s\\n' "$name"
done
if printf 'x' > /opt/data/workspace/{marker} 2>/dev/null; then
  printf 'WROTE_PARENT\\n'
else
  printf 'PARENT_DENIED\\n'
fi
printf 'x' > /tmp/{marker}
printf 'DONE\\n'
"""
    completed = exec_command(["/usr/bin/bash", "-c", script], workspace=tmp_path, timeout=20)
    assert completed.returncode == 0, completed.stderr
    assert "DONE" in completed.stdout
    assert not (tmp_path / marker).exists()
    for name in ("locks", "tmp", "out", "runs"):
        assert (tmp_path / "runtime" / name / marker).read_text(encoding="utf-8") == "x"
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / marker).exists()
    assert not Path(f"/tmp/{marker}").exists()
    extra = sorted(path.name for path in tmp_path.iterdir())
    assert extra == ["runtime", "sentinel"]


def test_malformed_model_list_is_payload_failure():
    transport = FakeTransport(lambda *args: (200, json.dumps({"data": "nope"}).encode()))
    with pytest.raises(RuntimeFailure) as caught:
        LMStudioProbe(transport=transport, environ=ready_environ()).require_ready()
    assert caught.value.code == "MODEL_STATE_INCOMPATIBLE"
