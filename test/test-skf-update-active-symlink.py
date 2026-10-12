#!/usr/bin/env python3
"""Tests for skf-update-active-symlink.py.

POSIX-only — Windows symlinks need admin/developer mode and don't support
the atomic temp-and-replace pattern this script relies on. Native Windows
is the same skip-territory as skf-atomic-write.py's flip-link primitive.

Covers update + verify subcommands:
  - idempotent no-op when target already correct
  - atomic flip from a different target
  - first-time creation (no prior link)
  - missing target directory → halt
  - mismatch detection in verify-only mode
  - refusal to overwrite a non-symlink path
  - update holds `active.skf-lock`, flip-link's lock (#723): a flip-link
    between its flip and its re-read is refused, it waits while another
    flip holds the lock and returns busy when the lock stays held, a
    second update waits for the first, and a no-op leaves no lock file
  - exit 1 after a flip that worked leaves the link moved (#732)
"""

from __future__ import annotations

import errno
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


# Hard skip on Windows — see module docstring.
pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="POSIX symlink semantics; Windows uses WSL2 per skf-atomic-write.py",
)


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-update-active-symlink.py"
# The sibling whose flip-link takes the lock update takes too.
ATOMIC_WRITE_PATH = SCRIPT_PATH.with_name("skf-atomic-write.py")

spec = importlib.util.spec_from_file_location("skf_update_active_symlink", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

aw_spec = importlib.util.spec_from_file_location("skf_atomic_write_for_update", ATOMIC_WRITE_PATH)
aw = importlib.util.module_from_spec(aw_spec)
assert aw_spec.loader is not None
aw_spec.loader.exec_module(aw)


# --------------------------------------------------------------------------
# Fixture helper
# --------------------------------------------------------------------------


def _make_group(tmp_path: Path, *versions: str) -> Path:
    """Build a skill_group dir with one or more version subdirectories."""
    group = tmp_path / "my-skill"
    group.mkdir()
    for v in versions:
        (group / v).mkdir()
    return group


# --------------------------------------------------------------------------
# read_link_target / atomic_flip_symlink
# --------------------------------------------------------------------------


class TestReadLinkTarget:
    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert mod.read_link_target(tmp_path / "nope") is None

    def test_returns_target_when_symlink(self, tmp_path: Path) -> None:
        target = tmp_path / "v1"
        target.mkdir()
        link = tmp_path / "active"
        os.symlink("v1", link)
        assert mod.read_link_target(link) == "v1"

    def test_raises_when_not_a_symlink(self, tmp_path: Path) -> None:
        # link path exists but is a real directory
        path = tmp_path / "active"
        path.mkdir()
        with pytest.raises(ValueError, match="not a symlink"):
            mod.read_link_target(path)


class TestAtomicFlip:
    def test_creates_first_time(self, tmp_path: Path) -> None:
        (tmp_path / "v1").mkdir()
        link = tmp_path / "active"
        mod.atomic_flip_symlink(link, "v1")
        assert link.is_symlink()
        assert os.readlink(link) == "v1"

    def test_replaces_existing(self, tmp_path: Path) -> None:
        (tmp_path / "v1").mkdir()
        (tmp_path / "v2").mkdir()
        link = tmp_path / "active"
        os.symlink("v1", link)
        mod.atomic_flip_symlink(link, "v2")
        assert os.readlink(link) == "v2"

    def test_no_orphan_temp_file_after_success(self, tmp_path: Path) -> None:
        (tmp_path / "v1").mkdir()
        link = tmp_path / "active"
        mod.atomic_flip_symlink(link, "v1")
        leftovers = [p for p in tmp_path.iterdir() if ".skf-symlink.tmp" in p.name]
        assert leftovers == []

    def test_cleans_stale_temp_from_prior_crash(self, tmp_path: Path) -> None:
        # simulate a crashed prior flip leaving the temp behind
        (tmp_path / "v1").mkdir()
        link = tmp_path / "active"
        stale_tmp = tmp_path / f".{link.name}.skf-symlink.tmp"
        os.symlink("v-crashed", stale_tmp)
        mod.atomic_flip_symlink(link, "v1")
        assert os.readlink(link) == "v1"
        assert not stale_tmp.exists()


# --------------------------------------------------------------------------
# update()
# --------------------------------------------------------------------------


class TestUpdate:
    def test_no_op_when_already_correct(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        os.symlink("1.0.0", group / "active")
        result = mod.update(group, "1.0.0")
        assert result["status"] == "ok"
        assert result["action_taken"] == "no-op"
        assert result["log_message"] == "active_symlink_update: ok (1.0.0)"

    def test_flip_when_different(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.1.0")
        os.symlink("1.0.0", group / "active")
        result = mod.update(group, "1.1.0")
        assert result["status"] == "flipped"
        assert result["action_taken"] == "flipped"
        assert result["current_target"] == "1.1.0"
        assert "1.0.0 -> 1.1.0" in result["log_message"]
        # disk state matches
        assert os.readlink(group / "active") == "1.1.0"

    def test_first_time_creation(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        # no prior active symlink
        result = mod.update(group, "1.0.0")
        assert result["status"] == "flipped"
        assert (group / "active").is_symlink()

    def test_missing_target_dir(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path)  # no version dirs
        result = mod.update(group, "2.0.0")
        assert result["status"] == "missing-target"
        assert "does not exist" in result["halt_message"]
        # no symlink was created
        assert not (group / "active").exists()

    def test_no_op_leaves_no_lock_file(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        os.symlink("1.0.0", group / "active")
        assert mod.update(group, "1.0.0")["status"] == "ok"
        assert sorted(p.name for p in group.iterdir()) == ["1.0.0", "active"], "no lock file left"


# --------------------------------------------------------------------------
# update() and the flip lock (#723)
# --------------------------------------------------------------------------


THREE_VERSIONS = ["0.5.8", "1.0.0", "1.6.2"]


def _three_versions(tmp_path: Path) -> Path:
    """oms-cognee with 0.5.8, 1.0.0 and 1.6.2, and `active -> 1.6.2`."""
    group = tmp_path / "oms-cognee"
    for v in THREE_VERSIONS:
        (group / v).mkdir(parents=True)
    os.symlink("1.6.2", group / "active")
    return group


def _flip_link(link: Path, target: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ATOMIC_WRITE_PATH), "flip-link", "--link", str(link), "--target", target],
        capture_output=True,
        text=True,
        check=False,
    )


def _hold_lock(group: Path) -> int:
    """Open and lock `active.skf-lock` as a flip does; the caller closes the fd."""
    fd = os.open(group / "active.skf-lock", os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        aw._acquire_lock(fd)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _update_cli(group: Path, version: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(SCRIPT_PATH), "update", "--skill-group", str(group), "--version", version],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class TestUpdateHoldsTheFlipLock:
    def test_a_flip_link_between_the_flip_and_the_reread_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        group = _three_versions(tmp_path)
        real_flip = mod.atomic_flip_symlink
        seen: dict[str, subprocess.CompletedProcess] = {}

        def flip_then_flip_link(link_path: Path, target: str) -> None:
            real_flip(link_path, target)
            seen["flip_link"] = _flip_link(link_path, "0.5.8")

        monkeypatch.setattr(mod, "atomic_flip_symlink", flip_then_flip_link)
        result = mod.update(group, "1.0.0")
        assert seen["flip_link"].returncode == 2, seen["flip_link"].stderr
        assert json.loads(seen["flip_link"].stderr)["message"] == (
            f"another process holds flip lock on {group / 'active'}")
        assert result["status"] == "flipped", result
        assert os.readlink(group / "active") == "1.0.0"

    def test_update_waits_while_another_flip_holds_the_lock(self, tmp_path: Path) -> None:
        group = _three_versions(tmp_path)
        fd = _hold_lock(group)
        out: dict[str, dict] = {}
        worker = threading.Thread(target=lambda: out.setdefault("result", mod.update(group, "1.0.0")))
        try:
            worker.start()
            time.sleep(0.3)
            assert os.readlink(group / "active") == "1.6.2", "update flipped while the lock was held"
        finally:
            # let go as a flip does: remove the file, then release the lock
            os.unlink(group / "active.skf-lock")
            aw._release_lock(fd)
            os.close(fd)
            worker.join(10)
        assert out["result"]["status"] == "flipped", out
        assert os.readlink(group / "active") == "1.0.0"
        assert sorted(p.name for p in group.iterdir()) == THREE_VERSIONS + ["active"], "no lock or temp link left"

    def test_update_is_busy_when_the_lock_stays_held(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        group = _three_versions(tmp_path)
        monkeypatch.setattr(mod, "FLIP_LOCK_WAIT_SECONDS", 0.2)
        fd = _hold_lock(group)
        try:
            started = time.monotonic()
            result = mod.update(group, "1.0.0")
            assert time.monotonic() - started >= 0.2
            assert result["status"] == "busy", result
            assert mod._exit_code_for_status(result["status"]) == 2
            assert (result["current_target"], result["action_taken"]) == (None, "halt")
            assert result["log_message"] == (
                f"active_symlink_update: busy (another process holds flip lock on {group / 'active'})")
            assert "Re-run once the other run ends" in result["halt_message"]
            assert os.readlink(group / "active") == "1.6.2"
            assert os.path.samestat(os.fstat(fd), os.stat(group / "active.skf-lock")), "the holder's file left the path"
        finally:
            aw._release_lock(fd)
            os.close(fd)

    def test_a_second_update_waits_for_the_first(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        group = _three_versions(tmp_path)
        tmp_link = group / ".active.skf-symlink.tmp"
        real_symlink = os.symlink
        made, go = threading.Event(), threading.Event()

        def symlink_then_pause(src, dst, *args, **kwargs):
            real_symlink(src, dst, *args, **kwargs)
            if Path(dst) == tmp_link and not made.is_set():
                made.set()
                go.wait(10)

        monkeypatch.setattr(os, "symlink", symlink_then_pause)
        out: dict[str, dict] = {}
        first = threading.Thread(target=lambda: out.setdefault("first", mod.update(group, "1.0.0")))
        first.start()
        try:
            assert made.wait(10), "the first update made its temp link"
            second = _update_cli(group, "0.5.8")
            time.sleep(0.3)
            assert second.poll() is None, "the second update did not wait"
            assert os.readlink(tmp_link) == "1.0.0" and os.readlink(group / "active") == "1.6.2"
        finally:
            go.set()
            first.join(10)
        stdout, stderr = second.communicate(timeout=10)
        assert out["first"]["status"] == "flipped", out
        assert second.returncode == 0, stderr
        assert json.loads(stdout)["status"] == "flipped"
        assert os.readlink(group / "active") == "0.5.8"
        assert sorted(p.name for p in group.iterdir()) == THREE_VERSIONS + ["active"], "no lock or temp link left"


# --------------------------------------------------------------------------
# verify()
# --------------------------------------------------------------------------


class TestVerify:
    def test_ok_when_match(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        os.symlink("1.0.0", group / "active")
        result = mod.verify(group, "1.0.0")
        assert result["status"] == "ok"
        assert result["current_target"] == "1.0.0"

    def test_mismatch_when_diverged(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.1.0")
        os.symlink("1.0.0", group / "active")
        result = mod.verify(group, "1.1.0")
        assert result["status"] == "mismatch"
        assert "divergence" in result["halt_message"]
        assert "1.0.0" in result["halt_message"]
        assert "1.1.0" in result["halt_message"]

    def test_mismatch_when_link_missing(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        # no active symlink at all
        result = mod.verify(group, "1.0.0")
        assert result["status"] == "mismatch"


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_update_no_op_exits_0(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0")
        os.symlink("1.0.0", group / "active")
        result = _run_cli(
            "update", "--skill-group", str(group), "--version", "1.0.0"
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "ok"

    def test_update_flips_exits_0(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.1.0")
        os.symlink("1.0.0", group / "active")
        result = _run_cli(
            "update", "--skill-group", str(group), "--version", "1.1.0"
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "flipped"

    def test_update_missing_target_exits_2(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path)
        result = _run_cli(
            "update", "--skill-group", str(group), "--version", "2.0.0"
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["status"] == "missing-target"

    def test_verify_mismatch_exits_2(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.1.0")
        os.symlink("1.0.0", group / "active")
        result = _run_cli(
            "verify", "--skill-group", str(group), "--version", "1.1.0"
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["status"] == "mismatch"

    def test_bad_skill_group_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli(
            "update",
            "--skill-group", str(tmp_path / "missing"),
            "--version", "1.0.0",
        )
        assert result.returncode == 1
        assert "not a directory" in result.stderr

    def test_missing_subcommand_exits_2(self, tmp_path: Path) -> None:
        result = _run_cli()
        assert result.returncode == 2  # argparse missing required subparser

    def test_a_lock_close_that_fails_after_the_flip_exits_1_with_the_link_moved(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """#732: the one exit 1 that comes after a flip that worked: closing the lock fails (EIO). Update
        Skill's "any other exit" rule then halts, and its rollback keeps the version the link already names."""
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        os.symlink("1.0.0", group / "active")
        load = mod._load_atomic_write

        def failing_load():
            atomic = load()
            release = atomic.release_flip_lock

            def release_then_fail(link, fd):
                release(link, fd)
                raise OSError(errno.EIO, os.strerror(errno.EIO))

            monkeypatch.setattr(atomic, "release_flip_lock", release_then_fail)
            return atomic

        monkeypatch.setattr(mod, "_load_atomic_write", failing_load)
        assert mod.main(["update", "--skill-group", str(group), "--version", "1.6.2"]) == 1
        out, err = capsys.readouterr()
        assert out == ""
        assert err.splitlines()[-1] == f"error: [Errno {errno.EIO}] {os.strerror(errno.EIO)}"
        assert os.readlink(group / "active") == "1.6.2"
