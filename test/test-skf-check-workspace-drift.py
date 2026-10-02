#!/usr/bin/env python3
"""Tests for skf-check-workspace-drift.py.

Covers the four-state guard from update-skill's gap-driven.md §3:
  - skipped (no pinned commit): pinned is "", "local", or whitespace-only
  - skipped (not a git working tree): source_root is not a git repo
  - ok: HEAD matches pinned (full SHA or short-SHA prefix)
  - mismatch: HEAD differs from pinned (with and without --allow-drift)

Also covers an inherited git environment: GIT_DIR / GIT_INDEX_FILE exported
by a git hook must not redirect the check (in-process or through the CLI)
or let a fixture write into another repository's index.

Uses real `git init` in tmp_path so we exercise the actual git invocation
the script uses.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
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
    """Run a git command in cwd, return stdout. Fails the test on non-zero.

    Drops the git location variables, as the helper does, so a fixture never
    reads or writes the index or repository a git hook exported, including
    in the tests that set them on purpose.
    """
    env = {k: v for k, v in os.environ.items() if k not in mod.GIT_LOCATION_VARS}
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
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


class TestWorkflowMessage:
    """test-skill runs the same guard, once per repository of a stack skill."""

    def test_default_speaks_for_update_skill(self, tmp_path: Path) -> None:
        sha1 = _init_repo(tmp_path / "repo")
        _add_commit(tmp_path / "repo")
        result = mod.check(
            tmp_path / "repo", pinned_commit=sha1, source_ref="v1", allow_drift=False
        )
        assert (
            "re-run update-skill with `--allow-workspace-drift`"
            in result["halt_message"]
        )

    def test_test_skill_message(self, tmp_path: Path) -> None:
        sha1 = _init_repo(tmp_path / "repo")
        sha2 = _add_commit(tmp_path / "repo")
        result = mod.check(
            tmp_path / "repo",
            pinned_commit=sha1,
            source_ref=None,
            allow_drift=True,
            workflow="test-skill",
        )
        message = result["halt_message"]
        assert result["status"] == "overridden"
        assert (
            "Test-skill verifies against the source the skill was extracted from."
            in message
        )
        assert "re-run test-skill with `--allow-workspace-drift`" in message
        assert "update-skill" not in message
        assert sha1 in message and sha2 in message and f"checkout {sha1}" in message
        assert "\u2014" not in message

    def test_every_stack_repository_is_its_own_call(self, tmp_path: Path) -> None:
        pins = {}
        for name in ("a", "b"):
            pins[tmp_path / name] = _init_repo(tmp_path / name)
        _add_commit(tmp_path / "b")
        codes = {}
        for repo, pin in pins.items():
            result = _run_cli(
                str(repo), "--pinned-commit", pin, "--workflow", "test-skill"
            )
            codes[repo.name] = (result.returncode, json.loads(result.stdout)["status"])
        assert codes == {"a": (0, "ok"), "b": (2, "mismatch")}

    def test_unknown_workflow_is_a_usage_error(self, tmp_path: Path) -> None:
        result = _run_cli(
            str(tmp_path), "--pinned-commit", "", "--workflow", "audit-skill"
        )
        assert result.returncode == 2
        assert "--workflow" in result.stderr


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the CLI with the environment inherited unchanged, so a test that
    exports git variables proves the script removes them itself."""
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


# --------------------------------------------------------------------------
# Inherited git environment (git hook, rebase --exec, linked worktree)
# --------------------------------------------------------------------------


def _export_hook_env(monkeypatch, repo: Path) -> None:
    """Export what a pre-commit hook in a linked worktree receives."""
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(repo / ".git" / "index"))


class TestInheritedGitEnv:
    def test_git_child_env_drops_location_vars(self, monkeypatch, tmp_path: Path) -> None:
        captured: dict = {}

        def _fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured.update(kwargs)
            return subprocess.CompletedProcess(argv, 0, stdout="true\n", stderr="")

        for var in mod.GIT_LOCATION_VARS:
            monkeypatch.setenv(var, str(tmp_path / "leaked"))
        monkeypatch.setenv("SKF_UNRELATED_VAR", "kept")
        monkeypatch.setattr(mod.subprocess, "run", _fake_run)

        assert mod._git(["rev-parse", "HEAD"], cwd=tmp_path) == (0, "true", "")
        assert captured["argv"] == ["git", "-C", str(tmp_path), "rev-parse", "HEAD"]
        assert set(mod.GIT_LOCATION_VARS).isdisjoint(captured["env"])
        assert captured["env"]["SKF_UNRELATED_VAR"] == "kept"

    def test_check_reads_source_head_not_the_exported_repo(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        decoy = tmp_path / "decoy"
        decoy_sha = _init_repo(decoy, initial_content="decoy\n")
        decoy_index = _git(decoy, "ls-files", "--stage")
        source_sha = _init_repo(tmp_path / "source")
        _export_hook_env(monkeypatch, decoy)

        result = mod.check(
            tmp_path / "source", pinned_commit=source_sha, source_ref=None, allow_drift=False
        )
        assert result["status"] == "ok"
        assert result["head_sha"] == source_sha
        assert _git(decoy, "rev-parse", "HEAD") == decoy_sha
        assert _git(decoy, "ls-files", "--stage") == decoy_index

    def test_non_git_folder_still_skips(self, monkeypatch, tmp_path: Path) -> None:
        decoy = tmp_path / "decoy"
        _init_repo(decoy, initial_content="decoy\n")
        plain = tmp_path / "plain"
        plain.mkdir()
        _export_hook_env(monkeypatch, decoy)

        result = mod.check(plain, pinned_commit="abc1234567", source_ref=None, allow_drift=False)
        assert result["status"] == "skipped"
        assert result["skip_reason"] == "not-a-git-tree"

    def test_cli_reads_source_head_not_the_exported_repo(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        decoy = tmp_path / "decoy"
        _init_repo(decoy, initial_content="decoy\n")
        source_sha = _init_repo(tmp_path / "source")
        _export_hook_env(monkeypatch, decoy)

        result = _run_cli(str(tmp_path / "source"), "--pinned-commit", source_sha)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "ok"
        assert payload["head_sha"] == source_sha

    def test_fixture_never_writes_an_exported_index(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        # `git commit -a` exports an absolute GIT_INDEX_FILE and no GIT_DIR.
        decoy = tmp_path / "decoy"
        _init_repo(decoy, initial_content="decoy\n")
        decoy_index = _git(decoy, "ls-files", "--stage")
        monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / ".git" / "index"))

        _init_repo(tmp_path / "source")
        _add_commit(tmp_path / "source")
        assert _git(decoy, "ls-files", "--stage") == decoy_index
        assert _git(tmp_path / "source", "ls-files") == "file.txt"


# --------------------------------------------------------------------------
# upstream: has the remote moved past the baseline?
# --------------------------------------------------------------------------
#
# A scratch upstream (work repository, pushed to a bare one) and a clone of
# it made the way create-skill makes one: `--depth 1 --branch <tag>` from a
# file:// URL, so the clone is shallow and single-branch and has no
# origin/HEAD. main moves past the tags, as real projects do.

SOURCE_TREE = REPO_ROOT / "src" / "shared" / "scripts" / "skf-source-tree.py"


_QUIET_IDENTITY = (
    "-c",
    "user.name=t",
    "-c",
    "user.email=t@t",
    "-c",
    "advice.detachedHead=false",
)


def _g(cwd: Path, *args: str) -> str:
    return _git(cwd, *_QUIET_IDENTITY, *args)


class _Upstream:
    def __init__(self, root: Path):
        self.root = root
        self.work = root / "work"
        self.bare = root / "up.git"
        self.work.mkdir(parents=True)
        _g(self.work, "init", "-q", "-b", "main")
        self.n = 0

    def commit(self) -> str:
        self.n += 1
        (self.work / "file.txt").write_text(f"{self.n}\n", encoding="utf-8")
        _g(self.work, "add", "file.txt")
        _g(self.work, "commit", "-q", "-m", f"c{self.n}")
        return _g(self.work, "rev-parse", "HEAD")

    def tag(self, name: str, annotated: bool = False, at: str = "HEAD") -> None:
        _g(self.work, "tag", *(["-a", name, "-m", name] if annotated else [name]), at)

    def publish(self) -> None:
        if not self.bare.exists():
            _g(self.root, "clone", "-q", "--bare", str(self.work), str(self.bare))
        else:
            _g(
                self.work,
                "push",
                "-q",
                "--force",
                str(self.bare),
                "refs/heads/*:refs/heads/*",
                "refs/tags/*:refs/tags/*",
            )

    def clone(self, ref: str | None, name: str = "clone", shallow: bool = True) -> Path:
        dest = self.root / name
        args = ["clone", "-q"]
        if shallow:
            args += ["--depth", "1"]
        if ref:
            args += ["--branch", ref]
        _g(self.root, *args, self.bare.as_uri(), str(dest))
        return dest


def _up(source: Path, ref: str, commit: str, **kw) -> dict:
    return mod.upstream(source, baseline_commit=commit, baseline_ref=ref, **kw)


@pytest.fixture
def upstream_repo(tmp_path: Path) -> _Upstream:
    up = _Upstream(tmp_path)
    up.commit()
    up.tag("v1.0.0")
    up.commit()
    up.tag("v2.0.0", annotated=True)
    up.commit()  # main moves past the newest tag
    up.publish()
    return up


class TestUpstreamShallowTagClone:
    """The acceptance fixture: a `--depth 1 --branch <tag>` clone."""

    def test_no_newer_tag_is_unchanged(self, upstream_repo: _Upstream) -> None:
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        result = _up(clone, "v2.0.0", v2)
        assert result["status"] == "unchanged", result
        assert result["basis"] == "same-commit"
        assert result["ref_kind"] == "tag"
        assert result["latest_tag"] == "v2.0.0" and result["latest_tag_commit"] == v2
        # main moved past the tag: that is not an upstream move for a tag pin
        assert result["remote_head"] != v2 and result["remote_default_branch"] == "main"
        assert result["upstream_ref"] is None and result["upstream_commit"] is None
        assert (
            result["audit_ref"],
            result["audit_ref_source"],
            result["audit_commit"],
        ) == ("v2.0.0", "baseline", v2)
        assert (
            result["log_message"] == f"upstream_check: unchanged (v2.0.0 at {v2[:7]})"
        )

    def test_newer_tag_is_moved(self, upstream_repo: _Upstream) -> None:
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        v3 = upstream_repo.commit()
        upstream_repo.tag("v3.0.0")
        upstream_repo.publish()
        result = _up(clone, "v2.0.0", v2[:8])
        assert result["status"] == "moved", result
        assert result["basis"] == "newer-tag"
        assert (
            result["upstream_ref"],
            result["upstream_commit"],
            result["upstream_commit_short"],
        ) == ("v3.0.0", v3, v3[:7])
        assert (
            result["latest_tag"] == "v3.0.0"
            and result["latest_tag_commit_short"] == v3[:7]
        )
        # the short pin resolves to the clone's full commit; the audit stays on
        # the baseline
        assert (
            result["baseline_commit"] == v2
            and result["baseline_commit_short"] == v2[:7]
        )
        assert (
            result["audit_ref"],
            result["audit_ref_source"],
            result["audit_commit"],
        ) == ("v2.0.0", "baseline", v2)
        assert (
            result["log_message"]
            == f"upstream_check: moved (v2.0.0 {v2[:7]} -> v3.0.0 {v3[:7]})"
        )

    def test_clone_has_no_remote_head_and_is_left_unchanged(
        self, upstream_repo: _Upstream
    ) -> None:
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        refs = _git(clone, "for-each-ref")
        assert "refs/remotes/origin/HEAD" not in refs
        upstream_repo.commit()
        upstream_repo.tag("v3.0.0")
        upstream_repo.publish()
        assert _up(clone, "v2.0.0", v2)["status"] == "moved"
        assert _git(clone, "for-each-ref") == refs
        assert not (clone / ".git" / "FETCH_HEAD").exists()
        assert _git(clone, "rev-parse", "HEAD") == v2


class TestUpstreamTags:
    def test_prerelease_does_not_move_a_release(self, upstream_repo: _Upstream) -> None:
        upstream_repo.tag("v3.0.0-rc.1")
        upstream_repo.publish()
        clone = upstream_repo.clone("v2.0.0")
        result = _up(clone, "v2.0.0", _git(clone, "rev-parse", "HEAD"))
        assert (
            result["status"] == "unchanged" and result["basis"] == "same-commit"
        ), result
        assert result["latest_tag"] == "v2.0.0"

    def test_commit_past_the_newest_tag_is_contained(
        self, upstream_repo: _Upstream
    ) -> None:
        # The skill was built from a commit past the newest tag of its family.
        clone = upstream_repo.clone(None, shallow=False)
        result = _up(clone, "v2.0.0", _git(clone, "rev-parse", "HEAD"))
        assert (result["status"], result["basis"], result["latest_tag"]) == (
            "unchanged",
            "contained",
            "v2.0.0",
        )

    def test_older_newest_tag_is_no_newer_tag(self, upstream_repo: _Upstream) -> None:
        # The baseline tag is gone; the newest left of its family is older.
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        _g(upstream_repo.bare, "tag", "-d", "v2.0.0")
        result = _up(clone, "v2.0.0", v2)
        assert (result["status"], result["basis"], result["latest_tag"]) == (
            "unchanged",
            "no-newer-tag",
            "v1.0.0",
        )

    def test_release_moves_a_prerelease(self, upstream_repo: _Upstream) -> None:
        upstream_repo.tag("v3.0.0-rc.1")
        upstream_repo.publish()
        clone = upstream_repo.clone("v3.0.0-rc.1")
        rc = _git(clone, "rev-parse", "HEAD")
        assert _up(clone, "v3.0.0-rc.1", rc)["status"] == "unchanged"
        final = upstream_repo.commit()
        upstream_repo.tag("v3.0.0-rc.2")
        upstream_repo.tag("v3.0.0")
        upstream_repo.publish()
        result = _up(clone, "v3.0.0-rc.1", rc)
        assert (
            result["status"],
            result["upstream_ref"],
            result["upstream_commit"],
        ) == ("moved", "v3.0.0", final)

    def test_versions_compare_as_numbers(self, upstream_repo: _Upstream) -> None:
        upstream_repo.tag("v10.0.0", at="HEAD~2")  # older commit, newer version
        upstream_repo.tag("v9.0.0")
        upstream_repo.publish()
        clone = upstream_repo.clone("v2.0.0")
        result = _up(clone, "v2.0.0", _git(clone, "rev-parse", "HEAD"))
        assert result["latest_tag"] == "v10.0.0" and result["status"] == "moved"

    def test_newer_tag_already_in_baseline_history_is_unchanged(
        self, upstream_repo: _Upstream
    ) -> None:
        # A full clone at main holds v2.0.0 and a later v2.0.1 in its history.
        upstream_repo.tag("v2.0.1", at="HEAD~1")
        upstream_repo.publish()
        clone = upstream_repo.clone(None, shallow=False)
        head = _git(clone, "rev-parse", "HEAD")
        result = _up(clone, "v2.0.0", head)
        assert (
            result["status"] == "unchanged" and result["basis"] == "contained"
        ), result
        assert result["latest_tag"] == "v2.0.1"

    def test_retagged_baseline_is_moved(self, upstream_repo: _Upstream) -> None:
        clone = upstream_repo.clone("v2.0.0")
        old = _git(clone, "rev-parse", "HEAD")
        upstream_repo.commit()
        _g(upstream_repo.work, "tag", "-f", "-a", "v2.0.0", "-m", "again")
        upstream_repo.publish()
        new = _git(upstream_repo.bare, "rev-parse", "v2.0.0^{commit}")
        result = _up(clone, "v2.0.0", old)
        assert (
            result["status"],
            result["basis"],
            result["upstream_ref"],
            result["upstream_commit"],
        ) == ("moved", "tag-moved", "v2.0.0", new)

    def test_bare_baseline_sees_a_newer_v_tag(self, tmp_path: Path) -> None:
        # expressjs/express tagged up to 4.22.0 bare, then v4.22.1 to v5.2.1.
        up = _Upstream(tmp_path)
        for name in ("4.21.2", "4.22.0", "v4.22.1", "v5.2.1"):
            newest = up.commit()
            up.tag(name)
        up.publish()
        clone = up.clone("4.22.0")
        result = _up(clone, "4.22.0", _git(clone, "rev-parse", "HEAD"))
        assert (result["status"], result["basis"], result["latest_tag"]) == (
            "moved",
            "newer-tag",
            "v5.2.1",
        ), result
        assert (result["upstream_ref"], result["upstream_commit"]) == ("v5.2.1", newest)

    @pytest.mark.parametrize("newer", ["2.1.0", "V2.1.0"])
    def test_v_baseline_sees_a_newer_tag_of_another_release_prefix(
        self, upstream_repo: _Upstream, newer: str
    ) -> None:
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        new = upstream_repo.commit()
        upstream_repo.tag(newer)
        upstream_repo.publish()
        result = _up(clone, "v2.0.0", v2)
        assert (result["status"], result["basis"], result["latest_tag"]) == (
            "moved",
            "newer-tag",
            newer,
        )
        assert (result["upstream_ref"], result["upstream_commit"]) == (newer, new)

    @pytest.mark.parametrize("stray", ["20240101", "1234", "V99"])
    def test_date_or_build_number_under_another_prefix_does_not_count(
        self, upstream_repo: _Upstream, stray: str
    ) -> None:
        upstream_repo.tag(stray)
        upstream_repo.publish()
        clone = upstream_repo.clone("v2.0.0")
        result = _up(clone, "v2.0.0", _git(clone, "rev-parse", "HEAD"))
        assert (result["status"], result["basis"], result["latest_tag"]) == (
            "unchanged",
            "same-commit",
            "v2.0.0",
        )

    def test_monorepo_tags_stay_in_their_family(self, upstream_repo: _Upstream) -> None:
        upstream_repo.tag("pkg@1.0.0", at="HEAD~1")
        upstream_repo.tag("pkg@1.1.0")
        upstream_repo.tag("other@9.0.0")
        upstream_repo.tag("v5.0.0")
        upstream_repo.tag("6.0.0")
        upstream_repo.publish()
        clone = upstream_repo.clone("pkg@1.0.0")
        result = _up(clone, "pkg@1.0.0", _git(clone, "rev-parse", "HEAD"))
        assert (result["status"], result["latest_tag"], result["upstream_ref"]) == (
            "moved",
            "pkg@1.1.0",
            "pkg@1.1.0",
        )

    def test_deleted_baseline_tag_still_finds_newer_siblings(
        self, upstream_repo: _Upstream
    ) -> None:
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        _g(upstream_repo.bare, "tag", "-d", "v2.0.0")
        _g(upstream_repo.bare, "tag", "v2.1.0", "main")
        result = _up(clone, "v2.0.0", v2)
        assert (result["status"], result["upstream_ref"]) == ("moved", "v2.1.0")
        assert any("no longer exists" in w for w in result["warnings"])

    def test_tag_without_a_version_compares_its_commit(
        self, upstream_repo: _Upstream
    ) -> None:
        upstream_repo.tag("stable", at="HEAD~1")
        upstream_repo.publish()
        clone = upstream_repo.clone("stable")
        pinned = _git(clone, "rev-parse", "HEAD")
        assert _up(clone, "stable", pinned)["status"] == "unchanged"
        _g(upstream_repo.bare, "tag", "-f", "stable", "main")
        result = _up(clone, "stable", pinned)
        assert (result["status"], result["basis"], result["latest_tag"]) == (
            "moved",
            "tag-moved",
            None,
        )


class TestUpstreamBranchesAndHead:
    def test_branch_follows_its_tip(self, upstream_repo: _Upstream) -> None:
        _g(upstream_repo.work, "branch", "dev")
        upstream_repo.publish()
        clone = upstream_repo.clone("dev")
        tip = _git(clone, "rev-parse", "HEAD")
        result = _up(clone, "dev", tip)
        assert (result["status"], result["ref_kind"], result["basis"]) == (
            "unchanged",
            "branch",
            "same-commit",
        )
        assert result["latest_tag"] == "v2.0.0"  # shown, not decisive
        _g(upstream_repo.work, "checkout", "-q", "dev")
        new = upstream_repo.commit()
        upstream_repo.publish()
        result = _up(clone, "dev", tip)
        assert (
            result["status"],
            result["basis"],
            result["upstream_ref"],
            result["upstream_commit"],
        ) == ("moved", "ref-moved", "dev", new)

    @pytest.mark.parametrize("ref", ["HEAD", "head"])
    def test_head_follows_the_default_branch(
        self, upstream_repo: _Upstream, ref: str
    ) -> None:
        clone = upstream_repo.clone(None)
        head = _git(clone, "rev-parse", "HEAD")
        assert _up(clone, ref, head)["status"] == "unchanged"
        new = upstream_repo.commit()
        upstream_repo.publish()
        result = _up(clone, ref, head)
        assert (
            result["status"],
            result["ref_kind"],
            result["upstream_ref"],
            result["upstream_commit"],
        ) == ("moved", "head", "HEAD", new)
        assert result["remote_head"] == new and result["remote_head_short"] == new[:7]

    def test_commit_ref_follows_the_default_branch(
        self, upstream_repo: _Upstream
    ) -> None:
        clone = upstream_repo.clone(None)
        head = _git(clone, "rev-parse", "HEAD")
        result = _up(clone, head, head)
        assert (result["status"], result["ref_kind"]) == ("unchanged", "commit")


class TestUpstreamSkips:
    @pytest.mark.parametrize("ref", ["", "local", "null", "None", "  "])
    def test_no_baseline_ref(self, upstream_repo: _Upstream, ref: str) -> None:
        clone = upstream_repo.clone("v2.0.0")
        result = _up(clone, ref, _git(clone, "rev-parse", "HEAD"))
        assert (result["status"], result["skip_reason"]) == (
            "skipped",
            "no-baseline-ref",
        )
        assert (result["audit_ref"], result["audit_ref_source"]) == (
            "(unknown)",
            "baseline",
        )
        assert result["log_message"] == "upstream_check: skipped (no-baseline-ref)"

    @pytest.mark.parametrize("commit", ["", "local", "null", "not-a-sha", "abc"])
    def test_no_baseline_commit(self, upstream_repo: _Upstream, commit: str) -> None:
        clone = upstream_repo.clone("v2.0.0")
        result = _up(clone, "v2.0.0", commit)
        assert (result["status"], result["skip_reason"]) == (
            "skipped",
            "no-baseline-commit",
        )
        assert (
            result["audit_ref"],
            result["audit_ref_source"],
            result["audit_commit"],
        ) == ("v2.0.0", "baseline", "(unknown)")

    def test_neither_is_unavailable(self, tmp_path: Path) -> None:
        result = _up(tmp_path, "", "")
        assert (
            result["audit_ref"],
            result["audit_ref_source"],
            result["audit_commit"],
        ) == ("(unknown)", "unavailable", "(unknown)")

    def test_not_a_git_tree(self, tmp_path: Path) -> None:
        for root in (tmp_path, tmp_path / "missing"):
            result = _up(root, "v1.0.0", "a" * 40)
            assert (result["status"], result["skip_reason"]) == (
                "skipped",
                "not-a-git-tree",
            )

    @pytest.mark.skipif(
        os.name == "nt" or os.geteuid() == 0,
        reason="needs POSIX permissions that bind the user",
    )
    def test_source_root_in_an_unsearchable_folder(self, tmp_path: Path) -> None:
        # Before Python 3.14, Path.is_dir() raises here instead of answering False.
        locked = tmp_path / "locked"
        (locked / "clone").mkdir(parents=True)
        locked.chmod(0)
        try:
            result = _up(locked / "clone", "v1.0.0", "a" * 40)
        finally:
            locked.chmod(0o755)
        assert (result["status"], result["skip_reason"]) == (
            "skipped",
            "not-a-git-tree",
        )

    def test_git_unavailable(self, upstream_repo: _Upstream, monkeypatch) -> None:
        clone = upstream_repo.clone("v2.0.0")
        monkeypatch.setattr(mod._sibling(), "_resolve_outside_cwd", lambda _name: None)
        result = _up(clone, "v2.0.0", "a" * 40)
        assert (result["status"], result["skip_reason"]) == (
            "skipped",
            "git-unavailable",
        )

    @pytest.mark.parametrize("ref", ["-x", "a..b", "a b", "v1.0.0/"])
    def test_invalid_baseline_ref(self, upstream_repo: _Upstream, ref: str) -> None:
        clone = upstream_repo.clone("v2.0.0")
        result = _up(clone, ref, _git(clone, "rev-parse", "HEAD"))
        assert (result["status"], result["skip_reason"]) == (
            "skipped",
            "invalid-baseline-ref",
        )

    def test_unknown_ref_is_missing(self, upstream_repo: _Upstream) -> None:
        clone = upstream_repo.clone("v2.0.0")
        result = _up(clone, "no-such-branch", _git(clone, "rev-parse", "HEAD"))
        assert (result["status"], result["skip_reason"]) == (
            "skipped",
            "baseline-ref-missing",
        )

    def test_unreachable_remote_is_fetch_failed(self, upstream_repo: _Upstream) -> None:
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        _git(clone, "remote", "set-url", "origin", str(upstream_repo.root / "gone.git"))
        result = _up(clone, "v2.0.0", v2)
        assert result["status"] == "fetch-failed" and result["skip_reason"] is None
        assert result["fetch_error"] and result["fetch_error"].startswith("fatal:")
        assert (
            result["audit_ref"],
            result["audit_ref_source"],
            result["audit_commit"],
        ) == ("v2.0.0", "baseline", v2)
        assert (
            result["log_message"]
            == f"upstream_check: fetch-failed ({result['fetch_error']})"
        )

    @pytest.mark.skipif(
        os.name == "nt", reason="the stalled upload-pack is a POSIX shell command"
    )
    def test_stalled_remote_is_stopped_within_the_limit(
        self, upstream_repo: _Upstream
    ) -> None:
        clone = upstream_repo.clone("v2.0.0")
        _git(clone, "config", "remote.origin.uploadpack", "sleep 30; git-upload-pack")
        _git(clone, "remote", "set-url", "origin", str(upstream_repo.bare))
        started = time.monotonic()
        result = _up(clone, "v2.0.0", _git(clone, "rev-parse", "HEAD"), timeout=1)
        assert time.monotonic() - started < 15
        assert result["status"] == "fetch-failed"
        assert result["fetch_error"] == "timed out after 1 seconds"


class TestUpstreamStatuses:
    def test_vocabularies_match_the_docstring(self) -> None:
        doc = mod.__doc__
        for name, values in (
            ("UPSTREAM_SKIP_REASONS", mod.UPSTREAM_SKIP_REASONS),
            ("UPSTREAM_BASES", mod.UPSTREAM_BASES),
        ):
            end = doc.index(f"({name})")
            start = doc.rindex("null |", 0, end)
            assert tuple(re.findall(r'"([a-z-]+)"', doc[start:end])) == values, name

    def test_every_output_has_every_key(
        self, upstream_repo: _Upstream, tmp_path: Path
    ) -> None:
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        outputs = [
            _up(clone, "v2.0.0", v2),
            _up(clone, "", v2),
            _up(tmp_path, "v2.0.0", v2),
        ]
        upstream_repo.commit()
        upstream_repo.tag("v3.0.0")
        upstream_repo.publish()
        outputs.append(_up(clone, "v2.0.0", v2))
        keys = set(outputs[0])
        assert all(set(o) == keys for o in outputs)
        assert {o["status"] for o in outputs} == {"unchanged", "skipped", "moved"}


class TestUpstreamCli:
    def test_upstream_prints_json_and_exits_0(self, upstream_repo: _Upstream) -> None:
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        result = _run_cli(
            "upstream",
            "--source-root",
            str(clone),
            "--baseline-commit",
            v2,
            "--baseline-ref",
            "v2.0.0",
            "--timeout",
            "30",
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "unchanged"
        assert result.stdout.isascii()

    def test_moved_and_skipped_exit_0(
        self, upstream_repo: _Upstream, tmp_path: Path
    ) -> None:
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        upstream_repo.commit()
        upstream_repo.tag("v3.0.0")
        upstream_repo.publish()
        for root, status in ((clone, "moved"), (tmp_path / "nowhere", "skipped")):
            result = _run_cli(
                "upstream",
                "--source-root",
                str(root),
                "--baseline-commit",
                v2,
                "--baseline-ref",
                "v2.0.0",
            )
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["status"] == status

    def test_upstream_parser_takes_the_documented_flags(self) -> None:
        # A prose call can be checked against upstream's flags with this parser.
        args = mod._build_upstream_parser().parse_args(
            ["--source-root", "r", "--baseline-commit", "c", "--baseline-ref", "v1"]
        )
        assert (args.source_root, args.baseline_commit, args.baseline_ref) == (
            "r",
            "c",
            "v1",
        )
        assert args.timeout == mod.DEFAULT_UPSTREAM_TIMEOUT_SEC

    def test_missing_flag_is_a_usage_error(self, tmp_path: Path) -> None:
        result = _run_cli(
            "upstream", "--source-root", str(tmp_path), "--baseline-ref", "v1"
        )
        assert result.returncode == 2
        assert "--baseline-commit" in result.stderr

    def test_unexpected_error_is_one_json_line(self, monkeypatch, capsys) -> None:
        def boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(mod, "upstream", boom)
        assert (
            mod.main(
                [
                    "upstream",
                    "--source-root",
                    ".",
                    "--baseline-commit",
                    "a" * 40,
                    "--baseline-ref",
                    "v1",
                ]
            )
            == 1
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert json.loads(captured.err) == {
            "status": "error",
            "message": "RuntimeError: boom",
        }

    def test_folder_named_upstream_goes_through_the_check(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        sha = _init_repo(tmp_path / "upstream")
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "./upstream", "--pinned-commit", sha],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["status"] == "ok"

    def test_upstream_ignores_an_exported_git_dir(
        self, upstream_repo: _Upstream, monkeypatch
    ) -> None:
        clone = upstream_repo.clone("v2.0.0")
        v2 = _git(clone, "rev-parse", "HEAD")
        decoy = upstream_repo.root / "decoy"
        _init_repo(decoy, initial_content="decoy\n")
        _export_hook_env(monkeypatch, decoy)
        result = _run_cli(
            "upstream",
            "--source-root",
            str(clone),
            "--baseline-commit",
            v2,
            "--baseline-ref",
            "v2.0.0",
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "unchanged" and payload["baseline_commit"] == v2


# --------------------------------------------------------------------------
# The sibling skf-source-tree.py
# --------------------------------------------------------------------------


class TestSibling:
    def test_upstream_loads_the_source_tree_beside_it(self) -> None:
        sibling = mod._sibling()
        assert Path(sibling.__file__).resolve() == SOURCE_TREE.resolve()
        assert mod._sibling() is sibling

    def test_upstream_without_its_sibling_is_an_error(self, tmp_path: Path) -> None:
        lone = tmp_path / "skf-check-workspace-drift.py"
        lone.write_bytes(SCRIPT_PATH.read_bytes())
        result = subprocess.run(
            [
                sys.executable,
                str(lone),
                "upstream",
                "--source-root",
                str(tmp_path),
                "--baseline-commit",
                "a" * 40,
                "--baseline-ref",
                "v1",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1 and result.stdout == ""
        assert json.loads(result.stderr)["status"] == "error"

    def test_the_check_needs_no_sibling(self, tmp_path: Path) -> None:
        lone = tmp_path / "skf-check-workspace-drift.py"
        lone.write_bytes(SCRIPT_PATH.read_bytes())
        sha = _init_repo(tmp_path / "repo")
        result = subprocess.run(
            [sys.executable, str(lone), str(tmp_path / "repo"), "--pinned-commit", sha],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["status"] == "ok"
