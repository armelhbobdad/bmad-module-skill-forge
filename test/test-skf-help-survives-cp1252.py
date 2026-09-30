"""Every script's --help works on a console that is not UTF-8.

A Windows console pipes stdout as cp1252, and argparse prints the module
docstring for --help, so a docstring character outside cp1252 (such as an
arrow) raised UnicodeEncodeError and the script exited 1. PYTHONIOENCODING
gives any platform the same stdout, so this test catches the crash on Linux
as well as on windows-latest.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = sorted(
    p for p in (REPO / "src").rglob("*.py")
    if "tests" not in p.parts and p.name != "__init__.py"
)


def test_the_scripts_are_found():
    assert len(SCRIPTS) > 50


@pytest.mark.parametrize("script", SCRIPTS, ids=[p.relative_to(REPO).as_posix() for p in SCRIPTS])
def test_help_survives_a_cp1252_stdout(script):
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True, stdin=subprocess.DEVNULL, env=env, timeout=60,
    )
    stderr = proc.stderr.decode("utf-8", "replace")
    assert "UnicodeEncodeError" not in stderr, stderr[-800:]
