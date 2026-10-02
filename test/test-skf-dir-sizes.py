"""Tests for skf-drop-skill/scripts/dir-sizes.py — deterministic recursive
directory sizing and human-readable byte formatting."""

from __future__ import annotations

import importlib.util
import json
import re
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


# --- argparse CLI (#601) ----------------------------------------------------


def _usage_error(res: subprocess.CompletedProcess) -> str:
    """The JSON usage error on stderr, with nothing on stdout."""
    assert res.returncode == 2
    assert res.stdout == ""
    err = json.loads(res.stderr)
    assert err["status"] == "error"
    return err["error"]


def test_help_prints_usage():
    res = _run("--help")
    assert res.returncode == 0
    assert res.stdout.startswith("usage: dir-sizes.py")
    for op in ("sizes", "humanize"):
        assert op in res.stdout


@pytest.mark.parametrize("op, arg", [("sizes", "path"), ("humanize", "bytes")])
def test_each_op_has_help(op, arg):
    res = _run(op, "--help")
    assert res.returncode == 0
    assert res.stdout.startswith(f"usage: dir-sizes.py {op}")
    assert f"[{arg} ...]" in res.stdout


@pytest.mark.parametrize("args", [(), ("bogus", "x"), ("sizes", "--bogus")],
                         ids=["no-op", "unknown-op", "unknown-flag"])
def test_usage_errors_stay_json_with_exit_2(args):
    assert _usage_error(_run(*args)).startswith("usage error: dir-sizes.py")


def test_sizes_with_no_paths_is_zero():
    res = _run("sizes")
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert (out["paths"], out["total_bytes"], out["total_human"]) == ([], 0, "0 B")


def test_main_help_runs_in_process(capsys):
    with pytest.raises(SystemExit) as exc:
        mod.main(["--help"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("usage: dir-sizes.py")


def test_the_drop_steps_call_the_cli_it_parses():
    """Each `{dirSizesHelper}` call select.md and execute.md document parses."""
    references = SCRIPT.parent.parent / "references"
    ops = []
    for name in ("select.md", "execute.md"):
        for line in (references / name).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("uv run {dirSizesHelper} "):
                continue
            words = re.sub(r"\{[^{}]*\}", "1024", line.removeprefix("uv run {dirSizesHelper} ")).split()
            ops.append(mod._build_parser().parse_args(words).op)
    assert sorted(ops) == ["humanize", "sizes"]
