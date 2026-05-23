# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Atomic Write — Crash-safe artifact writing for skill workflows.

Provides three CLI subcommands skills can invoke via bash to avoid
partial-write corruption and active-symlink races.

Subcommands:
  write      Stage content into <target>.skf-tmp, fsync, then rename to <target>.
             Content comes from stdin. Creates parent dirs as needed.

  stage-dir  Create <target>.skf-tmp/ as a staging directory (mkdir -p).
             Caller writes files into it, then calls commit-dir to atomically
             swap it into place as <target>/ (with prior target moved aside
             to <target>.skf-rollback-<pid> and removed on success).

  commit-dir Atomically swap <target>.skf-tmp/ into <target>/. If <target>/
             exists, move it to <target>.skf-rollback-<pid> first; on failure,
             restore. Supports rollback via --rollback to undo the most recent
             commit by restoring the rollback dir if still present.

  flip-link  Atomically update symlink <link> to point at <target> using
             the `ln -sfn tmp && mv -Tf tmp link` pattern (or equivalent via
             os.replace on the link path). Holds an flock on <link>.lock.

Cross-platform: locking branches between fcntl (POSIX) and msvcrt
(Windows). Symlink semantics on Windows require dev mode or admin —
flip-link surfaces a clear error rather than silently falling back.
Native Windows is untested in CI; the supported path is WSL2.

Exit codes:
  0 on success
  1 on user error (bad args, missing input)
  2 on operation failure (disk full, permission, race-detected)

CLI examples:
  cat metadata.json | python3 skf-atomic-write.py write --target /path/to/metadata.json
  python3 skf-atomic-write.py stage-dir --target /path/to/1.0.0
  python3 skf-atomic-write.py commit-dir --target /path/to/1.0.0
  python3 skf-atomic-write.py flip-link --link /path/to/active --target 1.0.0
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def _create_symlink_or_junction(target: str, link_path: Path) -> str:
    """Create a directory link from link_path to target.

    On POSIX: standard symlink. On Windows: try symlink first (works under
    Developer Mode or admin), fall back to a directory junction via `mklink /J`
    on PRIVILEGE_NOT_HELD / ACCESS_DENIED. Junctions don't need elevation and
    behave like directory symlinks for the resolve() / is_dir() consumers in
    skf-skill-inventory.py.

    Returns "symlink" or "junction" so callers can report which kind was made.
    """
    try:
        os.symlink(target, link_path)
        return "symlink"
    except OSError as e:
        if os.name != "nt" or getattr(e, "winerror", None) not in (1314, 5):
            raise
        # Junctions are absolute-path-only and target must be a real directory
        # at creation time. Resolve relative `target` against link_path's parent.
        abs_target = (link_path.parent / target).resolve()
        if not abs_target.is_dir():
            raise OSError(
                errno.ENOTDIR,
                f"junction fallback requires existing directory target: {abs_target}",
            ) from e
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_path), str(abs_target)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise OSError(
                e.errno,
                f"junction fallback failed: {result.stderr.strip() or result.stdout.strip()}",
            ) from e
        return "junction"


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


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
    sys.exit(code)


def _ok(payload: dict) -> None:
    payload.setdefault("status", "ok")
    print(json.dumps(payload))


def cmd_write(target: Path) -> None:
    """Write stdin to target atomically via temp + rename."""
    data = sys.stdin.buffer.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".skf-tmp")
    # O_BINARY (Windows only; 0 elsewhere) suppresses the text-mode \n -> \r\n
    # translation that would otherwise corrupt verbatim writes on Windows.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(tmp, flags, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, target)
    except OSError as e:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        _die(2, f"atomic write failed: {e}")
    _ok({"wrote": str(target), "bytes": len(data)})


def cmd_stage_dir(target: Path) -> None:
    """Create <target>.skf-tmp/ staging directory (clean if present)."""
    staging = target.with_name(target.name + ".skf-tmp")
    # A prior interrupted run can leave staging as a regular file or a dangling
    # symlink; shutil.rmtree only handles real directories, so dispatch by type.
    if staging.is_symlink() or (staging.exists() and not staging.is_dir()):
        try:
            staging.unlink()
        except OSError as e:
            _die(2, f"failed to clear stale staging entry {staging}: {e}")
    elif staging.is_dir():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    _ok({"staging": str(staging)})


def cmd_commit_dir(target: Path, rollback: bool = False) -> None:
    """Swap <target>.skf-tmp/ into <target>/.

    The swap is two os.replace calls (move prior aside, then move staging
    into place); a crash between them leaves the prior snapshot at
    <target>.skf-rollback-<pid>/ recoverable via --rollback. Concurrent
    commits against the same target are NOT supported — callers must
    serialize via the per-target flock provided by flip-link or external
    coordination.
    """
    staging = target.with_name(target.name + ".skf-tmp")
    rollback_dir = target.with_name(target.name + f".skf-rollback-{os.getpid()}")

    if rollback:
        # Pick the newest rollback dir by mtime, not by lexical PID sort.
        # Concurrent commits leave one rollback per PID; sorting by PID-as-string
        # could restore an older snapshot (PID "9999" sorts after "10001"). mtime
        # of the rollback dir = moment os.replace moved the prior target aside,
        # which is the correct "most recent" anchor.
        candidates = list(target.parent.glob(target.name + ".skf-rollback-*"))
        if not candidates:
            _die(1, f"no rollback dir for {target}")
        chosen = max(candidates, key=lambda p: p.stat().st_mtime)
        if target.exists():
            shutil.rmtree(target)
        os.replace(chosen, target)
        _ok({"restored": str(target), "from": str(chosen)})
        return

    if not staging.is_dir():
        _die(1, f"staging dir missing: {staging}")

    # First-install case: target's parent may not exist yet (e.g. fresh
    # {skill_group}/{version}/ install). os.replace requires the destination
    # parent to exist, so create it before either replace fires.
    target.parent.mkdir(parents=True, exist_ok=True)

    prior_moved = False
    if target.exists():
        if target.is_symlink() or target.is_file():
            _die(2, f"target is not a directory: {target}")
        try:
            os.replace(target, rollback_dir)
            prior_moved = True
        except OSError as e:
            _die(2, f"failed to move prior target aside: {e}")

    try:
        os.replace(staging, target)
    except OSError as e:
        if prior_moved:
            try:
                os.replace(rollback_dir, target)
            except OSError:
                pass
        _die(2, f"commit swap failed: {e}")

    if prior_moved:
        try:
            shutil.rmtree(rollback_dir)
        except OSError:
            pass

    _ok({"committed": str(target)})


def _is_link_or_junction(p: Path) -> bool:
    """True for POSIX symlinks AND Windows junctions/symlinks.

    `Path.is_symlink()` is False for Windows junctions; os.readlink succeeds
    for both symlinks and junctions (since CPython 3.8 on Windows). A regular
    directory raises OSError on readlink, which is the signal we want to
    refuse replacement.
    """
    if p.is_symlink():
        return True
    if not p.exists() and not p.is_symlink():
        return False
    try:
        os.readlink(p)
        return True
    except OSError:
        return False


def cmd_flip_link(link: Path, target: str) -> None:
    """Atomically point <link> at <target> using rename-over-symlink pattern.

    target is the value of the symlink (may be relative, as is convention
    for `active -> 1.0.0`). Held lock on <link>.lock prevents concurrent flips.

    On Windows, os.symlink requires Developer Mode or admin. When that fails
    with PRIVILEGE_NOT_HELD/ACCESS_DENIED the helper falls back to a directory
    junction (no elevation needed); junctions resolve identically for
    skf-skill-inventory's resolve_active_version().
    """
    lock_path = link.with_name(link.name + ".skf-lock")
    link.parent.mkdir(parents=True, exist_ok=True)

    # Refuse only if <link> is a real directory/file (not a symlink or junction).
    # Replacing a real dir would lose user data; replacing a link is the point.
    if link.exists() and not _is_link_or_junction(link):
        _die(2, f"refusing to replace non-link: {link}")

    lock_fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o644)
    lock_held = False
    try:
        try:
            _acquire_lock(lock_fd)
            lock_held = True
        except OSError as e:
            if e.errno == errno.EAGAIN:
                _die(2, f"another process holds flip lock on {link}")
            raise

        tmp_link = link.with_name(link.name + ".skf-tmp-link")
        if tmp_link.is_symlink() or tmp_link.exists():
            # On Windows a junction returns is_dir()=True, exists()=True but
            # is_symlink()=False — must rmdir/unlink based on type.
            if tmp_link.is_dir() and not tmp_link.is_symlink():
                tmp_link.rmdir()
            else:
                tmp_link.unlink()
        try:
            link_kind = _create_symlink_or_junction(target, tmp_link)
        except OSError as e:
            if os.name == "nt" and getattr(e, "winerror", None) in (1314, 5):
                _die(
                    2,
                    "symlink/junction creation failed on Windows. Junction fallback "
                    "requires the target directory to exist. Either enable Developer "
                    "Mode (Settings → Privacy & Security → For Developers) or use WSL2.",
                )
            raise
        # os.replace can swap a symlink-over-symlink atomically, but Windows
        # rejects renaming a directory (junction) over an existing directory
        # (junction or real). Drop the existing link first when junction-based.
        if link_kind == "junction" and (link.is_dir() or link.is_symlink() or link.exists()):
            if link.is_symlink() or not link.is_dir():
                link.unlink()
            else:
                link.rmdir()
        os.replace(tmp_link, link)
    finally:
        if lock_held:
            _release_lock(lock_fd)
        os.close(lock_fd)
        # Lock file is bookkeeping only — once the fd is closed the lock is
        # gone, so leaving the file around just litters the skill_group dir.
        # Best-effort unlink; a concurrent flipper may have already removed it.
        try:
            lock_path.unlink()
        except OSError:
            pass

    _ok({"link": str(link), "points_to": target, "kind": link_kind})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_write = sub.add_parser("write", help="Atomic file write from stdin")
    p_write.add_argument("--target", type=Path, required=True)

    p_stage = sub.add_parser("stage-dir", help="Create staging directory")
    p_stage.add_argument("--target", type=Path, required=True)

    p_commit = sub.add_parser("commit-dir", help="Commit staging directory to target")
    p_commit.add_argument("--target", type=Path, required=True)
    p_commit.add_argument("--rollback", action="store_true", help="Restore from rollback dir instead of committing")

    p_flip = sub.add_parser("flip-link", help="Atomic symlink flip")
    p_flip.add_argument("--link", type=Path, required=True)
    p_flip.add_argument("--target", type=str, required=True)

    args = parser.parse_args()

    if args.cmd == "write":
        cmd_write(args.target)
    elif args.cmd == "stage-dir":
        cmd_stage_dir(args.target)
    elif args.cmd == "commit-dir":
        cmd_commit_dir(args.target, rollback=args.rollback)
    elif args.cmd == "flip-link":
        cmd_flip_link(args.link, args.target)


if __name__ == "__main__":
    main()
