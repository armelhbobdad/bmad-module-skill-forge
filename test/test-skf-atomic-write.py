#!/usr/bin/env python3
"""Tests for skf-atomic-write.py.

Highest-value test: the `write` subcommand must persist stdin bytes verbatim,
including line endings. On Windows os.open defaults to text mode and would
inject CRLF (\n -> \r\n) without the O_BINARY flag, corrupting JSON/markdown
artifacts the workflows write through this helper.

flip-link: it creates a missing link, refuses a real folder, and, when
Windows refuses to open the lock file while the flip that held it is
removing it, retries for a short wait and then exits 2 with the held-lock
message naming the refusal. A refusal off Windows, with nothing at the
lock path or with a folder there is raised as before.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-atomic-write.py"
)

spec = importlib.util.spec_from_file_location("skf_atomic_write", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _run_write(target: Path, data: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "write", "--target", str(target)],
        input=data,
        capture_output=True,
    )


class TestWriteByteIdentity:
    """The write subcommand persists stdin bytes verbatim (no newline mangling)."""

    def test_write_preserves_bytes_verbatim(self):
        data = b"---\nname: x\n---\n\nline1\nline2\n"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "out.md"
            proc = _run_write(target, data)
            assert proc.returncode == 0, proc.stderr
            assert target.read_bytes() == data
            assert b"\r\n" not in target.read_bytes()

    def test_write_creates_parent_dirs(self):
        data = b"hello\nworld\n"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "nested" / "deep" / "out.txt"
            proc = _run_write(target, data)
            assert proc.returncode == 0, proc.stderr
            assert target.read_bytes() == data

    def test_write_leaves_no_temp_file(self):
        data = b"content\n"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "out.txt"
            proc = _run_write(target, data)
            assert proc.returncode == 0, proc.stderr
            assert not target.with_name(target.name + ".skf-tmp").exists()


def _run_flip(link: Path, target: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "flip-link", "--link", str(link), "--target", target],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _group(root: Path) -> Path:
    group = root / "skills" / "cognee"
    (group / "0.6.0" / "cognee").mkdir(parents=True)
    return group


def _refuse_lock_open(monkeypatch: pytest.MonkeyPatch, times: int | None = None) -> list[str]:
    """Make opening a `.skf-lock` file raise PermissionError, as Windows does
    while the flip that held it is removing it: the first `times` opens, or
    every open when `times` is None. Other opens go through. Returns the lock
    paths opened, refused or not. A retry that outlives its wait fails the
    test after a few hundred opens instead of hanging it."""
    real_open = mod.os.open
    calls: list[str] = []

    def flaky_open(path, flags, *args, **kwargs):
        if os.fspath(path).endswith(".skf-lock"):
            calls.append(os.fspath(path))
            if len(calls) > 300:
                raise AssertionError(f"{len(calls)} opens of {os.fspath(path)}: the retry ignores its wait")
            if times is None or len(calls) <= times:
                raise PermissionError(13, "Permission denied", os.fspath(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(mod.os, "open", flaky_open)
    return calls


def _pending_lock_file(group: Path) -> Path:
    """`active.skf-lock`, left in place as a file whose removal is pending."""
    lock = group / "active.skf-lock"
    lock.write_bytes(b"")
    return lock


class TestFlipLink:
    """flip-link leaves `active` naming the version folder beside it, or refuses without touching it.

    No test flips over an existing link: CI's Windows runner holds
    symlink privilege, and replacing an existing directory link is the one
    step whose Windows behaviour is unverified.
    """

    def test_flip_creates_a_missing_link(self, tmp_path):
        group = _group(tmp_path)
        proc = _run_flip(group / "active", "0.6.0")
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["status"] == "ok" and out["points_to"] == "0.6.0"
        assert out["kind"] in ("symlink", "junction")
        assert (group / "active").resolve() == (group / "0.6.0").resolve()
        assert sorted(p.name for p in group.iterdir()) == ["0.6.0", "active"], "no lock or temp link left"

    def test_flip_refuses_a_real_folder(self, tmp_path):
        group = _group(tmp_path)
        (group / "active" / "cognee").mkdir(parents=True)
        (group / "active" / "cognee" / "SKILL.md").write_bytes(b"x\n")
        proc = _run_flip(group / "active", "0.6.0")
        assert proc.returncode == 2
        assert json.loads(proc.stderr)["message"].startswith("refusing to replace non-link")
        assert (group / "active" / "cognee" / "SKILL.md").read_bytes() == b"x\n"

    def test_a_lock_file_windows_refuses_for_a_moment_is_retried(self, tmp_path, monkeypatch, capsys):
        # Windows refuses to open the lock file while the flip that held it
        # is removing it; the flip retries.
        group = _group(tmp_path)
        _pending_lock_file(group)
        monkeypatch.setattr(mod, "_IS_WINDOWS", True)
        calls = _refuse_lock_open(monkeypatch, times=2)
        mod.cmd_flip_link(group / "active", "0.6.0")
        assert len(calls) == 3
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ok" and out["points_to"] == "0.6.0"
        assert (group / "active").resolve() == (group / "0.6.0").resolve()
        assert sorted(p.name for p in group.iterdir()) == ["0.6.0", "active"], "no lock or temp link left"

    def test_a_lock_file_windows_keeps_refusing_exits_2_as_a_held_lock(self, tmp_path, monkeypatch, capsys):
        group = _group(tmp_path)
        _pending_lock_file(group)
        monkeypatch.setattr(mod, "_IS_WINDOWS", True)
        monkeypatch.setattr(mod, "_LOCK_OPEN_WAIT_SECONDS", 0.3)
        calls = _refuse_lock_open(monkeypatch)
        started = time.monotonic()
        with pytest.raises(SystemExit) as exc:
            mod.cmd_flip_link(group / "active", "0.6.0")
        assert time.monotonic() - started >= 0.3
        assert exc.value.code == 2
        assert len(calls) > 1
        captured = capsys.readouterr()
        assert captured.out == ""
        lines = captured.err.splitlines()
        assert len(lines) == 1, captured.err
        error = json.loads(lines[0])
        assert error["status"] == "error"
        assert error["message"].startswith(f"another process holds flip lock on {group / 'active'} (last open refused: ")
        assert "Permission denied" in error["message"]
        assert sorted(p.name for p in group.iterdir()) == ["0.6.0", "active.skf-lock"]

    def test_a_refused_lock_file_off_windows_is_raised(self, tmp_path, monkeypatch):
        group = _group(tmp_path)
        _pending_lock_file(group)
        monkeypatch.setattr(mod, "_IS_WINDOWS", False)
        calls = _refuse_lock_open(monkeypatch)
        with pytest.raises(PermissionError):
            mod.cmd_flip_link(group / "active", "0.6.0")
        assert len(calls) == 1
        assert sorted(p.name for p in group.iterdir()) == ["0.6.0", "active.skf-lock"]

    def test_a_refusal_with_no_lock_file_is_raised(self, tmp_path, monkeypatch):
        # Nothing at the lock path: the folder refuses the new file, which no
        # wait cures. One more open at once tells it from a removal that
        # ended just now.
        group = _group(tmp_path)
        monkeypatch.setattr(mod, "_IS_WINDOWS", True)
        calls = _refuse_lock_open(monkeypatch)
        with pytest.raises(PermissionError):
            mod.cmd_flip_link(group / "active", "0.6.0")
        assert len(calls) == 2
        assert sorted(p.name for p in group.iterdir()) == ["0.6.0"]

    def test_a_refusal_with_a_folder_at_the_lock_path_is_raised(self, tmp_path, monkeypatch):
        group = _group(tmp_path)
        (group / "active.skf-lock").mkdir()
        monkeypatch.setattr(mod, "_IS_WINDOWS", True)
        calls = _refuse_lock_open(monkeypatch)
        with pytest.raises(PermissionError):
            mod.cmd_flip_link(group / "active", "0.6.0")
        assert len(calls) == 1
        assert sorted(p.name for p in group.iterdir()) == ["0.6.0", "active.skf-lock"]
