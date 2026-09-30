# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Run Lock: one lock file per run, held across tool calls.

Every Bash tool call runs in a fresh shell, and an SKF workflow spans many
calls and turns. A lock that lives in a process (a held `flock`, the `$$`
PID that a later `kill -0` tests) is gone by the next call, so it can never
serialize two runs. This helper keeps the lock in a file instead: acquire
writes the owner and the time into the lock file, release deletes it only
for the run that owns it, and a lock older than the stale timeout counts as
left by a run that ended without releasing it.

CLI:

  uv run skf-run-lock.py acquire --lock <path> \\
      --owner <workflow>:<skill>:<run_id> [--stale-after <minutes>]
  uv run skf-run-lock.py release --lock <path> \\
      --owner <workflow>:<skill>:<run_id>
  uv run skf-run-lock.py run-id

--lock is the full path of the lock file. Name it by its full path in every
call, never through a shell variable an earlier call set.

--owner names the run: the workflow, the skill and a run id, joined by
colons (`update-skill:cocoindex:20260930T101500Z-3f9a1c2e`). When the run id
is missing (`update-skill:cocoindex`), acquire adds a new one and prints the
whole owner; pass that owner to release.

acquire

  Takes the lock when no lock file exists, when the lock is this owner's
  own (its time is renewed: a run that may outlast the timeout re-runs
  acquire to keep its lock), or when the lock is stale: older than
  --stale-after minutes (60 by default, at most 525600: one year). A stale
  lock is replaced, and stale_replaced says whose it was. Any other lock is
  held by another run: nothing changes, and the output names that run.
  Missing parent folders of --lock are created.

  A lock file that is not this helper's record (the PID and time lines that
  SKF versions before 3.0.0 wrote, the empty file an `flock` left) names no
  owner: held_by is null, and its time is the ISO time on its second line
  when there is one, else the file's modification time. It goes stale the
  same way.

  Output (one ASCII line; every key is always present):
    acquired             true | false
    refreshed            true when the lock was already this owner's
    lock                 absolute path of the lock file
    owner                the owner this call used, with its run id
    run_id               the run id in owner
    held_by              the owner holding the lock after this call (this
                         owner when acquired), or null for a lock that names
                         no owner
    held_since           ISO UTC time the holder took or renewed the lock
    stale_at             ISO UTC time the holder's lock goes stale
    stale_after_minutes  the timeout this call applied
    stale_replaced       null | {"held_by": ..., "held_since": ...}: the
                         stale lock this call replaced
    message              one line for the user; when acquired is false it
                         names the lock file to delete when no run is active

release

  Deletes the lock only when --owner holds it. A lock another run holds
  (one that replaced this run's stale lock, or one taken while this run
  never acquired) is left in place, so a halt path may always release.
  --owner is the whole owner acquire printed: acquire always writes a run
  id, so an owner without one could never match and is a bad argument.

  Output (one ASCII line; every key is always present):
    released    true | false
    reason      null | "absent" (no lock file) | "not-owner"
    lock        absolute path of the lock file
    owner       the owner given
    held_by     the owner still holding the lock (not-owner), else null
    held_since  its time (not-owner), else null
    message     one line

run-id

  Prints {"run_id": "<UTC stamp>-<8 hex>"}, for example
  `20260930T101500Z-3f9a1c2e`: the time of the call and a random suffix,
  safe in file names.

Lock file: one JSON line, {"owner": ..., "acquired_at": ..., "tool":
"skf-run-lock"}, written to `<lock>.skf-<8 hex>-tmp` and renamed over the
lock, so it is never seen half written. Each acquire and release reads and
changes the lock while it holds `<lock>.skf-guard`, an OS lock
(`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) that lives only for
that one call and is released if the call dies, so two runs that start
together never both take the lock and a release never deletes a lock
another run just took. The guard file is removed when the call ends. Every
name this helper creates beside the lock carries `.skf-`, which
skf-skill-inventory.py counts as SKF's own.

Library use: skf-forge-tier-rw.py loads this file by its path and calls
acquire_within() and release() around one read-modify-write. It passes
empty_is_stale=True: an empty lock file is what an `flock` on the same
path leaves (this helper never writes one), so it is replaced at once
instead of when it goes stale.

Exit codes (1 and 2 print one JSON line on stderr, {"status": "error",
"message": ...}, and nothing on stdout):
  0  acquire took or renewed the lock; release and run-id answered
  1  bad arguments: a missing or unknown argument, an owner that is not
     <workflow>:<skill>:<run_id> (acquire adds a missing run id, release
     needs it), a --stale-after that is not a number of minutes above 0
     and at most 525600, a --lock that is a folder
  2  the lock could not be read or written
  3  acquire found the lock held by another run; the output says which
"""

from __future__ import annotations

import argparse
import errno
import json
import math
import os
import re
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


DEFAULT_STALE_AFTER_MIN = 60
MAX_STALE_AFTER_MIN = 525600  # one year
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
RUN_ID_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
OWNER_MAX_LEN = 200
GUARD_SUFFIX = ".skf-guard"
GUARD_WAIT_SEC = 10.0
EXIT_HELD = 3
TOOL = "skf-run-lock"


class LockBusy(Exception):
    """acquire_within() ran out of time; .result is the last acquire output."""

    def __init__(self, result: dict):
        super().__init__(result["message"])
        self.result = result


# ─── Owner, time and run id ──────────────────────────────────────────────────


def new_run_id(now: datetime | None = None) -> str:
    """A run id: the UTC time and 8 random hex characters."""
    now = now or datetime.now(timezone.utc)
    return f"{now.strftime(RUN_ID_STAMP_FORMAT)}-{secrets.token_hex(4)}"


def _stamp(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime(TIME_FORMAT)


def _stale_at(since: datetime, window: timedelta) -> str:
    """The time a lock taken at `since` goes stale, or the last time a datetime can hold."""
    try:
        return _stamp(since + window)
    except OverflowError:
        # A lock file dated near year 9999: it only goes stale when deleted.
        return _stamp(datetime.max.replace(tzinfo=timezone.utc))


def _parse_time(text) -> datetime | None:
    if not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text.strip(), TIME_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _split_owner(owner: str) -> tuple[str, str, str]:
    """(workflow, skill, run_id) of an owner; run_id is "" when missing.

    Raises ValueError for an owner that is not `<workflow>:<skill>[:<run_id>]`.
    """
    if not isinstance(owner, str) or not owner or len(owner) > OWNER_MAX_LEN:
        raise ValueError(f"--owner must be <workflow>:<skill>:<run_id>, at most "
                         f"{OWNER_MAX_LEN} characters with its run id")
    if any(ch.isspace() or not ch.isprintable() for ch in owner):
        raise ValueError(f"--owner must not hold spaces or control characters: {owner!r}")
    parts = owner.split(":", 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"--owner must be <workflow>:<skill>:<run_id>, got {owner!r}")
    return parts[0], parts[1], parts[2] if len(parts) == 3 else ""


def _lock_path(lock) -> Path:
    path = Path(os.path.abspath(os.path.expanduser(str(lock))))
    if path.is_dir():
        raise ValueError(f"--lock names a folder, not a lock file: {path}")
    return path


def _minutes(seconds: float):
    minutes = seconds / 60
    return int(minutes) if minutes == int(minutes) else round(minutes, 4)


# ─── The guard: an OS lock for one call ──────────────────────────────────────


def _try_lock(fd: int) -> bool:
    try:
        if os.name == "nt":
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        if e.errno in (errno.EAGAIN, errno.EACCES, errno.EDEADLK, errno.EWOULDBLOCK):
            return False
        raise
    return True


def _unlock(fd: int) -> None:
    try:
        if os.name == "nt":
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def _still_named(fd: int, guard: Path) -> bool:
    """True when `guard` still names the file fd holds.

    On POSIX the holder removes the guard while it still holds it, so a call
    that was waiting on the removed file must open the path again. Windows
    refuses to remove a file another call has open, so there the path always
    names the file.
    """
    if os.name == "nt":
        return True
    try:
        named = os.stat(guard)
    except FileNotFoundError:
        return False
    held = os.fstat(fd)
    return (held.st_dev, held.st_ino) == (named.st_dev, named.st_ino)


class _Guard:
    """Hold `<lock>.skf-guard` while one call reads and changes the lock."""

    def __init__(self, lock: Path):
        self.path = lock.with_name(lock.name + GUARD_SUFFIX)
        self.fd: int | None = None

    def __enter__(self) -> "_Guard":
        deadline = time.monotonic() + GUARD_WAIT_SEC
        while True:
            try:
                fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
            except PermissionError:
                # Windows: the file is being removed by the call that held it.
                if os.name != "nt" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
                continue
            try:
                locked = _try_lock(fd)
                if locked and _still_named(fd, self.path):
                    self.fd = fd
                    return self
            except BaseException:
                os.close(fd)
                raise
            if locked:
                _unlock(fd)
            os.close(fd)
            if time.monotonic() >= deadline:
                raise OSError(errno.EAGAIN, f"{self.path} stayed locked for "
                                            f"{GUARD_WAIT_SEC:g} seconds")
            time.sleep(0.01)

    def __exit__(self, *exc) -> None:
        fd, self.fd = self.fd, None
        if os.name != "nt":
            # Remove it while still holding it (see _still_named).
            _unlink_quietly(self.path)
            _unlock(fd)
            os.close(fd)
        else:
            _unlock(fd)
            os.close(fd)
            # Refused while another call has it open; that call removes it.
            _unlink_quietly(self.path)


def _unlink_quietly(path: Path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _windows_retry(action) -> None:
    """Run action(); on Windows retry briefly while another process has the file open."""
    for attempt in range(5):
        try:
            action()
            return
        except PermissionError:
            if os.name != "nt" or attempt == 4:
                raise
            time.sleep(0.02 * (attempt + 1))


# ─── The lock record ─────────────────────────────────────────────────────────


class _Held:
    """What a lock file says: its owner (or None), since when, and whether it is empty."""

    def __init__(self, owner: str | None, since: datetime, empty: bool = False):
        self.owner = owner
        self.since = since
        self.empty = empty


def _read(lock: Path) -> _Held | None:
    """The lock's holder, or None when there is no lock file."""
    try:
        raw = lock.read_bytes()
        mtime = lock.stat().st_mtime
    except FileNotFoundError:
        return None
    text = raw.decode("utf-8", "replace")
    try:
        record = json.loads(text)
    except ValueError:
        record = None
    if isinstance(record, dict):
        owner = record.get("owner")
        owner = owner if isinstance(owner, str) and owner else None
        since = _parse_time(record.get("acquired_at"))
    else:
        # Not this helper's record: the PID and time lines older SKF versions
        # wrote, an empty file an `flock` left, or anything else.
        owner = None
        lines = text.splitlines()
        since = _parse_time(lines[1]) if len(lines) > 1 else None
    if since is None:
        since = datetime.fromtimestamp(mtime, timezone.utc)
    return _Held(owner, since, empty=not raw)


def _write(lock: Path, owner: str, now: datetime) -> None:
    """Write the record to a temp file beside the lock, then rename it over the lock."""
    record = {"owner": owner, "acquired_at": _stamp(now), "tool": TOOL}
    content = (json.dumps(record) + "\n").encode("utf-8")
    tmp = lock.with_name(f"{lock.name}.skf-{secrets.token_hex(4)}-tmp")
    # O_BINARY (Windows only; 0 elsewhere) keeps the bytes verbatim.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(tmp, flags, 0o644)
        try:
            os.write(fd, content)
            os.fsync(fd)
        finally:
            os.close(fd)
        _windows_retry(lambda: os.replace(tmp, lock))
    except OSError:
        _unlink_quietly(tmp)
        raise


# ─── acquire / release ───────────────────────────────────────────────────────


def acquire(lock, owner: str, stale_after: float, now: datetime | None = None,
            *, empty_is_stale: bool = False) -> dict:
    """Take the lock for owner, or report who holds it.

    stale_after is in seconds, at most one year. `now` is for tests. With
    empty_is_stale, an empty lock file counts as stale at once. Raises
    ValueError for a bad owner, lock or timeout, OSError when the lock cannot
    be read or written.
    """
    if (not isinstance(stale_after, (int, float)) or not math.isfinite(stale_after)
            or not 0 < stale_after <= MAX_STALE_AFTER_MIN * 60):
        raise ValueError(f"stale_after must be a number of seconds above 0 and at most "
                         f"{MAX_STALE_AFTER_MIN * 60} (one year), got {stale_after!r}")
    workflow, skill, run_id = _split_owner(owner)
    if not run_id:
        run_id = new_run_id(now)
        owner = f"{workflow}:{skill}:{run_id}"
        # Checked again with its run id, so release accepts every owner acquire prints.
        _split_owner(owner)
    path = _lock_path(lock)
    path.parent.mkdir(parents=True, exist_ok=True)
    window = timedelta(seconds=stale_after)

    with _Guard(path):
        held = _read(path)
        t = now or datetime.now(timezone.utc)
        refreshed = held is not None and held.owner == owner
        replaced = None
        if held is not None and not refreshed:
            if t - held.since < window and not (empty_is_stale and held.empty):
                who = held.owner or "an owner the lock file does not name"
                stale_at = _stale_at(held.since, window)
                return {
                    "acquired": False,
                    "refreshed": False,
                    "lock": str(path),
                    "owner": owner,
                    "run_id": run_id,
                    "held_by": held.owner,
                    "held_since": _stamp(held.since),
                    "stale_at": stale_at,
                    "stale_after_minutes": _minutes(stale_after),
                    "stale_replaced": None,
                    "message": (f"another run holds {path}: {who} since {_stamp(held.since)}. "
                                f"Wait for it to finish; if no run is active, delete {path} "
                                f"or wait until {stale_at}, when the lock goes stale."),
                }
            replaced = {"held_by": held.owner, "held_since": _stamp(held.since)}
        # Computed before the write, so no error can follow a lock taken.
        held_since, stale_at = _stamp(t), _stale_at(t, window)
        _write(path, owner, t)

    if refreshed:
        message = f"renewed the run lock {path} for {owner}"
    elif replaced:
        message = (f"took the run lock {path} for {owner}, replacing the stale lock of "
                   f"{replaced['held_by'] or 'an unnamed owner'} (since {replaced['held_since']})")
    else:
        message = f"took the run lock {path} for {owner}"
    return {
        "acquired": True,
        "refreshed": refreshed,
        "lock": str(path),
        "owner": owner,
        "run_id": run_id,
        "held_by": owner,
        "held_since": held_since,
        "stale_at": stale_at,
        "stale_after_minutes": _minutes(stale_after),
        "stale_replaced": replaced,
        "message": message,
    }


def acquire_within(lock, owner: str, stale_after: float, wait: float,
                   *, empty_is_stale: bool = False) -> dict:
    """acquire(), retried until it takes the lock or `wait` seconds pass.

    For a lock held inside one call. Raises LockBusy with the last output
    when the time runs out.
    """
    deadline = time.monotonic() + max(wait, 0)
    delay = 0.05
    while True:
        result = acquire(lock, owner, stale_after, empty_is_stale=empty_is_stale)
        if result["acquired"]:
            return result
        left = deadline - time.monotonic()
        if left <= 0:
            raise LockBusy(result)
        time.sleep(min(delay, left))
        delay = min(delay * 2, 0.5)


def release(lock, owner: str) -> dict:
    """Delete the lock when owner holds it; leave any other lock in place.

    Raises ValueError for an owner that is not <workflow>:<skill>:<run_id>.
    """
    if not _split_owner(owner)[2]:
        raise ValueError(f"release needs the owner acquire printed, with its run id "
                         f"(<workflow>:<skill>:<run_id>), got {owner!r}")
    path = _lock_path(lock)
    out = {"released": False, "reason": None, "lock": str(path), "owner": owner,
           "held_by": None, "held_since": None, "message": ""}
    if not path.parent.is_dir() or not os.path.lexists(path):
        out.update(reason="absent", message=f"no run lock at {path}; nothing to release")
        return out
    with _Guard(path):
        held = _read(path)
        if held is None:
            out.update(reason="absent", message=f"no run lock at {path}; nothing to release")
            return out
        if held.owner != owner:
            out.update(reason="not-owner", held_by=held.owner, held_since=_stamp(held.since),
                       message=(f"{path} belongs to {held.owner or 'an unnamed owner'}, "
                                f"not {owner}; left in place"))
            return out
        _windows_retry(lambda: os.unlink(path))
    out.update(released=True, message=f"released the run lock {path}")
    return out


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _error(message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)


class _JsonErrorParser(argparse.ArgumentParser):
    """Report a usage error as a JSON error with exit 1, like every other bad argument.

    The subcommand parsers are made with this class too, so a missing --lock
    or a --stale-after that is not a number never reaches argparse's own
    plain-text usage and exit 2.
    """

    def error(self, message: str) -> None:
        _error(f"usage error: {self.prog}: {message}")
        sys.exit(1)


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonErrorParser(
        description="Take and release an SKF run lock that holds across tool calls.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="{acquire,release,run-id}")

    p_acquire = sub.add_parser("acquire", help="take the lock, or report the run that holds it")
    p_acquire.add_argument("--lock", required=True, help="full path of the lock file")
    p_acquire.add_argument("--owner", required=True,
                           help="<workflow>:<skill>:<run_id>; a new run id is added when missing")
    p_acquire.add_argument("--stale-after", type=float, default=DEFAULT_STALE_AFTER_MIN,
                           help="minutes after which another run's lock is stale "
                                "(default 60, at most 525600)")

    p_release = sub.add_parser("release", help="delete the lock when this owner holds it")
    p_release.add_argument("--lock", required=True, help="full path of the lock file")
    p_release.add_argument("--owner", required=True, help="the owner acquire printed")

    sub.add_parser("run-id", help="print a new run id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "acquire":
            if not math.isfinite(args.stale_after) or not 0 < args.stale_after <= MAX_STALE_AFTER_MIN:
                raise ValueError(f"--stale-after must be a number of minutes above 0 and at "
                                 f"most {MAX_STALE_AFTER_MIN} (one year), got {args.stale_after:g}")
            out = acquire(args.lock, args.owner, args.stale_after * 60)
            code = 0 if out["acquired"] else EXIT_HELD
        elif args.cmd == "release":
            out, code = release(args.lock, args.owner), 0
        else:
            out, code = {"run_id": new_run_id()}, 0
    except ValueError as e:
        _error(str(e))
        return 1
    except OSError as e:
        _error(f"{type(e).__name__}: {e}")
        return 2
    print(json.dumps(out))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
