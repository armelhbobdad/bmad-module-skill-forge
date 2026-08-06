"""Tests for skf-drop-skill/scripts/dir-sizes.py — deterministic recursive
directory sizing and human-readable byte formatting."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "skf-drop-skill"
    / "scripts"
    / "dir-sizes.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("dir_sizes", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


# --- humanize_bytes ---------------------------------------------------------


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, "0 B"),
        (512, "512 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (int(4.2 * 1024 * 1024), "4.2 MB"),
        (1024**3, "1.0 GB"),
    ],
)
def test_humanize_bytes(n, expected):
    assert mod.humanize_bytes(n) == expected


def test_humanize_is_deterministic():
    assert mod.humanize_bytes(123456789) == mod.humanize_bytes(123456789)


# --- dir_bytes --------------------------------------------------------------


def test_dir_bytes_single_file(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"x" * 100)
    assert mod.dir_bytes(str(f)) == 100


def test_dir_bytes_recursive(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.bin").write_bytes(b"a" * 10)
    (tmp_path / "sub" / "b.bin").write_bytes(b"b" * 25)
    (tmp_path / "sub" / "c.bin").write_bytes(b"c" * 5)
    assert mod.dir_bytes(str(tmp_path)) == 40


def test_dir_bytes_symlink_not_followed(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "big.bin").write_bytes(b"z" * 10_000)
    link = tmp_path / "active"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")
    # measuring the link measures the link node, never the 10 KB behind it
    assert mod.dir_bytes(str(link)) < 10_000


# --- sizes op ---------------------------------------------------------------


def test_sizes_op(tmp_path: Path):
    d1 = tmp_path / "one"
    d1.mkdir()
    (d1 / "f").write_bytes(b"a" * 30)
    missing = tmp_path / "gone"

    res = _run("sizes", str(d1), str(missing))
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert out["status"] == "ok"
    assert out["total_bytes"] == 30
    by_path = {e["path"]: e for e in out["paths"]}
    assert by_path[str(d1)]["exists"] is True
    assert by_path[str(d1)]["bytes"] == 30
    assert by_path[str(missing)]["exists"] is False
    assert by_path[str(missing)]["bytes"] == 0


# --- humanize op ------------------------------------------------------------


def test_humanize_op_sums_and_formats():
    res = _run("humanize", "1024", "1024", "1024")
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert out["total_bytes"] == 3072
    assert out["total_human"] == "3.0 KB"


def test_humanize_op_empty_is_zero():
    res = _run("humanize")
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert out["total_bytes"] == 0
    assert out["total_human"] == "0 B"


# --- usage / exit codes -----------------------------------------------------


def test_no_op_exits_2():
    res = _run()
    assert res.returncode == 2


def test_unknown_op_exits_2():
    res = _run("bogus", "x")
    assert res.returncode == 2


def test_humanize_bad_int_exits_2():
    res = _run("humanize", "notanumber")
    assert res.returncode == 2
