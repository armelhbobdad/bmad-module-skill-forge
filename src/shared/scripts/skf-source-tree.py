# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Source Tree — read a remote skill's source at one commit.

A skill forged from a remote repository at Forge tier or above records, as
its `source_root`, the clone SKF keeps for that repository (the Compute
workspace path rule of create-skill's source-resolution-protocols.md:
`{SKF_WORKSPACE or ~/.skf/workspace}/repos/<host>/<owner...>/<repo>`). Every
SKF run on the repository shares that clone and leaves it at the commit it
needed, so update-skill never reads it as it stands. This helper gives each
update-skill run a private tree at one commit, moves the shared clone to
the commit the update recorded, and removes the tree at the end.

CLI:

  uv run skf-source-tree.py open --source-repo <repo> --source-root <path> \\
      --source-ref <ref> --pinned-commit <sha> [--target-ref <ref>] \\
      [--timeout <seconds>]
  uv run skf-source-tree.py advance --clone <path> --source-repo <repo> \\
      --target <sha> [--expect-commit <sha>] [--target-ref <ref>] \\
      [--tree <path>] [--hygiene-helper <path>] [--drift-helper <path>] \\
      [--lock-timeout <seconds>] [--timeout <seconds>]
  uv run skf-source-tree.py close --tree <path>

--tree (advance and close) takes the `tree` path open printed or the run
folder that holds it.

Time limit. open and advance finish within --timeout seconds (100 by
default, so a shell tool that stops commands after two minutes still gets
the JSON): every git call and sibling helper is cut to the time left, a
network call leaves the last 15 seconds to the local steps after it, a
local call leaves the last 5 to the final read of the clone's HEAD, and a
step that runs out of time reports `timed-out`. A call the limit stops is
stopped with everything it started (git's transport, a filter it runs):
on POSIX SIGTERM to its process group first, so git removes its lock
files, then SIGKILL; on Windows `taskkill /T /F`. Its output goes to
temporary files, never pipes, so a child that outlives it cannot hold the
helper past the limit.

open

  Takes a source only when --source-repo names a remote repository and
  --source-root is SKF's clone of it: the workspace path computed from
  --source-repo (compared as resolved paths, so a trailing slash or `~`
  does not matter), or a clone of the same repository under
  `repos/<host>/<owner...>/<repo>` of any SKF workspace folder, whatever
  the letter case of those folder names. The clone's `remote.origin.url`
  must name the same repository (read with `git config`, so `insteadOf`
  does not apply). Anything else is `skipped`.

  The target ref is --target-ref when given, else --source-ref; an empty,
  `null`, `none` or `HEAD` ref means the remote's default branch. `git
  ls-remote` names the commit the ref points to now: a tag wins over a
  branch of the same name, and an annotated tag resolves to its commit. A
  full 40-character commit is used as given. The helper then creates a
  private git repository in a run folder of its own, fetches that one
  commit into it (from the shared clone when the clone holds it, which
  only reads the clone, otherwise from the remote), checks it out and lists
  the files git changed between --pinned-commit and that commit.

  open never writes to the shared clone: it never fetches into it, checks
  it out, creates it, locks it or runs the hygiene helper there.

  When the remote cannot be reached or the commit cannot be fetched,
  --target-ref was not given and the clone holds --pinned-commit, the tree
  is built at the pinned commit instead (`offline`).

  Output (one ASCII line; every key is always present):
    status          "ready" | "offline" | "skipped" | "unavailable"
    skip_reason     null | "not-remote" | "not-workspace-clone"
    reason          null | "invalid-ref" | "git-unavailable" |
                    "upstream-unreachable" | "ref-not-found" |
                    "fetch-failed" | "checkout-failed" |
                    "tree-folder-failed" | "timed-out"  (OPEN_REASONS)
    message         one line for the user (offline and unavailable), else null
    tree            absolute path of this run's tree (ready, offline), else null
    clone           the workspace clone advance may update (SKF's clone of
                    --source-repo, present or missing); null when skipped or
                    when that folder is not SKF's clone
    target_ref      the ref compared ("HEAD" for the default branch)
    ref_kind        "tag" | "branch" | "head" | "commit" | "pinned" | null
    target_commit   40-hex commit the tree holds, else null
    moved           true | false | null (null without a pinned commit: an
                    empty, `local`, `null` or `none` --pinned-commit)
    diff_status     "ok" | "unavailable" | null (null unless ready or offline)
    changed_files   path of changed-files.json, else null
    changed_counts  {"added": n, "modified": n, "deleted": n}, else null
    warnings        list of strings

  Run folder: `skf-tree-<UTC stamp>-<8 characters>/` under
  `{SKF_WORKSPACE or ~/.skf/workspace}/trees/`, or under the system temp
  folder when that folder cannot be created. It holds:
    run.json            {tool, created, tree, source_repo, clone, target_commit}
    <repo>/             the tree: a private repository whose refs/skf/target
                        (and refs/skf/base) hold the commits it fetched
    changed-files.json  {"base": sha, "target": sha,
                         "files": [{"status": "A"|"M"|"D", "path": "a/b"}]}

  Every open first removes run folders an earlier run left behind whose
  name stamp is seven days old or more: only folders whose name matches,
  never a link, and on POSIX only folders the current user owns. Folder
  times are never used.

advance

  Moves the shared clone (--clone) to --target, the commit the update
  recorded, so test-skill and audit-skill read that commit there. It takes
  the clone's `.skf-workspace.lock`, the lock create-skill and audit-skill
  take (`fcntl.flock` on POSIX, the lock `flock -x` takes, and
  `msvcrt.locking` on Windows), waiting up to --lock-timeout seconds, and
  runs the hygiene helper inside it. It then does nothing when the clone
  already holds --target; otherwise it checks the clone out at --target
  only when the drift helper confirms the clone still holds --expect-commit
  and no tracked file has local changes, taking the commit from the tree
  --tree names before the remote. It never forces a checkout. A missing
  clone is cloned first, as create-skill does (clone first, lock after).

  refs/skf/advance, the ref a fetch into the clone writes, is always
  deleted again. When the time limit stops a fetch or the checkout in the
  clone and git has to be killed, so it cannot remove the lock file it
  held there (`shallow.lock`, `index.lock`), that file is removed; a
  checkout stopped part way reports `checkout-interrupted`, since the
  clone's files may then belong to both commits, and its warning gives
  the fetch and the forced checkout that finish it (the clone had no
  local changes when it began, and no ref keeps the commit there).

  Output (one ASCII line):
    status       "advanced" | "ok" | "skipped"
    skip_reason  null | "invalid-target" | "not-a-clone" | "clone-failed" |
                 "lock-busy" | "head-moved" | "head-unverified" |
                 "local-changes" | "target-missing" | "checkout-failed" |
                 "checkout-interrupted" | "timed-out"  (ADVANCE_SKIP_REASONS)
    head_sha     the clone's HEAD after the call, or null
    created      true when this call cloned the missing clone
    lock         "held" | "busy" | "unavailable" | "not-taken"
    hygiene      "ran" | "failed" | "skipped"
    log_message  one line
    warnings     list of strings

close

  Removes the run folder that holds the tree --tree names, or the run
  folder --tree names, only when its name matches the run-folder pattern,
  it is not a link, on POSIX the current user owns it, and its run.json
  names this tool and a tree inside it (the one --tree names, when --tree
  names a tree).

  Output (one ASCII line):
    {"status": "removed" | "missing" | "left" | "refused",
     "tree": <--tree>, "warnings": [...]}

Exit codes:
  0  open: ready, offline or skipped; advance and close: always once JSON
     is printed (they never gate)
  3  open: unavailable (JSON on stdout; the caller halts)
  1  unexpected error: {"status": "error", "message": ...} on stderr,
     nothing on stdout
  2  usage error (argparse)

git runs with the git location variables (GIT_DIR, GIT_INDEX_FILE, ...)
removed from its environment. A git hook or `git rebase --exec` exports
them (GIT_DIR too when run in a linked worktree); inherited by
`git -C <clone>`, they would make the helper read or write another
repository. git also runs with LC_ALL=C, no terminal prompt, no
credential-manager prompt and no hooks. It needs git 2.15 or newer.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

TOOL = "skf-source-tree"
TREE_PREFIX = "skf-tree-"
TREE_NAME_RE = re.compile(r"^skf-tree-(\d{8}T\d{6}Z)-[a-z0-9_]{8}$")
RUN_FILE = "run.json"
CHANGED_FILE = "changed-files.json"
LOCK_NAME = ".skf-workspace.lock"
ADVANCE_REF = "refs/skf/advance"
STALE_TREE_DAYS = 7
LOCK_WAIT_SEC = 60.0
LOCK_POLL_SEC = 0.25
LOCAL_TIMEOUT_SEC = 60
LS_REMOTE_TIMEOUT_SEC = 120
NETWORK_TIMEOUT_SEC = 600  # also used for checkout and clone
SIBLING_TIMEOUT_SEC = 120
# open and advance finish within --timeout seconds; a network call leaves
# the last NETWORK_RESERVE_SEC of it to the local steps that follow, and a
# local call the last FINAL_READ_SEC to the unlimited final reads.
DEFAULT_TIMEOUT_SEC = 100.0
NETWORK_RESERVE_SEC = 15.0
FINAL_READ_SEC = 5.0
KILL_WAIT_SEC = 2.0  # each wait after the time limit stops a call: SIGTERM or taskkill, then the child
OPEN_REASONS = ("invalid-ref", "git-unavailable", "upstream-unreachable", "ref-not-found",
                "fetch-failed", "checkout-failed", "tree-folder-failed", "timed-out")
ADVANCE_SKIP_REASONS = ("invalid-target", "not-a-clone", "clone-failed", "lock-busy", "head-moved",
                        "head-unverified", "local-changes", "target-missing", "checkout-failed",
                        "checkout-interrupted", "timed-out")
# The failures a call cut short by the time limit can cause: by a network
# call (cut NETWORK_RESERVE_SEC early) or by a local one.
_OPEN_NETWORK_LATE = ("upstream-unreachable", "fetch-failed")
_OPEN_LOCAL_LATE = ("invalid-ref", "checkout-failed")
_ADVANCE_NETWORK_LATE = ("clone-failed", "target-missing")
_ADVANCE_LOCAL_LATE = ("not-a-clone", "lock-busy", "head-unverified", "local-changes", "checkout-failed")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
# No leading `-`; a scoped `@scope/pkg@1.0.0` tag is allowed.
REF_RE = re.compile(r"^[A-Za-z0-9_@][A-Za-z0-9._/+@-]*$")
HEAD_ALIASES = {"", "null", "none", "head"}
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
# Every git call that writes a checkout (checkout, clone) passes these.
CHECKOUT_OPTS = ("-c", "core.longpaths=true", "-c", "advice.detachedHead=false")

_URL_RE = re.compile(
    r"^(?:https?|ssh|git)://(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?/(?P<path>.+?)/?$",
    re.IGNORECASE,
)
_SCP_RE = re.compile(r"^(?:[^@/:]+@)?(?P<host>[^/:]{2,}):(?P<path>[^/].*?)/?$")
_SHORTHAND_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
# Characters that stop a host, owner or repository name from naming one
# folder: Windows reads `\` as a separator and `C:` as a drive.
_NOT_A_NAME_RE = re.compile(r"[\\:\x00-\x1f\x7f]")

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


# --------------------------------------------------------------------------
# Pinned copies
# --------------------------------------------------------------------------


# Keep identical to _is_link_or_junction in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
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


# Keep identical to _acquire_lock in skf-atomic-write.py
# (test/test-skf-source-tree.py pins the copy).
def _acquire_lock(fd: int) -> None:
    """Acquire an exclusive non-blocking lock on fd (auto-released on close/exit)."""
    if os.name == "nt":
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EACCES, errno.EDEADLK):
                raise OSError(errno.EAGAIN, "lock held") from e
            raise
    else:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EACCES):
                raise OSError(errno.EAGAIN, "lock held") from e
            raise


# Keep identical to _release_lock in skf-atomic-write.py
# (test/test-skf-source-tree.py pins the copy).
def _release_lock(fd: int) -> None:
    if os.name == "nt":
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


# Keep identical to _same_path in skf-ccc-git-hygiene.py
# (test/test-skf-source-tree.py pins the copy).
def _same_path(a: str | Path, b: str | Path) -> bool:
    """Path identity that covers Windows case and 8.3 names, forward-slash
    git output and macOS /private."""
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _resolve_outside_cwd(command: str) -> str | None:
    """shutil.which with a CWD-shim guard. Returns the resolved path or None.

    shutil.which on Windows searches the current directory ahead of PATH,
    and CWD here may be a repository SKF does not control — a bare-name
    lookup resolving into CWD would execute a planted shim (e.g. git.exe).
    Such a resolution is treated as not-found. Explicit paths supplied by
    callers (containing a separator) are honored as-is. Keep the code
    identical to the sibling guards in skf-merge-ccc-exclusions.py,
    skf-detect-tools.py, skf-qmd-classify-collections.py,
    skf-ccc-git-hygiene.py, skf-tessl-review.py and
    skf-verify-provenance-completeness.py
    (test/test-skf-source-tree.py pins it against
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


# Keep identical to is_skippable_pinned in skf-check-workspace-drift.py
# (test/test-skf-source-tree.py pins the copy).
def is_skippable_pinned(pinned_commit: str) -> bool:
    """Recognize the scalar values that mean 'no pinned commit'."""
    if pinned_commit is None:
        return True
    stripped = pinned_commit.strip()
    return stripped == "" or stripped.lower() == "local"


# Keep identical to classify_match in skf-check-workspace-drift.py
# (test/test-skf-source-tree.py pins the copy).
def classify_match(pinned: str, head: str) -> str | None:
    """Return 'full' if pinned == head, 'short-prefix' if pinned is a prefix
    of head (≥ 7 chars to avoid coincidental collisions on short SHAs).
    Returns None on no match."""
    if pinned == head:
        return "full"
    if len(pinned) >= 7 and head.startswith(pinned):
        return "short-prefix"
    return None


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------


def _child_env() -> dict:
    """os.environ without the git location variables, and with no prompts."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}
    env["LC_ALL"] = "C"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    return env


_deadline: float | None = None


def _start_clock(seconds: float | None) -> None:
    """Start the time limit of this open or advance (None: no limit)."""
    global _deadline
    _deadline = None if seconds is None else time.monotonic() + max(0.0, seconds)


def _cap(timeout: float, network: bool = False) -> float | None:
    """timeout cut to the time the limit leaves; None when none is left.

    A network call leaves the last NETWORK_RESERVE_SEC to the local steps,
    a local call the last FINAL_READ_SEC to the final reads.
    """
    if _deadline is None:
        return timeout
    left = _deadline - time.monotonic() - (NETWORK_RESERVE_SEC if network else FINAL_READ_SEC)
    return min(timeout, left) if left > 0 else None


def _expired() -> bool:
    """True once no network call may start: the time limit is (nearly) spent."""
    return _cap(1.0, network=True) is None


def _out_of_time() -> bool:
    """True once no call at all may start."""
    return _cap(1.0) is None


def _late(reason: str | None, network_reasons: tuple, local_reasons: tuple) -> bool:
    """True when the time limit, not the reason itself, explains a failure."""
    return (reason in network_reasons and _expired()) or (reason in local_reasons and _out_of_time())


def _stop(proc: subprocess.Popen, windows: bool = os.name == "nt") -> bool:
    """Stop proc and everything it started once the time limit runs out.

    POSIX sends SIGTERM to its process group first, so git removes its lock
    files, then SIGKILL to whatever is left; Windows runs taskkill /T /F.
    Returns True when proc itself had to be killed (taskkill /F, or SIGKILL
    once SIGTERM had not ended it) and has ended: the lock files it held
    stay behind. False when SIGTERM ended it, or when it has not ended.
    """
    killed = windows
    try:
        if windows:
            taskkill = _resolve_outside_cwd("taskkill")
            if taskkill:
                subprocess.run([taskkill, "/F", "/T", "/PID", str(proc.pid)], stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=KILL_WAIT_SEC, check=False)
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=KILL_WAIT_SEC)
                ended = True
            except subprocess.TimeoutExpired:
                ended = False
            os.killpg(proc.pid, signal.SIGKILL)
            killed = not ended
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    try:
        proc.wait(timeout=KILL_WAIT_SEC)
    except subprocess.TimeoutExpired:
        return False
    return killed


def _run(argv: list[str], timeout: float | None) -> tuple[int | None, bytes, bytes, bool]:
    """Run argv with no stdin and _child_env(); (returncode, stdout, stderr, killed).

    returncode is None when the time limit stopped the call, and killed is
    True when it then had to be killed (see _stop). Output goes to
    temporary files, not pipes: on Windows a child git starts (ssh, the
    https transport) inherits the pipes and keeps them open after git is
    stopped, and reading a pipe to its end would wait for it. The call gets
    a process group (a POSIX session) of its own, so _stop reaches all it
    started. Raises OSError or ValueError when argv cannot start.
    """
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out_f, stderr=err_f, env=_child_env(),
                                **kwargs)
        killed = False
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            killed = _stop(proc)
            returncode = None
        out_f.seek(0)
        err_f.seek(0)
        return returncode, out_f.read(), err_f.read(), killed


# _git's returncode for a call the time limit stopped once it had started:
# STOPPED when SIGTERM ended it, so git removed its lock files itself, and
# KILLED when it had to be killed (see _stop), so they stay behind.
STOPPED = -2
KILLED = -3


def _git(cwd: str | Path, *args: str, timeout: float = LOCAL_TIMEOUT_SEC, network: bool = False,
         limited: bool = True) -> tuple[int, bytes, str] | None:
    """Run `git -C <cwd> <args>` with no hooks and the git location variables removed.

    Returns None when git cannot be found (or only as a shim in CWD) or
    cannot start, (-1, b"", "timeout") when the time limit leaves no time
    to start the call (`limited`; see _cap), (STOPPED or KILLED, stdout
    bytes, "timeout") when the limit stopped it, and otherwise (returncode,
    stdout bytes, stderr text). stdout is not stripped: the `-z` outputs
    need the raw bytes.
    """
    exe = _resolve_outside_cwd("git")
    if exe is None:
        return None
    if limited:
        timeout = _cap(timeout, network)
        if timeout is None:
            return -1, b"", "timeout"
    else:
        timeout = min(timeout, FINAL_READ_SEC)
    try:
        returncode, stdout, stderr, killed = _run([exe, "-c", f"core.hooksPath={os.devnull}", "-C", str(cwd),
                                                   *args], timeout)
    except (OSError, ValueError):
        return None
    if returncode is None:
        return (KILLED if killed else STOPPED), stdout, "timeout"
    return returncode, stdout, stderr.decode("utf-8", errors="replace")


def _ok(res: tuple[int, bytes, str] | None) -> bool:
    return res is not None and res[0] == 0


def _out(res: tuple[int, bytes, str] | None) -> str:
    """The first stdout line of a successful call, else ""."""
    if not _ok(res):
        return ""
    lines = res[1].decode("utf-8", errors="replace").strip().splitlines()
    return lines[0].strip() if lines else ""


def _last_error(stderr: str | None) -> str:
    """The last `fatal:`/`error:` line of git's stderr, else its last line."""
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith(("fatal:", "error:")):
            return line
    return lines[-1] if lines else "git failed"


def _err(res: tuple[int, bytes, str] | None) -> str:
    if res is None:
        return "git could not run"
    return _last_error(res[2])


def _rev(cwd: str | Path, rev: str, limited: bool = True) -> str | None:
    """The full commit `rev` names in the repository at cwd, else None."""
    sha = _out(_git(cwd, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", limited=limited))
    return sha if SHA40_RE.match(sha) else None


# --------------------------------------------------------------------------
# Which sources this helper takes
# --------------------------------------------------------------------------


def _one_name(part: str) -> bool:
    """True when part names one folder inside its parent on every platform.

    Not `\\`, `:` or a control character, and not only dots and spaces:
    Windows drops a name's trailing dots and spaces, so `.. ` is `..` there.
    """
    return bool(part.rstrip(". ")) and not _NOT_A_NAME_RE.search(part)


def parse_remote(value: str | None) -> tuple[str, tuple[str, ...], str] | None:
    """(host, owner_parts, repo) for a remote repository, else None.

    Accepts https/http/ssh/git URLs, scp-like `user@host:owner/repo` and the
    `owner/repo` shorthand (github.com; only when no such local path
    exists). A local path, `file:` URL or `<transport>::` address is None,
    and so is a host, owner or repository part that is not one folder name
    (see _one_name): SKF's clone and this run's tree are folders named
    after them.
    """
    if not value:
        return None
    value = value.strip()
    if (
        not value
        or value.startswith(("-", "/", "./", "../", "~"))
        or value.lower().startswith("file:")
        or "::" in value
        or _DRIVE_RE.match(value)
    ):
        return None
    m = _URL_RE.match(value)
    if m:
        host, path = m.group("host"), m.group("path")
    else:
        m = _SCP_RE.match(value)
        if m:
            host, path = m.group("host"), m.group("path")
        elif _SHORTHAND_RE.match(value) and not os.path.exists(value):
            host, path = "github.com", value
        else:
            return None
    parts = path.split("/")
    if parts and parts[-1].endswith(".git"):
        parts[-1] = parts[-1][: -len(".git")]
    if len(parts) < 2 or not all(_one_name(part) for part in (host, *parts)):
        return None
    return host.lower(), tuple(parts[:-1]), parts[-1]


def _key(parsed: tuple[str, tuple[str, ...], str]) -> tuple:
    host, owner, repo = parsed
    return host.casefold(), tuple(part.casefold() for part in owner), repo.casefold()


def _url(source_repo: str, parsed: tuple[str, tuple[str, ...], str]) -> str:
    """The URL git reads: source_repo itself, or https for the shorthand."""
    value = source_repo.strip()
    if "://" in value or (_SCP_RE.match(value) and not _SHORTHAND_RE.match(value)):
        return value
    host, owner, repo = parsed
    return f"https://{host}/{'/'.join(owner)}/{repo}"


def workspace_root() -> Path:
    return Path(os.path.expanduser(os.environ.get("SKF_WORKSPACE") or "~/.skf/workspace"))


def clone_path(parsed: tuple[str, tuple[str, ...], str]) -> Path:
    host, owner, repo = parsed
    return workspace_root().joinpath("repos", host, *owner, repo)


def _stays_inside(parsed: tuple[str, tuple[str, ...], str]) -> bool:
    """A second guard behind parse_remote: SKF's clone path for parsed lies
    inside `repos/` of the workspace, and the repository name, which names
    this run's tree inside its run folder, is one folder name."""
    repos = os.path.normcase(os.path.abspath(workspace_root() / "repos"))
    clone = os.path.normcase(os.path.abspath(clone_path(parsed)))
    try:
        inside = clone != repos and os.path.commonpath([repos, clone]) == repos
    except ValueError:  # another drive
        return False
    repo = parsed[2]
    return inside and repo not in (".", "..") and os.path.dirname(os.path.join("run", repo)) == "run"


def _stat_dir(p: str | Path) -> bool | None:
    """True for a folder, False when nothing is there, None when unreadable.

    os.stat, not pathlib: from Python 3.14 pathlib answers False inside a
    folder it cannot search instead of raising.
    """
    try:
        st = os.stat(p)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return None
    return stat.S_ISDIR(st.st_mode)


def _clone_matches(path: str | Path, parsed: tuple[str, tuple[str, ...], str]) -> bool:
    """True when path is the top of a clone whose origin is the same repository."""
    top = _out(_git(path, "rev-parse", "--show-toplevel"))
    if not top or not _same_path(top, path):
        return False
    origin = parse_remote(_out(_git(path, "config", "--get", "remote.origin.url")))
    return origin is not None and _key(origin) == _key(parsed)


def classify(source_repo: str, source_root: str) -> dict:
    """Decide whether source_root is SKF's clone of source_repo."""
    out = {"parsed": None, "clone": None, "usable": False, "skip_reason": None, "warnings": []}
    parsed = parse_remote(source_repo)
    if parsed is None or not _stays_inside(parsed):
        out["skip_reason"] = "not-remote"
        return out
    out["parsed"] = parsed
    root = os.path.expanduser(source_root.strip()) if source_root else ""
    if not root:
        out["skip_reason"] = "not-workspace-clone"
        return out
    workspace_clone = clone_path(parsed)
    if _same_path(root, workspace_clone):
        state = _stat_dir(workspace_clone)
        if state is False:
            out["clone"] = str(workspace_clone)
        elif state is True and _clone_matches(workspace_clone, parsed):
            out["clone"] = str(workspace_clone)
            out["usable"] = True
        else:
            out["warnings"].append(
                f"{workspace_clone} is not SKF's clone of {source_repo}; "
                "this run reads a fresh copy and leaves that folder alone"
            )
        return out
    host, owner, repo = parsed
    # Letter case never matters here: create-skill copies the host as the
    # URL spells it, and _clone_matches checks the origin.
    tail = tuple(p.casefold() for p in ("repos", host, *owner, repo))
    parts = Path(os.path.abspath(root)).parts
    if (
        _stat_dir(root) is True
        and len(parts) >= len(tail)
        and tuple(p.casefold() for p in parts[-len(tail):]) == tail
        and _clone_matches(root, parsed)
    ):
        out["clone"] = root
        out["usable"] = True
        return out
    out["skip_reason"] = "not-workspace-clone"
    return out


# --------------------------------------------------------------------------
# Refs
# --------------------------------------------------------------------------


def _ref_ok(ref: str) -> bool:
    if not REF_RE.fullmatch(ref) or ref == "@":
        return False
    return _ok(_git(tempfile.gettempdir(), "check-ref-format", "--allow-onelevel", f"refs/tags/{ref}"))


def resolve_ref(url: str, ref: str) -> tuple[str, str | None, str | None, str | None, str | None]:
    """(state, kind, sha, remote_ref, error) for ref on the remote at url.

    state is "ok", "ref-not-found" or "unreachable" (error then holds git's
    last error line). A full commit needs no network.
    """
    if SHA40_RE.match(ref):
        return "ok", "commit", ref, ref, None
    if ref == "HEAD":
        patterns = ["HEAD"]
    else:
        patterns = [f"refs/tags/{ref}", f"refs/tags/{ref}^{{}}", f"refs/heads/{ref}"]
    res = _git(tempfile.gettempdir(), "ls-remote", "--", url, *patterns, timeout=LS_REMOTE_TIMEOUT_SEC,
               network=True)
    if not _ok(res):
        return "unreachable", None, None, None, _err(res)
    refs = {}
    for line in res[1].decode("utf-8", errors="replace").splitlines():
        sha, _, name = line.partition("\t")
        if SHA40_RE.match(sha.strip()) and name.strip():
            refs[name.strip()] = sha.strip()
    for name, kind, remote_ref in (
        (f"refs/tags/{ref}^{{}}", "tag", f"refs/tags/{ref}"),
        (f"refs/tags/{ref}", "tag", f"refs/tags/{ref}"),
        (f"refs/heads/{ref}", "branch", f"refs/heads/{ref}"),
        ("HEAD", "head", "HEAD"),
    ):
        if name in refs and (ref == "HEAD") == (name == "HEAD"):
            return "ok", kind, refs[name], remote_ref, None
    return "ref-not-found", None, None, None, None


# --------------------------------------------------------------------------
# Run folders
# --------------------------------------------------------------------------


def _on_rm_error(func, path, _exc) -> None:
    """Make a read-only entry writable (Windows git pack files), then retry.

    A link is never chmod-ed: that would change the file it points to.
    """
    try:
        if not os.path.islink(path):
            os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _long_path(path: str) -> str:
    """The extended-length form of an absolute Windows path (`\\\\?\\C:\\...`,
    `\\\\?\\UNC\\server\\...`), which Windows accepts past MAX_PATH (260
    characters) even where long paths are not enabled."""
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def _rmtree(path: str | Path, windows: bool = os.name == "nt") -> bool:
    """Remove a folder tree; True when nothing is left at path.

    On Windows through the extended-length path: the checkout passes
    core.longpaths, so git writes files past MAX_PATH that a plain path
    can neither list nor remove.
    """
    target = _long_path(os.path.abspath(path)) if windows else path
    if sys.version_info >= (3, 12):
        shutil.rmtree(target, onexc=_on_rm_error)
    else:
        shutil.rmtree(target, onerror=_on_rm_error)
    return not os.path.lexists(path)


def _tree_roots() -> list[Path]:
    return [workspace_root() / "trees", Path(tempfile.gettempdir())]


def sweep(warnings: list[str]) -> None:
    """Remove run folders whose name stamp is STALE_TREE_DAYS old or more."""
    now = datetime.now(timezone.utc)
    for root in _tree_roots():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            m = TREE_NAME_RE.match(name)
            if not m:
                continue
            try:
                stamp = datetime.strptime(m.group(1), STAMP_FORMAT).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if now - stamp < timedelta(days=STALE_TREE_DAYS):
                continue  # recent, or stamped in the future
            path = root / name
            if _is_link_or_junction(path):
                continue
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if not stat.S_ISDIR(st.st_mode):
                continue
            if os.name != "nt" and st.st_uid != os.getuid():
                continue
            if not _rmtree(path):
                warnings.append(f"could not remove {path}")


def _new_run_dir(warnings: list[str]) -> Path | None:
    prefix = f"{TREE_PREFIX}{datetime.now(timezone.utc).strftime(STAMP_FORMAT)}-"
    trees = workspace_root() / "trees"
    try:
        os.makedirs(trees, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=prefix, dir=trees))
    except OSError:
        warnings.append(f"could not create a tree folder under {trees}; using the system temp folder")
    try:
        return Path(tempfile.mkdtemp(prefix=prefix, dir=tempfile.gettempdir()))
    except OSError:
        return None


def _write_json(path: str | Path, obj: dict) -> None:
    # O_BINARY (Windows only; 0 elsewhere) suppresses the text-mode \n -> \r\n
    # translation that would otherwise corrupt verbatim writes on Windows.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    try:
        os.write(fd, json.dumps(obj).encode("utf-8"))
    finally:
        os.close(fd)


def _read_record(run: Path) -> dict | None:
    """run.json of run folder `run` when it names this tool and a tree inside the folder, else None."""
    try:
        with open(run / RUN_FILE, encoding="utf-8") as fh:
            record = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("tool") != TOOL or not isinstance(record.get("tree"), str):
        return None
    if not _same_path(Path(record["tree"]).parent, run):
        return None
    return record


def _locate_run(given: Path) -> tuple[Path, Path | None]:
    """(run folder, tree) for a --tree value: the tree open printed, or its run folder (tree None).

    An agent may bind the run folder, where changed-files.json sits, rather
    than the tree: a folder named like a run folder that holds run.json (or
    is gone) is taken as one.
    """
    if TREE_NAME_RE.match(given.name) and (not os.path.lexists(given) or os.path.isfile(given / RUN_FILE)):
        return given, None
    return given.parent, given


def _seed(tree: Path, sha: str, name: str, clone: str | None, usable: bool, url: str,
          remote_ref: str | None) -> bool:
    """Fetch one commit into refs/skf/<name> of the tree.

    From the shared clone when it holds the commit (a local fetch only reads
    the clone), otherwise from the remote. True when the ref names a commit.
    """
    dest = f"refs/skf/{name}"
    if usable and clone and sha and _ok(_git(clone, "cat-file", "-e", f"{sha}^{{commit}}")):
        _git(tree, "fetch", "--quiet", "--no-tags", "--depth", "1", "--", str(clone), f"+{sha}:{dest}")
        if _rev(tree, dest):
            return True
    if remote_ref:
        _git(tree, "fetch", "--quiet", "--no-tags", "--depth", "1", "--", url, f"+{remote_ref}:{dest}",
             timeout=NETWORK_TIMEOUT_SEC, network=True)
    return _rev(tree, dest) is not None


# --------------------------------------------------------------------------
# open
# --------------------------------------------------------------------------


def _unavailable(out: dict, reason: str, message: str) -> tuple[int, dict]:
    out.update(status="unavailable", reason=reason, message=message, tree=None,
               target_commit=None, moved=None, diff_status=None, changed_files=None,
               changed_counts=None)
    return 3, out


def _diff(tree: Path, base: str, target: str) -> list[dict] | None:
    if base == target:
        return []
    res = _git(tree, "diff", "--name-status", "-z", "--no-renames", base, target)
    if not _ok(res):
        return None
    fields = res[1].split(b"\0")
    files = []
    for i in range(0, len(fields) - 1, 2):
        status_letter = fields[i].decode("ascii", errors="replace")[:1]
        path = fields[i + 1].decode("utf-8", errors="surrogateescape")
        status_letter = "M" if status_letter == "T" else status_letter
        if status_letter in ("A", "M", "D") and path:
            files.append({"status": status_letter, "path": path})
    return sorted(files, key=lambda f: f["path"])


def open_tree(args: argparse.Namespace) -> tuple[int, dict]:
    out = {
        "status": None, "skip_reason": None, "reason": None, "message": None, "tree": None,
        "clone": None, "target_ref": None, "ref_kind": None, "target_commit": None,
        "moved": None, "diff_status": None, "changed_files": None, "changed_counts": None,
        "warnings": [],
    }
    _start_clock(args.timeout)
    source_repo = args.source_repo.strip()
    ref = (args.target_ref or args.source_ref or "").strip()
    if ref.lower() in HEAD_ALIASES:
        ref = "HEAD"
    elif re.fullmatch(r"[0-9A-Fa-f]{40}", ref):
        ref = ref.lower()

    def _unavailable_or_late(reason: str, message: str) -> tuple[int, dict]:
        if _late(reason, _OPEN_NETWORK_LATE, _OPEN_LOCAL_LATE):
            reason = "timed-out"
            message = (f"Reading {ref} of {source_repo} did not finish within the "
                       f"{args.timeout:g}-second time limit; a first fetch of a large repository is slow")
        return _unavailable(out, reason, message)

    found = classify(source_repo, args.source_root)
    out["warnings"].extend(found["warnings"])
    if found["skip_reason"]:
        if found["parsed"] is not None and _out_of_time():
            # The clone checks were cut short: never read the folder as it stands.
            out["target_ref"] = ref
            return _unavailable_or_late("upstream-unreachable", "")
        out.update(status="skipped", skip_reason=found["skip_reason"])
        return 0, out
    parsed, clone, usable = found["parsed"], found["clone"], found["usable"]
    out["clone"] = clone
    out["target_ref"] = ref
    if _resolve_outside_cwd("git") is None:
        return _unavailable(out, "git-unavailable",
                            f"git is not installed; update-skill needs it to read {source_repo}")
    if ref != "HEAD" and not SHA40_RE.match(ref) and not _ref_ok(ref):
        return _unavailable_or_late("invalid-ref", f"{ref} is not a valid tag or branch name")

    sweep(out["warnings"])

    # `null` and `none` are a JSON null written out, as for --source-ref.
    pinned = (args.pinned_commit or "").strip().lower()
    pin = "" if is_skippable_pinned(pinned) or pinned in ("null", "none") else pinned
    pin_full, pin_local = None, False
    if pin and usable:
        pin_full = _rev(clone, pin)
        pin_local = pin_full is not None
    if pin_full is None and SHA40_RE.match(pin):
        pin_full = pin

    url = _url(source_repo, parsed)
    state, kind, sha, remote_ref, error = resolve_ref(url, ref)
    offline_message = None
    if state == "ref-not-found":
        return _unavailable(out, "ref-not-found",
                            f"{ref} is neither a tag nor a branch of {source_repo}; "
                            "pass the ref to use with --target-ref")
    if state == "unreachable":
        if args.target_ref:
            return _unavailable_or_late("upstream-unreachable",
                                        f"Could not reach {source_repo} ({error}), so {ref} could not be read")
        if not pin_local:
            pinned = pin[:12] or "(none recorded)"
            return _unavailable_or_late("upstream-unreachable",
                                        f"Could not reach {source_repo} ({error}), and no local copy of the "
                                        f"pinned commit {pinned} exists")
        sha, kind, remote_ref = pin_full, "pinned", None
        offline_message = (f"Could not reach {source_repo} ({error}); read the pinned commit "
                           f"{pin_full[:12]} from the local copy, so upstream changes were not checked")

    repo = parsed[2]
    while True:
        run = _new_run_dir(out["warnings"])
        if run is None:
            return _unavailable(out, "tree-folder-failed",
                                "Could not create a folder for this run's source tree in the SKF "
                                "workspace or the system temp folder")
        tree = run / repo
        created = datetime.now(timezone.utc).strftime(STAMP_FORMAT)
        record = {"tool": TOOL, "created": created, "tree": str(tree), "source_repo": source_repo,
                  "clone": clone}
        _write_json(run / RUN_FILE, record)
        init = _git(run, "init", "--quiet", "--template=", repo)
        if _ok(init) and _seed(tree, sha, "target", clone, usable, url, remote_ref):
            break
        fetch_error = _err(init) if not _ok(init) else "the commit could not be fetched"
        _rmtree(run)
        if offline_message is None and not args.target_ref and pin_local:
            sha, kind, remote_ref = pin_full, "pinned", None
            offline_message = (f"Could not fetch {ref} from {source_repo}; read the pinned commit "
                               f"{pin_full[:12]} from the local copy, so upstream changes were not checked")
            continue
        return _unavailable_or_late("fetch-failed", f"Could not fetch {ref} from {source_repo}: {fetch_error}")

    target_commit = _rev(tree, "refs/skf/target")
    checkout = _git(tree, *CHECKOUT_OPTS, "checkout", "--quiet", "--detach", target_commit or "",
                    timeout=NETWORK_TIMEOUT_SEC)
    if not target_commit or not _ok(checkout) or _rev(tree, "HEAD") != target_commit:
        _rmtree(run)
        return _unavailable_or_late("checkout-failed",
                                    f"Could not check out {ref} of {source_repo}: {_err(checkout)}")

    moved = None if not pin else classify_match(pin, target_commit) is None
    base = None
    if moved is False:
        base = target_commit
    elif pin_full and _seed(tree, pin_full, "base", clone, usable, url,
                            pin_full if SHA40_RE.match(pin_full) else None):
        base = _rev(tree, "refs/skf/base")

    files = _diff(tree, base, target_commit) if base else None
    if files is None:
        if pin_full and _expired():
            out["warnings"].append(f"the list of files changed since {pin_full[:12]} was not built within "
                                   f"the {args.timeout:g}-second time limit")
        out.update(diff_status="unavailable", changed_files=None, changed_counts=None)
    else:
        _write_json(run / CHANGED_FILE, {"base": base, "target": target_commit, "files": files})
        counts = {"added": 0, "modified": 0, "deleted": 0}
        for entry in files:
            counts[{"A": "added", "M": "modified", "D": "deleted"}[entry["status"]]] += 1
        out.update(diff_status="ok", changed_files=str(run / CHANGED_FILE), changed_counts=counts)

    record["target_commit"] = target_commit
    _write_json(run / RUN_FILE, record)
    out.update(status="offline" if offline_message else "ready", message=offline_message,
               tree=str(tree), ref_kind=kind, target_commit=target_commit, moved=moved)
    return 0, out


# --------------------------------------------------------------------------
# advance
# --------------------------------------------------------------------------


def _run_sibling(helper: str, *args: str) -> tuple[int, str] | None:
    """Run a sibling SKF helper with this interpreter; None when it cannot run."""
    timeout = _cap(SIBLING_TIMEOUT_SEC)
    if timeout is None:
        return None
    try:
        returncode, stdout, _stderr, _killed = _run([sys.executable, helper, *args], timeout)
    except (OSError, ValueError):
        return None
    if returncode is None:
        return None
    return returncode, stdout.decode("utf-8", errors="replace")


def _clear_lock(clone: Path, res: tuple[int, bytes, str] | None, name: str, warnings: list[str]) -> None:
    """Remove the lock file `name` a git call the time limit killed left in clone's .git.

    Only after KILLED: git held that lock while it ran (it fails at once
    when the lock exists), taskkill /F or SIGKILL kept it from removing
    it, and no other git can take it while the file is there. After
    STOPPED, SIGTERM let git remove it itself, so a lock of that name is
    another git's by then.
    """
    if res is None or res[0] != KILLED:
        return
    lock = clone / ".git" / name
    try:
        if stat.S_ISREG(os.lstat(lock).st_mode):
            os.remove(lock)
    except (FileNotFoundError, NotADirectoryError):
        pass
    except OSError as e:
        warnings.append(f"could not remove {lock} ({e}); remove it once no git command runs in {clone}")


def _helper_file(path: str) -> str | None:
    if not path:
        return None
    expanded = os.path.expanduser(path)
    try:
        return expanded if stat.S_ISREG(os.stat(expanded).st_mode) else None
    except OSError:
        return None


def advance(args: argparse.Namespace) -> dict:
    _start_clock(args.timeout)
    out = {"status": "skipped", "skip_reason": None, "head_sha": None, "created": False,
           "lock": "not-taken", "hygiene": "skipped", "log_message": "", "warnings": []}
    target = args.target.strip().lower()
    clone = Path(os.path.expanduser(args.clone.strip())) if args.clone.strip() else None

    def finish(status: str, reason: str | None = None) -> dict:
        if _late(reason, _ADVANCE_NETWORK_LATE, _ADVANCE_LOCAL_LATE):
            reason = "timed-out"
        if reason == "timed-out":
            out["warnings"].append(f"the {args.timeout:g}-second time limit ran out before the clone was moved")
        head = _rev(clone, "HEAD", limited=False) if clone is not None and _stat_dir(clone) is True else None
        out.update(status=status, skip_reason=reason, head_sha=head)
        short = head[:7] if head else "no commit"
        if status == "advanced":
            out["log_message"] = f"source_tree_advance: advanced {out.pop('_old', 'none')} -> {short}"
        elif status == "ok":
            out["log_message"] = f"source_tree_advance: ok ({short})"
        else:
            out["log_message"] = f"source_tree_advance: skipped ({reason}) at {short}"
        out.pop("_old", None)
        return out

    if not SHA40_RE.match(target):
        return finish("skipped", "invalid-target")
    parsed = parse_remote(args.source_repo)
    if parsed is None or clone is None or not _stays_inside(parsed):
        return finish("skipped", "not-a-clone")
    url = _url(args.source_repo, parsed)

    state = _stat_dir(clone)
    clone_head = None
    if state is False:
        target_ref = (args.target_ref or "").strip()
        branch = []
        if target_ref.lower() not in HEAD_ALIASES and not SHA40_RE.match(target_ref.lower()):
            branch = [f"--branch={target_ref}"]
        try:
            os.makedirs(clone.parent, exist_ok=True)
            res = _git(clone.parent, *CHECKOUT_OPTS, "clone", "--quiet", "--depth", "1", *branch, "--",
                       url, str(clone), timeout=NETWORK_TIMEOUT_SEC, network=True)
        except OSError as e:
            res = (1, b"", f"error: {e}")
        if not _ok(res):
            if os.path.lexists(clone):
                _rmtree(clone)
            out["warnings"].append(_err(res))
            return finish("skipped", "clone-failed")
        out["created"] = True
        clone_head = _rev(clone, "HEAD")
    elif state is None or not _clone_matches(clone, parsed):
        return finish("skipped", "not-a-clone")

    fd = None
    try:
        try:
            # O_BINARY (Windows only; 0 elsewhere) suppresses the text-mode \n -> \r\n
            # translation; the lock file is never written, only locked.
            fd = os.open(clone / LOCK_NAME, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
            deadline = time.monotonic() + (_cap(max(0.0, args.lock_timeout)) or 0.0)
            while True:
                try:
                    _acquire_lock(fd)
                    out["lock"] = "held"
                    break
                except OSError as e:
                    if e.errno != errno.EAGAIN:
                        raise
                    if time.monotonic() >= deadline:
                        out["lock"] = "busy"
                        return finish("skipped", "lock-busy")
                    time.sleep(LOCK_POLL_SEC)
        except OSError as e:
            out["warnings"].append(f"concurrency guard unavailable ({e}); continuing without it")
            out["lock"] = "unavailable"
            if fd is not None:
                os.close(fd)
                fd = None

        hygiene = _helper_file(args.hygiene_helper)
        if hygiene:
            ran = _run_sibling(hygiene, "workspace", "--repo", str(clone))
            out["hygiene"] = "ran" if ran is not None and ran[0] == 0 else "failed"

        head = _rev(clone, "HEAD")
        out["_old"] = head[:7] if head else "none"
        if head == target:
            return finish("ok")
        if out["created"]:
            if head != clone_head:
                return finish("skipped", "head-moved")
        else:
            drift = _helper_file(args.drift_helper)
            if not drift:
                return finish("skipped", "head-unverified")
            ran = _run_sibling(drift, str(clone), "--pinned-commit", args.expect_commit)
            try:
                verdict = json.loads(ran[1]).get("status") if ran is not None else None
            except (ValueError, AttributeError):
                verdict = None
            if verdict == "mismatch":
                return finish("skipped", "head-moved")
            if verdict != "ok":
                return finish("skipped", "head-unverified")

        status = _git(clone, "--no-optional-locks", "status", "--porcelain=v1", "-z", "--untracked-files=no")
        if not _ok(status) or status[1]:
            return finish("skipped", "local-changes")

        # A fetch or checkout cut short in the shared clone could leave a lock
        # file there: start one only with the local reserve still ahead.
        if _expired():
            return finish("skipped", "timed-out")
        if not _ok(_git(clone, "cat-file", "-e", f"{target}^{{commit}}")):
            tree = os.path.expanduser(args.tree.strip()) if args.tree.strip() else ""
            if tree:
                run, named = _locate_run(Path(tree))
                record = _read_record(run) if named is None else None
                tree = record["tree"] if record else tree
            if tree and _stat_dir(tree) is True:
                fetched = _git(clone, "fetch", "--quiet", "--no-tags", "--depth", "1", "--", tree,
                               f"+{target}:{ADVANCE_REF}")
                _clear_lock(clone, fetched, "shallow.lock", out["warnings"])
            if not _ok(_git(clone, "cat-file", "-e", f"{target}^{{commit}}")):
                fetched = _git(clone, "fetch", "--quiet", "--no-tags", "--depth", "1", "--", url,
                               f"+{target}:{ADVANCE_REF}", timeout=NETWORK_TIMEOUT_SEC, network=True)
                _clear_lock(clone, fetched, "shallow.lock", out["warnings"])
            if not _ok(_git(clone, "cat-file", "-e", f"{target}^{{commit}}")):
                _git(clone, "update-ref", "-d", ADVANCE_REF, limited=False)
                return finish("skipped", "target-missing")

        if _expired():
            _git(clone, "update-ref", "-d", ADVANCE_REF, limited=False)
            return finish("skipped", "timed-out")
        checkout = _git(clone, *CHECKOUT_OPTS, "checkout", "--quiet", "--detach", target,
                        timeout=NETWORK_TIMEOUT_SEC)
        _clear_lock(clone, checkout, "index.lock", out["warnings"])
        _git(clone, "update-ref", "-d", ADVANCE_REF, limited=False)
        if checkout is not None and checkout[0] in (STOPPED, KILLED):
            # git moves HEAD last: a checkout stopped after it did so had finished.
            if _rev(clone, "HEAD", limited=False) == target:
                return finish("advanced")
            out["warnings"].append(
                f"the {args.timeout:g}-second time limit stopped the checkout of {target[:12]} part way, so "
                f"{clone} may hold files of both commits; it had no local changes when the checkout began, and "
                f'these commands finish it: git -C "{clone}" fetch --depth 1 origin {target} and then '
                f'git -C "{clone}" checkout --force --detach {target}')
            return finish("skipped", "checkout-interrupted")
        if not _ok(checkout):
            out["warnings"].append(_err(checkout))
            return finish("skipped", "checkout-failed")
        if _rev(clone, "HEAD") != target:
            return finish("skipped", "checkout-failed")
        return finish("advanced")
    finally:
        if fd is not None:
            _release_lock(fd)
            os.close(fd)


# --------------------------------------------------------------------------
# close
# --------------------------------------------------------------------------


def close(args: argparse.Namespace) -> dict:
    out = {"status": "refused", "tree": args.tree, "warnings": []}
    given = Path(os.path.expanduser(args.tree.strip())) if args.tree.strip() else None
    if given is None:
        return out
    run, tree = _locate_run(given)
    if not TREE_NAME_RE.match(run.name):
        return out
    if not os.path.lexists(run):
        out["status"] = "missing"
        return out
    if _is_link_or_junction(run):
        return out
    try:
        st = os.lstat(run)
    except OSError:
        return out
    if not stat.S_ISDIR(st.st_mode) or (os.name != "nt" and st.st_uid != os.getuid()):
        return out
    record = _read_record(run)
    if record is None or (tree is not None and not _same_path(record["tree"], tree)):
        return out
    if _rmtree(run):
        out["status"] = "removed"
    else:
        out["status"] = "left"
        out["warnings"].append(f"could not remove {run}; a later run removes it once it is "
                               f"{STALE_TREE_DAYS} days old")
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-source-tree",
        description="Read a remote skill's source at one commit, in a private tree.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_open = sub.add_parser("open", help="prepare this run's private source tree")
    p_open.add_argument("--source-repo", default="", help="metadata.json source_repo")
    p_open.add_argument("--source-root", default="", help="metadata.json source_root")
    p_open.add_argument("--source-ref", default="", help="metadata.json source_ref")
    p_open.add_argument("--pinned-commit", default="", help="metadata.json source_commit")
    p_open.add_argument("--target-ref", default="", help="tag, branch, HEAD or commit to read instead")
    p_open.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SEC,
                        help="seconds open may take (default 100)")

    p_advance = sub.add_parser("advance", help="move the workspace clone to the recorded commit")
    p_advance.add_argument("--clone", required=True, help="the workspace clone open reported")
    p_advance.add_argument("--source-repo", required=True, help="metadata.json source_repo")
    p_advance.add_argument("--target", required=True, help="the 40-hex commit the update recorded")
    p_advance.add_argument("--expect-commit", default="", help="the skill's previous source_commit")
    p_advance.add_argument("--target-ref", default="", help="the ref the update read")
    p_advance.add_argument("--tree", default="",
                           help="this run's tree (or its run folder), the first place to take the commit from")
    p_advance.add_argument("--hygiene-helper", default="", help="path of skf-ccc-git-hygiene.py")
    p_advance.add_argument("--drift-helper", default="", help="path of skf-check-workspace-drift.py")
    p_advance.add_argument("--lock-timeout", type=float, default=LOCK_WAIT_SEC,
                           help="seconds to wait for the workspace lock")
    p_advance.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SEC,
                           help="seconds advance may take (default 100)")

    p_close = sub.add_parser("close", help="remove this run's private source tree")
    p_close.add_argument("--tree", required=True, help="the tree open reported, or its run folder")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "open":
            code, out = open_tree(args)
        elif args.cmd == "advance":
            code, out = 0, advance(args)
        else:
            code, out = 0, close(args)
    except Exception as e:  # noqa: BLE001 - one JSON error line, never a traceback
        print(json.dumps({"status": "error", "message": f"{type(e).__name__}: {e}"}), file=sys.stderr)
        return 1
    print(json.dumps(out))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
