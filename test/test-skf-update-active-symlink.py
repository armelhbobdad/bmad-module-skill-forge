#!/usr/bin/env python3
"""Tests for skf-update-active-symlink.py.

The tests that read POSIX link text or POSIX lock-file semantics skip
Windows (POSIX_ONLY). The helper runs on native Windows too (#735): with
`sys.platform` reading as Windows it parses its arguments, flips and
verifies; a simulated junction (a link Path.is_symlink() does not report,
whose os.readlink is a `\\\\?\\` path, and over which a rename is refused)
is read back as the version it names and flipped, a junction whose folder
was deleted, one into another group's folder and a loop included. On
Windows, TestNativeWindows makes os.symlink fail as it does without symlink
rights, so the real `mklink /J` path runs, flips over a directory symlink
with the runner's own privilege, and checks #742's case: a real folder put
at `active` after a junction flip makes verify exit 1 with no JSON.

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
  - verify exits 1 with no JSON when a real folder replaced the link after
    a flip, or the skill folder is no folder (#742)
  - native Windows: no platform refusal, a junction read and flipped (#735)
  - repair-after-drop (#1158): the one replacement rule (pick_new_active),
    a link changed only when it names the dropped version (a dangling
    junction's stored path included), never one that names a newer
    unexported version; busy, lock, flip and unlink failures exit 2 with a
    manual fix, and a manifest or helper it cannot read exits 1 with the
    link untouched
"""

from __future__ import annotations

import errno
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest


# The tests that read POSIX link text or POSIX lock-file semantics.
POSIX_ONLY = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="POSIX link text and lock-file semantics; TestNativeWindows covers Windows",
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


@POSIX_ONLY
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


@POSIX_ONLY
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


@POSIX_ONLY
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


@POSIX_ONLY
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


@POSIX_ONLY
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
# Native Windows (#735)
# --------------------------------------------------------------------------


# What os.readlink gives for a junction on Windows: its absolute substitution path.
JUNCTION_PREFIX = "\\\\?\\C:\\Users\\me\\skills\\oms-cognee\\"


def _simulate_windows_links(monkeypatch: pytest.MonkeyPatch) -> None:
    """Native Windows without symlink rights, on POSIX.

    A link whose stored target is absolute stands for a junction:
    Path.is_symlink() is False for it, the helper's and flip-link's
    os.readlink give its `\\\\?\\` path, and Path.resolve() follows it as Windows
    follows a junction. os.symlink fails as Windows does without the
    privilege, so flip-link's fallback makes such a junction, and a rename
    over an existing link is refused as Windows refuses one over a
    directory. Only the two scripts see the patched os.readlink: realpath
    keeps the real one.
    """
    real_is_symlink, real_readlink, real_replace = Path.is_symlink, os.readlink, os.replace

    def is_junction(path) -> bool:
        return real_is_symlink(Path(path)) and os.path.isabs(real_readlink(path))

    def readlink(path, *args, **kwargs):
        stored = real_readlink(path, *args, **kwargs)
        return JUNCTION_PREFIX + os.path.basename(stored) if os.path.isabs(stored) else stored

    def replace(src, dst, *args, **kwargs):
        if os.path.lexists(dst):
            raise PermissionError(errno.EACCES, "Access is denied", os.fspath(dst))
        real_replace(src, dst, *args, **kwargs)

    def make_junction(target: str, link_path: Path) -> str:
        abs_target = (link_path.parent / target).resolve()
        if not abs_target.is_dir():
            raise OSError(errno.ENOTDIR, f"junction fallback requires existing directory target: {abs_target}")
        os.symlink(str(abs_target), link_path)
        return "junction"

    windows_os = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os) if not name.startswith("__")})
    windows_os.readlink, windows_os.replace = readlink, replace
    monkeypatch.setattr(Path, "is_symlink", lambda self: real_is_symlink(self) and not is_junction(self))
    monkeypatch.setattr(mod, "os", windows_os)
    load = mod._load_atomic_write

    def load_on_windows():
        atomic = load()
        monkeypatch.setattr(atomic, "os", windows_os)
        monkeypatch.setattr(atomic, "_IS_WINDOWS", True)
        monkeypatch.setattr(atomic, "_create_symlink_or_junction", make_junction)
        return atomic

    monkeypatch.setattr(mod, "_load_atomic_write", load_on_windows)
    monkeypatch.setattr(sys, "platform", "win32")


def _junction(group: Path, version: str) -> None:
    """`active` as the junction a Create Skill flip-link without symlink rights makes."""
    os.symlink(str((group / version).resolve()), group / "active")


@POSIX_ONLY
class TestOnWindowsSimulated:
    def test_update_and_verify_run_when_the_platform_reads_as_windows(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        os.symlink("1.0.0", group / "active")
        monkeypatch.setattr(sys, "platform", "win32")
        assert mod.main(["update", "--skill-group", str(group), "--version", "1.6.2"]) == 0
        assert json.loads(capsys.readouterr().out)["log_message"] == "active_symlink_update: flipped (1.0.0 -> 1.6.2)"
        assert os.readlink(group / "active") == "1.6.2"
        assert mod.main(["verify", "--skill-group", str(group), "--version", "1.6.2"]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "ok"

    def test_a_junction_reads_as_the_version_it_names(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        _junction(group, "1.6.2")
        _simulate_windows_links(monkeypatch)
        assert not (group / "active").is_symlink()
        assert mod.read_link_target(group / "active") == "1.6.2"
        result = mod.verify(group, "1.6.2")
        assert (result["status"], result["current_target"]) == ("ok", "1.6.2")
        result = mod.update(group, "1.6.2")
        assert (result["status"], result["action_taken"]) == ("ok", "no-op")

    def test_a_junction_whose_folder_is_gone_reads_as_its_stored_path(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        group = _make_group(tmp_path, "0.5.8", "1.0.0")
        _junction(group, "0.5.8")
        shutil.rmtree(group / "0.5.8")
        _simulate_windows_links(monkeypatch)
        assert mod.read_link_target(group / "active") == JUNCTION_PREFIX + "0.5.8"
        result = mod.verify(group, "1.0.0")
        assert (result["status"], result["current_target"]) == ("mismatch", JUNCTION_PREFIX + "0.5.8")

    def test_a_junction_to_another_groups_folder_reads_as_its_stored_path_and_is_flipped(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        other = tmp_path / "other-skill" / "1.6.2"
        other.mkdir(parents=True)
        os.symlink(str(other.resolve()), group / "active")
        _simulate_windows_links(monkeypatch)
        assert mod.read_link_target(group / "active") == JUNCTION_PREFIX + "1.6.2"
        result = mod.update(group, "1.6.2")
        assert (result["status"], result["current_target"]) == ("flipped", "1.6.2"), result
        assert (group / "active").resolve() == (group / "1.6.2").resolve()
        assert other.is_dir(), "the other group's folder is kept"

    def test_a_junction_loop_reads_as_its_stored_path_and_is_flipped(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """Python 3.11 and 3.12 raise RuntimeError, not OSError, when resolve meets a loop: the loop reads as its
        stored path, so `verify` reports a mismatch rather than a traceback, and `update` replaces it."""
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        os.symlink(str(group / "active"), group / "active")
        _simulate_windows_links(monkeypatch)
        real_resolve = Path.resolve

        def resolve(self, strict=False):
            if os.path.islink(self) and os.readlink(self) == str(self):
                raise RuntimeError(f"Symlink loop from {str(self)!r}")
            return real_resolve(self, strict=strict)

        monkeypatch.setattr(Path, "resolve", resolve)
        assert mod.read_link_target(group / "active") == JUNCTION_PREFIX + "active"
        assert mod.main(["verify", "--skill-group", str(group), "--version", "1.6.2"]) == 2
        out, err = capsys.readouterr()
        result = json.loads(out)
        assert (result["status"], result["current_target"]) == ("mismatch", JUNCTION_PREFIX + "active")
        assert err == ""
        assert mod.main(["update", "--skill-group", str(group), "--version", "1.6.2"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert (result["status"], result["current_target"]) == ("flipped", "1.6.2"), result
        assert result["log_message"] == f"active_symlink_update: flipped ({JUNCTION_PREFIX}active -> 1.6.2)"
        assert (group / "active").resolve() == (group / "1.6.2").resolve()
        assert mod.verify(group, "1.6.2")["status"] == "ok"

    def test_a_real_folder_is_still_refused(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        shutil.copytree(group / "1.0.0", group / "active")
        _simulate_windows_links(monkeypatch)
        with pytest.raises(ValueError, match="exists but is not a symlink"):
            mod.update(group, "1.6.2")
        assert (group / "active").is_dir() and not os.path.islink(group / "active")

    @pytest.mark.parametrize("start", ["1.0.0", "0.5.8", None], ids=["junction", "junction-folder-gone", "no-link"])
    def test_update_flips_without_symlink_rights(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
            start: str | None) -> None:
        """Update Skill's flip and Drop Skill's repoint after a purge: `active` ends a junction to the version."""
        group = _make_group(tmp_path, "0.5.8", "1.0.0", "1.6.2")
        if start is not None:
            _junction(group, start)
        if start == "0.5.8":
            shutil.rmtree(group / "0.5.8")
        _simulate_windows_links(monkeypatch)
        assert mod.main(["update", "--skill-group", str(group), "--version", "1.6.2"]) == 0
        result = json.loads(capsys.readouterr().out)
        previous = {"1.0.0": "1.0.0", "0.5.8": JUNCTION_PREFIX + "0.5.8", None: "(none)"}[start]
        assert (result["status"], result["current_target"]) == ("flipped", "1.6.2")
        assert result["log_message"] == f"active_symlink_update: flipped ({previous} -> 1.6.2)"
        assert not (group / "active").is_symlink() and (group / "active").resolve() == (group / "1.6.2").resolve()
        assert mod.main(["verify", "--skill-group", str(group), "--version", "1.6.2"]) == 0
        assert json.loads(capsys.readouterr().out)["current_target"] == "1.6.2"
        left = sorted(p.name for p in group.iterdir())
        assert left == [v for v in ("0.5.8", "1.0.0", "1.6.2") if (group / v).is_dir()] + ["active"], left

    def test_a_refused_rename_over_a_symlink_removes_it_first(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With symlink rights Windows makes a symlink, and refuses to rename it over the old directory link."""
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        os.symlink("1.0.0", group / "active")
        _simulate_windows_links(monkeypatch)
        load = mod._load_atomic_write

        def with_symlink_rights():
            atomic = load()
            monkeypatch.setattr(atomic, "_create_symlink_or_junction", lambda target, link: (
                os.symlink(target, link), "symlink")[1])
            return atomic

        monkeypatch.setattr(mod, "_load_atomic_write", with_symlink_rights)
        result = mod.update(group, "1.6.2")
        assert (result["status"], result["current_target"]) == ("flipped", "1.6.2")
        assert os.readlink(group / "active") == "1.6.2"
        assert sorted(p.name for p in group.iterdir()) == ["1.0.0", "1.6.2", "active"]

    def test_the_mismatch_message_names_flip_link(self, tmp_path: Path) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        message = mod._envelope_mismatch(group, "1.6.2", "1.0.0")["halt_message"]
        assert (f'`uv run "{mod.ATOMIC_WRITE_HELPER}" flip-link --link "{group / "active"}" --target "1.6.2"`'
                in message), message
        assert "ln -s" not in message


# --------------------------------------------------------------------------
# repair-after-drop (#1158)
# --------------------------------------------------------------------------


def _dropped(tmp_path: Path, active: str | None, statuses: dict, on_disk: tuple, link: str | None,
             name: str = "cognee") -> Path:
    """A skill group after a version purge: the manifest the drop left, the version packages on disk and `active`."""
    skills = tmp_path / "skills"
    group = skills / name
    group.mkdir(parents=True)
    for version in on_disk:
        (group / version / name).mkdir(parents=True)
    versions = {v: {"ides": [], "last_exported": "2026-01-01", "status": s} for v, s in statuses.items()}
    manifest = {"schema_version": "2", "exports": {name: {"active_version": active, "versions": versions}}}
    (skills / ".export-manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    if link is not None:
        os.symlink(link, group / "active")
    return group


def _rows(statuses: dict, on_disk: tuple) -> list[dict]:
    """skf-skill-inventory.py resolve's version rows, newest first."""
    names = sorted(set(statuses) | set(on_disk), key=lambda v: [int(p) for p in v.split(".")], reverse=True)
    return [{"version": v, "status": statuses.get(v), "in_manifest": v in statuses, "on_disk": v in on_disk}
            for v in names]


class TestPickNewActive:
    @pytest.mark.parametrize("active, statuses, on_disk, dropped, expected", [
        ("0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"}, ("0.6.0",), "0.5.0", "0.6.0"),
        ("0.5.0", {"0.6.0": "archived", "0.5.0": "deprecated", "0.4.0": "archived"}, ("0.6.0", "0.4.0"), "0.5.0",
         "0.6.0"),
        ("0.6.0", {"0.6.0": "deprecated", "0.5.0": "archived"}, ("0.6.0", "0.5.0"), "0.4.0", "0.5.0"),
        ("0.6.0", {"0.6.0": "active", "0.5.0": "archived"}, ("0.5.0",), "0.4.0", "0.5.0"),
        (None, {"0.6.0": "archived", "0.5.0": "archived"}, ("0.6.0", "0.5.0"), "0.6.0", "0.5.0"),
        ("0.5.0", {"0.5.0": "deprecated", "0.4.0": "deprecated"}, ("0.4.0",), "0.5.0", None),
        ("0.5.0", {"0.5.0": "deprecated"}, ("0.7.0",), "0.5.0", None),
    ], ids=["manifest-active", "newest-non-deprecated", "active-deprecated", "active-not-on-disk", "no-active",
            "none-left", "unexported-folder-is-no-candidate"])
    def test_one_rule(self, active, statuses, on_disk, dropped, expected) -> None:
        assert mod.pick_new_active(active, _rows(statuses, on_disk), dropped) == expected

    @pytest.mark.parametrize("target, names", [
        ("0.5.0", True), ("0.5.0/", True), ("./0.5.0", True), ("0.6.0", False), (None, False), ("", False),
        ("\\\\?\\C:\\skills\\cognee\\0.5.0", True), ("/abs/skills/cognee/0.5.0", True),
        ("/abs/skills/other/0.5.0", False), ("../other/0.5.0", False), ("0.5.0-rc", False),
    ])
    def test_names_version(self, tmp_path: Path, target: str | None, names: bool) -> None:
        assert mod.names_version(target, tmp_path / "cognee", "0.5.0") is names


@POSIX_ONLY
class TestRepairAfterDrop:
    def _cli(self, group: Path, dropped: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict | None, str]:
        code = mod.main(["repair-after-drop", "--skill-group", str(group), "--dropped", dropped])
        out, err = capsys.readouterr()
        return code, json.loads(out) if out else None, err

    def test_the_manifest_active_version_is_kept(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        group = _dropped(tmp_path, "0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"}, ("0.6.0",), "0.5.0")
        code, result, err = self._cli(group, "0.5.0", capsys)
        assert (code, err) == (0, "")
        assert result == {"action": "flipped", "link_target": "0.5.0", "new_active": "0.6.0", "manual_fix": None,
                          "error": None}
        assert os.readlink(group / "active") == "0.6.0"
        assert sorted(p.name for p in group.iterdir()) == ["0.6.0", "active"], "no lock or temp link left"

    def test_the_dropped_active_version_gives_way_to_the_newest(self, tmp_path: Path,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
        statuses = {"0.6.0": "archived", "0.5.0": "deprecated", "0.4.0": "archived"}
        group = _dropped(tmp_path, "0.5.0", statuses, ("0.6.0", "0.4.0"), "0.5.0")
        code, result, _ = self._cli(group, "0.5.0", capsys)
        assert (code, result["action"], result["new_active"]) == (0, "flipped", "0.6.0")
        assert os.readlink(group / "active") == "0.6.0"

    def test_with_no_version_left_the_link_is_removed(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        group = _dropped(tmp_path, "0.5.0", {"0.5.0": "deprecated"}, (), "0.5.0")
        code, result, _ = self._cli(group, "0.5.0", capsys)
        assert code == 0
        assert result == {"action": "unlinked", "link_target": "0.5.0", "new_active": None, "manual_fix": None,
                          "error": None}
        assert not os.path.lexists(group / "active")

    @pytest.mark.parametrize("link", ["0.7.0", "0.6.0", None], ids=["newer-unexported", "another-version", "no-link"])
    def test_a_link_that_names_another_version_is_left_alone(self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                             link: str | None) -> None:
        """The purge never moves a link a writing workflow flipped to a newer version it has not exported."""
        statuses = {"0.6.0": "active", "0.5.0": "deprecated"}
        group = _dropped(tmp_path, "0.6.0", statuses, ("0.7.0", "0.6.0"), link)
        code, result, _ = self._cli(group, "0.5.0", capsys)
        assert code == 0
        assert result == {"action": "none", "link_target": link, "new_active": None, "manual_fix": None,
                          "error": None}
        assert (os.readlink(group / "active") if link else os.path.lexists(group / "active")) == (link or False)

    def test_a_real_folder_at_active_is_left_alone(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        group = _dropped(tmp_path, "0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"}, ("0.6.0",), None)
        (group / "active").mkdir()
        code, result, _ = self._cli(group, "0.5.0", capsys)
        assert (code, result["action"], result["link_target"]) == (0, "none", None)
        assert (group / "active").is_dir() and not os.path.islink(group / "active")

    def test_a_held_lock_is_busy_with_a_fix_for_after_the_other_run(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        group = _dropped(tmp_path, "0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"}, ("0.6.0",), "0.5.0")
        monkeypatch.setattr(mod, "FLIP_LOCK_WAIT_SECONDS", 0.2)
        fd = _hold_lock(group)
        try:
            code, result, _ = self._cli(group, "0.5.0", capsys)
        finally:
            aw._release_lock(fd)
            os.close(fd)
        assert (code, result["action"], result["new_active"]) == (2, "failed", "0.6.0")
        assert result["error"] == f"another process holds flip lock on {group / 'active'}"
        assert result["manual_fix"] == (
            f'once the other run has finished, if `active` still names 0.5.0, run `uv run "{mod.ATOMIC_WRITE_HELPER}" '
            f'flip-link --link "{group / "active"}" --target "0.6.0"`')
        assert os.readlink(group / "active") == "0.5.0"

    def test_a_lock_error_leaves_a_fix_with_the_error(self, tmp_path: Path,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
        group = _dropped(tmp_path, "0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"}, ("0.6.0",), "0.5.0")
        (group / "active.skf-lock").mkdir()
        code, result, _ = self._cli(group, "0.5.0", capsys)
        assert (code, result["action"]) == (2, "failed")
        assert result["manual_fix"].startswith(
            f'if `active` still names 0.5.0, run `uv run "{mod.ATOMIC_WRITE_HELPER}" flip-link --link '
            f'"{group / "active"}" --target "0.6.0"` ([Errno {errno.EISDIR}]')
        assert result["manual_fix"].endswith(f"{result['error']})")
        assert os.readlink(group / "active") == "0.5.0"
        # The fix works once the folder the error names is gone.
        (group / "active.skf-lock").rmdir()
        assert _flip_link(group / "active", "0.6.0").returncode == 0
        assert os.readlink(group / "active") == "0.6.0"

    @pytest.mark.parametrize("fails", ["flip", "unlink", "mismatch"])
    def test_a_flip_or_unlink_that_fails_leaves_a_fix_with_the_error(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], fails: str) -> None:
        on_disk = () if fails == "unlink" else ("0.6.0", "0.4.0")
        statuses = {"0.6.0": "active", "0.5.0": "deprecated", "0.4.0": "archived"}
        group = _dropped(tmp_path, "0.6.0", statuses, on_disk, "0.5.0")
        if fails == "flip":
            def broken_flip(link_path: Path, target: str) -> None:
                raise OSError(errno.ENOSPC, "No space left on device")
            monkeypatch.setattr(mod, "atomic_flip_symlink", broken_flip)
        elif fails == "mismatch":
            def other_flip(link_path: Path, target: str) -> None:
                os.unlink(link_path)
                os.symlink("0.4.0", link_path)
            monkeypatch.setattr(mod, "atomic_flip_symlink", other_flip)
        else:
            load = mod._load_atomic_write

            def without_unlink():
                atomic = load()

                def refuse(path):
                    raise PermissionError(errno.EACCES, "Permission denied", str(path))
                monkeypatch.setattr(atomic, "_remove_link", refuse)
                return atomic
            monkeypatch.setattr(mod, "_load_atomic_write", without_unlink)
        code, result, _ = self._cli(group, "0.5.0", capsys)
        assert (code, result["action"], result["link_target"]) == (2, "failed", "0.5.0")
        link = group / "active"
        if fails == "unlink":
            assert result["new_active"] is None
            assert result["manual_fix"] == (
                f'if `active` still names 0.5.0, remove the link: `rm "{link}"` ({result["error"]})')
            assert os.readlink(link) == "0.5.0"
        else:
            command = f'run `uv run "{mod.ATOMIC_WRITE_HELPER}" flip-link --link "{link}" --target "0.6.0"`'
            assert result["manual_fix"] == f"if `active` still names 0.5.0, {command} ({result['error']})"
            said = {"flip": "No space left on device", "mismatch": "`active` names 0.4.0 after the flip"}[fails]
            assert said in result["error"]
            if fails == "flip":
                assert os.readlink(link) == "0.5.0", "a flip that fails leaves the link as it was"
        assert not (group / "active.skf-lock").exists(), "the lock is released"

    @pytest.mark.parametrize("broken", ["corrupt-manifest", "cp1252-manifest", "not-a-folder", "no-inventory",
                                        "no-atomic-write"])
    def test_what_it_cannot_read_exits_1_and_leaves_the_link(self, tmp_path: Path, broken: str) -> None:
        group = _dropped(tmp_path, "0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"}, ("0.6.0",), "0.5.0")
        script, target = SCRIPT_PATH, group
        if broken == "corrupt-manifest":
            (group.parent / ".export-manifest.json").write_bytes(b"{not json")
        elif broken == "cp1252-manifest":
            (group.parent / ".export-manifest.json").write_bytes('{"exports": {"caf\u00e9": {}}}'.encode("cp1252"))
        elif broken == "not-a-folder":
            target = tmp_path / "not-a-folder"
            target.write_text("x\n", encoding="utf-8")
        else:
            scripts = tmp_path / "partial-install"
            scripts.mkdir()
            script = scripts / SCRIPT_PATH.name
            shutil.copyfile(SCRIPT_PATH, script)
            kept = "skf-atomic-write.py" if broken == "no-inventory" else "skf-skill-inventory.py"
            shutil.copyfile(SCRIPT_PATH.with_name(kept), scripts / kept)
        proc = subprocess.run([sys.executable, str(script), "repair-after-drop", "--skill-group", str(target),
                               "--dropped", "0.5.0"], capture_output=True, text=True, encoding="utf-8", check=False)
        assert (proc.returncode, proc.stdout) == (1, ""), proc.stderr
        [line] = proc.stderr.splitlines()
        said = {"corrupt-manifest": "error: cannot read the export manifest: JSON parse error",
                "cp1252-manifest": "error: cannot read the export manifest: Cannot read",
                "not-a-folder": f"error: skill-group not a directory: {target}",
                "no-inventory": "error: cannot load the inventory helper ",
                "no-atomic-write": "error: cannot load the flip-lock helper "}[broken]
        assert line.startswith(said), line
        assert os.readlink(group / "active") == "0.5.0", "a manifest it cannot read never leads to an unlink"

    def test_the_cli_prints_the_json(self, tmp_path: Path) -> None:
        group = _dropped(tmp_path, "0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"}, ("0.6.0",), "0.5.0")
        proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "repair-after-drop", "--skill-group", str(group),
                               "--dropped", "0.5.0"], capture_output=True, text=True, encoding="utf-8", check=False)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["action"] == "flipped"
        proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "repair-after-drop", "--skill-group", str(group)],
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 2 and "--dropped" in proc.stderr


@POSIX_ONLY
class TestRepairAfterDropOnWindowsSimulated:
    @pytest.mark.parametrize("left, expected", [(("1.0.0", "1.6.2"), "1.6.2"), ((), None)],
                             ids=["flipped", "unlinked"])
    def test_a_dangling_junction_to_the_dropped_version_is_repaired(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
            left: tuple, expected: str | None) -> None:
        """A junction whose folder the purge deleted reads back as its stored `...\\oms-cognee\\0.5.8` path."""
        statuses = {"1.6.2": "active", "1.0.0": "archived", "0.5.8": "deprecated"}
        group = _dropped(tmp_path, "1.6.2" if left else "0.5.8", statuses if left else {"0.5.8": "deprecated"},
                         (*left, "0.5.8"), None, name="oms-cognee")
        _junction(group, "0.5.8")
        shutil.rmtree(group / "0.5.8")
        _simulate_windows_links(monkeypatch)
        assert mod.read_link_target(group / "active") == JUNCTION_PREFIX + "0.5.8"
        assert mod.main(["repair-after-drop", "--skill-group", str(group), "--dropped", "0.5.8"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert (result["action"], result["link_target"], result["new_active"]) == (
            "flipped" if expected else "unlinked", JUNCTION_PREFIX + "0.5.8", expected)
        if expected:
            assert not (group / "active").is_symlink() and (group / "active").resolve() == (group / expected).resolve()
        else:
            assert not os.path.lexists(group / "active")

    def test_a_junction_to_another_version_is_left_alone(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        group = _dropped(tmp_path, "1.0.0", {"1.0.0": "active", "0.5.8": "deprecated"}, ("1.6.2", "1.0.0"), None,
                         name="oms-cognee")
        _junction(group, "1.6.2")
        _simulate_windows_links(monkeypatch)
        assert mod.main(["repair-after-drop", "--skill-group", str(group), "--dropped", "0.5.8"]) == 0
        assert json.loads(capsys.readouterr().out)["action"] == "none"
        assert (group / "active").resolve() == (group / "1.6.2").resolve()


def _no_symlink_rights(monkeypatch: pytest.MonkeyPatch) -> None:
    """os.symlink fails as Windows does without Developer Mode or admin (ERROR_PRIVILEGE_NOT_HELD)."""
    def refuse(src, dst, *args, **kwargs):
        raise OSError(errno.EPERM, "A required privilege is not held by the client", os.fspath(dst), 1314)

    monkeypatch.setattr(os, "symlink", refuse)


def _is_junction(path: Path) -> bool:
    return not path.is_symlink() and os.lstat(path).st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="the real junction path runs on Windows only")
class TestNativeWindows:
    def _update(self, group: Path, version: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
        code = mod.main(["update", "--skill-group", str(group), "--version", version])
        return code, json.loads(capsys.readouterr().out)

    def _verify(self, group: Path, version: str, capsys: pytest.CaptureFixture[str]) -> dict:
        assert mod.main(["verify", "--skill-group", str(group), "--version", version]) == 0
        return json.loads(capsys.readouterr().out)

    def test_update_makes_a_junction_without_symlink_rights(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        group = _make_group(tmp_path, "1.0.0")
        _no_symlink_rights(monkeypatch)
        code, result = self._update(group, "1.0.0", capsys)
        assert (code, result["status"]) == (0, "flipped"), result
        assert _is_junction(group / "active")
        assert self._verify(group, "1.0.0", capsys)["current_target"] == "1.0.0"
        assert sorted(p.name for p in group.iterdir()) == ["1.0.0", "active"], "no lock or temp link left"

    def test_update_flips_a_junction_to_another_version(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        _no_symlink_rights(monkeypatch)
        assert self._update(group, "1.0.0", capsys)[0] == 0
        code, result = self._update(group, "1.6.2", capsys)
        assert (code, result["log_message"]) == (0, "active_symlink_update: flipped (1.0.0 -> 1.6.2)"), result
        assert _is_junction(group / "active")
        assert (group / "active").resolve() == (group / "1.6.2").resolve()
        assert self._verify(group, "1.6.2", capsys)["current_target"] == "1.6.2"
        code, result = self._update(group, "1.6.2", capsys)
        assert (code, result["action_taken"]) == (0, "no-op")
        assert sorted(p.name for p in group.iterdir()) == ["1.0.0", "1.6.2", "active"]

    def test_update_flips_a_junction_whose_folder_was_deleted(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """Drop Skill's repoint after a purge deleted the version the junction names."""
        group = _make_group(tmp_path, "0.5.8", "1.0.0")
        _no_symlink_rights(monkeypatch)
        assert self._update(group, "0.5.8", capsys)[0] == 0
        shutil.rmtree(group / "0.5.8")
        code, result = self._update(group, "1.0.0", capsys)
        assert (code, result["status"]) == (0, "flipped"), result
        assert _is_junction(group / "active")
        assert self._verify(group, "1.0.0", capsys)["current_target"] == "1.0.0"
        assert sorted(p.name for p in group.iterdir()) == ["1.0.0", "active"], "no lock or temp link left"

    def test_update_flips_over_a_directory_symlink(
            self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """With the runner's own symlink privilege: the rename over an existing directory link."""
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        try:
            os.symlink("1.0.0", group / "active", target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"this runner holds no symlink privilege: {exc}")
        code, result = self._update(group, "1.6.2", capsys)
        assert (code, result["status"]) == (0, "flipped"), result
        assert (group / "active").is_symlink() and os.readlink(group / "active") == "1.6.2"
        assert self._verify(group, "1.6.2", capsys)["current_target"] == "1.6.2"
        assert sorted(p.name for p in group.iterdir()) == ["1.0.0", "1.6.2", "active"]

    def test_verify_exits_1_when_a_folder_replaced_the_junction(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """#742's case on Windows: a real folder put at `active` after a flip gives exit 1, nothing on stdout and
        one `error:` line, the outcome write.md §8a halts on."""
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        _no_symlink_rights(monkeypatch)
        assert self._update(group, "1.6.2", capsys)[0] == 0
        assert _is_junction(group / "active")
        os.rmdir(group / "active")
        assert (group / "1.6.2").is_dir(), "removing the junction left its folder"
        (group / "active").mkdir()
        (group / "active" / "SKILL.md").write_text("copy\n", encoding="utf-8")
        assert mod.main(["verify", "--skill-group", str(group), "--version", "1.6.2"]) == 1
        out, err = capsys.readouterr()
        assert out == ""
        lines = err.splitlines()
        assert len(lines) == 1, err
        assert lines[0].startswith("error: ") and str(group / "active") in lines[0] and "not a symlink" in lines[0]


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


@POSIX_ONLY
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

    def test_verify_exits_1_with_no_json_when_a_folder_replaced_the_link_after_a_flip(self, tmp_path: Path) -> None:
        """#742: the outcomes write.md §8a's "any other exit" rule meets. A real folder put at `active` between
        §8's flip and §8a's check (a copy, as `ln -s` makes in Git Bash without symlink rights), and a skill folder
        that is no folder, give exit 1, nothing on stdout and one `error:` line on stderr."""
        group = _make_group(tmp_path, "1.0.0", "1.6.2")
        os.symlink("1.0.0", group / "active")
        flipped = _run_cli("update", "--skill-group", str(group), "--version", "1.6.2")
        assert flipped.returncode == 0, flipped.stderr
        assert json.loads(flipped.stdout)["status"] == "flipped"
        os.unlink(group / "active")
        (group / "active").mkdir()
        (group / "active" / "SKILL.md").write_text("copy\n", encoding="utf-8")
        result = _run_cli("verify", "--skill-group", str(group), "--version", "1.6.2")
        assert result.returncode == 1
        assert result.stdout == ""
        last = result.stderr.splitlines()[-1]
        assert last.startswith("error: ") and str(group / "active") in last and "not a symlink" in last
        not_a_folder = tmp_path / "not-a-folder"
        not_a_folder.write_text("x\n", encoding="utf-8")
        for missing in (not_a_folder, tmp_path / "gone"):
            result = _run_cli("verify", "--skill-group", str(missing), "--version", "1.6.2")
            assert result.returncode == 1
            assert result.stdout == ""
            assert result.stderr.splitlines()[-1] == f"error: skill-group not a directory: {missing}"
