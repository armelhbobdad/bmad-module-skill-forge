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
lock path or with a folder there is raised as before. On POSIX, a flip
refused by a held lock leaves the lock file to its holder; a flip whose
locked file is no longer at the path opens the path again, and exits 2
when a newer flip holds the file there or the wait runs out; the holder
removes the file before it releases the lock. The copy of
_names_open_file stays identical to the one in gap-ledger.py.
"""

from __future__ import annotations

import ast
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
GAP_LEDGER_PATH = Path(__file__).parent.parent / "src" / "skf-test-skill" / "scripts" / "gap-ledger.py"

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

    On Windows no test flips over an existing link: CI's Windows runner
    holds symlink privilege, and replacing an existing directory link is the
    one step whose Windows behaviour is unverified. TestFlipLockOnPosix,
    which skips Windows, flips over one.
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

    def test_a_flip_refused_by_a_held_lock_leaves_the_holders_file(self, tmp_path):
        # No link exists yet, so this runs on Windows without flipping over one.
        group = _group(tmp_path)
        link, lock = group / "active", group / "active.skf-lock"
        fd = _hold_lock(lock)
        try:
            proc = _run_flip(link, "0.6.0")
            assert proc.returncode == 2, proc.stderr
            assert json.loads(proc.stderr)["message"] == f"another process holds flip lock on {link}"
            assert _still_at_path(fd, lock), "the holder's lock file is still at the path"
            assert not os.path.lexists(link), "no link created"
        finally:
            os.close(fd)

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


THREE_VERSIONS = ["0.5.8", "1.0.0", "1.6.2"]


def _three_versions(root: Path) -> Path:
    """skills/oms-cognee with 0.5.8, 1.0.0 and 1.6.2, and `active -> 1.6.2`."""
    group = root / "skills" / "oms-cognee"
    for version in THREE_VERSIONS:
        (group / version / "oms-cognee").mkdir(parents=True)
    os.symlink("1.6.2", group / "active")
    return group


def _hold_lock(path: Path, acquire=None) -> int:
    """Open `path` and lock it as a flip does; the caller closes the fd.

    Pass the real _acquire_lock as `acquire` once a test has patched the
    module's, or the lock would go through the patch."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        (acquire or mod._acquire_lock)(fd)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _still_at_path(fd: int, path: Path) -> bool:
    return os.path.lexists(path) and os.path.samestat(os.fstat(fd), os.stat(path))


@pytest.mark.skipif(os.name == "nt", reason="POSIX removes the lock file while it is held, Windows after the release")
class TestFlipLockOnPosix:
    """One flip at a time holds the lock on `active.skf-lock` (#713).

    The holder removes the lock file before it releases the lock, so a flip
    that locked the removed file must find that the path no longer names it,
    and a flip refused by the holder must leave the file where it is.
    """

    def test_a_refused_flip_leaves_the_holders_lock_file(self, tmp_path):
        group = _three_versions(tmp_path)
        link, lock = group / "active", group / "active.skf-lock"
        fd = _hold_lock(lock)
        try:
            for target in ("1.0.0", "0.5.8"):
                proc = _run_flip(link, target)
                assert proc.returncode == 2, proc.stderr
                assert json.loads(proc.stderr)["message"] == f"another process holds flip lock on {link}"
                assert _still_at_path(fd, lock), "the holder's lock file is still at the path"
                assert os.readlink(link) == "1.6.2"
        finally:
            os.close(fd)
        # The holder is gone, its file is left: the next flip locks it and removes it.
        proc = _run_flip(link, "1.0.0")
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["points_to"] == "1.0.0"
        assert os.readlink(link) == "1.0.0"
        assert sorted(p.name for p in group.iterdir()) == THREE_VERSIONS + ["active"], "no lock or temp link left"

    def test_a_flip_whose_file_a_newer_flip_replaced_exits_2(self, tmp_path, monkeypatch, capsys):
        # Between this flip's open and its lock, the holder removed the file
        # and a newer flip put its own file at the path and locked it.
        group = _three_versions(tmp_path)
        link, lock = group / "active", group / "active.skf-lock"
        real_acquire = mod._acquire_lock
        newer: list[int] = []

        def newer_flip_takes_the_path(fd):
            if not newer:
                lock.unlink()
                newer.append(_hold_lock(lock, real_acquire))
            return real_acquire(fd)

        monkeypatch.setattr(mod, "_acquire_lock", newer_flip_takes_the_path)
        try:
            with pytest.raises(SystemExit) as exc:
                mod.cmd_flip_link(link, "1.0.0")
            assert exc.value.code == 2
            captured = capsys.readouterr()
            assert captured.out == ""
            assert json.loads(captured.err)["message"] == f"another process holds flip lock on {link}"
            assert os.readlink(link) == "1.6.2"
            assert _still_at_path(newer[0], lock), "the newer flip's lock file is still at the path"
        finally:
            for fd in newer:
                os.close(fd)

    def test_a_flip_whose_file_was_removed_locks_the_path_again(self, tmp_path, monkeypatch, capsys):
        # Between this flip's open and its lock, the holder removed the file
        # and nothing took its place.
        group = _three_versions(tmp_path)
        link, lock = group / "active", group / "active.skf-lock"
        real_acquire = mod._acquire_lock
        calls: list[int] = []

        def holder_removes_the_file_first(fd):
            if not calls:
                lock.unlink()
            calls.append(fd)
            return real_acquire(fd)

        monkeypatch.setattr(mod, "_acquire_lock", holder_removes_the_file_first)
        mod.cmd_flip_link(link, "1.0.0")
        assert len(calls) == 2, "the flip opened and locked the path again"
        assert json.loads(capsys.readouterr().out)["points_to"] == "1.0.0"
        assert os.readlink(link) == "1.0.0"
        assert sorted(p.name for p in group.iterdir()) == THREE_VERSIONS + ["active"], "no lock or temp link left"

    def test_a_file_that_keeps_leaving_the_path_exits_2_after_the_wait(self, tmp_path, monkeypatch, capsys):
        group = _three_versions(tmp_path)
        link, lock = group / "active", group / "active.skf-lock"
        real_acquire = mod._acquire_lock
        calls: list[int] = []

        def holder_removes_the_file_each_time(fd):
            calls.append(fd)
            if len(calls) > 300:
                raise AssertionError(f"{len(calls)} locks of {lock}: the retry ignores its wait")
            lock.unlink()
            time.sleep(0.01)
            return real_acquire(fd)

        monkeypatch.setattr(mod, "_acquire_lock", holder_removes_the_file_each_time)
        monkeypatch.setattr(mod, "_LOCK_OPEN_WAIT_SECONDS", 0.2)
        started = time.monotonic()
        with pytest.raises(SystemExit) as exc:
            mod.cmd_flip_link(link, "1.0.0")
        assert time.monotonic() - started >= 0.2
        assert exc.value.code == 2
        assert len(calls) > 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert json.loads(captured.err)["message"] == f"another process holds flip lock on {link}"
        assert os.readlink(link) == "1.6.2"
        assert sorted(p.name for p in group.iterdir()) == THREE_VERSIONS + ["active"]

    def test_the_holder_removes_the_lock_file_before_it_releases_the_lock(self, tmp_path, monkeypatch, capsys):
        group = _three_versions(tmp_path)
        link, lock = group / "active", group / "active.skf-lock"
        real_release = mod._release_lock
        at_release: list[bool] = []

        def release(fd):
            at_release.append(os.path.lexists(lock))
            return real_release(fd)

        monkeypatch.setattr(mod, "_release_lock", release)
        mod.cmd_flip_link(link, "1.0.0")
        assert at_release == [False], "the lock file was still at the path when the lock was released"
        assert json.loads(capsys.readouterr().out)["points_to"] == "1.0.0"
        assert sorted(p.name for p in group.iterdir()) == THREE_VERSIONS + ["active"]


def _top_level_def(path: Path, name: str) -> str:
    """ast.dump of the top-level def named `name` (comments ignored)."""
    for node in ast.parse(path.read_text(encoding="utf-8"), filename=str(path)).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node)
    raise AssertionError(f"{name} not found at the top level of {path.name}")


class TestPinnedCopy:
    """skf-atomic-write.py carries a copy of _names_open_file from gap-ledger.py."""

    def test_names_open_file_copy_is_identical(self):
        assert _top_level_def(SCRIPT_PATH, "_names_open_file") == _top_level_def(GAP_LEDGER_PATH, "_names_open_file"), (
            "_names_open_file in skf-atomic-write.py differs from gap-ledger.py; keep the copies identical")

    def test_the_copy_carries_its_keep_identical_note(self):
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "Keep identical to _names_open_file in gap-ledger.py" in text
        assert "test/test-skf-atomic-write.py pins the copy" in text
