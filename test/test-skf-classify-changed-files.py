#!/usr/bin/env python3
"""Tests for skf-classify-changed-files.py: update-skill's Category A.

Covers:
  - diff mode: git's changed-file rows sort tracked files into modified and
    deleted, and untracked in-scope files with a row into added
  - the brief's scope globs: `**` across folders, an exclude that overrides
    an include, the tracked-extension fallback of an empty include
  - what is never added: file_entries paths, --exclude paths, vendored
    folders; promoted scope-expansion globs, changed or not
  - the same-content move check, through a real git repository
  - tree-without-diff and local modes, with the provenance map's time
  - the CLI: statuses, `null` values, exit codes
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-classify-changed-files.py"

spec = importlib.util.spec_from_file_location("skf_classify_changed_files", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

GIT_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
)
BASELINE = datetime(2026, 1, 1, tzinfo=timezone.utc)
BEFORE = BASELINE - timedelta(days=1)
AFTER = BASELINE + timedelta(days=1)
FAKE_BASE = "b" * 40
FAKE_TARGET = "c" * 40


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------


def _write(root: Path, rel: str, content: str = "x = 1\n") -> Path:
    # binary write so Windows CRLF translation doesn't perturb the contents
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


def _touch(path: Path, when: datetime) -> None:
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def _provenance(entries=(), file_entries=(), **top) -> dict:
    return {
        "provenance_version": "2.0",
        "source_commit": "abc123",
        "generated_at": "2026-01-01T00:00:00Z",
        "entries": [{"export_name": "e", "source_file": p} for p in entries],
        "file_entries": [{"file_type": "doc", "source_file": p} for p in file_entries],
        **top,
    }


def _brief(include=("src/**",), exclude=(), amendments=()) -> dict:
    return {"scope": {"include": list(include), "exclude": list(exclude), "amendments": list(amendments)}}


def _changed(*rows: tuple[str, str], base: str = FAKE_BASE, target: str = FAKE_TARGET) -> dict:
    return {"base": base, "target": target, "files": [{"status": s, "path": p} for s, p in rows]}


def _diff(root: Path, provenance: dict, brief: dict, *rows: tuple[str, str], **kwargs) -> dict:
    return mod.classify(root, provenance, brief, diff_status="ok", changed=_changed(*rows), **kwargs)


def _a(result: dict) -> dict:
    return result["category_a"]


def _git(cwd: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}
    proc = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
         "-C", str(cwd), *args],
        capture_output=True, encoding="utf-8", errors="replace", env=env, stdin=subprocess.DEVNULL,
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


# --------------------------------------------------------------------------
# diff mode
# --------------------------------------------------------------------------


class TestDiffMode:
    def test_rows_sort_the_tracked_files(self, tmp_path: Path) -> None:
        for rel in ("src/a.py", "src/c.py", "src/d.py"):
            _write(tmp_path, rel)
        prov = _provenance(entries=["src/a.py", "src/b.py", "src/c.py", "src/d.py"])
        r = _diff(tmp_path, prov, _brief(), ("M", "src/a.py"), ("D", "src/b.py"), ("A", "src/d.py"))
        assert r["mode"] == "diff"
        assert _a(r) == {"modified": ["src/a.py", "src/d.py"], "added": [], "deleted": ["src/b.py"]}
        assert r["summary"] == {"tracked": 4, "modified": 2, "added": 0, "deleted": 1, "moved": 0, "unchanged": 1}

    def test_a_tracked_file_the_source_lacks_is_deleted(self, tmp_path: Path) -> None:
        r = _diff(tmp_path, _provenance(entries=["src/gone.py"]), _brief())
        assert _a(r)["deleted"] == ["src/gone.py"]

    def test_untracked_files_with_a_row_in_scope_are_added(self, tmp_path: Path) -> None:
        for rel in ("src/new.py", "src/pkg/__init__.py", "docs/guide.py"):
            _write(tmp_path, rel)
        r = _diff(tmp_path, _provenance(), _brief(include=["src/**/*.py"]),
                  ("A", "src/new.py"), ("M", "src/pkg/__init__.py"), ("A", "docs/guide.py"))
        assert _a(r)["added"] == ["src/new.py", "src/pkg/__init__.py"]

    def test_an_untracked_file_without_a_row_is_not_added(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/old.py")
        assert _a(_diff(tmp_path, _provenance(), _brief()))["added"] == []

    @pytest.mark.parametrize("include,path,added", [
        ("src/**/*.py", "src/a.py", True),
        ("src/**/*.py", "src/x/y/z.py", True),
        ("**/*.py", "a.py", True),
        ("src/*.py", "src/x/a.py", False),
        ("src/**", "srcs/a.py", False),
    ], ids=["zero-folders", "many-folders", "root-file", "star-stays-in-folder", "no-prefix-match"])
    def test_double_star_spans_folders(self, tmp_path: Path, include: str, path: str, added: bool) -> None:
        _write(tmp_path, path)
        r = _diff(tmp_path, _provenance(), _brief(include=[include]), ("A", path))
        assert (_a(r)["added"] == [path]) is added

    def test_an_exclude_overrides_an_include(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/m.py")
        _write(tmp_path, "src/deep/tests/t.py")
        r = _diff(tmp_path, _provenance(), _brief(include=["src/**"], exclude=["**/tests/**"]),
                  ("A", "src/m.py"), ("A", "src/deep/tests/t.py"))
        assert _a(r)["added"] == ["src/m.py"]

    def test_an_empty_include_falls_back_to_the_tracked_extensions(self, tmp_path: Path) -> None:
        for rel in ("src/a.py", "src/b.py", "README.md", "src/c.ts", "tests/t.py"):
            _write(tmp_path, rel)
        r = _diff(tmp_path, _provenance(entries=["src/a.py"]), _brief(include=[], exclude=["tests/**"]),
                  ("A", "src/b.py"), ("A", "README.md"), ("A", "src/c.ts"), ("A", "tests/t.py"))
        assert _a(r)["added"] == ["src/b.py"]

    def test_file_entries_paths_are_never_added(self, tmp_path: Path) -> None:
        _write(tmp_path, "scripts/run.sh")
        r = _diff(tmp_path, _provenance(file_entries=["scripts/run.sh"]), _brief(include=["**"]),
                  ("M", "scripts/run.sh"))
        assert _a(r) == {"modified": [], "added": [], "deleted": []}

    def test_an_excluded_path_is_in_no_list(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/llms.txt")
        _write(tmp_path, "src/a.py")
        r = _diff(tmp_path, _provenance(entries=["src/a.py"]), _brief(include=["**"]),
                  ("A", "src/llms.txt"), ("M", "src/a.py"), excludes=["src/llms.txt", "./src/a.py"])
        assert _a(r) == {"modified": [], "added": [], "deleted": []}
        assert r["summary"]["tracked"] == 0

    def test_vendored_folders_are_never_added(self, tmp_path: Path) -> None:
        for rel in ("node_modules/x/i.py", "dist/y.py", "src/build/z.py"):
            _write(tmp_path, rel)
        r = _diff(tmp_path, _provenance(), _brief(include=["**"]),
                  ("A", "node_modules/x/i.py"), ("A", "dist/y.py"), ("A", "src/build/z.py"))
        assert _a(r)["added"] == []

    def test_a_tracked_file_in_a_vendored_folder_is_still_tracked(self, tmp_path: Path) -> None:
        _write(tmp_path, "build/gen.py")
        r = _diff(tmp_path, _provenance(entries=["build/gen.py"]), _brief(include=["**"]), ("M", "build/gen.py"))
        assert _a(r)["modified"] == ["build/gen.py"]


class TestPromotedGlobs:
    PROMOTED = {"action": "promoted", "category": "scope-expansion", "path": "packages/new/**"}

    def _tree(self, tmp_path: Path) -> None:
        _write(tmp_path, "packages/new/a.py")
        _write(tmp_path, "packages/new/sub/b.py")
        _write(tmp_path, "packages/new/fixtures/f.py")

    def test_a_promoted_glob_adds_its_files_changed_or_not(self, tmp_path: Path) -> None:
        self._tree(tmp_path)
        brief = _brief(include=["src/**", "packages/new/**"], exclude=["**/fixtures/**"],
                       amendments=[self.PROMOTED])
        r = _diff(tmp_path, _provenance(), brief)
        assert _a(r)["added"] == ["packages/new/a.py", "packages/new/sub/b.py"]

    def test_once_a_file_it_matches_is_tracked_only_changed_files_are_added(self, tmp_path: Path) -> None:
        self._tree(tmp_path)
        brief = _brief(include=["packages/new/**"], amendments=[self.PROMOTED])
        r = _diff(tmp_path, _provenance(entries=["packages/new/a.py"]), brief)
        assert _a(r)["added"] == []

    def test_the_latest_amendment_decides(self, tmp_path: Path) -> None:
        self._tree(tmp_path)
        skipped = {**self.PROMOTED, "action": "skipped"}
        brief = _brief(include=["packages/new/**"], amendments=[self.PROMOTED, skipped])
        assert _a(_diff(tmp_path, _provenance(), brief))["added"] == []

    def test_only_scope_expansion_promotions_count(self, tmp_path: Path) -> None:
        self._tree(tmp_path)
        doc_promotion = {"action": "promoted", "path": "packages/new/**"}
        brief = _brief(include=["packages/new/**"], amendments=[doc_promotion])
        assert _a(_diff(tmp_path, _provenance(), brief))["added"] == []

    def test_promoted_globs_are_reported_by_the_helper(self) -> None:
        brief = _brief(amendments=[self.PROMOTED, {**self.PROMOTED, "path": "./lib/**"}])
        assert mod.promoted_globs(brief, {"lib/a.py"}) == ["packages/new/**"]


# --------------------------------------------------------------------------
# Same-content moves (diff mode, a real repository)
# --------------------------------------------------------------------------


class TestSameContentMoves:
    def _repo(self, tmp_path: Path) -> tuple[Path, str]:
        repo = tmp_path / "tree"
        _write(repo, "src/a.py", "def a():\n    return 1\n")
        _write(repo, "src/b.py", "def b():\n    return 2\n")
        _git(repo, "init", "-q")
        return repo, _commit(repo, "base")

    def test_a_file_with_the_same_contents_at_a_new_path_is_moved(self, tmp_path: Path) -> None:
        repo, base = self._repo(tmp_path)
        (repo / "src" / "a.py").unlink()
        (repo / "src" / "sub").mkdir()
        (repo / "src" / "b.py").rename(repo / "src" / "sub" / "b.py")
        _write(repo, "src/c.py", "def c():\n    return 3\n")
        target = _commit(repo, "target")
        changed = _changed(("D", "src/a.py"), ("D", "src/b.py"), ("A", "src/c.py"), ("A", "src/sub/b.py"),
                           base=base, target=target)
        r = mod.classify(repo, _provenance(entries=["src/a.py", "src/b.py"]), _brief(),
                         diff_status="ok", changed=changed)
        assert r["moved_files"] == [{"old_path": "src/b.py", "new_path": "src/sub/b.py"}]
        assert _a(r) == {"modified": [], "added": ["src/c.py"], "deleted": ["src/a.py"]}
        assert r["summary"]["moved"] == 1 and r["summary"]["unchanged"] == 0
        assert r["warnings"] == []

    def test_contents_two_deleted_files_share_are_not_paired(self, tmp_path: Path) -> None:
        repo = tmp_path / "tree"
        _write(repo, "src/a.py", "same = 1\n")
        _write(repo, "src/b.py", "same = 1\n")
        _git(repo, "init", "-q")
        base = _commit(repo, "base")
        (repo / "src" / "a.py").unlink()
        (repo / "src" / "b.py").unlink()
        _write(repo, "src/c.py", "same = 1\n")
        target = _commit(repo, "target")
        changed = _changed(("D", "src/a.py"), ("D", "src/b.py"), ("A", "src/c.py"), base=base, target=target)
        r = mod.classify(repo, _provenance(entries=["src/a.py", "src/b.py"]), _brief(),
                         diff_status="ok", changed=changed)
        assert r["moved_files"] == []
        assert _a(r)["deleted"] == ["src/a.py", "src/b.py"] and _a(r)["added"] == ["src/c.py"]

    def test_without_commits_the_check_is_skipped_with_a_warning(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/new.py")
        changed = _changed(("D", "src/old.py"), ("A", "src/new.py"), base="", target="")
        r = mod.classify(tmp_path, _provenance(entries=["src/old.py"]), _brief(), diff_status="ok", changed=changed)
        assert r["moved_files"] == []
        assert r["warnings"] == ["moved-check-skipped: the changed-files list names no base or target commit"]

    def test_a_git_failure_is_a_warning(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/new.py")
        r = _diff(tmp_path, _provenance(entries=["src/old.py"]), _brief(), ("D", "src/old.py"), ("A", "src/new.py"))
        assert r["moved_files"] == []
        assert _a(r)["deleted"] == ["src/old.py"] and _a(r)["added"] == ["src/new.py"]
        (warning,) = r["warnings"]
        assert warning.startswith("moved-check-skipped: ")

    def test_no_git_call_without_both_a_deleted_and_an_added_file(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/new.py")
        r = _diff(tmp_path, _provenance(), _brief(), ("A", "src/new.py"))
        assert r["warnings"] == []


# --------------------------------------------------------------------------
# tree-without-diff and local modes
# --------------------------------------------------------------------------


class TestTreeWithoutDiff:
    def test_every_tracked_file_is_rechecked(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/a.py")
        _write(tmp_path, "src/untracked.py")
        _write(tmp_path, "notes.txt")
        r = mod.classify(tmp_path, _provenance(entries=["src/a.py", "src/b.py"]), _brief(),
                         tree_status="ready", diff_status="unavailable")
        assert r["mode"] == "tree-without-diff"
        assert _a(r) == {"modified": ["src/a.py"], "added": ["src/untracked.py"], "deleted": ["src/b.py"]}
        assert r["warnings"] == [
            "file-diff-unavailable: abc123 could not be read, so every tracked file was re-checked"]


class TestLocalMode:
    def _source(self, tmp_path: Path) -> Path:
        root = tmp_path / "source"
        _touch(_write(root, "src/old.py"), BEFORE)
        _touch(_write(root, "src/edited.py"), AFTER)
        _touch(_write(root, "src/fresh.py"), AFTER)
        _touch(_write(root, "src/stale.py"), BEFORE)
        return root

    def test_modification_times_decide(self, tmp_path: Path) -> None:
        root = self._source(tmp_path)
        prov = _provenance(entries=["src/old.py", "src/edited.py", "src/gone.py"])
        r = mod.classify(root, prov, _brief())
        assert r["mode"] == "local"
        assert _a(r) == {"modified": ["src/edited.py"], "added": ["src/fresh.py"], "deleted": ["src/gone.py"]}
        assert (r["baseline_time"], r["baseline_source"]) == ("2026-01-01T00:00:00Z", "generated_at")
        assert r["summary"]["unchanged"] == 1

    def test_an_update_that_read_the_source_moves_the_baseline(self, tmp_path: Path) -> None:
        root = self._source(tmp_path)
        prov = _provenance(entries=["src/edited.py"], update_type="incremental", last_update="2026-03-01")
        r = mod.classify(root, prov, _brief())
        assert _a(r)["modified"] == [] and _a(r)["added"] == []
        # The date's earliest instant: 2026-03-01 starts at UTC+14 first.
        assert (r["baseline_time"], r["baseline_source"]) == ("2026-02-28T10:00:00Z", "last_update")

    def test_a_file_edited_before_the_update_dates_utc_midnight_is_modified(self, tmp_path: Path) -> None:
        # An update east of UTC can run, and a file be edited after it, while
        # UTC still reads the day before the date the update wrote.
        root = tmp_path / "source"
        late = datetime(2026, 9, 29, 23, 30, tzinfo=timezone.utc)
        _touch(_write(root, "src/edited.py"), late)
        _touch(_write(root, "src/fresh.py"), late)
        _touch(_write(root, "src/old.py"), datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc))
        prov = _provenance(entries=["src/edited.py", "src/old.py"], generated_at="2026-09-01T10:00:00Z",
                           update_type="incremental", last_update="2026-09-30")
        r = mod.classify(root, prov, _brief())
        assert _a(r) == {"modified": ["src/edited.py"], "added": ["src/fresh.py"], "deleted": []}
        assert (r["baseline_time"], r["baseline_source"]) == ("2026-09-29T10:00:00Z", "last_update")

    def test_a_gap_driven_update_does_not_move_the_baseline(self, tmp_path: Path) -> None:
        root = self._source(tmp_path)
        prov = _provenance(entries=["src/edited.py"], update_type="gap-driven", last_update="2026-03-01")
        r = mod.classify(root, prov, _brief())
        assert _a(r)["modified"] == ["src/edited.py"]
        assert r["baseline_source"] == "generated_at"

    def test_no_usable_time_rechecks_everything(self, tmp_path: Path) -> None:
        root = self._source(tmp_path)
        prov = _provenance(entries=["src/old.py"], generated_at="not a date")
        r = mod.classify(root, prov, _brief())
        assert _a(r)["modified"] == ["src/old.py"]
        assert _a(r)["added"] == ["src/edited.py", "src/fresh.py", "src/stale.py"]
        assert r["baseline_time"] is None
        (warning,) = r["warnings"]
        assert warning.startswith("no-baseline-time: ")

    def test_a_promoted_glob_adds_files_older_than_the_baseline(self, tmp_path: Path) -> None:
        root = self._source(tmp_path)
        _touch(_write(root, "lib/extra.py"), BEFORE)
        promoted = {"action": "promoted", "category": "scope-expansion", "path": "lib/**"}
        r = mod.classify(root, _provenance(), _brief(include=["src/**", "lib/**"], amendments=[promoted]))
        assert "lib/extra.py" in _a(r)["added"] and "src/stale.py" not in _a(r)["added"]

    @pytest.mark.parametrize("value,expected", [
        ("2026-01-01T00:00:00Z", BASELINE),
        ("2026-01-01T02:00:00+02:00", BASELINE),
        ("2026-01-01T00:00:00", BASELINE - timedelta(hours=14)),
        ("2026-01-01", BASELINE - timedelta(hours=14)),
        ("yesterday", None),
        (None, None),
        ("0001-01-01", None),
    ], ids=["zulu", "offset", "no-zone", "date-only", "not-a-date", "missing", "out-of-range"])
    def test_times_are_read_as_the_earliest_instant_they_name(self, value, expected) -> None:
        assert mod._parse_time(value) == expected


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


def _inputs(tmp_path: Path, *, changed: dict | None = None) -> dict[str, Path]:
    root = tmp_path / "source"
    _write(root, "src/a.py")
    _write(root, "src/new.py")
    prov = tmp_path / "provenance-map.json"
    prov.write_bytes(json.dumps(_provenance(entries=["src/a.py"])).encode("utf-8"))
    brief = tmp_path / "skill-brief.yaml"
    brief.write_bytes(yaml.safe_dump(_brief()).encode("utf-8"))
    paths = {"root": root, "prov": prov, "brief": brief}
    if changed is not None:
        paths["changed"] = tmp_path / "changed-files.json"
        paths["changed"].write_bytes(json.dumps(changed).encode("utf-8"))
    return paths


def _base_args(paths: dict[str, Path]) -> list[str]:
    return ["classify", "--source-root", str(paths["root"]), "--provenance-map", str(paths["prov"]),
            "--brief", str(paths["brief"])]


class TestCli:
    def test_diff_mode(self, tmp_path: Path) -> None:
        paths = _inputs(tmp_path, changed=_changed(("M", "src/a.py"), ("A", "src/new.py")))
        res = _run_cli(*_base_args(paths), "--tree-status", "ready", "--diff-status", "ok",
                       "--changed-files", str(paths["changed"]))
        assert res.returncode == 0, res.stderr
        out = json.loads(res.stdout)
        assert out["mode"] == "diff"
        assert out["category_a"] == {"modified": ["src/a.py"], "added": ["src/new.py"], "deleted": []}

    def test_changed_files_alone_means_diff_mode(self, tmp_path: Path) -> None:
        paths = _inputs(tmp_path, changed=_changed(("M", "src/a.py")))
        res = _run_cli(*_base_args(paths), "--changed-files", str(paths["changed"]))
        assert json.loads(res.stdout)["mode"] == "diff"

    def test_null_values_count_as_not_given(self, tmp_path: Path) -> None:
        paths = _inputs(tmp_path)
        res = _run_cli(*_base_args(paths), "--tree-status", "null", "--diff-status", "None",
                       "--changed-files", "null")
        assert res.returncode == 0, res.stderr
        assert json.loads(res.stdout)["mode"] == "local"

    def test_an_exclude_on_the_cli(self, tmp_path: Path) -> None:
        paths = _inputs(tmp_path, changed=_changed(("A", "src/new.py")))
        res = _run_cli(*_base_args(paths), "--diff-status", "ok", "--changed-files", str(paths["changed"]),
                       "--exclude", "src/new.py")
        assert json.loads(res.stdout)["category_a"]["added"] == []

    @pytest.mark.parametrize("args", [("--help",), ("classify", "--help")], ids=["top", "classify"])
    def test_help_prints_the_modes_and_output(self, args: tuple[str, ...]) -> None:
        res = _run_cli(*args)
        assert res.returncode == 0, res.stderr
        for section in ("Modes, from the statuses:", "MODIFIED  a tracked file", "Output JSON (stdout):",
                        "Exit codes:"):
            assert section in res.stdout, section

    def test_diff_status_ok_needs_the_changed_files(self, tmp_path: Path) -> None:
        paths = _inputs(tmp_path)
        res = _run_cli(*_base_args(paths), "--diff-status", "ok")
        assert res.returncode == 1
        assert "--changed-files" in res.stderr

    @pytest.mark.parametrize("missing", ["root", "prov", "brief"])
    def test_a_missing_input_exits_1(self, tmp_path: Path, missing: str) -> None:
        paths = _inputs(tmp_path)
        paths[missing] = tmp_path / "absent"
        res = _run_cli(*_base_args(paths))
        assert res.returncode == 1
        assert res.stderr.startswith("error: ")

    @pytest.mark.parametrize("content", [b"{not json", b'{"files": "none"}'], ids=["invalid-json", "no-files-list"])
    def test_an_unreadable_changed_files_exits_1(self, tmp_path: Path, content: bytes) -> None:
        paths = _inputs(tmp_path)
        bad = tmp_path / "changed-files.json"
        bad.write_bytes(content)
        res = _run_cli(*_base_args(paths), "--diff-status", "ok", "--changed-files", str(bad))
        assert res.returncode == 1
        assert res.stderr.startswith("error: ")

    def test_no_subcommand_exits_2(self) -> None:
        assert _run_cli().returncode == 2
