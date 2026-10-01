#!/usr/bin/env python3
"""Tests for skf-update-run-state.py: what an update wrote, undone on a halt.

Covers:
  - begin in-place: a snapshot of the package (links kept as links), the
    forge version's provenance map and evidence report, and the brief;
    rollback restores each byte for byte and removes a file the run created
  - begin new-version: refuses a folder that exists; rollback removes the
    folders the run created and the staging folder, never a link and never
    the folder the active link names
  - finish closes the window: the snapshot goes, rollback changes nothing
  - rollback with no run state, twice, and with --remove-run-dir; the run
    folder found from a stale lock's owner (--run-root, --owner, --skill)
  - finish marks the run finished before the snapshot goes
  - halt: rollback, source tree, run lock (never another run's), then the
    halt's line through the shared emitter with a warning for each step it
    could not finish; a refused payload, and the run again
  - the CLI: argument checks, exit codes and one JSON line
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "shared" / "scripts" / "skf-update-run-state.py"

_spec = importlib.util.spec_from_file_location("skf_update_run_state", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _tree(root: Path) -> dict:
    """Every file under root with its bytes, and every link with its target."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in [*dirnames, *filenames]:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                out[rel] = ("link", os.readlink(path))
            elif path.is_file():
                out[rel] = path.read_bytes()
    return out


def _run(*args: str) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, encoding="utf-8")
    stream = proc.stdout if proc.stdout.strip() else proc.stderr
    return proc.returncode, json.loads(stream)


def _skill(tmp_path: Path) -> dict:
    package = tmp_path / "skills" / "lib" / "1.0.0" / "lib"
    _write(package / "SKILL.md", b"# lib\n\n<!-- [MANUAL:notes] -->\nmine\n<!-- [/MANUAL:notes] -->\n")
    _write(package / "metadata.json", b'{"name": "lib", "version": "1.0.0"}\n')
    _write(package / "references" / "api.md", b"# api\n")
    forge = tmp_path / "forge" / "lib" / "1.0.0"
    _write(forge / "provenance-map.json", b'{"entries": []}\n')
    _write(forge / "test-report-lib-x.md", b"report\n")
    brief = _write(tmp_path / "forge" / "lib" / "skill-brief.yaml", b"name: lib\nscope:\n  exclude: []\n")
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / "skf-update-skill-abc123"
    run_dir.mkdir(parents=True)
    return {"package": package, "forge": forge, "brief": brief, "run_dir": run_dir}


class TestInPlace:
    def test_a_halt_puts_every_file_back(self, tmp_path: Path) -> None:
        s = _skill(tmp_path)
        before = {"package": _tree(s["package"]), "forge": _tree(s["forge"]), "brief": s["brief"].read_bytes()}
        out = mod.begin_in_place(s["run_dir"], s["package"], s["forge"], s["brief"])
        assert out["status"] == "began" and out["failed"] == []
        state = json.loads((s["run_dir"] / "run-state.json").read_bytes())
        assert state["snapshot"]["forge_files"] == {"provenance-map.json": True, "evidence-report.md": False}
        # the repair writes in place: SKILL.md, a reference, metadata, the map, a new evidence report, the brief
        _write(s["package"] / "SKILL.md", b"# lib\n\nrewritten\n")
        _write(s["package"] / "references" / "api.md", b"# api\n\nfixed\n")
        _write(s["package"] / "references" / "new.md", b"# new\n")
        _write(s["package"] / "metadata.json", b'{"name": "lib", "version": "1.0.0", "generation_date": "x"}\n')
        _write(s["forge"] / "provenance-map.json", b'{"entries": [{"export_name": "x"}]}\n')
        _write(s["forge"] / "evidence-report.md", b"## Update Operation\n")
        _write(s["brief"], b"name: lib\nscope:\n  exclude: [pkg/x.py]\n")
        out = mod.rollback(s["run_dir"], remove_run_dir=False)
        assert out["status"] == "rolled-back" and out["failed"] == []
        assert _tree(s["package"]) == before["package"]
        assert _tree(s["forge"]) == before["forge"]  # the evidence report the run created is gone
        assert s["brief"].read_bytes() == before["brief"]
        assert (s["forge"] / "evidence-report.md").as_posix() in out["removed"]
        # nothing beside the package is left behind
        assert sorted(os.listdir(s["package"].parent)) == ["lib"]
        assert mod.rollback(s["run_dir"], remove_run_dir=False)["status"] == "already-rolled-back"

    def test_a_link_in_the_package_stays_a_link(self, tmp_path: Path) -> None:
        s = _skill(tmp_path)
        outside = _write(tmp_path / "outside" / "secret.txt", b"not the skill's\n").parent
        try:
            os.symlink(outside, s["package"] / "assets", target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("this platform cannot create a symlink here")
        mod.begin_in_place(s["run_dir"], s["package"], s["forge"], None)
        assert (s["run_dir"] / "snapshot" / "package" / "assets").is_symlink()
        _write(s["package"] / "SKILL.md", b"changed\n")
        assert mod.rollback(s["run_dir"], remove_run_dir=False)["failed"] == []
        assert (s["package"] / "assets").is_symlink()
        assert (outside / "secret.txt").read_bytes() == b"not the skill's\n"

    def test_finish_closes_the_window(self, tmp_path: Path) -> None:
        s = _skill(tmp_path)
        mod.begin_in_place(s["run_dir"], s["package"], s["forge"], s["brief"])
        _write(s["package"] / "SKILL.md", b"repaired\n")
        assert mod.finish(s["run_dir"])["status"] == "finished"
        assert not (s["run_dir"] / "snapshot").exists()
        assert mod.rollback(s["run_dir"], remove_run_dir=False)["status"] == "finished"
        assert (s["package"] / "SKILL.md").read_bytes() == b"repaired\n"

    def test_a_run_folder_begins_once(self, tmp_path: Path) -> None:
        s = _skill(tmp_path)
        mod.begin_in_place(s["run_dir"], s["package"], s["forge"], None)
        with pytest.raises(ValueError, match="already began"):
            mod.begin_in_place(s["run_dir"], s["package"], s["forge"], None)


class TestNewVersion:
    def _folders(self, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
        group = tmp_path / "skills" / "lib"
        return group, group / "1.0.1", group / "1.0.1.skf-tmp", tmp_path / "forge" / "lib" / "1.0.1"

    def test_a_halt_removes_the_folders_the_run_created(self, tmp_path: Path) -> None:
        group, version, staging, forge = self._folders(tmp_path)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write(group / "1.0.0" / "lib" / "SKILL.md", b"previous\n")
        out = mod.begin_new_version(run_dir, [version, forge], staging, group)
        assert out["status"] == "began"
        _write(version / "lib" / "SKILL.md", b"new\n")
        _write(forge / "provenance-map.json", b"{}\n")
        _write(staging / "lib" / "x", b"half\n")
        out = mod.rollback(run_dir, remove_run_dir=False)
        assert out["failed"] == [] and sorted(out["removed"]) == sorted(
            p.as_posix() for p in (version, forge, staging))
        assert not version.exists() and not forge.exists() and not staging.exists()
        assert (group / "1.0.0" / "lib" / "SKILL.md").read_bytes() == b"previous\n"

    def test_an_existing_folder_is_never_recorded(self, tmp_path: Path) -> None:
        group, version, staging, forge = self._folders(tmp_path)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write(forge / "provenance-map.json", b"{}\n")
        out = mod.begin_new_version(run_dir, [version, forge], staging, group)
        assert out == {**mod._out("exists"), "path": forge.as_posix()}
        assert not (run_dir / "run-state.json").exists()
        code, printed = _run("begin", "--run-dir", str(run_dir), "--mode", "new-version",
                             "--created", str(version), "--created", str(forge))
        assert code == 3 and printed["status"] == "exists"

    def test_the_active_version_and_a_link_are_kept(self, tmp_path: Path) -> None:
        group, version, staging, forge = self._folders(tmp_path)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        mod.begin_new_version(run_dir, [version, forge], staging, group)
        _write(version / "lib" / "SKILL.md", b"new\n")
        forge.parent.mkdir(parents=True)
        (tmp_path / "elsewhere").mkdir()
        try:
            os.symlink("1.0.1", group / "active", target_is_directory=True)
            os.symlink(tmp_path / "elsewhere", forge, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("this platform cannot create a symlink here")
        out = mod.rollback(run_dir, remove_run_dir=False)
        assert sorted(k["why"] for k in out["kept"]) == ["a link: this run never creates one",
                                                         "the active link names it"]
        assert version.is_dir() and forge.is_symlink()

    def test_a_live_version_keeps_its_forge_folder(self, tmp_path: Path) -> None:
        # write.md moved the active link before a later check halted: the version is live
        group, version, staging, forge = self._folders(tmp_path)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        mod.begin_new_version(run_dir, [version, forge], staging, group)
        _write(version / "lib" / "SKILL.md", b"new\n")
        _write(forge / "provenance-map.json", b"{}\n")
        try:
            os.symlink("1.0.1", group / "active", target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("this platform cannot create a symlink here")
        out = mod.rollback(run_dir, remove_run_dir=False)
        assert out["removed"] == [] and version.is_dir() and forge.is_dir()
        assert {k["why"] for k in out["kept"]} == {"the active link names it", "the active link names its version"}


class TestRollbackAndCli:
    def test_no_run_state_is_nothing_to_undo(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".skf-run" / "skf-update-skill-dead"
        _write(run_dir / "halt.json", b"{}")
        assert mod.rollback(run_dir, remove_run_dir=False)["status"] == "nothing-to-roll-back"
        out = mod.rollback(run_dir, remove_run_dir=True)
        assert out["run_dir_removed"] is True and not run_dir.exists()

    @pytest.mark.parametrize("name", ["skf-update-skill-x", "other-run", "skf-update-skill-"],
                             ids=["outside-run-root", "not-an-update-run", "no-run-id"])
    def test_remove_run_dir_deletes_only_an_update_run_folder(self, tmp_path: Path, name: str) -> None:
        # a run id read from a lock file must never reach a folder outside the run root
        parent = tmp_path / ("elsewhere" if name == "skf-update-skill-x" else ".skf-run")
        run_dir = parent / name
        _write(run_dir / "keep.txt", b"not a run folder\n")
        with pytest.raises(ValueError, match="deletes only an update run folder"):
            mod.rollback(run_dir, remove_run_dir=True)
        assert (run_dir / "keep.txt").exists()
        code, out = _run("rollback", "--run-dir", str(run_dir), "--remove-run-dir")
        assert code == 1 and (run_dir / "keep.txt").exists()

    def test_a_traversing_run_id_never_leaves_the_run_root(self, tmp_path: Path) -> None:
        victim = tmp_path / "src"
        _write(victim / "keep.txt", b"keep\n")
        (tmp_path / ".skf-run" / "skf-update-skill-x").mkdir(parents=True)
        run_dir = tmp_path / ".skf-run" / "skf-update-skill-x" / ".." / ".." / "src"
        code, out = _run("rollback", "--run-dir", str(run_dir), "--remove-run-dir")
        assert code == 1 and (victim / "keep.txt").exists()

    def test_an_interrupted_run_is_rolled_back_and_its_folder_removed(self, tmp_path: Path) -> None:
        s = _skill(tmp_path)
        code, out = _run("begin", "--run-dir", str(s["run_dir"]), "--mode", "in-place", "--package",
                         str(s["package"]), "--forge-version", str(s["forge"]), "--brief", str(s["brief"]))
        assert code == 0 and out["status"] == "began"
        _write(s["package"] / "SKILL.md", b"half written\n")
        code, out = _run("rollback", "--run-dir", str(s["run_dir"]), "--remove-run-dir")
        assert code == 0 and out["status"] == "rolled-back" and out["run_dir_removed"] is True
        assert b"[MANUAL:notes]" in (s["package"] / "SKILL.md").read_bytes()
        assert not s["run_dir"].exists()

    @pytest.mark.parametrize("args", [
        ["begin", "--mode", "in-place", "--forge-version", "f"],
        ["begin", "--mode", "new-version", "--package", "p"],
        ["finish"],
    ], ids=["in-place-no-package", "new-version-no-created", "finish-before-begin"])
    def test_bad_calls_exit_1(self, tmp_path: Path, args: list) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        code, out = _run(*args[:1], "--run-dir", str(run_dir), *args[1:])
        assert code == 1 and out["status"] == "error"

    def test_a_state_file_this_helper_did_not_write_is_refused(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        _write(run_dir / "run-state.json", b'{"snapshot": "not mine"}')
        code, out = _run("rollback", "--run-dir", str(run_dir))
        assert code == 1 and "not a run state this helper wrote" in out["message"]


class TestFinishOrder:
    def test_a_snapshot_that_cannot_be_removed_leaves_a_finished_run(self, tmp_path: Path, monkeypatch) -> None:
        s = _skill(tmp_path)
        mod.begin_in_place(s["run_dir"], s["package"], s["forge"], None)

        def refuse(path: Path) -> None:
            raise OSError("locked")

        monkeypatch.setattr(mod, "_remove", refuse)
        out = mod.finish(s["run_dir"])
        # the writes stand: a later rollback (or the next update's cleanup) never reads it as interrupted
        assert out["status"] == "finished" and out["failed"][0]["error"] == "locked"
        assert json.loads((s["run_dir"] / "run-state.json").read_bytes())["finished"] is True
        assert mod.rollback(s["run_dir"], remove_run_dir=False)["status"] == "finished"


class TestRollbackByOwner:
    def test_the_owner_names_the_run_folder(self, tmp_path: Path) -> None:
        s = _skill(tmp_path)
        mod.begin_in_place(s["run_dir"], s["package"], s["forge"], None)
        _write(s["package"] / "SKILL.md", b"half written\n")
        root = s["run_dir"].parent
        code, out = _run("rollback", "--run-root", str(root), "--owner", "update-skill:lib:abc123", "--skill", "lib",
                         "--remove-run-dir")
        assert code == 0 and out["status"] == "rolled-back" and out["run_dir_removed"] is True
        assert b"[MANUAL:notes]" in (s["package"] / "SKILL.md").read_bytes() and not s["run_dir"].exists()

    @pytest.mark.parametrize("owner", ["update-skill:other:abc123", "update-skill:lib", "create-skill:lib:abc123"],
                             ids=["another-skill", "no-run-id", "another-workflow"])
    def test_an_owner_that_names_no_update_run_changes_nothing(self, tmp_path: Path, owner: str) -> None:
        s = _skill(tmp_path)
        mod.begin_in_place(s["run_dir"], s["package"], s["forge"], None)
        _write(s["package"] / "SKILL.md", b"half written\n")
        code, out = _run("rollback", "--run-root", str(s["run_dir"].parent), "--owner", owner, "--skill", "lib",
                         "--remove-run-dir")
        assert code == 0 and out["status"] == "no-run-folder"
        assert s["run_dir"].exists() and (s["package"] / "SKILL.md").read_bytes() == b"half written\n"

    def test_a_traversing_run_id_in_an_owner_is_refused(self, tmp_path: Path) -> None:
        root = tmp_path / ".skf-run"
        root.mkdir()
        _write(tmp_path / "keep" / "keep.txt", b"keep\n")
        code, out = _run("rollback", "--run-root", str(root), "--owner", "update-skill:lib:../../keep",
                         "--remove-run-dir")
        assert code == 1 and (tmp_path / "keep" / "keep.txt").exists()

    @pytest.mark.parametrize("args", [["--owner", "update-skill:lib:x"], ["--run-root", "r"],
                                      ["--run-dir", "d", "--run-root", "r", "--owner", "update-skill:lib:x"]],
                             ids=["owner-without-root", "root-without-owner", "both-forms"])
    def test_the_two_forms_do_not_mix(self, args: list) -> None:
        code, out = _run("rollback", *args)
        assert code == 1 and out["status"] == "error"


RUN_LOCK = REPO_ROOT / "src" / "shared" / "scripts" / "skf-run-lock.py"
PAYLOAD = {"status": "halted-for-write-failure", "phase": "merge:new-version-folder", "path": "skills/lib/1.0.1",
           "reason": "stage: disk full", "skill_name": "lib", "version": "1.0.0", "previous_version": "1.0.0",
           "update_mode": "normal"}


def _halt(*args: str, payload: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "halt", *args],
                          input=json.dumps(payload) if payload is not None else None,
                          stdin=subprocess.DEVNULL if payload is None else None,
                          capture_output=True, encoding="utf-8")


def _lock(lock: Path, owner: str) -> None:
    proc = subprocess.run([sys.executable, str(RUN_LOCK), "acquire", "--lock", str(lock), "--owner", owner,
                           "--stale-after", "60"], capture_output=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr


class TestHalt:
    def _new_version(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        group = tmp_path / "skills" / "lib"
        version, forge = group / "1.0.1", tmp_path / "forge" / "lib" / "1.0.1"
        run_dir = tmp_path / "_bmad-output" / ".skf-run" / "skf-update-skill-abc123"
        run_dir.mkdir(parents=True)
        mod.begin_new_version(run_dir, [version, forge], group / "1.0.1.skf-tmp", group)
        _write(version / "lib" / "SKILL.md", b"new\n")
        _write(forge / "provenance-map.json", b"{}\n")
        return run_dir, version, forge

    def test_one_call_undoes_releases_and_prints_the_line(self, tmp_path: Path) -> None:
        run_dir, version, forge = self._new_version(tmp_path)
        lock = tmp_path / "forge" / "lib" / ".skf-update.lock"
        _lock(lock, "update-skill:lib:abc123")
        proc = _halt("--run-dir", str(run_dir), "--tree", str(tmp_path / "not-a-tree"), "--lock", str(lock),
                     "--owner", "update-skill:lib:abc123", "--emit", payload=PAYLOAD)
        assert proc.returncode == 0, proc.stderr
        summary, line = proc.stdout.splitlines()
        out = json.loads(summary)
        assert out["rollback"] == "rolled-back" and not version.exists() and not forge.exists()
        assert (out["lock"], out["tree"], out["emitted"]) == ("released", "refused", True) and not lock.exists()
        envelope = json.loads(line.split("SKF_UPDATE_RESULT_JSON: ", 1)[1])["skf_update"]
        assert envelope["status"] == "halted-for-write-failure" and envelope["files_written"] == []
        assert envelope["error"] == {"phase": "merge:new-version-folder", "path": "skills/lib/1.0.1",
                                     "reason": "stage: disk full"}
        # the tree it could not remove is named; the run folder stays for the person to read
        assert envelope["warnings"] == [f"source-tree-not-removed: {tmp_path / 'not-a-tree'} (refused)"]
        assert run_dir.is_dir()

    def test_a_lock_another_run_took_stays(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        lock = tmp_path / ".skf-update.lock"
        _lock(lock, "update-skill:lib:other99")
        proc = _halt("--run-dir", str(run_dir), "--lock", str(lock), "--owner", "update-skill:lib:abc123")
        out = json.loads(proc.stdout)
        assert proc.returncode == 0 and out["lock"] == "not-owner" and out["warnings"] == [] and lock.exists()
        assert out["rollback"] == "nothing-to-roll-back" and out["emitted"] is False

    def test_a_refused_payload_is_fixed_and_run_again(self, tmp_path: Path) -> None:
        run_dir, version, _ = self._new_version(tmp_path)
        proc = _halt("--run-dir", str(run_dir), "--emit", payload={**PAYLOAD, "status": "halted"})
        assert proc.returncode == 1 and "skf-update-result-envelope" in proc.stderr
        assert json.loads(proc.stdout.splitlines()[0])["emitted"] is False and not version.exists()
        # the second run redoes nothing already done and prints the line
        proc = _halt("--run-dir", str(run_dir), "--emit", payload=PAYLOAD)
        assert proc.returncode == 0
        assert json.loads(proc.stdout.splitlines()[0])["rollback"] == "already-rolled-back"
        assert proc.stdout.splitlines()[1].startswith("SKF_UPDATE_RESULT_JSON: ")

    def test_a_run_folder_that_is_gone_still_gets_its_line(self, tmp_path: Path) -> None:
        proc = _halt("--run-dir", str(tmp_path / "gone"), "--emit", payload=PAYLOAD)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout.splitlines()[0])["rollback"] == "nothing-to-roll-back"

    def test_a_rollback_that_fails_is_a_warning_on_the_line(self, tmp_path: Path, monkeypatch) -> None:
        run_dir, version, _ = self._new_version(tmp_path)

        def refuse(path: Path) -> None:
            raise OSError("busy")

        monkeypatch.setattr(mod, "_remove", refuse)
        out = mod.halt(run_dir, None, None, None)
        assert out["rollback"] == "rolled-back" and version.exists()
        assert f"rollback-incomplete: {version.as_posix()}: busy" in out["warnings"]

    @pytest.mark.parametrize(("args", "payload"), [(["--lock", "l"], None), (["--emit"], "not json"),
                                                   (["--emit"], ["a list"])],
                             ids=["lock-without-owner", "payload-not-json", "payload-not-an-object"])
    def test_bad_calls_exit_1(self, tmp_path: Path, args: list, payload) -> None:
        proc = subprocess.run([sys.executable, str(SCRIPT), "halt", "--run-dir", str(tmp_path), *args],
                              input=payload if isinstance(payload, str) else json.dumps(payload),
                              capture_output=True, encoding="utf-8")
        assert proc.returncode == 1 and json.loads(proc.stderr)["status"] == "error"
