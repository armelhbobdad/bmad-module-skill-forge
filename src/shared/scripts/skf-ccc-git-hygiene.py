# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF CCC Git Hygiene — keep ccc's index folders and SKF's workspace lock
out of git outside the project root.

ccc adds `/.cocoindex_code/` to `.gitignore` only when it creates a project
at the top of a git checkout whose `.git` is a folder. That leaves two gaps,
one per subcommand:

  - In an SKF workspace clone the `.gitignore` ccc edits is usually
    tracked, so the edit is a local change that makes git refuse a later
    checkout of another ref, and SKF's `.skf-workspace.lock` shows as
    untracked.
  - A ccc project in a subfolder of a checkout, in a linked worktree or in
    a submodule gets no entry at all, so git lists its index database as
    untracked and a `git add -A` would commit it.

CLI:

  uv run skf-ccc-git-hygiene.py workspace --repo <clone path>
  uv run skf-ccc-git-hygiene.py nested --dir <source folder> --project-root <project root>

`~` is expanded in --repo, --dir, --project-root and SKF_WORKSPACE.

workspace, in order:

  1. Guard: act only when --repo lies under
     `{SKF_WORKSPACE or ~/.skf/workspace}/repos/` and is the top level of its
     git work tree (`git rev-parse --show-toplevel`). Anything else is
     skipped without a write.
  2. Exclude: append `.cocoindex_code/` (unanchored, so an index in a
     subfolder is covered too) and `/.skf-workspace.lock`, under an SKF
     header, to the file `git rev-parse --git-path info/exclude` names (the
     common one for a linked worktree). An entry already there as an exact
     line is not added again. This runs before any `.gitignore` change, so
     the index folder never shows between the two steps; when it fails,
     `.gitignore` is left alone.
  3. `.gitignore` repair: when the working-tree `.gitignore` is exactly what
     ccc's append makes of the committed one (line endings normalized on
     both sides; ccc writes nothing when its entry is already a line),
     restore it with `git checkout -- .gitignore`, which reapplies autocrlf
     and eol attributes. When `.gitignore` is untracked and holds exactly
     ccc's two lines, delete it. Any other change, a link, conflict stages,
     an unusual mode or a deleted tracked file is kept.

nested:

  Skips a missing folder, the project root, a `.cocoindex_code` link and a
  folder without `.cocoindex_code/settings.yml`. It then runs
  `git check-ignore -q --no-index` for `settings.yml`, `target_sqlite.db`
  and `cocoindex.db/mdb/data.mdb` under `.cocoindex_code/`, one call per
  path (`-q` refuses several). When any of them is not ignored, it creates
  `.cocoindex_code/.gitignore` holding `*` so the folder ignores itself.
  The write is create-only: an existing file is never overwritten, and a
  write that fails removes the partial file it created. When git
  already tracks index files there, the notice names the
  `git rm -r --cached` remedy. It never reads or writes the project's
  `.gitignore` or any `info/exclude`.

Output: one JSON object on one stdout line (ASCII).

  workspace:
    mode              "workspace"
    status            "ok" | "skipped"
    skip_reason       null | "missing" | "not-a-workspace-clone" |
                      "git-unavailable" | "git-failed" | "not-a-clone-root"
    repo              --repo as given
    exclude_path      absolute path of the exclude file, or null
    exclude_added     the entries appended by this run, in order
    gitignore_action  null when skipped | "none" | "restored" | "deleted" |
                      "kept"
    warnings          one entry per failed sub-step

  nested:
    mode              "nested"
    status            "ok" | "skipped"
    skip_reason       null | "missing" | "project-root" |
                      "index-dir-is-link" | "no-ccc-project" |
                      "git-unavailable" | "not-a-work-tree" | "git-failed"
    index_dir         --dir as given plus "/.cocoindex_code"
    action            null when skipped | "none" | "wrote" | "exists" |
                      "failed"
    tracked_db_files  tracked paths under the folder other than
                      settings.yml and .gitignore
    notice            one line for the user, or null
    warnings          one entry per failed sub-step

Exit codes:
  0  every "ok" and "skipped" result, including partial failures reported
     in `warnings`
  1  unexpected error: {"status": "error", "message": ...} on stderr,
     nothing on stdout
  2  usage error (argparse)

git runs with the git location variables (GIT_DIR, GIT_INDEX_FILE, ...)
removed from its environment. A git hook or `git rebase --exec` exports
them (GIT_DIR too when run in a linked worktree); inherited by
`git -C <clone>`, they would make the helper touch another repository.

It never edits a project's own `.gitignore`: in a workspace clone it only
restores the committed file or deletes the one ccc created, and elsewhere
it writes only inside a ccc index folder.

It never gates: callers treat any non-zero exit or missing JSON as "did not
run" and continue.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CCC_DIR = ".cocoindex_code"
CCC_ENTRY = "/.cocoindex_code/"
CCC_BLOCK = b"# CocoIndex Code (ccc)\n/.cocoindex_code/\n"  # what ccc init appends
EXCLUDE_HEADER = "# SKF: ccc index folders and the workspace lock stay out of git"
EXCLUDE_ENTRIES = (".cocoindex_code/", "/.skf-workspace.lock")
INDEX_PROBES = (
    ".cocoindex_code/settings.yml",
    ".cocoindex_code/target_sqlite.db",
    ".cocoindex_code/cocoindex.db/mdb/data.mdb",
)
SELF_IGNORE = b"# Created by SKF so git ignores this ccc index folder.\n*\n"
NOT_DB_FILES = {".cocoindex_code/settings.yml", ".cocoindex_code/.gitignore"}
GIT_TIMEOUT_SEC = 30
# Keep identical to GIT_LOCATION_VARS in skf-check-workspace-drift.py.
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


# Keep identical to _is_link_or_junction in skf-atomic-write.py
# (test/test-skf-ccc-git-hygiene.py pins the copy).
def _is_link_or_junction(p: Path) -> bool:
    """True for POSIX symlinks AND Windows junctions/symlinks.

    `Path.is_symlink()` is False for Windows junctions; os.readlink succeeds
    for both symlinks and junctions (since CPython 3.8 on Windows). A regular
    directory raises OSError on readlink, which is the signal we want to
    refuse replacement. On Windows, any other reparse point (a cloud-sync
    placeholder, a deduplicated file, an app execution alias) raises
    ValueError: it does not redirect to another path, so it is not a link.
    """
    if p.is_symlink():
        return True
    if not p.exists() and not p.is_symlink():
        return False
    try:
        os.readlink(p)
        return True
    except (OSError, ValueError):
        return False


def _resolve_outside_cwd(command: str) -> str | None:
    """shutil.which with a CWD-shim guard. Returns the resolved path or None.

    shutil.which on Windows searches the current directory ahead of PATH,
    and CWD here may be a repository SKF does not control — a bare-name
    lookup resolving into CWD would execute a planted shim (e.g. git.exe).
    Such a resolution is treated as not-found. Explicit paths supplied by
    callers (containing a separator) are honored as-is. Keep the code
    identical to the sibling guards in skf-merge-ccc-exclusions.py,
    skf-detect-tools.py, skf-qmd-classify-collections.py,
    skf-source-tree.py, skf-tessl-review.py and
    skf-verify-provenance-completeness.py
    (test/test-skf-ccc-git-hygiene.py pins it against
    skf-merge-ccc-exclusions.py).
    """
    resolved = shutil.which(command)
    if resolved is None:
        return None
    if os.sep in command or (os.altsep and os.altsep in command):
        return resolved
    resolved_dir = os.path.dirname(resolved)
    if resolved_dir:
        cwd = os.path.normcase(os.path.abspath(os.getcwd()))
        if os.path.normcase(os.path.abspath(resolved_dir)) == cwd:
            return None
    return resolved


def _git(root: Path, *args: str) -> tuple[int, bytes, str] | None:
    """Run `git -C <root> <args>` with the git location variables removed.

    Returns None when git cannot be found (or only as a shim in CWD) or
    cannot start, (-1, b"", "timeout") on a timeout, and otherwise
    (returncode, stdout bytes, stderr text). LC_ALL=C keeps git's messages
    in one locale.
    """
    exe = _resolve_outside_cwd("git")
    if exe is None:
        return None
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            [exe, "-C", str(root), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=env,
            timeout=GIT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return -1, b"", "timeout"
    except (OSError, ValueError):
        return None
    return result.returncode, result.stdout, result.stderr.decode("utf-8", errors="replace")


def _same_path(a: str | Path, b: str | Path) -> bool:
    """Path identity that covers Windows case and 8.3 names, forward-slash
    git output and macOS /private."""
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _norm(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def is_ccc_edit(committed: bytes | None, worktree: bytes) -> bool:
    """True when `worktree` is exactly what ccc's .gitignore append makes of `committed`
    (None = no tracked .gitignore). Line endings are normalized on both sides, so ccc's
    text-mode rewrite (LF on POSIX, CRLF throughout on Windows) matches."""
    w = _norm(worktree)
    if committed is None:
        return w == CCC_BLOCK
    base = _norm(committed)
    if CCC_ENTRY in base.decode("utf-8", "surrogateescape").splitlines():
        return False  # ccc writes nothing when its entry is already a line
    sep = b"\n" if base and not base.endswith(b"\n") else b""
    return w == base + sep + CCC_BLOCK


def _ensure_excludes(path: Path, warnings: list[str]) -> list[str] | None:
    """Append the EXCLUDE_ENTRIES missing from `path` as exact lines.

    Returns the entries added ([] when all were there), or None after a
    read or write failure, which is recorded in `warnings`.
    """
    try:
        try:
            cur = path.read_bytes()
        except FileNotFoundError:
            cur = b""
        text = _norm(cur).decode("utf-8", "surrogateescape")
        present = {line.rstrip(" \t") for line in text.split("\n")}
        missing = [entry for entry in EXCLUDE_ENTRIES if entry not in present]
        if not missing:
            return []
        lead = "\n" if cur and not cur.endswith((b"\n", b"\r")) else ""
        block = lead + EXCLUDE_HEADER + "\n" + "".join(entry + "\n" for entry in missing)
        path.parent.mkdir(parents=True, exist_ok=True)
        # O_BINARY (Windows only; 0 elsewhere) keeps the LF line endings.
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0),
            0o644,
        )
        try:
            os.write(fd, block.encode("utf-8"))
        finally:
            os.close(fd)
    except OSError as e:
        warnings.append(f"could not update {path}: {e.strerror or e}")
        return None
    return missing


def _repair_gitignore(repo: Path, warnings: list[str]) -> str:
    """Undo ccc's edit to the clone's top-level .gitignore; see the module docstring."""
    gi = repo / ".gitignore"
    if _is_link_or_junction(gi):
        return "kept"
    res = _git(repo, "ls-files", "-z", "--stage", "--", ".gitignore")
    if res is None or res[0] != 0:
        warnings.append("git ls-files failed for .gitignore; left it alone")
        return "kept"
    entries = [e for e in res[1].split(b"\0") if e]
    try:
        if not entries:  # untracked
            if not gi.exists():
                return "none"
            if not gi.is_file():
                return "kept"
            if not is_ccc_edit(None, gi.read_bytes()):
                return "kept"
            gi.unlink()
            return "deleted"
        if len(entries) != 1:  # conflict stages
            return "kept"
        meta = entries[0].split(b"\t", 1)[0].split(b" ")
        if len(meta) != 3:
            return "kept"
        mode, sha, stage = meta
        if stage != b"0" or mode not in (b"100644", b"100755"):
            return "kept"
        if not gi.is_file():  # a deleted tracked file is someone else's change
            return "kept"
        blob = _git(repo, "cat-file", "blob", sha.decode("ascii"))
        if blob is None or blob[0] != 0:
            warnings.append("git cat-file failed for .gitignore; left it alone")
            return "kept"
        worktree = gi.read_bytes()
    except OSError as e:
        warnings.append(f"could not read or delete {gi}: {e.strerror or e}")
        return "kept"
    if _norm(worktree) == _norm(blob[1]):
        return "none"  # unchanged, or line endings only: left alone
    if not is_ccc_edit(blob[1], worktree):
        return "kept"
    res = _git(repo, "checkout", "-q", "--", ".gitignore")
    if res is None or res[0] != 0:
        warnings.append("git checkout -- .gitignore failed; left it alone")
        return "kept"
    return "restored"


def workspace(repo_arg: str) -> dict:
    """The `workspace` subcommand; returns the output object."""
    out = {
        "mode": "workspace",
        "status": "skipped",
        "skip_reason": None,
        "repo": repo_arg,
        "exclude_path": None,
        "exclude_added": [],
        "gitignore_action": None,
        "warnings": [],
    }
    repo = Path(os.path.expanduser(repo_arg))
    if not repo.is_dir():
        out["skip_reason"] = "missing"
        return out
    ws = os.environ.get("SKF_WORKSPACE") or "~/.skf/workspace"
    repos_root = os.path.normcase(os.path.realpath(os.path.join(os.path.expanduser(ws), "repos")))
    real = os.path.normcase(os.path.realpath(repo))
    try:
        inside = os.path.commonpath([real, repos_root]) == repos_root and real != repos_root
    except ValueError:  # different drives on Windows
        inside = False
    if not inside:
        out["skip_reason"] = "not-a-workspace-clone"
        return out
    top = _git(repo, "rev-parse", "--show-toplevel")
    if top is None:
        out["skip_reason"] = "git-unavailable"
        return out
    if top[0] == -1:
        out["skip_reason"] = "git-failed"
        return out
    if top[0] != 0 or os.path.normcase(os.path.realpath(os.fsdecode(top[1].strip()))) != real:
        out["skip_reason"] = "not-a-clone-root"
        return out
    out["status"] = "ok"
    added = None
    gp = _git(repo, "rev-parse", "--git-path", "info/exclude")
    if gp is None or gp[0] != 0:
        out["warnings"].append("git rev-parse --git-path info/exclude failed")
    else:
        path = Path(os.fsdecode(gp[1].strip()))
        if not path.is_absolute():
            path = repo / path
        out["exclude_path"] = os.path.abspath(path)
        added = _ensure_excludes(path, out["warnings"])
    if added is None:
        out["gitignore_action"] = "kept"
        out["warnings"].append(
            ".gitignore left alone: restoring it without the exclude would show the index folder"
        )
        return out
    out["exclude_added"] = added
    out["gitignore_action"] = _repair_gitignore(repo, out["warnings"])
    return out


def _nested_notice(action: str, index_dir: str, tracked: int, reason: str = "") -> str | None:
    if action == "wrote" and tracked == 0:
        return (
            f"Wrote {index_dir}/.gitignore so git ignores the ccc index in that folder; "
            f"your own .gitignore files are unchanged."
        )
    if action == "wrote":
        return (
            f"Wrote {index_dir}/.gitignore so git ignores new ccc index files in that folder, "
            f"but git already tracks {tracked} of its files; to stop tracking them, run: "
            f"git rm -r --cached -- \"{index_dir}\""
        )
    if action == "exists":
        return (
            f"git lists files in {index_dir} as untracked, and the .gitignore already in that "
            f"folder does not ignore them; add a line holding only * to {index_dir}/.gitignore."
        )
    if action == "failed":
        return (
            f"Could not write {index_dir}/.gitignore ({reason}); git lists the ccc index in "
            f"that folder as untracked. Create that file holding the line * to keep it out of git."
        )
    return None


def nested(dir_arg: str, project_root: str) -> dict:
    """The `nested` subcommand; returns the output object."""
    index_dir = dir_arg.rstrip("/\\") + "/" + CCC_DIR
    out = {
        "mode": "nested",
        "status": "skipped",
        "skip_reason": None,
        "index_dir": index_dir,
        "action": None,
        "tracked_db_files": 0,
        "notice": None,
        "warnings": [],
    }
    d = Path(os.path.expanduser(dir_arg))
    if not d.is_dir():
        out["skip_reason"] = "missing"
        return out
    if _same_path(d, os.path.expanduser(project_root)):
        out["skip_reason"] = "project-root"
        return out
    idx = d / CCC_DIR
    if _is_link_or_junction(idx):
        out["skip_reason"] = "index-dir-is-link"
        return out
    if not (idx / "settings.yml").is_file():
        out["skip_reason"] = "no-ccc-project"
        return out
    listed = False
    for probe in INDEX_PROBES:  # one call per path: -q refuses several
        res = _git(d, "check-ignore", "-q", "--no-index", "--", probe)
        if res is None:
            out["skip_reason"] = "git-unavailable"
            return out
        if res[0] == 1:
            listed = True
        elif res[0] == 128:
            out["skip_reason"] = "not-a-work-tree"
            return out
        elif res[0] != 0:
            out["skip_reason"] = "git-failed"
            return out
    out["status"] = "ok"
    if not listed:
        out["action"] = "none"
        return out
    tracked = _git(d, "ls-files", "-z", "--", CCC_DIR)  # paths relative to d
    if tracked is not None and tracked[0] == 0:
        files = [os.fsdecode(f) for f in tracked[1].split(b"\0") if f]
        out["tracked_db_files"] = sum(1 for f in files if f not in NOT_DB_FILES)
    target = idx / ".gitignore"
    try:
        fd = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o644,
        )
    except FileExistsError:
        out["action"] = "exists"
        out["notice"] = _nested_notice("exists", index_dir, out["tracked_db_files"])
        return out
    except OSError as e:
        return _nested_failed(out, e.strerror or str(e))
    reason = None
    try:
        try:
            if os.write(fd, SELF_IGNORE) != len(SELF_IGNORE):
                reason = "short write"
        finally:
            os.close(fd)
    except OSError as e:
        reason = e.strerror or str(e)
    if reason is not None:
        # Remove the partial file this run created, so the next run writes it
        # again instead of reporting a foreign .gitignore.
        with contextlib.suppress(OSError):
            os.unlink(target)
        return _nested_failed(out, reason)
    out["action"] = "wrote"
    out["notice"] = _nested_notice("wrote", index_dir, out["tracked_db_files"])
    return out


def _nested_failed(out: dict, reason: str) -> dict:
    """Record a failed create or write of the self-ignoring file in `out`."""
    index_dir = out["index_dir"]
    out["action"] = "failed"
    out["warnings"].append(f"could not create {index_dir}/.gitignore: {reason}")
    out["notice"] = _nested_notice("failed", index_dir, 0, reason)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Keep ccc's index folders and SKF's workspace lock out of git.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    ws = sub.add_parser("workspace", help="repair and exclude in an SKF workspace clone")
    ws.add_argument("--repo", required=True, help="the workspace clone's top-level folder")
    ne = sub.add_parser("nested", help="make a nested ccc index folder ignore itself")
    ne.add_argument("--dir", required=True, help="the local source folder ccc indexed")
    ne.add_argument("--project-root", required=True, help="the SKF project root")
    args = parser.parse_args(argv)
    try:
        if args.command == "workspace":
            result = workspace(args.repo)
        else:
            result = nested(args.dir, args.project_root)
    except Exception as e:  # noqa: BLE001 — any failure means "did not run"
        print(json.dumps({"status": "error", "message": f"{type(e).__name__}: {e}"}), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
