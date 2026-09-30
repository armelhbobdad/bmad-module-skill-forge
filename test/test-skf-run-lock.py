#!/usr/bin/env python3
"""Tests for skf-run-lock.py.

A workflow takes its lock in one tool call and releases it several calls
later, each call in a new process, so the headline test acquires the lock
in a process that exits, then checks that a second run is refused until the
stale timeout passes and replaces the lock after it. The rest covers
release by the owner only, renewal by the owner, run ids, the lock files
older SKF versions left (PID and time lines, the empty file an `flock`
left, which empty_is_stale replaces at once), the guard that keeps
simultaneous calls from both taking the lock, acquire_within() (the
in-call form skf-forge-tier-rw.py uses) and the CLI exit codes, usage
errors included.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-run-lock.py"

spec = importlib.util.spec_from_file_location("skf_run_lock", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

T0 = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
HOUR = 3600.0
OWNER_A = "update-skill:demo:run-a"
OWNER_B = "update-skill:demo:run-b"

# Runs the script once a start file exists, so several processes reach
# acquire at the same moment.
RUNNER = (
    "import os, runpy, sys, time\n"
    "go, script = sys.argv[1], sys.argv[2]\n"
    "while not os.path.exists(go):\n"
    "    time.sleep(0.002)\n"
    "sys.argv = sys.argv[2:]\n"
    "runpy.run_path(script, run_name='__main__')\n"
)


def _cli(*args: str) -> tuple[int, dict | None, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True, text=True, timeout=60,
    )
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, out, proc.stderr


def _record(lock: Path) -> dict:
    return json.loads(lock.read_text(encoding="utf-8"))


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def _at(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def lock(tmp_path: Path) -> Path:
    return tmp_path / "forge" / ".skf-update.lock"


# ─── acquire ────────────────────────────────────────────────────────────────


class TestAcquire:
    def test_takes_a_free_lock_and_records_owner_and_time(self, lock):
        out = mod.acquire(lock, OWNER_A, HOUR, now=T0)
        assert out == {
            "acquired": True,
            "refreshed": False,
            "lock": str(lock),
            "owner": OWNER_A,
            "run_id": "run-a",
            "held_by": OWNER_A,
            "held_since": "2026-09-30T10:00:00Z",
            "stale_at": "2026-09-30T11:00:00Z",
            "stale_after_minutes": 60,
            "stale_replaced": None,
            "message": out["message"],
        }
        assert _record(lock) == {"owner": OWNER_A, "acquired_at": "2026-09-30T10:00:00Z",
                                 "tool": "skf-run-lock"}
        # The parent folder was created, and no temp or guard file is left.
        assert _names(lock.parent) == [".skf-update.lock"]

    def test_refuses_another_owner_while_the_lock_is_fresh(self, lock):
        mod.acquire(lock, OWNER_A, HOUR, now=T0)
        out = mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(minutes=59, seconds=59))
        assert out["acquired"] is False
        assert out["held_by"] == OWNER_A
        assert out["held_since"] == "2026-09-30T10:00:00Z"
        assert out["stale_at"] == "2026-09-30T11:00:00Z"
        assert out["stale_replaced"] is None
        assert out["owner"] == OWNER_B
        assert str(lock) in out["message"] and OWNER_A in out["message"]
        assert _record(lock)["owner"] == OWNER_A

    def test_replaces_a_stale_lock_and_says_whose_it_was(self, lock):
        mod.acquire(lock, OWNER_A, HOUR, now=T0)
        out = mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(hours=1))
        assert out["acquired"] is True
        assert out["refreshed"] is False
        assert out["stale_replaced"] == {"held_by": OWNER_A, "held_since": "2026-09-30T10:00:00Z"}
        assert out["held_by"] == OWNER_B
        assert _record(lock)["owner"] == OWNER_B
        assert _names(lock.parent) == [".skf-update.lock"]

    def test_the_owner_renews_its_own_lock(self, lock):
        mod.acquire(lock, OWNER_A, HOUR, now=T0)
        out = mod.acquire(lock, OWNER_A, HOUR, now=T0 + timedelta(minutes=30))
        assert out["acquired"] is True
        assert out["refreshed"] is True
        assert out["held_since"] == "2026-09-30T10:30:00Z"
        # Renewed at 10:30, so the lock is still fresh at 11:15.
        later = mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(minutes=75))
        assert later["acquired"] is False
        assert later["stale_at"] == "2026-09-30T11:30:00Z"

    @pytest.mark.parametrize("owner", ["test-skill:demo", "test-skill:demo:"])
    def test_an_owner_without_run_id_gets_a_new_one(self, lock, owner):
        out = mod.acquire(lock, owner, HOUR, now=T0)
        assert mod.RUN_ID_RE.fullmatch(out["run_id"])
        assert out["run_id"].startswith("20260930T100000Z-")
        assert out["owner"] == f"test-skill:demo:{out['run_id']}"
        assert _record(lock)["owner"] == out["owner"]

    @pytest.mark.parametrize("owner", [
        "", "demo", ":demo", "update-skill:", "update-skill::run",
        "update-skill:de mo:1", "update-skill:demo:1\n", "x:" + "y" * 250,
    ])
    def test_rejects_a_malformed_owner(self, lock, owner):
        with pytest.raises(ValueError):
            mod.acquire(lock, owner, HOUR, now=T0)
        assert not lock.exists()

    def test_an_owner_must_fit_with_the_run_id_acquire_adds(self, lock):
        # A run id and its colon are 26 characters, and an owner is at most 200.
        with pytest.raises(ValueError):
            mod.acquire(lock, "x:" + "y" * 173, HOUR, now=T0)
        assert not lock.exists()
        out = mod.acquire(lock, "x:" + "y" * 172, HOUR, now=T0)
        assert len(out["owner"]) == mod.OWNER_MAX_LEN
        # release takes every owner acquire prints.
        assert mod.release(lock, out["owner"])["released"] is True

    @pytest.mark.parametrize("stale_after", [
        0, -1, float("nan"), float("inf"), mod.MAX_STALE_AFTER_MIN * 60 + 1, 1e12,
    ])
    def test_rejects_a_timeout_out_of_range(self, lock, stale_after):
        with pytest.raises(ValueError):
            mod.acquire(lock, OWNER_A, stale_after, now=T0)
        assert not lock.exists()

    def test_the_longest_timeout_is_one_year(self, lock):
        out = mod.acquire(lock, OWNER_A, mod.MAX_STALE_AFTER_MIN * 60, now=T0)
        assert out["stale_at"] == "2027-09-30T10:00:00Z"
        assert out["stale_after_minutes"] == 525600

    def test_a_lock_dated_near_year_9999_is_refused_without_overflow(self, lock):
        lock.parent.mkdir(parents=True)
        lock.write_text(json.dumps({"owner": OWNER_A, "acquired_at": "9999-12-31T23:00:00Z"}) + "\n",
                        encoding="utf-8")
        out = mod.acquire(lock, OWNER_B, HOUR * 2, now=T0)
        assert out["acquired"] is False
        assert out["stale_at"] == "9999-12-31T23:59:59Z"

    def test_rejects_a_lock_path_that_is_a_folder(self, tmp_path):
        with pytest.raises(ValueError):
            mod.acquire(tmp_path, OWNER_A, HOUR, now=T0)


# ─── lock files the helper did not write ────────────────────────────────────


class TestForeignLockFiles:
    def test_pid_lock_from_an_older_version_goes_stale_by_its_time(self, lock):
        lock.parent.mkdir(parents=True)
        lock.write_bytes(b"12345\n2026-09-30T10:00:00Z\n")
        held = mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(minutes=10))
        assert held["acquired"] is False
        assert held["held_by"] is None
        assert held["held_since"] == "2026-09-30T10:00:00Z"
        out = mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(hours=1))
        assert out["acquired"] is True
        assert out["stale_replaced"] == {"held_by": None, "held_since": "2026-09-30T10:00:00Z"}
        assert _record(lock)["owner"] == OWNER_B

    @pytest.mark.parametrize("content", [b"", b"not a lock record\n", b"{\"owner\": 7}\n"])
    def test_a_file_with_no_owner_uses_its_modification_time(self, lock, content):
        lock.parent.mkdir(parents=True)
        lock.write_bytes(content)
        os.utime(lock, (T0.timestamp(), T0.timestamp()))
        held = mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(minutes=30))
        assert held["acquired"] is False
        assert held["held_by"] is None
        assert held["held_since"] == "2026-09-30T10:00:00Z"
        out = mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(hours=2))
        assert out["acquired"] is True
        assert out["stale_replaced"]["held_by"] is None

    def test_a_record_with_a_bad_time_keeps_its_owner(self, lock):
        lock.parent.mkdir(parents=True)
        lock.write_text(json.dumps({"owner": OWNER_A, "acquired_at": "yesterday"}) + "\n",
                        encoding="utf-8")
        os.utime(lock, (T0.timestamp(), T0.timestamp()))
        held = mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(minutes=1))
        assert held["held_by"] == OWNER_A
        assert held["held_since"] == "2026-09-30T10:00:00Z"

    def test_empty_is_stale_replaces_a_fresh_empty_file_at_once(self, lock):
        lock.parent.mkdir(parents=True)
        lock.write_bytes(b"")
        os.utime(lock, (T0.timestamp(), T0.timestamp()))
        out = mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(seconds=1), empty_is_stale=True)
        assert out["acquired"] is True
        assert out["stale_replaced"] == {"held_by": None, "held_since": "2026-09-30T10:00:00Z"}
        assert _record(lock)["owner"] == OWNER_B

    @pytest.mark.parametrize("content", [
        b"12345\n2026-09-30T10:00:00Z\n",
        (json.dumps({"owner": OWNER_A, "acquired_at": "2026-09-30T10:00:00Z"}) + "\n").encode(),
    ])
    def test_empty_is_stale_still_honours_a_lock_with_content(self, lock, content):
        lock.parent.mkdir(parents=True)
        lock.write_bytes(content)
        out = mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(minutes=1), empty_is_stale=True)
        assert out["acquired"] is False
        assert lock.read_bytes() == content


# ─── release ────────────────────────────────────────────────────────────────


class TestRelease:
    def test_the_owner_releases_its_lock(self, lock):
        mod.acquire(lock, OWNER_A, HOUR, now=T0)
        out = mod.release(lock, OWNER_A)
        assert out["released"] is True
        assert out["reason"] is None
        assert out["held_by"] is None
        assert not lock.exists()
        assert _names(lock.parent) == []

    def test_another_run_cannot_release_it(self, lock):
        mod.acquire(lock, OWNER_A, HOUR, now=T0)
        out = mod.release(lock, OWNER_B)
        assert out["released"] is False
        assert out["reason"] == "not-owner"
        assert out["held_by"] == OWNER_A
        assert out["held_since"] == "2026-09-30T10:00:00Z"
        assert _record(lock)["owner"] == OWNER_A

    def test_a_run_whose_lock_was_replaced_leaves_the_new_one(self, lock):
        mod.acquire(lock, OWNER_A, HOUR, now=T0)
        mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(hours=2))
        out = mod.release(lock, OWNER_A)
        assert out["reason"] == "not-owner"
        assert _record(lock)["owner"] == OWNER_B

    def test_a_lock_that_names_no_owner_is_left_in_place(self, lock):
        lock.parent.mkdir(parents=True)
        lock.write_bytes(b"12345\n2026-09-30T10:00:00Z\n")
        out = mod.release(lock, OWNER_A)
        assert out["reason"] == "not-owner"
        assert out["held_by"] is None
        assert lock.read_bytes() == b"12345\n2026-09-30T10:00:00Z\n"

    def test_no_lock_is_nothing_to_release(self, lock):
        out = mod.release(lock, OWNER_A)
        assert out["released"] is False
        assert out["reason"] == "absent"
        # A release never creates the lock's folder.
        assert not lock.parent.exists()
        lock.parent.mkdir()
        assert mod.release(lock, OWNER_A)["reason"] == "absent"
        assert _names(lock.parent) == []

    @pytest.mark.parametrize("owner", [
        "", "demo", ":demo", "update-skill:demo", "update-skill:demo:", "update-skill:de mo:1",
    ])
    def test_rejects_an_owner_that_could_never_match(self, lock, owner):
        """acquire always writes a run id, so an owner without one is a caller's mistake."""
        mod.acquire(lock, OWNER_A, HOUR, now=T0)
        with pytest.raises(ValueError):
            mod.release(lock, owner)
        assert _record(lock)["owner"] == OWNER_A


# ─── the guard ──────────────────────────────────────────────────────────────


class TestGuard:
    def test_acquire_waits_for_the_guard_another_call_holds(self, lock):
        lock.parent.mkdir(parents=True)
        with mod._Guard(lock):
            proc = subprocess.Popen(
                [sys.executable, str(SCRIPT_PATH), "acquire", "--lock", str(lock),
                 "--owner", OWNER_B],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            time.sleep(0.5)
            assert proc.poll() is None, "acquire did not wait for the guard"
            assert not lock.exists()
        stdout, stderr = proc.communicate(timeout=60)
        assert proc.returncode == 0, stderr
        assert json.loads(stdout)["acquired"] is True
        assert _names(lock.parent) == [".skf-update.lock"]

    def test_a_guard_left_by_a_killed_call_is_taken_and_removed(self, lock):
        lock.parent.mkdir(parents=True)
        (lock.parent / ".skf-update.lock.skf-guard").write_bytes(b"")
        assert mod.acquire(lock, OWNER_A, HOUR, now=T0)["acquired"] is True
        assert _names(lock.parent) == [".skf-update.lock"]

    def test_a_guard_held_too_long_is_an_error(self, lock, monkeypatch):
        lock.parent.mkdir(parents=True)
        lock.write_bytes(b"")
        monkeypatch.setattr(mod, "GUARD_WAIT_SEC", 0.2)
        with mod._Guard(lock):
            with pytest.raises(OSError):
                mod.acquire(lock, OWNER_B, HOUR, now=T0 + timedelta(days=1))
            with pytest.raises(OSError):
                mod.release(lock, OWNER_B)
        assert lock.read_bytes() == b""


# ─── acquire_within ─────────────────────────────────────────────────────────


class TestAcquireWithin:
    def test_raises_lock_busy_when_the_wait_runs_out(self, lock):
        mod.acquire(lock, OWNER_A, HOUR)
        start = time.monotonic()
        with pytest.raises(mod.LockBusy) as busy:
            mod.acquire_within(lock, OWNER_B, HOUR, 0.3)
        assert time.monotonic() - start >= 0.3
        assert busy.value.result["held_by"] == OWNER_A
        assert _record(lock)["owner"] == OWNER_A

    def test_takes_the_lock_once_the_holder_releases_it(self, lock):
        mod.acquire(lock, OWNER_A, HOUR)
        timer = threading.Timer(0.3, mod.release, args=(lock, OWNER_A))
        timer.start()
        try:
            out = mod.acquire_within(lock, OWNER_B, HOUR, 10)
        finally:
            timer.join()
        assert out["acquired"] is True
        assert _record(lock)["owner"] == OWNER_B

    def test_replaces_a_stale_lock_without_waiting(self, lock):
        mod.acquire(lock, OWNER_A, 1.0, now=datetime.now(timezone.utc) - timedelta(seconds=5))
        out = mod.acquire_within(lock, OWNER_B, 1.0, 0)
        assert out["stale_replaced"]["held_by"] == OWNER_A

    def test_empty_is_stale_is_passed_to_acquire(self, lock):
        lock.parent.mkdir(parents=True)
        lock.write_bytes(b"")
        with pytest.raises(mod.LockBusy):
            mod.acquire_within(lock, OWNER_B, HOUR, 0)
        out = mod.acquire_within(lock, OWNER_B, HOUR, 0, empty_is_stale=True)
        assert out["acquired"] is True
        assert out["stale_replaced"]["held_by"] is None


# ─── across processes (the CLI) ─────────────────────────────────────────────


class TestAcrossProcesses:
    def test_the_lock_outlives_the_process_that_took_it(self, tmp_path):
        """A holder process exits; a second run is refused until the timeout, then replaces it.

        --stale-after 0.05 is 3 seconds. held_since has whole seconds, so the
        second call is refused as long as it starts within 2 seconds of the first.
        """
        lock = tmp_path / "1.0.0" / ".test-skill.lock"
        owner_a, owner_b = "test-skill:demo:run-a", "test-skill:demo:run-b"

        code, first, err = _cli("acquire", "--lock", str(lock), "--owner", owner_a,
                                "--stale-after", "0.05")
        assert code == 0, err
        assert first["acquired"] is True
        assert first["stale_after_minutes"] == 0.05
        # The process that took the lock has exited; the lock is still there.
        assert _record(lock)["owner"] == owner_a

        code, second, err = _cli("acquire", "--lock", str(lock), "--owner", owner_b,
                                 "--stale-after", "0.05")
        assert code == 3, err
        assert second["acquired"] is False
        assert second["held_by"] == owner_a

        stale_at = datetime.strptime(second["stale_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        time.sleep(max((stale_at - datetime.now(timezone.utc)).total_seconds() + 0.2, 0))

        code, third, err = _cli("acquire", "--lock", str(lock), "--owner", owner_b,
                                "--stale-after", "0.05")
        assert code == 0, err
        assert third["acquired"] is True
        assert third["stale_replaced"]["held_by"] == owner_a

        code, out, _ = _cli("release", "--lock", str(lock), "--owner", owner_a)
        assert code == 0
        assert out["released"] is False and out["reason"] == "not-owner"
        assert _record(lock)["owner"] == owner_b

        code, out, _ = _cli("release", "--lock", str(lock), "--owner", owner_b)
        assert code == 0
        assert out["released"] is True
        assert _names(lock.parent) == []

    @pytest.mark.parametrize("stale", [False, True])
    def test_simultaneous_acquires_take_the_lock_once(self, tmp_path, stale):
        lock = tmp_path / ".skf-rename-demo.lock"
        if stale:
            lock.write_bytes(b"4242\n2020-01-01T00:00:00Z\n")
        go = tmp_path / "go"
        owners = [f"rename-skill:demo:run-{i}" for i in range(8)]
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", RUNNER, str(go), str(SCRIPT_PATH), "acquire",
                 "--lock", str(lock), "--owner", owner],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for owner in owners
        ]
        time.sleep(0.5)
        go.write_bytes(b"")
        results = []
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=60)
            assert proc.returncode in (0, 3), stderr
            results.append((proc.returncode, json.loads(stdout)))

        winners = [out for code, out in results if code == 0]
        assert len(winners) == 1
        winner = winners[0]["owner"]
        assert all(out["held_by"] == winner for _, out in results)
        assert _record(lock)["owner"] == winner
        replaced = [out for _, out in results if out["stale_replaced"]]
        assert len(replaced) == (1 if stale else 0)
        assert sorted(p.name for p in tmp_path.iterdir()) == [".skf-rename-demo.lock", "go"]

    def test_run_id(self):
        code, first, _ = _cli("run-id")
        assert code == 0
        assert mod.RUN_ID_RE.fullmatch(first["run_id"])
        _, second, _ = _cli("run-id")
        assert first["run_id"] != second["run_id"]

    @pytest.mark.parametrize("args", [
        ["acquire", "--owner", "update-skill"],
        ["acquire", "--owner", OWNER_A, "--stale-after", "0"],
        ["acquire", "--owner", OWNER_A, "--stale-after", "-5"],
        ["acquire", "--owner", OWNER_A, "--stale-after", "nan"],
        ["acquire", "--owner", OWNER_A, "--stale-after", "525601"],
        ["acquire", "--owner", OWNER_A, "--stale-after", "1e10"],
        ["release", "--owner", "demo"],
        ["release", "--owner", "update-skill:demo"],
    ])
    def test_bad_arguments_exit_1(self, lock, args):
        code, out, err = _cli(*args[:1], "--lock", str(lock), *args[1:])
        assert code == 1
        assert out is None
        assert json.loads(err)["status"] == "error"
        assert not lock.exists()

    @pytest.mark.parametrize("args", [
        ["acquire", "--owner", OWNER_A],
        ["acquire", "--lock", "{lock}"],
        ["acquire", "--lock", "{lock}", "--owner", OWNER_A, "--stale-after", "abc"],
        ["release", "--lock", "{lock}"],
        [],
        ["unlock", "--lock", "{lock}", "--owner", OWNER_A],
        ["run-id", "--lock", "{lock}"],
    ])
    def test_usage_errors_exit_1_with_a_json_error(self, lock, args):
        """argparse's own usage errors are plain text with exit 2; this helper keeps them JSON."""
        code, out, err = _cli(*(a.replace("{lock}", str(lock)) for a in args))
        assert code == 1
        assert out is None
        error = json.loads(err)
        assert error["status"] == "error"
        assert error["message"].startswith("usage error: ")
        assert not lock.parent.exists()

    def test_a_folder_as_lock_exits_1(self, tmp_path):
        code, _, err = _cli("acquire", "--lock", str(tmp_path), "--owner", OWNER_A)
        assert code == 1
        assert "folder" in json.loads(err)["message"]

    def test_a_lock_that_cannot_be_written_exits_2(self, tmp_path):
        blocker = tmp_path / "not-a-folder"
        blocker.write_bytes(b"")
        code, out, err = _cli("acquire", "--lock", str(blocker / "x.lock"), "--owner", OWNER_A)
        assert code == 2
        assert out is None
        assert json.loads(err)["status"] == "error"
