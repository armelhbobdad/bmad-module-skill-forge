#!/usr/bin/env python3
"""Tests for skf-ccc-git-hygiene.py.

- The ccc-edit predicate mirrors ccc's `.gitignore` append exactly: line
  endings normalized on both sides, nothing when ccc's entry is already a
  line, and anything else (a user line, a second block, a separator) is not
  ccc's edit.
- workspace: in a clone under `{SKF_WORKSPACE}/repos/`, ccc's edit to a
  tracked `.gitignore` is restored (an untracked block-only file deleted),
  so the checkout of another ref that failed before now succeeds; the index
  and the lock go into `.git/info/exclude` (the common one for a linked
  worktree), survive a checkout that drops upstream rules and keep
  `git stash -u` away from them; every other change is kept, and a clone
  outside the workspace root or a subfolder is never touched.
- nested: a ccc project in a subfolder, a linked worktree or a submodule
  gets a self-ignoring `.cocoindex_code/.gitignore`, once, with the exact
  notice, whichever index path git does not ignore; an existing file, the
  project root and a folder outside a work tree are left alone; an index
  git already tracks names the remedy; a failed write leaves no partial
  file behind.
- CLI: one ASCII JSON line on exit 0, usage errors exit 2, and an inherited
  GIT_DIR / GIT_INDEX_FILE never reaches another repository.
- The link check and the CWD-shim guard stay identical to their siblings.

Fixture repositories are real git repositories under tmp_path; the helper
runs as a child process for the CLI-level tests and is imported for the
in-process ones.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "src" / "shared" / "scripts"
HELPER = SCRIPTS / "skf-ccc-git-hygiene.py"
ATOMIC_WRITE = SCRIPTS / "skf-atomic-write.py"
MERGE_HELPER = SCRIPTS / "skf-merge-ccc-exclusions.py"

BLOCK = b"# CocoIndex Code (ccc)\n/.cocoindex_code/\n"
SELF_IGNORE = b"# Created by SKF so git ignores this ccc index folder.\n*\n"
EXCLUDE_BLOCK = (
    b"# SKF: ccc index folders and the workspace lock stay out of git\n"
    b".cocoindex_code/\n/.skf-workspace.lock\n"
)
LOCK = ".skf-workspace.lock"
WORKSPACE_KEYS = {
    "mode", "status", "skip_reason", "repo", "exclude_path", "exclude_added",
    "gitignore_action", "warnings",
}
NESTED_KEYS = {
    "mode", "status", "skip_reason", "index_dir", "action", "tracked_db_files",
    "notice", "warnings",
}
# Dropped from every fixture git call, as the helper drops them, so a test
# that exports them on purpose never has its fixtures write elsewhere.
_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
)
IDENTITY = (
    "-c", "user.name=t",
    "-c", "user.email=t@t",
    "-c", "init.defaultBranch=main",
    "-c", "protocol.file.allow=always",
)

_MODULE = None


def _helper():
    """The helper imported in-process (loaded on first use, so a missing
    file fails each test rather than the whole module's collection)."""
    global _MODULE
    if _MODULE is None:
        spec = importlib.util.spec_from_file_location("skf_ccc_git_hygiene", HELPER)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        _MODULE = module
    return _MODULE


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _LOCATION_VARS}
    env["LC_ALL"] = "C"  # git's messages in English, whatever the machine's locale
    proc = subprocess.run(
        ["git", *IDENTITY, "-C", str(cwd), *args],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        env=env,
        timeout=120,
    )
    if check:
        assert proc.returncode == 0, (args, proc.stdout, proc.stderr)
    return proc


def git_out(cwd: Path, *args: str) -> str:
    return git(cwd, *args).stdout.decode("utf-8", errors="replace").strip()


def porcelain(root: Path) -> str:
    return git(root, "status", "--porcelain=v1", "-uall").stdout.decode("utf-8", errors="replace")


def co_v2(root: Path) -> int:
    """Fetch tag v2 and check it out, as a workspace hit does; returns the checkout's rc."""
    git(root, "fetch", "-q", "origin", "tag", "v2")
    return git(root, "-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD", check=False).returncode


def fake_index(root: Path) -> None:
    idx = root / ".cocoindex_code"
    (idx / "cocoindex.db" / "mdb").mkdir(parents=True, exist_ok=True)
    (idx / "settings.yml").write_bytes(b"exclude_patterns: []\n")
    (idx / "target_sqlite.db").write_bytes(b"\0" * 64)
    (idx / "cocoindex.db" / "mdb" / "data.mdb").write_bytes(b"\0" * 16)
    (idx / "cocoindex.db" / "mdb" / "lock.mdb").write_bytes(b"")


def ccc_append(root: Path, newline: str | None = None) -> None:
    """A byte-exact mirror of ccc's `.gitignore` append. newline=None writes
    os.linesep (CRLF on Windows); "\\r\\n" emulates Windows on POSIX."""
    if not (root / ".git").is_dir():
        return
    gi = root / ".gitignore"
    if gi.is_file():
        with open(gi, encoding="utf-8", newline=None) as f:
            content = f.read()
        if "/.cocoindex_code/" in content.splitlines():
            return
        if content and not content.endswith("\n"):
            content += "\n"
        content += "# CocoIndex Code (ccc)\n/.cocoindex_code/\n"
    else:
        content = "# CocoIndex Code (ccc)\n/.cocoindex_code/\n"
    with open(gi, "w", encoding="utf-8", newline=newline) as f:
        f.write(content)


def make_upstream(
    base: Path,
    name: str,
    v1_gitignore: bytes | None,
    v2_gitignore: bytes | None,
    extra_v1: dict[str, bytes] | None = None,
) -> Path:
    """An upstream repository with tags v1 and v2; `a.py` changes between them."""
    up = base / f"up-{name}"
    git(base, "init", "-q", str(up))
    (up / "a.py").write_bytes(b"v1\n")
    if v1_gitignore is not None:
        (up / ".gitignore").write_bytes(v1_gitignore)
    for rel, data in (extra_v1 or {}).items():
        (up / rel).parent.mkdir(parents=True, exist_ok=True)
        (up / rel).write_bytes(data)
    git(up, "add", "-A")
    git(up, "commit", "-q", "-m", "v1")
    git(up, "tag", "v1")
    (up / "a.py").write_bytes(b"v2\n")
    if v2_gitignore is None:
        (up / ".gitignore").unlink(missing_ok=True)
    else:
        (up / ".gitignore").write_bytes(v2_gitignore)
    git(up, "add", "-A")
    git(up, "commit", "-q", "-m", "v2")
    git(up, "tag", "v2")
    return up


def clone(up: Path, dest: Path, *, autocrlf: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    extra = ["-c", "core.autocrlf=true"] if autocrlf else []
    git(dest.parent, "clone", "-q", *extra, "--depth", "1", "--branch", "v1", up.as_uri(), str(dest))
    return dest


def run_helper(*args, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HELPER), *map(str, args)],
        cwd=cwd,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        env=env,
        timeout=120,
    )


def run_json(*args, cwd: Path, env: dict | None = None) -> dict:
    proc = run_helper(*args, cwd=cwd, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout.decode("utf-8"))


def symlink_or_skip(target: Path, link: Path, *, directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"symlinks unavailable: {e}")


@pytest.fixture
def ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "ws"
    (root / "repos").mkdir(parents=True)
    monkeypatch.setenv("SKF_WORKSPACE", str(root))
    return root


def ws_clone(ws: Path, up: Path, name: str, **kwargs) -> Path:
    return clone(up, ws / "repos" / "h" / "o" / name, **kwargs)


def workspace(repo: Path, cwd: Path) -> dict:
    return run_json("workspace", "--repo", repo, cwd=cwd)


# --------------------------------------------------------------------------
# Predicate
# --------------------------------------------------------------------------

ACCEPTED = {
    "lf": (b"node_modules/\n", b"node_modules/\n" + BLOCK),
    "no-final-newline": (b"node_modules/", b"node_modules/\n" + BLOCK),
    "crlf-rewritten-lf": (b"node_modules/\r\nbuild/\r\n", b"node_modules/\nbuild/\n" + BLOCK),
    "crlf-written": (
        b"node_modules/\r\nbuild/\r\n",
        b"node_modules/\r\nbuild/\r\n# CocoIndex Code (ccc)\r\n/.cocoindex_code/\r\n",
    ),
    "lone-cr": (b"node_modules/\r", b"node_modules/\n" + BLOCK),
    "empty": (b"", BLOCK),
    "trailing-blank-line": (b"node_modules/\n\n", b"node_modules/\n\n" + BLOCK),
    "bom": (b"\xef\xbb\xbfnode_modules/\n", b"\xef\xbb\xbfnode_modules/\n" + BLOCK),
}
REJECTED = {
    "entry-already-present-plus-block": (b"/.cocoindex_code/\n", b"/.cocoindex_code/\n" + BLOCK),
    "user-line-after-block": (b"node_modules/\n", b"node_modules/\n" + BLOCK + b"mine\n"),
    "block-twice": (b"node_modules/\n", b"node_modules/\n" + BLOCK + BLOCK),
    "blank-separator": (b"node_modules/\n", b"node_modules/\n\n" + BLOCK),
    "missing-comment-line": (b"node_modules/\n", b"node_modules/\n/.cocoindex_code/\n"),
    "block-without-final-newline": (b"node_modules/\n", b"node_modules/\n" + BLOCK[:-1]),
    "identical": (b"node_modules/\n", b"node_modules/\n"),
}
MIRROR_INPUTS = {
    **{name: (committed, False) for name, (committed, _) in ACCEPTED.items()},
    "entry-present": (b"node_modules/\n/.cocoindex_code/\n", True),
    "entry-present-crlf": (b"/.cocoindex_code/\r\ndist/\r\n", True),
}


class TestPredicate:
    @pytest.mark.parametrize("committed, worktree", ACCEPTED.values(), ids=ACCEPTED.keys())
    def test_ccc_edit_accepted(self, committed: bytes, worktree: bytes) -> None:
        assert _helper().is_ccc_edit(committed, worktree) is True

    @pytest.mark.parametrize("committed, worktree", REJECTED.values(), ids=REJECTED.keys())
    def test_not_ccc_edit(self, committed: bytes, worktree: bytes) -> None:
        assert _helper().is_ccc_edit(committed, worktree) is False

    def test_untracked_block_only(self) -> None:
        mod = _helper()
        assert mod.is_ccc_edit(None, BLOCK) is True
        assert mod.is_ccc_edit(None, BLOCK.replace(b"\n", b"\r\n")) is True
        assert mod.is_ccc_edit(None, BLOCK + b"extra\n") is False

    @pytest.mark.parametrize("newline", [None, "\r\n"], ids=["native", "windows"])
    @pytest.mark.parametrize("committed, present", MIRROR_INPUTS.values(), ids=MIRROR_INPUTS.keys())
    def test_mirror_output_is_accepted(self, tmp_path: Path, committed: bytes, present: bool, newline) -> None:
        (tmp_path / ".git").mkdir()
        gi = tmp_path / ".gitignore"
        gi.write_bytes(committed)
        ccc_append(tmp_path, newline=newline)
        written = gi.read_bytes()
        if present:
            assert written == committed, "the mirror writes nothing when the entry is a line"
            assert _helper().is_ccc_edit(committed, written) is False
        else:
            assert _helper().is_ccc_edit(committed, written) is True


# --------------------------------------------------------------------------
# workspace: .gitignore repair
# --------------------------------------------------------------------------

RESTORE_CASES = {
    "A": (b"node_modules/\n", b"node_modules/\ndist/\n"),
    "C": (b"node_modules/\n", b"node_modules/\n"),
    "D": (b"node_modules/", b"node_modules/\ndist/\n"),
    "E": (b"node_modules/\r\nbuild/\r\n", b"node_modules/\r\nbuild/\r\ndist/\r\n"),
    "F": (b"", b"dist/\n"),
    "H": (b"node_modules/\n\n", b"node_modules/\n\ndist/\n"),
}


def _ccc_state(root: Path) -> None:
    """What a forge that indexed the clone with ccc leaves behind."""
    ccc_append(root)
    fake_index(root)
    (root / LOCK).write_bytes(b"")


class TestWorkspaceRepair:
    @pytest.mark.parametrize("case", RESTORE_CASES.keys())
    def test_restored_then_checkout_succeeds(self, tmp_path: Path, ws: Path, case: str) -> None:
        v1, v2 = RESTORE_CASES[case]
        up = make_upstream(tmp_path, case, v1, v2)
        if case != "C":
            probe = clone(up, tmp_path / "probe" / case)
            _ccc_state(probe)
            assert co_v2(probe) != 0, "the fixture must reproduce the refused checkout"
        repo = ws_clone(ws, up, case)
        _ccc_state(repo)
        result = workspace(repo, tmp_path)
        assert result["status"] == "ok", result
        assert result["gitignore_action"] == "restored", result
        assert porcelain(repo) == ""
        assert (repo / ".gitignore").read_bytes() == git(repo, "show", "HEAD:.gitignore").stdout
        assert co_v2(repo) == 0
        assert git_out(repo, "rev-parse", "HEAD") == git_out(up, "rev-parse", "v2^{commit}")
        assert (repo / ".cocoindex_code" / "settings.yml").is_file()
        again = workspace(repo, tmp_path)
        assert again["exclude_added"] == []
        assert again["gitignore_action"] == "none"

    def test_untracked_ccc_only_gitignore_deleted(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "B", None, b"dist/\n")
        repo = ws_clone(ws, up, "B")
        _ccc_state(repo)
        assert (repo / ".gitignore").read_bytes().replace(b"\r\n", b"\n") == BLOCK
        result = workspace(repo, tmp_path)
        assert result["gitignore_action"] == "deleted", result
        assert not (repo / ".gitignore").exists()
        assert porcelain(repo) == ""
        assert co_v2(repo) == 0

    def test_committed_entry_left_alone(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "G", b"node_modules/\n/.cocoindex_code/\n", b"/.cocoindex_code/\ndist/\n")
        repo = ws_clone(ws, up, "G")
        _ccc_state(repo)
        result = workspace(repo, tmp_path)
        assert result["gitignore_action"] == "none", result
        assert porcelain(repo) == ""

    def test_windows_crlf_edit_restored_with_autocrlf(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "AC", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "AC", autocrlf=True)
        fresh = (repo / ".gitignore").read_bytes()
        assert fresh == b"node_modules/\r\n"
        ccc_append(repo, newline="\r\n")
        assert porcelain(repo) != ""
        result = workspace(repo, tmp_path)
        assert result["gitignore_action"] == "restored", result
        assert (repo / ".gitignore").read_bytes() == fresh
        assert porcelain(repo) == ""

    def test_other_gitignore_change_kept(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "U", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "U")
        ccc_append(repo)
        with open(repo / ".gitignore", "ab") as f:
            f.write(b"mine\n")
        before = (repo / ".gitignore").read_bytes()
        result = workspace(repo, tmp_path)
        assert result["gitignore_action"] == "kept", result
        assert (repo / ".gitignore").read_bytes() == before

    def test_untracked_gitignore_with_other_lines_kept(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "UB", None, b"dist/\n")
        repo = ws_clone(ws, up, "UB")
        (repo / ".gitignore").write_bytes(BLOCK + b"mine\n")
        result = workspace(repo, tmp_path)
        assert result["gitignore_action"] == "kept", result
        assert (repo / ".gitignore").read_bytes() == BLOCK + b"mine\n"

    def test_duplicate_block_after_existing_entry_kept(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "DUP", b"/.cocoindex_code/\n", b"/.cocoindex_code/\ndist/\n")
        repo = ws_clone(ws, up, "DUP")
        with open(repo / ".gitignore", "ab") as f:
            f.write(BLOCK)
        result = workspace(repo, tmp_path)
        assert result["gitignore_action"] == "kept", result
        assert (repo / ".gitignore").read_bytes() == b"/.cocoindex_code/\n" + BLOCK

    def test_deleted_tracked_gitignore_kept(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "DEL", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "DEL")
        (repo / ".gitignore").unlink()
        result = workspace(repo, tmp_path)
        assert result["gitignore_action"] == "kept", result
        assert not (repo / ".gitignore").exists()

    def test_symlinked_gitignore_kept(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "LNK", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "LNK")
        target = tmp_path / "elsewhere.gitignore"
        target.write_bytes(b"node_modules/\n" + BLOCK)
        (repo / ".gitignore").unlink()
        symlink_or_skip(target, repo / ".gitignore")
        result = workspace(repo, tmp_path)
        assert result["gitignore_action"] == "kept", result
        assert (repo / ".gitignore").is_symlink()
        assert target.read_bytes() == b"node_modules/\n" + BLOCK

    def test_other_tracked_change_left_alone(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "O", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "O")
        ccc_append(repo)
        with open(repo / "a.py", "ab") as f:
            f.write(b"local\n")
        result = workspace(repo, tmp_path)
        assert result["gitignore_action"] == "restored", result
        assert (repo / "a.py").read_bytes() == b"v1\nlocal\n"
        assert co_v2(repo) != 0, "a change the checkout would overwrite still refuses it"
        assert (repo / "a.py").read_bytes() == b"v1\nlocal\n"

    def test_exclude_failure_leaves_gitignore_alone(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "XF", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "XF")
        ccc_append(repo)
        before = (repo / ".gitignore").read_bytes()
        shutil.rmtree(repo / ".git" / "info", ignore_errors=True)
        (repo / ".git" / "info").write_bytes(b"not a folder\n")
        result = workspace(repo, tmp_path)
        assert result["status"] == "ok", result
        assert result["gitignore_action"] == "kept", result
        assert result["warnings"], result
        assert (repo / ".gitignore").read_bytes() == before


# --------------------------------------------------------------------------
# workspace: exclude
# --------------------------------------------------------------------------


class TestWorkspaceExclude:
    def test_exclude_lists_index_and_lock_and_stash_keeps_them(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "S", b"node_modules/\n", b"node_modules/\ndist/\n")
        control = clone(up, tmp_path / "control")
        _ccc_state(control)
        git(control, "stash", "push", "-u", "-q", "-m", "control")
        assert not (control / LOCK).exists(), "without the exclude, stash -u takes the lock"

        repo = ws_clone(ws, up, "S")
        _ccc_state(repo)
        result = workspace(repo, tmp_path)
        assert result["exclude_added"] == [".cocoindex_code/", "/.skf-workspace.lock"]
        exclude = Path(result["exclude_path"])
        assert exclude.read_bytes().endswith(EXCLUDE_BLOCK)
        git(repo, "stash", "push", "-u", "-m", "x")
        # The stash took nothing: neither the lock nor the index is a local change.
        assert git(repo, "rev-parse", "-q", "--verify", "refs/stash", check=False).returncode == 1
        assert (repo / LOCK).exists()
        assert (repo / ".cocoindex_code" / "settings.yml").is_file()

    def test_subtree_index_hidden(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "SUB", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "SUB")
        workspace(repo, tmp_path)
        fake_index(repo / "sub")
        assert porcelain(repo) == ""

    def test_upstream_db_rule_does_not_hide_settings(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "E2", b"*.db\n*.mdb\n", b"*.db\n*.mdb\ndist/\n")
        repo = ws_clone(ws, up, "E2")
        _ccc_state(repo)
        result = workspace(repo, tmp_path)
        assert result["gitignore_action"] == "restored", result
        assert porcelain(repo) == ""

    def test_exclude_survives_checkout_to_ref_that_drops_upstream_rules(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "E3", b"*.lock\n.cocoindex_code/\n", b"dist/\n")
        repo = ws_clone(ws, up, "E3")
        fake_index(repo)
        (repo / LOCK).write_bytes(b"")
        assert porcelain(repo) == "", "v1's own rules hide both"
        workspace(repo, tmp_path)
        assert co_v2(repo) == 0
        assert porcelain(repo) == ""

    def test_missing_info_dir_created(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "MI", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "MI")
        shutil.rmtree(repo / ".git" / "info", ignore_errors=True)
        result = workspace(repo, tmp_path)
        assert result["exclude_added"] == [".cocoindex_code/", "/.skf-workspace.lock"]
        assert (repo / ".git" / "info" / "exclude").read_bytes() == EXCLUDE_BLOCK

    def test_exclude_without_final_newline_gets_separator(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "NL", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "NL")
        exclude = repo / ".git" / "info" / "exclude"
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_bytes(b"# mine\n*.tmp")
        workspace(repo, tmp_path)
        assert exclude.read_bytes() == b"# mine\n*.tmp\n" + EXCLUDE_BLOCK

    def test_exclude_exact_line_reused(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "RU", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "RU")
        exclude = repo / ".git" / "info" / "exclude"
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_bytes(b".cocoindex_code/\n")
        first = workspace(repo, tmp_path)
        assert first["exclude_added"] == ["/.skf-workspace.lock"]
        expected = (
            b".cocoindex_code/\n"
            b"# SKF: ccc index folders and the workspace lock stay out of git\n"
            b"/.skf-workspace.lock\n"
        )
        assert exclude.read_bytes() == expected
        second = workspace(repo, tmp_path)
        assert second["exclude_added"] == []
        assert exclude.read_bytes() == expected

    def test_linked_worktree_uses_common_exclude(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "WT", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "WT")
        linked = ws / "repos" / "h" / "o" / "WT-linked"
        git(repo, "worktree", "add", "-q", "--detach", str(linked))
        result = workspace(linked, tmp_path)
        assert result["status"] == "ok", result
        assert os.path.samefile(result["exclude_path"], repo / ".git" / "info" / "exclude")
        fake_index(linked)
        assert porcelain(linked) == ""


# --------------------------------------------------------------------------
# workspace: guards
# --------------------------------------------------------------------------


class TestWorkspaceGuards:
    def test_outside_workspace_root_untouched(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "X", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = clone(up, tmp_path / "outside" / "X")
        ccc_append(repo)
        edited = (repo / ".gitignore").read_bytes()
        exclude = repo / ".git" / "info" / "exclude"
        exclude_before = exclude.read_bytes() if exclude.exists() else None
        result = workspace(repo, tmp_path)
        assert (result["status"], result["skip_reason"]) == ("skipped", "not-a-workspace-clone")
        assert result["gitignore_action"] is None
        assert (repo / ".gitignore").read_bytes() == edited
        assert (exclude.read_bytes() if exclude.exists() else None) == exclude_before

    def test_default_workspace_root_without_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.delenv("SKF_WORKSPACE", raising=False)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        up = make_upstream(tmp_path, "DW", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = clone(up, home / ".skf" / "workspace" / "repos" / "h" / "o" / "DW")
        ccc_append(repo)
        result = workspace(repo, tmp_path)
        assert result["status"] == "ok", result
        assert result["gitignore_action"] == "restored"

    def test_subfolder_is_not_a_clone_root(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "SF", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "SF")
        ccc_append(repo)
        (repo / "sub").mkdir()
        edited = (repo / ".gitignore").read_bytes()
        result = workspace(repo / "sub", tmp_path)
        assert (result["status"], result["skip_reason"]) == ("skipped", "not-a-clone-root")
        assert (repo / ".gitignore").read_bytes() == edited
        assert b"skf-workspace.lock" not in (repo / ".git" / "info" / "exclude").read_bytes()

    def test_missing_folder(self, tmp_path: Path, ws: Path) -> None:
        result = workspace(ws / "repos" / "h" / "o" / "nope", tmp_path)
        assert (result["status"], result["skip_reason"]) == ("skipped", "missing")
        assert result["exclude_path"] is None

    def test_tilde_repo_expanded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("SKF_WORKSPACE", "~/ws")
        up = make_upstream(tmp_path, "TI", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = clone(up, home / "ws" / "repos" / "h" / "o" / "TI")
        ccc_append(repo)
        result = run_json("workspace", "--repo", "~/ws/repos/h/o/TI", cwd=tmp_path)
        assert result["status"] == "ok", result
        assert result["repo"] == "~/ws/repos/h/o/TI"
        assert result["gitignore_action"] == "restored"
        assert porcelain(repo) == ""

    def test_git_unavailable(self, tmp_path: Path, ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        up = make_upstream(tmp_path, "GU", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "GU")
        fake_index(repo)
        mod = _helper()
        monkeypatch.setattr(mod, "_resolve_outside_cwd", lambda command: None)
        result = mod.workspace(str(repo))
        assert (result["status"], result["skip_reason"]) == ("skipped", "git-unavailable")
        nested = mod.nested(str(repo), str(tmp_path))
        assert (nested["status"], nested["skip_reason"]) == ("skipped", "git-unavailable")

    @pytest.mark.skipif(os.name == "nt", reason="POSIX shell shim")
    def test_git_shim_in_cwd_not_run(self, tmp_path: Path, ws: Path) -> None:
        up = make_upstream(tmp_path, "SH", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "SH")
        ccc_append(repo)
        shim_dir = tmp_path / "shim"
        shim_dir.mkdir()
        marker = tmp_path / "shim-ran"
        shim = shim_dir / "git"
        shim.write_bytes(f"#!/bin/sh\necho ran > '{marker}'\nexit 0\n".encode("utf-8"))
        shim.chmod(0o755)
        env = {**os.environ, "PATH": str(shim_dir)}
        result = run_json("workspace", "--repo", repo, cwd=shim_dir, env=env)
        assert (result["status"], result["skip_reason"]) == ("skipped", "git-unavailable")
        assert not marker.exists()


# --------------------------------------------------------------------------
# nested
# --------------------------------------------------------------------------


def make_project(base: Path, gitignore: bytes = BLOCK, name: str = "proj") -> Path:
    """A project whose root `.gitignore` holds `gitignore`, with a source in packages/lib."""
    proj = base / name
    git(base, "init", "-q", str(proj))
    (proj / ".gitignore").write_bytes(gitignore)
    (proj / "packages" / "lib" / "src").mkdir(parents=True)
    (proj / "packages" / "lib" / "src" / "g.py").write_bytes(b"x = 1\n")
    git(proj, "add", "-A")
    git(proj, "commit", "-q", "-m", "init")
    return proj


def nested(proj: Path, source: str, root: str | Path | None = None) -> dict:
    return run_json("nested", "--dir", source, "--project-root", root or proj, cwd=proj)


LIB_NOTICE = (
    "Wrote packages/lib/.cocoindex_code/.gitignore so git ignores the ccc index in that folder; "
    "your own .gitignore files are unchanged."
)


class TestNested:
    def test_subfolder_index_ignores_itself(self, tmp_path: Path) -> None:
        proj = make_project(tmp_path)
        lib = proj / "packages" / "lib"
        fake_index(lib)
        assert len(porcelain(proj).splitlines()) == 4
        root_gitignore = (proj / ".gitignore").read_bytes()
        exclude = proj / ".git" / "info" / "exclude"
        exclude_before = exclude.read_bytes() if exclude.exists() else None
        result = nested(proj, "packages/lib")
        assert (result["status"], result["action"]) == ("ok", "wrote"), result
        assert (lib / ".cocoindex_code" / ".gitignore").read_bytes() == SELF_IGNORE
        assert porcelain(proj) == ""
        assert git(proj, "add", "-A", "--dry-run").stdout == b""
        assert (proj / ".gitignore").read_bytes() == root_gitignore
        assert (exclude.read_bytes() if exclude.exists() else None) == exclude_before
        assert result["index_dir"] == "packages/lib/.cocoindex_code"
        assert result["notice"] == LIB_NOTICE
        again = nested(proj, "packages/lib")
        assert (again["action"], again["notice"]) == ("none", None)

    def test_partial_db_rule_still_writes(self, tmp_path: Path) -> None:
        proj = make_project(tmp_path, b"*.db\n*.mdb\n")
        fake_index(proj / "packages" / "lib")
        assert porcelain(proj) == "?? packages/lib/.cocoindex_code/settings.yml\n"
        result = nested(proj, "packages/lib")
        assert result["action"] == "wrote", result
        assert porcelain(proj) == ""

    @pytest.mark.parametrize(
        ("rules", "listed"),
        [
            pytest.param(
                b"settings.yml\n",
                ["target_sqlite.db", "cocoindex.db/mdb/data.mdb", "cocoindex.db/mdb/lock.mdb"],
                id="settings-only-ignored",
            ),
            pytest.param(b"*.yml\n*.mdb\n", ["target_sqlite.db"], id="only-sqlite-db-listed"),
            pytest.param(
                b"*.yml\ntarget_sqlite.db\n",
                ["cocoindex.db/mdb/data.mdb", "cocoindex.db/mdb/lock.mdb"],
                id="only-lmdb-listed",
            ),
        ],
    )
    def test_settings_rule_still_writes(self, tmp_path: Path, rules: bytes, listed: list[str]) -> None:
        """Every index probe counts: an ignored settings.yml, or one ignored database,
        does not make the folder ignored."""
        proj = make_project(tmp_path, rules)
        fake_index(proj / "packages" / "lib")
        before = {f"?? packages/lib/.cocoindex_code/{rel}" for rel in listed}
        assert set(porcelain(proj).splitlines()) == before
        result = nested(proj, "packages/lib")
        assert result["action"] == "wrote", result
        assert porcelain(proj) == ""

    def test_already_ignored_writes_nothing(self, tmp_path: Path) -> None:
        proj = make_project(tmp_path, b".cocoindex_code/\n")
        fake_index(proj / "packages" / "lib")
        result = nested(proj, "packages/lib")
        assert (result["status"], result["action"], result["notice"]) == ("ok", "none", None)
        assert not (proj / "packages" / "lib" / ".cocoindex_code" / ".gitignore").exists()

    def test_committed_index_reports_tracked_files(self, tmp_path: Path) -> None:
        proj = make_project(tmp_path)
        fake_index(proj / "packages" / "lib")
        git(proj, "add", "-A")
        git(proj, "commit", "-q", "-m", "index")
        result = nested(proj, "packages/lib")
        assert result["action"] == "wrote", result
        assert result["tracked_db_files"] == 3
        remedy = 'git rm -r --cached -- "packages/lib/.cocoindex_code"'
        assert remedy in result["notice"]
        git(proj, "rm", "-r", "-q", "--cached", "--", "packages/lib/.cocoindex_code")
        git(proj, "commit", "-q", "-m", "untrack")
        assert porcelain(proj) == ""

    def test_linked_worktree_and_submodule_write(self, tmp_path: Path) -> None:
        other = tmp_path / "other"
        git(tmp_path, "init", "-q", str(other))
        (other / "a.py").write_bytes(b"a\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "init")
        proj = make_project(tmp_path, BLOCK + b"/wt/\n")
        git(other, "worktree", "add", "-q", str(proj / "wt"))
        fake_index(proj / "wt")
        assert porcelain(proj / "wt") != ""
        linked = nested(proj, "wt")
        assert linked["action"] == "wrote", linked
        assert porcelain(proj / "wt") == ""

        sub_up = tmp_path / "subup"
        git(tmp_path, "init", "-q", str(sub_up))
        (sub_up / "a.py").write_bytes(b"a\n")
        git(sub_up, "add", "-A")
        git(sub_up, "commit", "-q", "-m", "init")
        superproject = make_project(tmp_path, BLOCK, name="super")
        git(superproject, "submodule", "add", "-q", sub_up.as_uri(), "mod")
        git(superproject, "commit", "-q", "-m", "submodule")
        fake_index(superproject / "mod")
        assert porcelain(superproject) != ""
        sub = nested(superproject, "mod")
        assert sub["action"] == "wrote", sub
        assert porcelain(superproject) == ""
        assert porcelain(superproject / "mod") == ""

    def test_foreign_gitignore_left_unchanged(self, tmp_path: Path) -> None:
        proj = make_project(tmp_path)
        fake_index(proj / "packages" / "lib")
        foreign = proj / "packages" / "lib" / ".cocoindex_code" / ".gitignore"
        foreign.write_bytes(b"foo\n")
        result = nested(proj, "packages/lib")
        assert result["action"] == "exists", result
        assert result["notice"] == (
            "git lists files in packages/lib/.cocoindex_code as untracked, and the .gitignore "
            "already in that folder does not ignore them; add a line holding only * to "
            "packages/lib/.cocoindex_code/.gitignore."
        )
        assert foreign.read_bytes() == b"foo\n"

    @pytest.mark.parametrize("failure", ["raises", "short-write"])
    def test_write_failure_is_failed_and_leaves_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, failure: str
    ) -> None:
        """A write that fails after the create reports "failed" on exit 0 and removes
        the partial file, so the next run writes it instead of reporting "exists"."""
        proj = make_project(tmp_path)
        lib = proj / "packages" / "lib"
        fake_index(lib)
        target = lib / ".cocoindex_code" / ".gitignore"
        mod = _helper()
        real_write = os.write

        def failing_write(fd: int, data: bytes) -> int:
            if data != SELF_IGNORE:
                return real_write(fd, data)
            if failure == "raises":
                raise OSError(28, "No space left on device")
            return real_write(fd, data[:-1])

        monkeypatch.setattr(mod.os, "write", failing_write)
        rc = mod.main(["nested", "--dir", str(lib), "--project-root", str(proj)])
        monkeypatch.setattr(mod.os, "write", real_write)
        captured = capsys.readouterr()
        assert rc == 0, captured.err
        result = json.loads(captured.out)
        reason = "No space left on device" if failure == "raises" else "short write"
        index_dir = str(lib) + "/.cocoindex_code"
        assert (result["status"], result["action"]) == ("ok", "failed"), result
        assert result["warnings"] == [f"could not create {index_dir}/.gitignore: {reason}"]
        assert result["notice"] == (
            f"Could not write {index_dir}/.gitignore ({reason}); git lists the ccc index in "
            f"that folder as untracked. Create that file holding the line * to keep it out of git."
        )
        assert not target.exists()
        again = mod.nested(str(lib), str(proj))
        assert again["action"] == "wrote", again
        assert target.read_bytes() == SELF_IGNORE

    @pytest.mark.parametrize(
        "case",
        ["project-root-dot", "project-root-abs", "project-root-abs-slash", "no-ccc-project",
         "missing", "not-a-work-tree", "index-dir-is-link"],
    )
    def test_nested_skips(self, tmp_path: Path, case: str) -> None:
        proj = make_project(tmp_path)
        env = None
        cwd = proj
        index = proj / "packages" / "lib" / ".cocoindex_code"
        if case.startswith("project-root"):
            fake_index(proj)
            index = proj / ".cocoindex_code"
            source = {"project-root-dot": ".", "project-root-abs": str(proj),
                      "project-root-abs-slash": str(proj) + os.sep}[case]
            expected = "project-root"
        elif case == "no-ccc-project":
            index.mkdir(parents=True)
            source, expected = "packages/lib", case
        elif case == "missing":
            source, expected = "packages/nope", case
        elif case == "not-a-work-tree":
            lib = tmp_path / "nogit" / "lib"
            lib.mkdir(parents=True)
            fake_index(lib)
            index = lib / ".cocoindex_code"
            source, expected, cwd = str(lib), case, tmp_path
            env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tmp_path)}
        else:
            real = tmp_path / "real-index"
            fake_index(real)
            symlink_or_skip(real / ".cocoindex_code", index, directory=True)
            index = real / ".cocoindex_code"
            source, expected = "packages/lib", "index-dir-is-link"
        result = run_json("nested", "--dir", source, "--project-root", proj, cwd=cwd, env=env)
        assert (result["status"], result["skip_reason"]) == ("skipped", expected), result
        assert (result["action"], result["notice"]) == (None, None)
        assert not (index / ".gitignore").exists()

    def test_tilde_dir_and_project_root_expanded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        proj = make_project(home, b"node_modules/\n")
        lib = proj / "packages" / "lib"
        fake_index(lib)
        result = run_json("nested", "--dir", "~/proj/packages/lib", "--project-root", "~/proj", cwd=tmp_path)
        assert (result["status"], result["action"]) == ("ok", "wrote"), result
        assert result["index_dir"] == "~/proj/packages/lib/.cocoindex_code"
        assert (lib / ".cocoindex_code" / ".gitignore").read_bytes() == SELF_IGNORE
        assert porcelain(proj) == ""
        fake_index(proj)
        root = run_json("nested", "--dir", "~/proj", "--project-root", "~/proj", cwd=tmp_path)
        assert (root["status"], root["skip_reason"]) == ("skipped", "project-root"), root
        assert not (proj / ".cocoindex_code" / ".gitignore").exists()

    def test_git_timeout_is_git_failed(self, tmp_path: Path, ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        proj = make_project(tmp_path)
        fake_index(proj / "packages" / "lib")
        up = make_upstream(tmp_path, "TO", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "TO")
        mod = _helper()

        def timeout(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

        monkeypatch.setattr(mod.subprocess, "run", timeout)
        result = mod.nested(str(proj / "packages" / "lib"), str(proj))
        assert (result["status"], result["skip_reason"]) == ("skipped", "git-failed")
        assert not (proj / "packages" / "lib" / ".cocoindex_code" / ".gitignore").exists()
        ws_result = mod.workspace(str(repo))
        assert (ws_result["status"], ws_result["skip_reason"]) == ("skipped", "git-failed")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class TestCli:
    @pytest.mark.parametrize("mode", ["workspace", "nested"])
    def test_single_ascii_json_line_exit_0(self, tmp_path: Path, ws: Path, mode: str) -> None:
        if mode == "workspace":
            up = make_upstream(tmp_path, "cli", b"node_modules/\n", b"node_modules/\ndist/\n")
            repo = ws_clone(ws, up, "café")
            ccc_append(repo)
            args, cwd, keys = ["workspace", "--repo", repo], tmp_path, WORKSPACE_KEYS
        else:
            proj = make_project(tmp_path, name="pröj")
            fake_index(proj / "packages" / "lib")
            source = proj / "packages" / "lib"  # absolute, so index_dir and notice carry the non-ASCII name
            args, cwd, keys = ["nested", "--dir", source, "--project-root", proj], proj, NESTED_KEYS
        proc = run_helper(*args, cwd=cwd)
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == b""
        assert proc.stdout.isascii(), proc.stdout
        text = proc.stdout.decode("ascii").replace("\r\n", "\n")
        assert text.count("\n") == 1 and text.endswith("\n")
        payload = json.loads(text)
        assert set(payload) == keys
        assert payload["mode"] == mode and payload["status"] == "ok"
        assert payload["warnings"] == []

    def test_usage_error_exit_2(self, tmp_path: Path) -> None:
        assert HELPER.is_file()
        for args in ([], ["nested", "--dir", "x"], ["workspace"], ["other"]):
            proc = run_helper(*args, cwd=tmp_path)
            assert proc.returncode == 2, (args, proc.stderr)
            assert b"usage:" in proc.stderr, proc.stderr
            assert proc.stdout == b""

    def test_inherited_git_env_does_not_leak(self, tmp_path: Path, ws: Path) -> None:
        decoy = make_project(tmp_path, b"decoy/\n", name="decoy")
        decoy_files = [decoy / ".git" / "index", decoy / ".gitignore", decoy / ".git" / "info" / "exclude"]
        before = [p.read_bytes() if p.exists() else None for p in decoy_files]
        up = make_upstream(tmp_path, "ENV", b"node_modules/\n", b"node_modules/\ndist/\n")
        repo = ws_clone(ws, up, "ENV")
        _ccc_state(repo)
        proj = make_project(tmp_path, name="proj")
        fake_index(proj / "packages" / "lib")
        env = {
            **os.environ,
            "GIT_DIR": str(decoy / ".git"),
            "GIT_INDEX_FILE": str(decoy / ".git" / "index"),
        }
        result = run_json("workspace", "--repo", repo, cwd=tmp_path, env=env)
        assert result["gitignore_action"] == "restored", result
        assert porcelain(repo) == ""
        nested_result = run_json("nested", "--dir", "packages/lib", "--project-root", proj, cwd=proj, env=env)
        assert nested_result["action"] == "wrote", nested_result
        assert [p.read_bytes() if p.exists() else None for p in decoy_files] == before


# --------------------------------------------------------------------------
# Pinned copies and constants
# --------------------------------------------------------------------------


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(found) == 1, f"{path.name} has {len(found)} top-level {name}"
    return found[0]


def _without_docstring(node: ast.FunctionDef) -> str:
    """ast.dump of the function with a leading docstring dropped."""
    node = copy.deepcopy(node)
    first = node.body[0] if node.body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        node.body = node.body[1:]
    return ast.dump(node)


class TestPinnedCopies:
    def test_link_check_copy_matches_atomic_write(self) -> None:
        ours = _function(HELPER, "_is_link_or_junction")
        theirs = _function(ATOMIC_WRITE, "_is_link_or_junction")
        assert ast.dump(ours) == ast.dump(theirs)

    def test_cwd_guard_code_matches_merge_helper(self) -> None:
        ours = _function(HELPER, "_resolve_outside_cwd")
        theirs = _function(MERGE_HELPER, "_resolve_outside_cwd")
        assert _without_docstring(ours) == _without_docstring(theirs)

    def test_copies_carry_keep_identical_notes(self) -> None:
        text = HELPER.read_text(encoding="utf-8")
        assert "Keep identical to GIT_LOCATION_VARS in skf-check-workspace-drift.py" in text
        assert "Keep identical to _is_link_or_junction in skf-atomic-write.py" in text
        assert "test/test-skf-ccc-git-hygiene.py pins" in text

    def test_link_check_other_reparse_points_not_links(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mod = _helper()
        placeholder = tmp_path / "placeholder"
        placeholder.write_bytes(b"x")

        def reparse(path, *args, **kwargs):
            raise ValueError("not a symbolic link")

        monkeypatch.setattr(mod.os, "readlink", reparse)
        assert mod._is_link_or_junction(placeholder) is False

    def test_constants(self) -> None:
        mod = _helper()
        assert mod.CCC_BLOCK == b"# CocoIndex Code (ccc)\n/.cocoindex_code/\n"
        assert mod.SELF_IGNORE.endswith(b"\n*\n")
        assert mod.SELF_IGNORE == SELF_IGNORE
        assert mod.EXCLUDE_ENTRIES == (".cocoindex_code/", "/.skf-workspace.lock")
