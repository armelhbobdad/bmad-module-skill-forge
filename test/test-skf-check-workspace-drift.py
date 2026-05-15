#!/usr/bin/env python3
"""Tests for skf-check-workspace-drift.py.

Covers the four-state guard from re-extract.md §0.a:
  - skipped (no pinned commit): pinned is "", "local", or whitespace-only
  - skipped (not a git working tree): source_root is not a git repo
  - ok: HEAD matches pinned (full SHA or short-SHA prefix)
  - mismatch: HEAD differs from pinned (with and without --allow-drift)

Uses real `git init` in tmp_path so we exercise the actual git invocation
the script uses.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-check-workspace-drift.py"

spec = importlib.util.spec_from_file_location("skf_check_workspace_drift", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Test fixture: real git repo in tmp_path
# --------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    """Run a git command in cwd, return stdout. Fails the test on non-zero."""
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _init_repo(path: Path, *, initial_content: str = "first\n") -> str:
    """Create a git repo with one commit. Returns the commit SHA."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "file.txt").write_text(initial_content, encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "first")
    return _git(path, "rev-parse", "HEAD")


def _add_commit(path: Path, content: str = "second\n") -> str:
    (path / "file.txt").write_text(content, encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "second")
    return _git(path, "rev-parse", "HEAD")


# --------------------------------------------------------------------------
# is_skippable_pinned + classify_match unit tests
# --------------------------------------------------------------------------


class TestIsSkippablePinned:
    @pytest.mark.parametrize("value", [None, "", "   ", "local", "LOCAL", "  local  "])
    def test_skippable(self, value) -> None:
        assert mod.is_skippable_pinned(value) is True

    @pytest.mark.parametrize("value", ["abc1234", "abc1234deadbeef", "main"])
    def test_not_skippable(self, value) -> None:
        assert mod.is_skippable_pinned(value) is False


class TestClassifyMatch:
    def test_full_match(self) -> None:
        sha = "abc1234deadbeef0123456789abcdef0123456789"
        assert mod.classify_match(sha, sha) == "full"

    def test_short_prefix_match(self) -> None:
        full = "abc1234deadbeef0123456789abcdef0123456789"
        assert mod.classify_match(full[:8], full) == "short-prefix"
        assert mod.classify_match(full[:12], full) == "short-prefix"

    def test_too_short_no_match(self) -> None:
        # < 7 chars — refuses to match to avoid coincidental collisions
        assert mod.classify_match("abc", "abc1234deadbeef") is None

    def test_no_overlap(self) -> None:
        assert (
            mod.classify_match(
                "abc1234", "def5678deadbeef0123456789abcdef0123456789"
            )
            is None
        )


# --------------------------------------------------------------------------
# check() — skipped paths
# --------------------------------------------------------------------------


class TestSkipped:
    def test_empty_pinned_skips(self, tmp_path: Path) -> None:
        result = mod.check(tmp_path, pinned_commit="", source_ref=None, allow_drift=False)
        assert result["status"] == "skipped"
        assert result["skip_reason"] == "no-pinned-commit"
        assert result["log_message"] == "workspace_drift_check: skipped (no pinned commit)"
        assert result["halt_message"] is None

    def test_local_pinned_skips(self, tmp_path: Path) -> None:
        result = mod.check(tmp_path, pinned_commit="local", source_ref=None, allow_drift=False)
        assert result["status"] == "skipped"
        assert result["skip_reason"] == "no-pinned-commit"

    def test_not_a_git_tree_skips(self, tmp_path: Path) -> None:
        # tmp_path has no .git/ — rev-parse --is-inside-work-tree returns non-zero
        result = mod.check(
            tmp_path, pinned_commit="abc1234567", source_ref=None, allow_drift=False
        )
        assert result["status"] == "skipped"
        assert result["skip_reason"] == "not-a-git-tree"
        assert result["log_message"] == (
            "workspace_drift_check: skipped (not a git working tree)"
        )


# --------------------------------------------------------------------------
# check() — ok paths
# --------------------------------------------------------------------------


class TestOk:
    def test_full_sha_match(self, tmp_path: Path) -> None:
        sha = _init_repo(tmp_path / "repo")
        result = mod.check(
            tmp_path / "repo", pinned_commit=sha, source_ref=None, allow_drift=False
        )
        assert result["status"] == "ok"
        assert result["match_kind"] == "full"
        assert result["head_sha"] == sha
        assert result["head_short_sha"] == sha[:7]
        assert result["log_message"] == f"workspace_drift_check: ok ({sha[:7]})"

    def test_short_sha_match(self, tmp_path: Path) -> None:
        sha = _init_repo(tmp_path / "repo")
        result = mod.check(
            tmp_path / "repo", pinned_commit=sha[:8], source_ref=None, allow_drift=False
        )
        assert result["status"] == "ok"
        assert result["match_kind"] == "short-prefix"

    def test_ok_with_source_ref(self, tmp_path: Path) -> None:
        # source_ref doesn't affect ok branch — included only in halt_message
        sha = _init_repo(tmp_path / "repo")
        result = mod.check(
            tmp_path / "repo",
            pinned_commit=sha,
            source_ref="v1.0.0",
            allow_drift=False,
        )
        assert result["status"] == "ok"
        assert result["halt_message"] is None


# --------------------------------------------------------------------------
# check() — mismatch paths
# --------------------------------------------------------------------------


class TestMismatch:
    def test_mismatch_no_allow_drift(self, tmp_path: Path) -> None:
        sha1 = _init_repo(tmp_path / "repo")
        sha2 = _add_commit(tmp_path / "repo")
        # pinned at sha1, HEAD is sha2
        result = mod.check(
            tmp_path / "repo",
            pinned_commit=sha1,
            source_ref=None,
            allow_drift=False,
        )
        assert result["status"] == "mismatch"
        assert result["head_sha"] == sha2
        assert result["halt_message"] is not None
        assert sha1 in result["halt_message"]
        assert sha2 in result["halt_message"]
        # halt-message has fallback "unset" when source_ref is None
        assert "unset" in result["halt_message"]

    def test_mismatch_with_allow_drift(self, tmp_path: Path) -> None:
        sha1 = _init_repo(tmp_path / "repo")
        sha2 = _add_commit(tmp_path / "repo")
        result = mod.check(
            tmp_path / "repo",
            pinned_commit=sha1,
            source_ref=None,
            allow_drift=True,
        )
        assert result["status"] == "overridden"
        assert result["log_message"].startswith("workspace_drift_check: overridden")
        # halt_message is populated so caller can surface as warning
        assert result["halt_message"] is not None

    def test_mismatch_halt_includes_source_ref(self, tmp_path: Path) -> None:
        sha1 = _init_repo(tmp_path / "repo")
        _add_commit(tmp_path / "repo")
        result = mod.check(
            tmp_path / "repo",
            pinned_commit=sha1,
            source_ref="v2.1.0",
            allow_drift=False,
        )
        assert "v2.1.0" in result["halt_message"]
        # the suggested checkout target is the ref, not the SHA
        assert "git -C" in result["halt_message"]
        assert "checkout v2.1.0" in result["halt_message"]


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
    def test_ok_exits_0(self, tmp_path: Path) -> None:
        sha = _init_repo(tmp_path / "repo")
        result = _run_cli(
            str(tmp_path / "repo"), "--pinned-commit", sha
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "ok"

    def test_skipped_no_pinned_exits_0(self, tmp_path: Path) -> None:
        result = _run_cli(str(tmp_path), "--pinned-commit", "")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "skipped"
        assert payload["skip_reason"] == "no-pinned-commit"

    def test_skipped_not_git_exits_0(self, tmp_path: Path) -> None:
        result = _run_cli(str(tmp_path), "--pinned-commit", "abc1234567")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["skip_reason"] == "not-a-git-tree"

    def test_mismatch_no_drift_exits_2(self, tmp_path: Path) -> None:
        sha1 = _init_repo(tmp_path / "repo")
        _add_commit(tmp_path / "repo")
        result = _run_cli(
            str(tmp_path / "repo"), "--pinned-commit", sha1
        )
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["status"] == "mismatch"

    def test_mismatch_with_drift_exits_0(self, tmp_path: Path) -> None:
        sha1 = _init_repo(tmp_path / "repo")
        _add_commit(tmp_path / "repo")
        result = _run_cli(
            str(tmp_path / "repo"),
            "--pinned-commit", sha1,
            "--allow-drift",
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "overridden"

    def test_missing_source_root_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli(
            str(tmp_path / "missing"), "--pinned-commit", "abc1234567"
        )
        assert result.returncode == 1
        assert "not a directory" in result.stderr

    def test_missing_pinned_commit_arg_exits_2(self, tmp_path: Path) -> None:
        # argparse required-arg missing
        result = _run_cli(str(tmp_path))
        assert result.returncode == 2  # argparse convention
        assert "pinned-commit" in result.stderr
