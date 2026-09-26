"""Verify the installed package and guard against external import activity."""

from pathlib import Path
import subprocess
import sys


def test_package_import():
    import controlops_research

    expected = Path(__file__).resolve().parents[1] / "src" / "controlops_research"
    assert Path(controlops_research.__file__).resolve().parent == expected


def test_import_has_no_external_side_effects(tmp_path):
    # Fresh isolated interpreter: no cached package and no working-directory
    # namespace package can hide a broken editable installation.
    code = r'''
import sys

def guard(event, args):
    if event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in {
        "os.system", "os.fork", "os.posix_spawn"
    }:
        raise AssertionError("Import attempted external activity: " + event)
    if event == "open":
        path = str(args[0]).replace("\\", "/")
        # Import machinery may read installed Python source/bytecode only.
        if not path.endswith((".py", ".pyc")):
            raise AssertionError("Import attempted non-code file access: " + path)

sys.addaudithook(guard)
import controlops_research
assert controlops_research.__file__
'''
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code], cwd=tmp_path,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
