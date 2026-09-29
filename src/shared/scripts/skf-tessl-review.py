# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Tessl Review — the optional Tessl Review for create-skill and test-skill.

Tessl Review (`tessl review run`) scores a skill on Tessl's servers: validation
checks plus two AI judges, one for the frontmatter description and one for
the content. It needs a Tessl account, uploads the skill's files, keeps each
review in a Tessl workspace's history and spends Tessl credits, so SKF runs it
only when the user names that workspace as `tessl_review_workspace` in the
forger-sidecar preferences.yaml. This helper owns every decision around the
review, so the step files hold no tessl commands:

  submit   read the preference, find tessl, check the sign-in, copy the
           skill's own files into a temporary folder, send that copy to
           Tessl Review without waiting for the review (`--no-wait`), remove
           the copy and print one JSON result: `pending` with Tessl's run id,
           or why no review was started.
  collect  check a submitted review (`tessl review view <run-id> --json`)
           every POLL_INTERVAL_SEC seconds for up to --max-seconds (at most
           COLLECT_MAX_SEC) and print `pending` again or the finished
           result. A check that fails without an answer SKF can read, or
           does not answer in time, is tried again: Tessl may still finish
           the review. With --final, a review SKF did not see finish is
           `timeout`. collect runs no other tessl command; it repeats the
           submit result's workspace and tessl version (--workspace,
           --tessl-version) in its result.
  parse    normalize a saved `tessl review run --json` or `tessl review view
           --json` output (for tests and for re-reading a review by hand).

A fresh review takes Tessl about two minutes, as long as some shell tools
allow one command, so no call waits for a whole review: every call ends
within two minutes, the tessl calls' own time limits included (on a limit
the helper kills tessl and everything it started). The calling step runs
collect again while the result is `pending`, at most MAX_COLLECTS times,
the last one with --final.

Only SKILL.md and the references/, scripts/ and assets/ folders are uploaded,
without links. metadata.json, context-snippet.md and the workspace artifacts
create-skill stages beside them (provenance-map.json, evidence-report.md)
stay on the machine. Every tessl call runs with a temporary folder as its
working directory, so tessl never reads or writes the user's project.

Output (stdout, one JSON object with every key in RESULT_KEYS, every
subcommand):
  status                 one of STATUSES
  summary                one line; the reports record `Tessl Review: <summary>`
  detail                 diagnostic text, or null
  workspace              the workspace the review was submitted to, or null
  tessl_version          x.y.z (from submit's `tessl --version`), or null
  exit_code              exit code of the last `tessl review run` or
                         `tessl review view`, or null
  run_id                 Tessl's reviewRunId, or null before a submit
  review_score           0-100 (review.reviewScore), or null
  description_score      0-100 (description judge), or null
  content_score          0-100 (content judge), or null
  validation             null, or {passed, errors, warnings,
                         findings: [{name, status, message}]}
  description_suggestions, content_suggestions   lists of strings
  warnings               lines for the reports' warnings: a score below
                         SCORE_FLOOR, validation errors, or, for every status
                         but `reviewed` and `off`, the summary itself

Exit codes:
  0  a result was printed (every status, including off and failed)
  2  usage error (argparse)

It never passes --force, --threshold or --label to tessl, never waits for a
review in one call, never installs tessl and never follows a link inside the
skill folder.

CLI (uv run, for the PEP 723 pyyaml dependency):
  uv run skf-tessl-review.py submit <skill-dir> --preferences <preferences.yaml>
  uv run skf-tessl-review.py collect <run-id> [--workspace <name>] [--tessl-version <x.y.z>]
                                     [--max-seconds N] [--final]
  uv run skf-tessl-review.py parse <saved-review.json>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

PREF_KEY = "tessl_review_workspace"
PROBE_TIMEOUT_SEC = 20  # tessl --version, tessl whoami (submit only)
SUBMIT_TIMEOUT_SEC = 45  # tessl review run --no-wait (about 7 seconds observed)
VIEW_TIMEOUT_SEC = 20  # one tessl review view
POLL_INTERVAL_SEC = 10  # pause between two views in one collect
COLLECT_MAX_SEC = 90  # default and upper bound of collect --max-seconds
KILL_WAIT_SEC = 5  # each wait after a time limit: taskkill, then the child
MAX_COLLECTS = 6  # collect calls a step makes before it gives up (the last with --final)
SCORE_FLOOR = 60
STATUSES = (
    "reviewed", "pending", "off", "invalid-config", "not-installed", "signed-out",
    "command-unavailable", "unknown-run", "timeout", "failed", "parse-failure",
)
RESULT_KEYS = (
    "status", "summary", "detail", "workspace", "tessl_version", "exit_code",
    "run_id", "review_score", "description_score", "content_score", "validation",
    "description_suggestions", "content_suggestions", "warnings",
)
# Run statuses tessl reports before a review finishes: `review run --no-wait`
# answers pending and `review view` incomplete; running and queued are
# accepted too, so a renamed in-progress status is not read as a failure.
PENDING_RUN_STATUSES = ("pending", "incomplete", "running", "queued")
BUNDLE_DIRS = ("references", "scripts", "assets")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
STATUS_GLYPHS = "✘✔⚠✖✓✗!•› \t"
# tessl's stub for a removed command, and its unknown-command error.
REMOVED_RE = re.compile(r"has been replaced|has been removed|no command registered", re.IGNORECASE)
SIGNED_OUT_RE = re.compile(r"not logged in|please authenticate|tessl login", re.IGNORECASE)
UNKNOWN_RUN_RE = re.compile(r"could not find review run", re.IGNORECASE)
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")  # used with fullmatch
# Used with fullmatch. On Windows tessl is often an npm .cmd shim that cmd.exe
# parses, so a workspace name never carries &, |, ^, % or quotes.
WORKSPACE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

SUMMARIES = {
    "off": f"off — set {PREF_KEY} in preferences.yaml to enable",
    "not-installed": "not run — tessl is not installed",
    "signed-out": "not run — not signed in to Tessl (run tessl login, or set TESSL_TOKEN)",
    "command-unavailable": "not run — the installed tessl has no working review run command (update tessl)",
}


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


def _resolve_outside_cwd(command: str) -> str | None:
    """shutil.which with a CWD-shim guard. Returns the resolved path or None.

    shutil.which on Windows searches the current directory ahead of PATH,
    and CWD here is the user's project — a bare-name lookup resolving into
    CWD would execute a planted shim (e.g. tessl.cmd). Such a resolution is
    treated as not-found. Explicit paths supplied by callers (containing a
    separator) are honored as-is. Keep the code identical to the sibling
    guards in skf-merge-ccc-exclusions.py, skf-detect-tools.py,
    skf-qmd-classify-collections.py, skf-ccc-git-hygiene.py,
    skf-source-tree.py and skf-verify-provenance-completeness.py
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


def _result(status: str, summary: str, **fields) -> dict:
    """A result with every key in RESULT_KEYS; `fields` overrides the defaults."""
    out = {key: None for key in RESULT_KEYS}
    out.update({"description_suggestions": [], "content_suggestions": [], "warnings": []})
    out.update(status=status, summary=summary)
    out.update(fields)
    if status not in ("reviewed", "off") and not out["warnings"]:
        out["warnings"] = [f"Tessl Review: {summary}"]
    return out


def _in_workspace(workspace: str | None) -> str:
    return f" in workspace {workspace}" if workspace else ""


def _pending(run_id: str, workspace: str | None = None, **fields) -> dict:
    summary = (f"no result yet — Tessl Review run {run_id} has not finished{_in_workspace(workspace)} "
               f"(tessl review view {run_id})")
    return _result("pending", summary, run_id=run_id, workspace=workspace, **fields)


def _timed_out(run_id: str, workspace: str | None = None, **fields) -> dict:
    summary = (f"no result — Tessl Review run {run_id} did not finish while SKF waited; it may still "
               f"finish{_in_workspace(workspace)} (tessl review view {run_id})")
    return _result("timeout", summary, run_id=run_id, workspace=workspace, **fields)


def _lines(text: str) -> list[str]:
    """Non-empty lines without ANSI codes or leading status glyphs."""
    out = []
    for line in ANSI_RE.sub("", text or "").splitlines():
        stripped = line.strip().lstrip(STATUS_GLYPHS).strip()
        if stripped:
            out.append(stripped)
    return out


def _first_line(text: str) -> str | None:
    lines = _lines(text)
    return lines[0] if lines else None


def _now() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


# --- preferences ------------------------------------------------------------


def load_workspace(prefs_path: Path) -> tuple[str, str | None, str | None]:
    """Return (state, workspace, reason) from preferences.yaml.

    state is "on", "off" or "invalid". Only a usable workspace name turns the
    review on. A missing or unreadable file, invalid YAML, an absent key or
    a null, false or empty value is off. Any other value is invalid: the
    user tried to opt in, and the report says why it did not work.
    """
    try:
        text = prefs_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "off", None, None
    except (OSError, UnicodeDecodeError) as exc:
        return "off", None, f"cannot read {prefs_path.as_posix()}: {exc}"
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return "off", None, f"preferences.yaml is not valid YAML: {exc}"
    if not isinstance(data, dict):
        return "off", None, None
    value = data.get(PREF_KEY)
    if value is None or value is False or value == "":
        return "off", None, None
    if not isinstance(value, str) or not WORKSPACE_RE.fullmatch(value):
        return "invalid", None, (f"{PREF_KEY} must be a Tessl workspace name of letters, digits, '.', '_' "
                                 f"and '-' (got {value!r})")
    return "on", value, None


# --- parsing ----------------------------------------------------------------


def _extract_json(text: str):
    stripped = (text or "").strip()
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    lines = stripped.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("{"):
            try:
                return json.loads("\n".join(lines[i:]))
            except ValueError:
                return None
    return None


def _percent(value) -> int | None:
    """0-1 fraction to a whole percent, rounding half up as tessl displays it."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or value > 1:
        return None
    return int(math.floor(value * 100 + 0.5))


def _count(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _judge(judges: dict, name: str) -> tuple[int | None, list[str]]:
    judge = judges.get(name)
    if not isinstance(judge, dict) or judge.get("success") is not True:
        return None, []
    evaluation = judge.get("evaluation") if isinstance(judge.get("evaluation"), dict) else {}
    raw = evaluation.get("suggestions")
    suggestions = [s.strip() for s in raw if isinstance(s, str) and s.strip()] if isinstance(raw, list) else []
    return _percent(judge.get("normalizedScore")), suggestions


def parse_review(data) -> dict:
    """Normalize a parsed, finished `tessl review run|view --json` object. Never raises."""
    if not isinstance(data, dict):
        why = "no JSON object"
        return _result("parse-failure", f"failed — Tessl Review output could not be read ({why})", detail=why)
    run_id = data.get("reviewRunId") if isinstance(data.get("reviewRunId"), str) else None
    run_status = data.get("status")
    if run_status is not None and run_status != "completed":
        detail = f"Tessl Review run {run_id or '(no id)'} ended with status {run_status!r}"
        return _result("failed", f"failed — {detail}", detail=detail, run_id=run_id)
    review = data.get("review")
    score = review.get("reviewScore") if isinstance(review, dict) else None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
        why = "no review.reviewScore from 0 to 100"
        return _result("parse-failure", f"failed — Tessl Review output could not be read ({why})",
                       detail=why, run_id=run_id)
    review_score = int(math.floor(score + 0.5))
    raw_validation = data.get("validation") if isinstance(data.get("validation"), dict) else {}
    checks = raw_validation.get("checks") if isinstance(raw_validation.get("checks"), list) else []
    passed = raw_validation.get("overallPassed")
    validation = {
        "passed": passed if isinstance(passed, bool) else None,
        "errors": _count(raw_validation.get("errorCount")),
        "warnings": _count(raw_validation.get("warningCount")),
        "findings": [
            {"name": str(c.get("name", "")), "status": str(c.get("status", "")), "message": str(c.get("message", ""))}
            for c in checks
            if isinstance(c, dict) and c.get("status") != "passed"
        ],
    }
    judges = data.get("judges") if isinstance(data.get("judges"), dict) else {}
    description_score, description_suggestions = _judge(judges, "description")
    content_score, content_suggestions = _judge(judges, "content")

    warnings = []
    for label, value in (("review score", review_score), ("description score", description_score),
                         ("content score", content_score)):
        if value is not None and value < SCORE_FLOOR:
            warnings.append(f"Tessl Review {label} {value}% is below {SCORE_FLOOR}%")
    if validation["errors"]:
        warnings.append(f"Tessl Review validation found {validation['errors']} error(s)")

    def pct(v):
        return "n/a" if v is None else f"{v}%"

    def num(v):
        return "n/a" if v is None else str(v)

    verdict = {True: "passed", False: "failed", None: "n/a"}[validation["passed"]]
    summary = (
        f"reviewed — score {review_score}% (description {pct(description_score)}, "
        f"content {pct(content_score)}, validation {verdict}: "
        f"{num(validation['errors'])} errors, {num(validation['warnings'])} warnings)"
    )
    return _result(
        "reviewed", summary,
        run_id=run_id,
        review_score=review_score,
        description_score=description_score,
        content_score=content_score,
        validation=validation,
        description_suggestions=description_suggestions,
        content_suggestions=content_suggestions,
        warnings=warnings,
    )


def interpret(data, workspace: str | None = None) -> dict:
    """Normalize a parsed `tessl review run|view --json` object: `pending` while
    the run is in progress, else parse_review. Never raises."""
    if isinstance(data, dict) and data.get("status") in PENDING_RUN_STATUSES:
        run_id = data.get("reviewRunId")
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            why = "a review in progress without a reviewRunId"
            return _result("parse-failure", f"failed — Tessl Review output could not be read ({why})",
                           detail=why, workspace=workspace)
        return _pending(run_id, workspace)
    result = parse_review(data)
    result["workspace"] = workspace
    return result


def classify(stdout: str, stderr: str, exit_code: int | None, run_id: str | None = None,
             workspace: str | None = None) -> dict:
    """Turn a finished `tessl review run --no-wait --json` or `tessl review view
    --json` call into a result.

    JSON on stdout wins whatever the exit code: tessl exits 1 with the full
    JSON when a score misses --threshold or validation fails. Without JSON,
    the removed-command text is checked first, then an unknown run id, then
    the sign-in text; a clean exit with no JSON is a parse failure, anything
    else a failure.
    """
    data = _extract_json(stdout)
    if data is not None:
        result = interpret(data, workspace)
        if result["run_id"] is None:
            result["run_id"] = run_id
        return result
    common = {"run_id": run_id, "workspace": workspace}
    text = f"{stderr}\n{stdout}"
    message = _first_line(stderr) or _first_line(stdout) or f"tessl exited with code {exit_code}"
    if REMOVED_RE.search(text):
        return _result("command-unavailable", SUMMARIES["command-unavailable"], detail=message, **common)
    if UNKNOWN_RUN_RE.search(text):
        summary = f"no result — Tessl has no review run {run_id} (tessl review list shows the runs)"
        return _result("unknown-run", summary, detail=message, **common)
    if SIGNED_OUT_RE.search(text):
        return _result("signed-out", SUMMARIES["signed-out"], detail=message, **common)
    if exit_code == 0:
        why = "tessl printed no JSON"
        return _result("parse-failure", f"failed — Tessl Review output could not be read ({why})",
                       detail=message, **common)
    summary = f"failed — {message}"
    if "workspace" in message.lower():
        summary += f" (check {PREF_KEY} in preferences.yaml; tessl workspace list shows yours)"
    return _result("failed", summary, detail=message, **common)


# --- running tessl ----------------------------------------------------------


def resolve_tessl() -> list[str] | None:
    """tessl on PATH first, else the npm launcher already in the npx cache (never installed)."""
    exe = _resolve_outside_cwd("tessl")
    if exe:
        return [exe]
    npx = _resolve_outside_cwd("npx")
    if npx:
        return [npx, "--no-install", "tessl"]
    return None


def _kill_tree(proc: subprocess.Popen, windows: bool = os.name == "nt") -> None:
    """Kill the child and everything it started (the npm launcher starts the tessl binary)."""
    try:
        if windows:
            taskkill = _resolve_outside_cwd("taskkill")
            if taskkill:
                subprocess.run([taskkill, "/F", "/T", "/PID", str(proc.pid)], stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=KILL_WAIT_SEC, check=False)
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


def _run(cmd: list[str], timeout: float, cwd: str) -> tuple[int | None, str, str, bool]:
    """Run cmd in cwd; return (returncode, stdout, stderr, timed_out).

    returncode is None when the command timed out or could not start. Output
    goes to temporary files, not pipes, so a grandchild that keeps a pipe
    open cannot block the wait after a timeout; the child gets its own
    process group (POSIX session) so the kill reaches the whole tree.
    """
    env = dict(os.environ)
    env["NO_COLOR"] = "1"
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out_f, stderr=err_f,
                                    cwd=cwd, env=env, **kwargs)
        except (OSError, ValueError) as exc:
            return None, "", f"cannot start {Path(cmd[0]).name}: {exc}", False
        timed_out = False
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
            try:
                proc.wait(timeout=KILL_WAIT_SEC)
            except subprocess.TimeoutExpired:
                pass
            rc = None
        out_f.seek(0)
        err_f.seek(0)
        stdout = out_f.read().decode("utf-8", errors="replace")
        stderr = err_f.read().decode("utf-8", errors="replace")
    return rc, stdout, stderr, timed_out


def _raise(exc: OSError) -> None:
    raise exc


def stage_bundle(skill_dir: Path, dest_root: Path) -> Path:
    """Copy SKILL.md, references/, scripts/ and assets/ (no links) to dest_root/<skill-dir name>/.

    Probes with os.lstat and walks with onerror=_raise, so an unreadable
    folder raises OSError instead of silently shrinking the upload (Python
    3.14's pathlib reports such a folder as absent).
    """
    skill_dir = Path(os.path.abspath(skill_dir))
    target = dest_root / skill_dir.name
    target.mkdir()
    skill_md = skill_dir / "SKILL.md"
    if _is_link_or_junction(skill_md):
        raise OSError(f"{skill_md.as_posix()} is a link; SKF uploads no linked file")
    shutil.copyfile(skill_md, target / "SKILL.md")
    for entry in BUNDLE_DIRS:
        src = skill_dir / entry
        try:
            st = os.lstat(src)
        except FileNotFoundError:
            continue
        if _is_link_or_junction(src) or not stat.S_ISDIR(st.st_mode):
            continue
        for root, dirs, files in os.walk(src, onerror=_raise):
            root_path = Path(root)
            dirs[:] = sorted(d for d in dirs if not _is_link_or_junction(root_path / d))
            rel = root_path.relative_to(skill_dir)
            (target / rel).mkdir(parents=True, exist_ok=True)
            for name in sorted(files):
                file_path = root_path / name
                if _is_link_or_junction(file_path):
                    continue
                shutil.copyfile(file_path, target / rel / name)
    return target


def _probe_version(base: list[str], cwd: str, **common) -> tuple[str | None, dict | None]:
    """(version, None) when `tessl --version` answers, else (None, the result to print)."""
    rc, out, err, timed_out = _run([*base, "--version"], PROBE_TIMEOUT_SEC, cwd)
    if timed_out:
        detail = f"tessl --version did not answer within {PROBE_TIMEOUT_SEC} seconds"
        return None, _result("failed", f"failed — {detail}", detail=detail, **common)
    lines = _lines(out) if rc == 0 else []
    version = lines[-1] if lines else None  # the npm launcher may print a download notice first
    if not version:
        return None, _result("not-installed", SUMMARIES["not-installed"],
                             detail=_first_line(err) or _first_line(out), **common)
    return version, None


def submit_review(skill_dir: Path, prefs_path: Path) -> dict:
    """Send a copy of the skill to Tessl Review without waiting; `pending` with the run id on success."""
    state, workspace, reason = load_workspace(prefs_path)
    if state == "off":
        return _result("off", SUMMARIES["off"], detail=reason)
    if state == "invalid":
        return _result("invalid-config", f"not run — {reason}", detail=reason)
    try:
        os.stat(skill_dir / "SKILL.md")
    except OSError as exc:
        detail = f"cannot read {(skill_dir / 'SKILL.md').as_posix()}: {exc.strerror or exc}"
        return _result("failed", f"failed — {detail}", detail=detail, workspace=workspace)
    base = resolve_tessl()
    if base is None:
        return _result("not-installed", SUMMARIES["not-installed"], detail="neither tessl nor npx is on PATH",
                       workspace=workspace)
    with tempfile.TemporaryDirectory(prefix="skf-tessl-", ignore_cleanup_errors=True) as tmp:
        version, failure = _probe_version(base, tmp, workspace=workspace)
        if failure is not None:
            return failure
        rc, out, err, timed_out = _run([*base, "whoami"], PROBE_TIMEOUT_SEC, tmp)
        if timed_out:
            detail = f"tessl whoami did not answer within {PROBE_TIMEOUT_SEC} seconds"
            return _result("failed", f"failed — {detail}", detail=detail, workspace=workspace,
                           tessl_version=version)
        if rc != 0:
            message = _first_line(err) or _first_line(out) or f"tessl whoami exited with code {rc}"
            if SIGNED_OUT_RE.search(f"{err}\n{out}"):
                return _result("signed-out", SUMMARIES["signed-out"], detail=message, workspace=workspace,
                               tessl_version=version)
            return _result("failed", f"failed — tessl whoami: {message}", detail=message, workspace=workspace,
                           tessl_version=version)
        try:
            bundle = stage_bundle(skill_dir, Path(tmp))
        except OSError as exc:
            detail = f"cannot copy the skill's files: {exc}"
            return _result("failed", f"failed — {detail}", detail=detail, workspace=workspace,
                           tessl_version=version)
        cmd = [*base, "review", "run", str(bundle), "--workspace", workspace, "--no-wait", "--json"]
        rc, out, err, timed_out = _run(cmd, SUBMIT_TIMEOUT_SEC, tmp)
    # Leaving the block removed the copy: Tessl has it once `review run --no-wait` answers.
    if timed_out:
        detail = f"tessl review run did not answer within {SUBMIT_TIMEOUT_SEC} seconds"
        return _result("failed", f"failed — {detail}", detail=detail, workspace=workspace,
                       tessl_version=version)
    result = classify(out, err, rc, workspace=workspace)
    result.update(tessl_version=version, exit_code=rc)
    return result


def collect_review(run_id: str, workspace: str | None = None, max_seconds: float = COLLECT_MAX_SEC,
                   final: bool = False, tessl_version: str | None = None) -> dict:
    """Check a submitted review until it finishes or max_seconds (at most COLLECT_MAX_SEC) run out.

    Runs only `tessl review view`; workspace and tessl_version are the submit
    result's, repeated in this result. A view starts only when it and the
    pause before it still end within the budget, which starts before
    anything else, so the call's waiting stays within max(budget, one view)
    plus the kill waits. A view that does not answer in time, or that tessl
    answers with an error and no JSON (a network error, say), is retried like
    one that reports the run in progress: Tessl may still finish the review.
    Only JSON, an unknown run id, a sign-in error, a removed command or a
    tessl that cannot start ends the call early.
    """
    deadline = _now() + min(max(max_seconds, 0), COLLECT_MAX_SEC)
    common = {"run_id": run_id, "workspace": workspace, "tessl_version": tessl_version}
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        detail = f"{run_id!r} is not a Tessl review run id"
        return _result("unknown-run", f"no result — Tessl has no review run {run_id!r}: it is not a run id",
                       detail=detail, **common)
    base = resolve_tessl()
    if base is None:
        return _result("not-installed", SUMMARIES["not-installed"], detail="neither tessl nor npx is on PATH",
                       **common)
    rc, detail = None, None
    with tempfile.TemporaryDirectory(prefix="skf-tessl-", ignore_cleanup_errors=True) as tmp:
        while True:
            rc, out, err, timed_out = _run([*base, "review", "view", run_id, "--json"], VIEW_TIMEOUT_SEC, tmp)
            if timed_out:
                detail = f"tessl review view did not answer within {VIEW_TIMEOUT_SEC} seconds"
            else:
                result = classify(out, err, rc, run_id=run_id, workspace=workspace)
                result.update(tessl_version=tessl_version, exit_code=rc)
                retry = (rc is not None and _extract_json(out) is None
                         and result["status"] in ("failed", "parse-failure"))
                if result["status"] != "pending" and not retry:
                    return result
                detail = f"tessl review view: {result['detail']}" if retry else None
            if _now() + POLL_INTERVAL_SEC + VIEW_TIMEOUT_SEC > deadline:
                break
            _sleep(POLL_INTERVAL_SEC)
    if final:
        return _timed_out(run_id, workspace, detail=detail, tessl_version=tessl_version, exit_code=rc)
    return _pending(run_id, workspace, detail=detail, tessl_version=tessl_version, exit_code=rc)


# --- CLI --------------------------------------------------------------------


def _force_utf8(*streams) -> None:
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors=getattr(stream, "errors", None) or "strict")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skf-tessl-review", description="Optional Tessl Review for SKF skills.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_submit = sub.add_parser("submit", help=f"send a skill folder to Tessl Review when preferences.yaml sets {PREF_KEY}")
    p_submit.add_argument("skill_dir")
    p_submit.add_argument("--preferences", required=True)
    p_collect = sub.add_parser("collect", help="check a submitted review and print its result or pending")
    p_collect.add_argument("run_id")
    p_collect.add_argument("--workspace", default=None, help="the workspace named in the result (the submit result's)")
    p_collect.add_argument("--tessl-version", default=None,
                           help="the tessl version named in the result (the submit result's)")
    p_collect.add_argument("--max-seconds", type=int, default=COLLECT_MAX_SEC,
                           help=f"how long to keep checking, at most {COLLECT_MAX_SEC} (larger values count as {COLLECT_MAX_SEC})")
    p_collect.add_argument("--final", action="store_true", help="report a review still running as timeout")
    p_parse = sub.add_parser("parse", help="normalize a saved `tessl review run|view --json` output")
    p_parse.add_argument("file")
    return parser


def _given(value: str | None) -> str | None:
    """A value repeated from the submit result; empty or a rendered null means none."""
    value = (value or "").strip()
    return None if value.lower() in ("", "null", "none", "~") else value


def main(argv=None) -> int:
    _force_utf8(sys.stdout)
    args = _build_parser().parse_args(argv)
    if args.cmd == "submit":
        result = submit_review(Path(args.skill_dir), Path(args.preferences))
    elif args.cmd == "collect":
        result = collect_review(args.run_id, _given(args.workspace), args.max_seconds, args.final,
                                _given(args.tessl_version))
    else:
        try:
            text = Path(args.file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            result = _result("parse-failure", f"failed — cannot read {args.file}: {exc}", detail=str(exc))
        else:
            result = interpret(_extract_json(text))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
