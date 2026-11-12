# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Health Check Seen: the fingerprints of a health-check finding and the
seen-issue cache that every SKF workflow on the machine shares.

src/shared/health-check.md, the last step of every SKF workflow, files a
finding as a GitHub issue once per defect on a machine and reports a fixed
defect that comes back as a regression. This helper owns the deterministic
part of that: the two hashes, the tolerant read of the cache, the bounded
check of a recorded issue's state, the verdict, and the locked merge-write
of a record. The step keeps the judgment: whether a finding is real, its
severity, section slug and defect key, the user's pick at a matching issue,
and the wording of a regression.

CLI:

  uv run skf-health-check-seen.py fingerprint --severity <bug|friction|gap> \\
      --workflow <name> --step-file <path> --section <slug> --defect-key <key>
  uv run skf-health-check-seen.py lookup --fp <fp> --legacy-fp <fp> \\
      [--cache <path>]
  uv run skf-health-check-seen.py record --fp <fp> \\
      --action <created|reacted|commented> --issue-url <url> \\
      --date <YYYY-MM-DD> [--regression] [--cache <path>]

--cache is $HOME/.skf/health-check-seen.json (Path.home()) by default. The
step passes none, so every workflow reads and writes the same file.

fingerprint
-----------
  fp         "fp-" and the first 7 hex characters of
             sha1("{severity}|{workflow}|{step_file}|{section}|{defect_key}"),
             taken over the UTF-8 bytes with no newline
  legacy_fp  the same hash without "|{defect_key}": the section fingerprint,
             which SKF versions without the defect key used as the
             fingerprint and which every defect of one severity in one
             section shares

Each value must keep its rule, else exit 2 naming it: the severity is bug,
friction or gap; the section is kebab-case (^[a-z0-9]+(-[a-z0-9]+)*$); the
defect key is one to four such words (^[a-z0-9]+(-[a-z0-9]+){0,3}$); the
workflow and the step file are not empty and hold no "|" and no line break,
so two different findings never hash the same text. The workflow and the
step file are hashed as given.

  Output: {"fp": "fp-a54e7a6", "legacy_fp": "fp-eb2d6f2"}

lookup
------
Reads the cache. A file that is missing, empty, unreadable, not UTF-8, not
JSON or not a JSON object is an empty cache, never an error. The record
under --fp decides; only when the cache has no --fp key does the record
under --legacy-fp decide. On the record found, the first branch that
matches gives the verdict:

  1. no record under either fingerprint: unseen
  2. "action" is "resolved" (written by hand once the defect was fixed):
     regression
  3. "action" is created, reacted or commented, and "issue_url" is set: the
     issue's own state decides, read with
     `gh issue view <issue_url> --json state,stateReason`, stopped after 10
     seconds (GH_TIMEOUT_SEC). State CLOSED with stateReason COMPLETED, or
     state MERGED (a resolving pull request), is regression. Every other
     answer (OPEN, a NOT_PLANNED or DUPLICATE close) and every failure (no
     gh, the time limit, a non-zero exit, output that is not that JSON) is
     handled. gh runs only for an issue_url that starts with https:// and
     holds no whitespace; any other value counts as a failure.
  4. one of those three actions with "issue_url" empty or absent: handled
  5. no "action", any other action, or a record that is not an object:
     unrecognized

A record found only under --legacy-fp may be another defect's, so two
verdicts change: handled becomes unseen (a legacy record never
suppresses) and regression becomes possible-regression. unrecognized
stays.

  Output: {"verdict": "unseen" | "handled" | "regression"
                      | "possible-regression" | "unrecognized",
           "record": <the record found, as the cache holds it> | null,
           "matched_on": "fp" | "legacy_fp" | null}

handled is the only verdict that suppresses a report.

record
------
Sets the --fp key alone to {"issue_url": ..., "action": ..., "date": ...}
and keeps every other key as it read them, records under a legacy
fingerprint included. --action is one of the three this workflow writes
(resolved is written by hand), --issue-url starts with https:// and holds
no whitespace, and --date is a real YYYY-MM-DD date.

A "resolved" record under --fp is never downgraded: it is replaced only
with --regression, which the step passes, with any of the three actions,
once a regression verdict is followed by an open issue that tracks the
recurrence: the new issue it filed (created), or the matching one the user
reacted or commented on. Without it nothing is written and "written" is
false. A record that is not resolved is set with or without it.

The read, merge and write run while this call holds <cache>.lock, taken
through skf-run-lock.py's acquire_within() and release() (the sibling in
this folder) as skf-forge-tier-rw.py does: a lock older than 15 seconds
(LOCK_STALE_SEC) was left by a killed call and is replaced, an empty lock
file at once (empty_is_stale), and the call waits up to 10 seconds
(LOCK_WAIT_SEC) for another one to finish. The parent folder is created.
The new file is written beside the cache, synced to disk and renamed over
it (on Windows the rename is retried while another process has the cache
open), so no reader sees it half written. A cache that exists and is not
a JSON object is first renamed to <cache>.corrupt-<UTC YYYYMMDDTHHMMSSZ>
(with -2, -3 and so on after a first one in the same second), so the
records in it can still be repaired by hand; when that rename fails,
nothing is written. An empty file is an empty cache.

  Output: {"written": true | false, "fp": ...,
           "record": <what the cache now holds under --fp>,
           "set_aside": <the path the corrupt cache was renamed to> | null}

No network and no gh call in fingerprint or record.

Exit codes (1 and 2 print one JSON line on stderr, {"status": "error",
"message": ...}, and nothing on stdout):
  0  answered
  1  record could not take the lock, read the cache, set a corrupt one
     aside or write it
  2  a bad argument: a missing or unknown one, or a value that breaks its
     rule
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

SEVERITIES = ("bug", "friction", "gap")
# The actions this workflow writes; each suppresses while its issue is live.
WRITTEN_ACTIONS = ("created", "reacted", "commented")
RESOLVED = "resolved"

# Each rule is matched with fullmatch: `$` alone would let a value that ends in a newline through.
SECTION_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
DEFECT_KEY_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+){0,3}")
FP_RE = re.compile(r"fp-[0-9a-f]{7}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
URL_PREFIX = "https://"

GH_TIMEOUT_SEC = 10.0
LOCK_STALE_SEC = 15.0
LOCK_WAIT_SEC = 10.0
CORRUPT_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
# Windows refuses to rename over a file another process has open (a lookup
# reading the cache, a virus scanner); the rename is retried for this long.
_IS_WINDOWS = os.name == "nt"
_REPLACE_WAIT_SECONDS = 5.0
_REPLACE_POLL_SECONDS = 0.02

HERE = Path(__file__).resolve().parent
SOURCE_TREE_HELPER = HERE / "skf-source-tree.py"
RUN_LOCK_HELPER = HERE / "skf-run-lock.py"

_SIBLINGS: dict[str, object] = {}


class UsageError(Exception):
    """A value that breaks its rule (exit 2)."""


class WriteError(Exception):
    """record could not take the lock, read the cache, set a corrupt one aside or write it (exit 1)."""


def _load(path: Path):
    """A sibling script loaded by its path, once."""
    module = _SIBLINGS.get(path.name)
    if module is None:
        spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[path.name] = module
    return module


def default_cache() -> Path:
    return Path.home() / ".skf" / "health-check-seen.json"


# --------------------------------------------------------------------------
# fingerprint
# --------------------------------------------------------------------------


def _check_field(name: str, value: str) -> None:
    if not value:
        raise UsageError(f"{name} must not be empty")
    if "|" in value or "\n" in value or "\r" in value:
        raise UsageError(f"{name} must hold no '|' and no line break, got {value!r}")


def _sha7(text: str) -> str:
    try:
        data = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise UsageError(f"the fingerprint fields must be valid UTF-8: {exc}") from None
    return hashlib.sha1(data).hexdigest()[:7]


def fingerprint(severity: str, workflow: str, step_file: str, section: str, defect_key: str) -> dict:
    """{"fp", "legacy_fp"} of one finding. Raises UsageError for a value that breaks its rule."""
    if severity not in SEVERITIES:
        raise UsageError(f"--severity must be one of {', '.join(SEVERITIES)}, got {severity!r}")
    _check_field("--workflow", workflow)
    _check_field("--step-file", step_file)
    if not SECTION_RE.fullmatch(section):
        raise UsageError(f"--section must be a kebab-case heading slug (^[a-z0-9]+(-[a-z0-9]+)*$), "
                         f"got {section!r}")
    if not DEFECT_KEY_RE.fullmatch(defect_key):
        raise UsageError(f"--defect-key must be one to four lower-case words joined by hyphens "
                         f"(^[a-z0-9]+(-[a-z0-9]+){{0,3}}$), got {defect_key!r}")
    legacy = f"{severity}|{workflow}|{step_file}|{section}"
    return {"fp": "fp-" + _sha7(f"{legacy}|{defect_key}"), "legacy_fp": "fp-" + _sha7(legacy)}


# --------------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------------


def _parse(raw: bytes) -> dict | None:
    """The cache object in raw bytes; {} for an empty file, None when it is not a JSON object."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):  # RecursionError: nested past the parser's depth
        return None
    return data if isinstance(data, dict) else None


def load_cache(cache: Path) -> dict:
    """The cache as a dict: missing, empty, unreadable or corrupt is {} (never raises)."""
    try:
        raw = cache.read_bytes()
    except OSError:
        return {}
    return _parse(raw) or {}


# --------------------------------------------------------------------------
# lookup
# --------------------------------------------------------------------------


def gh_issue_state(issue_url: str, timeout: float = GH_TIMEOUT_SEC) -> dict | None:
    """`gh issue view <issue_url> --json state,stateReason`: its JSON object, or None on any failure.

    gh is found and run through skf-source-tree.py's _resolve_outside_cwd
    (never a gh planted in the current folder) and _run (the call and all it
    started are stopped at the time limit).
    """
    try:
        tree = _load(SOURCE_TREE_HELPER)
        exe = tree._resolve_outside_cwd("gh")
        if exe is None:
            return None
        rc, out, _err, _killed = tree._run([exe, "issue", "view", issue_url, "--json", "state,stateReason"],
                                           timeout)
    except (ImportError, OSError, SyntaxError, ValueError, AttributeError):
        return None
    if rc != 0:
        return None
    try:
        answer = json.loads(out.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    if not isinstance(answer, dict) or not isinstance(answer.get("state"), str):
        return None
    return answer


def _gh_url(value) -> bool:
    """An issue_url gh may be given: https://, no whitespace (so never a flag)."""
    return isinstance(value, str) and value.startswith(URL_PREFIX) and not any(ch.isspace() for ch in value)


def _issue_verdict(issue_url) -> str:
    """Branch 3: regression for a completed close or a merge, handled for anything else."""
    if not _gh_url(issue_url):
        return "handled"
    answer = gh_issue_state(issue_url, GH_TIMEOUT_SEC)
    if answer is None:
        return "handled"
    state = answer["state"].upper()
    reason = answer.get("stateReason")
    reason = reason.upper() if isinstance(reason, str) else ""
    if (state == "CLOSED" and reason == "COMPLETED") or state == "MERGED":
        return "regression"
    return "handled"


def _verdict(record) -> str:
    """Branches 2 to 5 on a record that exists."""
    if not isinstance(record, dict):
        return "unrecognized"
    action = record.get("action")
    if action == RESOLVED:
        return "regression"
    if action in WRITTEN_ACTIONS:
        if record.get("issue_url") in (None, ""):
            return "handled"
        return _issue_verdict(record.get("issue_url"))
    return "unrecognized"


def lookup(fp: str, legacy_fp: str, cache: Path) -> dict:
    """{"verdict", "record", "matched_on"} for one finding."""
    _check_fp("--fp", fp)
    _check_fp("--legacy-fp", legacy_fp)
    data = load_cache(cache)
    if fp in data:
        record = data[fp]
        return {"verdict": _verdict(record), "record": record, "matched_on": "fp"}
    if legacy_fp in data:
        record = data[legacy_fp]
        verdict = _verdict(record)
        # A section fingerprint may be another defect's: it never suppresses, and a fix it records is only possible.
        verdict = {"handled": "unseen", "regression": "possible-regression"}.get(verdict, verdict)
        return {"verdict": verdict, "record": record, "matched_on": "legacy_fp"}
    return {"verdict": "unseen", "record": None, "matched_on": None}


# --------------------------------------------------------------------------
# record
# --------------------------------------------------------------------------


def _check_fp(name: str, value: str) -> None:
    if not FP_RE.fullmatch(value):
        raise UsageError(f"{name} must be fp- and 7 lower-case hex characters, got {value!r}")


def _check_record_args(fp: str, action: str, issue_url: str, day: str) -> None:
    _check_fp("--fp", fp)
    if action not in WRITTEN_ACTIONS:
        raise UsageError(f"--action must be one of {', '.join(WRITTEN_ACTIONS)}, got {action!r}")
    if not _gh_url(issue_url):
        raise UsageError(f"--issue-url must start with {URL_PREFIX} and hold no whitespace, got {issue_url!r}")
    try:
        if not DATE_RE.fullmatch(day):
            raise ValueError
        date.fromisoformat(day)
    except ValueError:
        raise UsageError(f"--date must be a real date as YYYY-MM-DD, got {day!r}") from None


def _replace(src: Path, dst: Path) -> None:
    """os.replace, retried on Windows while another process has dst open."""
    deadline = time.monotonic() + _REPLACE_WAIT_SECONDS
    while True:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not _IS_WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(_REPLACE_POLL_SECONDS)


def _atomic_write(target: Path, content: str) -> None:
    """Crash-safe write via temp + fsync + rename, as skf-forge-tier-rw.py's _atomic_write does."""
    tmp = target.with_name(f"{target.name}.skf-{secrets.token_hex(4)}-tmp")
    # O_BINARY (Windows only; 0 elsewhere) keeps \n from turning into \r\n.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(tmp, flags, 0o644)
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        _replace(tmp, target)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _set_aside(cache: Path) -> Path:
    """Rename a corrupt cache to <cache>.corrupt-<UTC stamp>, never over an earlier one."""
    stamp = datetime.now(timezone.utc).strftime(CORRUPT_STAMP_FORMAT)
    aside = cache.with_name(f"{cache.name}.corrupt-{stamp}")
    n = 2
    while os.path.lexists(aside):
        aside = cache.with_name(f"{cache.name}.corrupt-{stamp}-{n}")
        n += 1
    _replace(cache, aside)
    return aside


def _merge(cache: Path, fp: str, new: dict, regression: bool) -> dict:
    """The read, merge and write; runs while the caller holds the lock."""
    set_aside = None
    try:
        raw = cache.read_bytes()
    except FileNotFoundError:
        data = {}
    else:
        data = _parse(raw)
        if data is None:
            try:
                set_aside = _set_aside(cache)
            except OSError as exc:
                raise WriteError(f"cannot set aside {cache}, which is not a JSON object: {exc}. "
                                 f"Nothing was written.") from None
            data = {}
    existing = data.get(fp)
    if isinstance(existing, dict) and existing.get("action") == RESOLVED and not regression:
        # Never downgrade a fix: only an open issue that tracks the recurrence replaces it.
        return {"written": False, "fp": fp, "record": existing, "set_aside": None}
    data[fp] = new
    try:
        _atomic_write(cache, json.dumps(data, indent=2) + "\n")
    except OSError as exc:
        where = f" (the corrupt cache was renamed to {set_aside})" if set_aside else ""
        raise WriteError(f"cannot write {cache}: {exc}{where}") from None
    return {"written": True, "fp": fp, "record": new, "set_aside": str(set_aside) if set_aside else None}


def record(fp: str, action: str, issue_url: str, day: str, regression: bool, cache: Path) -> dict:
    """Set the --fp record under <cache>.lock. Raises UsageError or WriteError."""
    _check_record_args(fp, action, issue_url, day)
    new = {"issue_url": issue_url, "action": action, "date": day}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        run_lock = _load(RUN_LOCK_HELPER)
    except (ImportError, OSError, SyntaxError) as exc:
        raise WriteError(f"cannot prepare {cache}: {exc}") from None
    lock = cache.with_name(cache.name + ".lock")
    owner = f"health-check-seen:record:{run_lock.new_run_id()}"
    try:
        run_lock.acquire_within(lock, owner, LOCK_STALE_SEC, LOCK_WAIT_SEC, empty_is_stale=True)
    except run_lock.LockBusy as busy:
        info = busy.result
        raise WriteError(f"{lock} is held by {info['held_by'] or 'an unnamed owner'} since {info['held_since']}: "
                         f"another run is writing {cache.name}. Nothing was written.") from None
    except (OSError, ValueError) as exc:
        raise WriteError(f"cannot take {lock}: {exc}") from None
    try:
        try:
            return _merge(cache, fp, new, regression)
        except OSError as exc:
            raise WriteError(f"cannot read {cache}: {exc}") from None
    finally:
        try:
            run_lock.release(lock, owner)
        except (OSError, ValueError):
            pass  # a lock this call could not delete goes stale on its own


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _error(message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)


class _JsonErrorParser(argparse.ArgumentParser):
    """Report a usage error as a JSON error with exit 2, like every value that breaks its rule."""

    def error(self, message: str) -> None:
        _error(f"usage error: {self.prog}: {message}")
        sys.exit(2)


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonErrorParser(
        description="Fingerprint a health-check finding, look it up in the seen-issue cache, record it there.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="{fingerprint,lookup,record}")

    p_fp = sub.add_parser("fingerprint", help="print the fingerprint and the section (legacy) fingerprint")
    p_fp.add_argument("--severity", required=True, choices=SEVERITIES)
    p_fp.add_argument("--workflow", required=True, help="the workflow name, hashed as given")
    p_fp.add_argument("--step-file", required=True, dest="step_file", help="the step file path, hashed as given")
    p_fp.add_argument("--section", required=True, help="the kebab-case section heading slug")
    p_fp.add_argument("--defect-key", required=True, dest="defect_key",
                      help="one to four lower-case words joined by hyphens")

    p_lookup = sub.add_parser("lookup", help="the verdict for a finding from the seen-issue cache")
    p_lookup.add_argument("--fp", required=True)
    p_lookup.add_argument("--legacy-fp", required=True, dest="legacy_fp")
    p_lookup.add_argument("--cache", help="the cache file (default $HOME/.skf/health-check-seen.json)")

    p_record = sub.add_parser("record", help="record a finding's issue in the seen-issue cache")
    p_record.add_argument("--fp", required=True)
    p_record.add_argument("--action", required=True, choices=WRITTEN_ACTIONS)
    p_record.add_argument("--issue-url", required=True, dest="issue_url")
    p_record.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_record.add_argument("--regression", action="store_true",
                          help="after a regression verdict: the issue tracks the recurrence, so it replaces a resolved "
                               "record")
    p_record.add_argument("--cache", help="the cache file (default $HOME/.skf/health-check-seen.json)")
    return parser


def _cache_arg(value: str | None) -> Path:
    return Path(value).expanduser() if value else default_cache()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "fingerprint":
            out = fingerprint(args.severity, args.workflow, args.step_file, args.section, args.defect_key)
        elif args.cmd == "lookup":
            out = lookup(args.fp, args.legacy_fp, _cache_arg(args.cache))
        else:
            out = record(args.fp, args.action, args.issue_url, args.date, args.regression, _cache_arg(args.cache))
    except UsageError as exc:
        _error(str(exc))
        return 2
    except WriteError as exc:
        _error(str(exc))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
