# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Detect Tools — Parallel tool detection + tier calculation for skf-setup.

Replaces the prose-driven tool-detection sequence in `src/skf-setup/references/
detect-and-tier.md` §3-§8b with one Python invocation. Probes ast-grep,
gh, qmd, ccc, git and uv concurrently, holds each to its minimum version,
applies the 4-rule tier decision table (calculate_tier() below), evaluates
--tier-override (with sanity check) and --require-tier (with tool-prerequisite
check independent of the tier name), and emits one JSON document on stdout.

Minimum versions come from tool-requirements.yaml in the shared/ folder
above this script's scripts/ folder, in the source tree and in an installed
project alike. Each probed tool gets `minimum`, `meets_minimum` (null when
its version cannot be read or it has no minimum) and `below_minimum`. A tier
tool below its minimum is reported like a stopped qmd, `available: false`,
so the tier and --require-tier leave it out with no change to the rules
below; git and uv are no tier tools, so they only warn. A version the
script cannot read, a null minimum or a list it cannot read never lowers a
tier. `tools_below_minimum` lists each tool below its minimum with what the
setup report and envelope need to name it, since skf-emit-result-envelope.py
reads no YAML.

Schema documented in DETECT_OUTPUT_SCHEMA at the bottom of this docstring.
The output is consumed by step 1 prose, step 2 (forge-tier.yaml writer),
and step 4, where skf-emit-result-envelope.py reads the copy step 1 keeps
in the run folder (detect-tools.json) for the status report and envelope.

Tier rules (first match wins):
  Deep   = ast-grep + gh-cli + qmd (all healthy)
  Forge+ = ast-grep + ccc (regardless of gh/qmd)
  Forge  = ast-grep
  Quick  = otherwise

CCC verification is two-step (matches step 1 §7):
  Step A: `ccc --help` exits 0 AND output contains "CocoIndex Code" marker.
          Rejects code2prompt-aliased-as-ccc and similar PATH shadowing.
  Step B: `ccc doctor` succeeds (daemon healthy).
  ccc has no version flag: its version is the cocoindex-code line of
  `uv tool list` (`cocoindex-code v0.2.41`), null when uv did not install it.

QMD verification is two-step (matches step 1 §5 post-PR-#248):
  Step A: `qmd --version` exits 0 (binary identity, falls back to --help).
  Step B: `qmd status` succeeds (daemon healthy).
  qmd_status: "absent" | "daemon_stopped" | "healthy" — affects climb hint.

Exit codes:
  0  detection completed (status=ok in payload; require_tier may still be
     unsatisfied — that is a payload field, not an exit signal here)
  1  user error (bad args)
  2  internal error (timeout, subprocess crash that escaped the per-probe
     guard)

CLI (canonical invocation is `uv run` so PEP 723 inline metadata is
honored — see docs/getting-started.md for why uv is the documented
runtime prerequisite):

  uv run skf-detect-tools.py
  uv run skf-detect-tools.py --tier-override Deep
  uv run skf-detect-tools.py --require-tier Forge+
  uv run skf-detect-tools.py --snyk-env-var SNYK_TOKEN

`uv run` installs pyyaml, which reads the prior state and the minimums;
under a bare `python3` without it, both read as absent.

DETECT_OUTPUT_SCHEMA (v1):
  {
    "status": "ok",
    "version": "v1",
    "tools": {
      # Every probed tool also has "minimum": str|null, "meets_minimum":
      # bool|null and "below_minimum": bool; "version" is the probe's first
      # output line (ccc's is the bare version).
      "ast_grep":      {"available": bool, "version": str|null},
      "gh_cli":        {"available": bool, "version": str|null},
      "qmd":           {"available": bool, "status": "absent"|"daemon_stopped"|"healthy",
                        "version": str|null},
      "ccc":           {"available": bool, "daemon": "healthy"|"stopped"|"error"|null,
                        "version": str|null},
      "git":           {"available": bool, "version": str|null},
      "uv":            {"available": bool, "version": str|null},
      "security_scan": {"available": bool}
    },
    "tools_below_minimum": [
      # One per tool below its minimum, in the order of tool-requirements.yaml.
      {"tool": str, "name": str, "version": str, "minimum": str,
       "upgrade": str|null, "tier": "Forge"|"Forge+"|"Deep"|null}
    ],
    "tier": {
      "calculated":              "Quick"|"Forge"|"Forge+"|"Deep",
      "detected":                "Quick"|"Forge"|"Forge+"|"Deep",
      "override_applied":        bool,
      "override_value":          str|null,
      "override_invalid":        bool,
      "override_invalid_value":  str|null,
      "override_invalid_suggestion": str|null,
      "override_unsafe":         bool,
      "override_unsafe_missing": [str]
    },
    "require_tier": {
      "requested":     "Quick"|"Forge"|"Forge+"|"Deep"|null,
      "satisfied":     bool|null,
      "missing_tools": [str]
    },
    "prior": {
      # Populated from --prior-state-from's forge-tier.yaml (first run: all null/empty).
      "previous_tier":                          "Quick"|"Forge"|"Forge+"|"Deep"|null,
      "previous_detection_date":                str|null,
      "previous_tools":                         {tool: bool, ...},
      "previous_ccc_index_status":              str|null,
      "previous_ccc_indexed_path":              str|null,
      "previous_ccc_last_indexed":              str|null,
      "previous_ccc_staleness_threshold_hours": int|null,
      "previous_ccc_file_count":                 int|null,
      # Deterministic CCC-index freshness verdict — computed against
      # --project-root and datetime.now(UTC) captured at detect time, so the
      # ccc-index.md step forwards a boolean (as --index-fresh) to
      # skf-merge-ccc-exclusions.py instead of doing timestamp math.
      "ccc_index_fresh":                        bool
    },
    "deltas": {
      "tools_added":   [str],
      "tools_removed": [str],
      "tier_changed":  bool
    }
  }
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


VALID_TIERS = ("Quick", "Forge", "Forge+", "Deep")
PROBE_TIMEOUT_SEC = 8  # per-tool subprocess.run timeout
# Prefer the OS `timeout(1)` utility to bound each probe. A daemon-backed
# tool (e.g. `qmd status`) can block in an uninterruptible syscall against
# its daemon; `subprocess.run`'s own post-timeout `process.wait()` is
# unbounded and never returns in that case, hanging the whole detector.
# `timeout --kill-after` reaps the child (and its session) at the OS level,
# so Python's wait always returns. POSIX-only: Windows' `timeout.exe` is an
# unrelated builtin (waits for input; cannot run a command), and the
# uninterruptible-wait hang is itself POSIX-specific (Windows uses a
# forcible TerminateProcess), so on Windows we fall back to subprocess.run's
# own timeout. None when unavailable.
_TIMEOUT_BIN = shutil.which("timeout") if os.name == "posix" else None
CCC_IDENTITY_MARKER = "cocoindex code"  # case-insensitive substring
# The one list of tool versions: shared/ holds it beside scripts/.
REQUIREMENTS_FILE = Path(__file__).resolve().parent.parent / "tool-requirements.yaml"
# The first x.y or x.y.z of a version line: `gh version 2.101.0 (2026-09-15)`.
VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
MINIMUM_RE = re.compile(r"\d+(?:\.\d+)*")
# `uv tool list` names each package uv installed, with its version.
CCC_PACKAGE_RE = re.compile(r"^cocoindex-code v(\S+)", re.MULTILINE)


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
    sys.exit(code)


def _ok(payload: dict) -> None:
    payload.setdefault("status", "ok")
    payload.setdefault("version", "v1")
    print(json.dumps(payload))


def _resolve_outside_cwd(command: str) -> str | None:
    """shutil.which with a CWD-shim guard. Returns the resolved path or None.

    shutil.which on Windows searches the current directory ahead of PATH,
    and CWD here is the repo under analysis — a bare-name lookup resolving
    into CWD would execute a repo-planted shim (e.g. ast-grep.cmd). Such a
    resolution is treated as not-found. Explicit paths supplied by callers
    (containing a separator) are honored as-is. Keep identical to the
    sibling guards in skf-qmd-classify-collections.py,
    skf-merge-ccc-exclusions.py, skf-ccc-git-hygiene.py,
    skf-source-tree.py, skf-tessl-review.py and
    skf-verify-provenance-completeness.py.
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


def _run(cmd: list[str], timeout: int = PROBE_TIMEOUT_SEC) -> tuple[int, str, str]:
    """Run a subprocess. Return (returncode, stdout, stderr). Never raises.

    Treats every failure mode (FileNotFoundError, TimeoutExpired, OSError,
    CalledProcessError) as a failed probe — returns rc=127 and an empty
    stdout/stderr. Tool detection should never crash the workflow.

    cmd[0] is resolved through shutil.which() before spawning (with the
    CWD-shim guard in _resolve_outside_cwd): Windows CreateProcess only
    ever appends .exe to a bare name, so npm-installed shims
    (ast-grep.CMD, qmd.CMD) would raise FileNotFoundError and read as
    "tool absent". An unresolvable command returns rc=127 without
    spawning anything.

    The child is wrapped in the OS `timeout(1)` utility (when available) so a
    daemon-backed probe blocked in an uninterruptible syscall (e.g.
    `qmd status` waiting on its daemon socket) is reaped at the OS level —
    `subprocess.run`'s own post-timeout `process.wait()` is unbounded and
    would otherwise never return, hanging the whole detector. Child
    stdout/stderr are redirected to temp files (no pipe to drain), and
    `start_new_session=True` isolates the child's process group; the
    Python-level timeout is a secondary net set slightly above the OS one.
    """
    resolved = _resolve_outside_cwd(cmd[0])
    if resolved is None:
        return 127, "", ""
    cmd = [resolved, *cmd[1:]]
    if _TIMEOUT_BIN:
        run_cmd = [_TIMEOUT_BIN, "--kill-after=2", str(timeout), *cmd]
        py_timeout = timeout + 5
    else:
        run_cmd = cmd
        py_timeout = timeout
    try:
        with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
            result = subprocess.run(
                run_cmd,
                stdin=subprocess.DEVNULL,
                stdout=out_f,
                stderr=err_f,
                timeout=py_timeout,
                check=False,
                start_new_session=True,
            )
            # Mocked unit tests patch `subprocess.run` to return a fake with
            # `.stdout`/`.stderr` strings set; real runs redirect to the temp
            # files (so `result.stdout` is None — read the files instead).
            stdout = result.stdout
            if stdout is None:
                out_f.seek(0)
                stdout = out_f.read().decode("utf-8", "replace")
            stderr = result.stderr
            if stderr is None:
                err_f.seek(0)
                stderr = err_f.read().decode("utf-8", "replace")
            return result.returncode, stdout or "", stderr or ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 127, "", ""


def _first_line(text: str) -> str | None:
    """Return the first non-empty stripped line of `text`, or None."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _probe_version(command: str) -> dict:
    """One `<command> --version` call: available, and the first output line."""
    rc, stdout, _ = _run([command, "--version"])
    if rc != 0:
        return {"available": False, "version": None}
    return {"available": True, "version": _first_line(stdout)}


def probe_ast_grep() -> dict:
    return _probe_version("ast-grep")


def probe_gh_cli() -> dict:
    return _probe_version("gh")


def probe_git() -> dict:
    """Not a tier tool: held to its minimum, which only warns."""
    return _probe_version("git")


def probe_uv() -> dict:
    """Not a tier tool: held to its minimum, which only warns."""
    return _probe_version("uv")


def probe_qmd() -> dict:
    """Two-step probe: --version (binary identity) then status (daemon health)."""
    rc, stdout, _ = _run(["qmd", "--version"])
    if rc != 0:
        # --version may not be supported on every qmd build; fall back to --help.
        rc, stdout, _ = _run(["qmd", "--help"])
        if rc != 0:
            return {"available": False, "status": "absent", "version": None}
    version = _first_line(stdout)

    rc_status, _, _ = _run(["qmd", "status"])
    if rc_status != 0:
        return {"available": False, "status": "daemon_stopped", "version": version}
    return {"available": True, "status": "healthy", "version": version}


def probe_ccc() -> dict:
    """Two-step probe: --help with identity marker, then doctor for daemon health."""
    rc, stdout, _ = _run(["ccc", "--help"])
    if rc != 0:
        return {"available": False, "daemon": None, "version": None}
    if CCC_IDENTITY_MARKER not in stdout.lower():
        # `ccc` resolved to a foreign binary (e.g. code2prompt alias). Refuse.
        return {"available": False, "daemon": None, "version": None}

    rc_doctor, _, _ = _run(["ccc", "doctor"])
    # ccc exposes no version CLI: `ccc --version` prints a usage banner, and
    # `ccc doctor` / `ccc --help` lead with a settings header ("Global
    # Settings") or usage line — never a version string. Capturing that first
    # line mislabels a header as a version, so report daemon health (below)
    # as ccc's identifier instead of a misparse.
    version = None
    if rc_doctor == 0:
        return {"available": True, "daemon": "healthy", "version": version}
    # Distinguishing "stopped" from "error" requires parsing doctor output;
    # without a documented contract, default to "error" and let the caller
    # treat both as operational unavailability with daemon-level remediation.
    return {"available": True, "daemon": "error", "version": version}


def probe_ccc_version() -> str | None:
    """ccc's version from `uv tool list`, or None when uv did not install it."""
    rc, stdout, _ = _run(["uv", "tool", "list"])
    match = CCC_PACKAGE_RE.search(stdout) if rc == 0 else None
    return found_version(match.group(1)) if match else None


def probe_security_scan(env_var: str) -> dict:
    """Informational only — does NOT affect tier."""
    return {"available": bool(os.environ.get(env_var, "").strip())}


def load_requirements(path=None) -> dict:
    """The tools of tool-requirements.yaml by key, or {} when it cannot be read.

    A list that is missing or not YAML gives no tool a minimum, so it holds
    none back.
    """
    try:
        import yaml  # local import, as in read_prior_state
        data = yaml.safe_load(Path(path or REQUIREMENTS_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}
    tools = data.get("tools") if isinstance(data, dict) else None
    if not isinstance(tools, dict):
        return {}
    return {key: entry for key, entry in tools.items() if isinstance(entry, dict)}


def found_version(text) -> str | None:
    """The first x.y or x.y.z of a version line, as written there, or None."""
    match = VERSION_RE.search(text) if isinstance(text, str) else None
    return match.group(0) if match else None


def meets_minimum(version, minimum) -> bool | None:
    """Whether a probed version is at least the minimum, missing parts read as 0.

    None when either cannot be read: a version SKF cannot parse, or a null
    minimum, never holds a tool back.
    """
    found = found_version(version)
    if found is None or not isinstance(minimum, str) or not MINIMUM_RE.fullmatch(minimum):
        return None
    have = [int(part) for part in found.split(".")]
    need = [int(part) for part in minimum.split(".")]
    width = max(len(have), len(need))
    return have + [0] * (width - len(have)) >= need + [0] * (width - len(need))


def apply_minimums(tools: dict, requirements: dict) -> list[dict]:
    """Hold each probed tool to its minimum; return the tools below theirs.

    Adds `minimum`, `meets_minimum` and `below_minimum` to every probed tool
    (security_scan is none). A tier tool below its minimum becomes
    `available: false`, so calculate_tier() and tier_prerequisites_met()
    leave it out; any other kind only warns. Each tool below its minimum
    gets one entry, in the list's order, naming it, its version and minimum,
    how to upgrade it and, for a tier tool, the first tier it counts toward.
    """
    below = []
    order = [*requirements, *(key for key in tools if key not in requirements)]
    for key in order:
        probe = tools.get(key)
        if key == "security_scan" or not isinstance(probe, dict):
            continue
        entry = requirements.get(key, {})
        minimum = entry.get("minimum") if isinstance(entry.get("minimum"), str) else None
        meets = meets_minimum(probe.get("version"), minimum)
        probe.update({"minimum": minimum, "meets_minimum": meets, "below_minimum": meets is False})
        if meets is not False:
            continue
        tier_tool = entry.get("kind") == "tier"
        if tier_tool:
            probe["available"] = False
        tiers = entry.get("tiers") if isinstance(entry.get("tiers"), list) else []
        upgrade = entry.get("upgrade")
        below.append({
            "tool": key,
            "name": str(entry.get("name") or key),
            "version": found_version(probe.get("version")),
            "minimum": minimum,
            "upgrade": " ".join(upgrade.split()) if isinstance(upgrade, str) and upgrade.strip() else None,
            "tier": str(tiers[0]) if tier_tool and tiers else None,
        })
    return below


def calculate_tier(tools: dict) -> str:
    ag = tools["ast_grep"]["available"]
    gh = tools["gh_cli"]["available"]
    qm = tools["qmd"]["available"]
    cc = tools["ccc"]["available"]

    if ag and gh and qm:
        return "Deep"
    if ag and cc:
        return "Forge+"
    if ag:
        return "Forge"
    return "Quick"


def suggest_valid_tier(bad_value: str) -> str | None:
    """For an invalid --tier-override or --require-tier value, return the closest valid tier name.

    Two-stage match:
    1. Case-insensitive exact match — handles `deep` / `DEEP` / `forge+` /
       `FORGE+` (the most common typo class: right tier, wrong case).
    2. difflib fuzzy match against `VALID_TIERS` with a 0.6 cutoff — handles
       `frorge`, `quik`, `forge plus`, etc.

    Returns None if no candidate clears the cutoff. Used only for diagnostic
    messages — the override itself is never silently auto-corrected.
    """
    import difflib

    if not bad_value or not isinstance(bad_value, str):
        return None
    cleaned = bad_value.strip()
    if not cleaned:
        return None
    cleaned_lower = cleaned.lower()
    for valid in VALID_TIERS:
        if valid.lower() == cleaned_lower:
            return valid
    matches = difflib.get_close_matches(cleaned, VALID_TIERS, n=1, cutoff=0.6)
    return matches[0] if matches else None


def require_tier_error(value) -> str | None:
    """The user error for a --require-tier value that is not a tier, or None.

    The check is exact (case-sensitive), so a typo fails closed instead of
    switching the tier gate off. The message names the valid tiers, adds
    suggest_valid_tier's did-you-mean when one clears its cutoff, and holds
    no quote, backslash or control character, even when the value does:
    skf-setup carries it into its blocked envelope's reason, inside a
    single-quoted shell payload.
    """
    if value in VALID_TIERS:
        return None
    valid = ", ".join(VALID_TIERS)
    safe = {"'": "`", '"': "`", "\\": "/"}
    shown = "".join("?" if ord(ch) < 0x20 or ord(ch) == 0x7F else safe.get(ch, ch) for ch in str(value))
    message = (f"--require-tier must be one of {valid} (case-sensitive), got "
               + (shown if shown.strip() else "an empty value"))
    suggestion = suggest_valid_tier(value)
    return f"{message}; did you mean {suggestion}?" if suggestion else message


def tier_prerequisites_met(tier: str, tools: dict) -> tuple[bool, list[str]]:
    """Return (satisfied, missing_tools) for tier-prerequisite checks.

    Used by both --tier-override sanity check and --require-tier evaluation.
    Deep does NOT subsume Forge+ (Deep does not require ccc), so a Deep
    calculation with no ccc still fails a Forge+ requirement.
    """
    needed: dict[str, str] = {
        "Quick": {},
        "Forge": {"ast_grep": "ast-grep"},
        "Forge+": {"ast_grep": "ast-grep", "ccc": "ccc"},
        "Deep": {"ast_grep": "ast-grep", "gh_cli": "gh", "qmd": "qmd"},
    }[tier]
    missing = [display for key, display in needed.items() if not tools[key]["available"]]
    return (len(missing) == 0, missing)


def read_prior_state(prior_state_path) -> dict:
    """Read forge-tier.yaml from a previous run, return prior tier / tools / detection_date.

    Returns a flat dict (always present, keys always set) so callers don't
    branch on missing-file vs empty-file vs malformed-file — the script owns
    that classification. On any read failure or absent file, returns the
    "first-run" shape (everything null/empty). The CCC freshness fields are
    surfaced separately so the caller doesn't reparse YAML in prose.
    """
    empty = {
        "previous_tier": None,
        "previous_detection_date": None,
        "previous_tools": {},
        "previous_ccc_index_status": None,
        "previous_ccc_indexed_path": None,
        "previous_ccc_last_indexed": None,
        "previous_ccc_staleness_threshold_hours": None,
        "previous_ccc_file_count": None,
    }
    if not prior_state_path:
        return empty
    try:
        import yaml  # local import — only needed when --prior-state-from is used
        from pathlib import Path as _P
        p = _P(prior_state_path)
        if not p.exists():
            return empty
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return empty

    tools_map = data.get("tools") if isinstance(data.get("tools"), dict) else {}
    ccc_index = data.get("ccc_index") if isinstance(data.get("ccc_index"), dict) else {}

    return {
        "previous_tier": data.get("tier") if data.get("tier") in VALID_TIERS else None,
        "previous_detection_date": data.get("tier_detected_at"),
        "previous_tools": tools_map,
        "previous_ccc_index_status": ccc_index.get("status"),
        "previous_ccc_indexed_path": ccc_index.get("indexed_path"),
        "previous_ccc_last_indexed": ccc_index.get("last_indexed"),
        "previous_ccc_staleness_threshold_hours": ccc_index.get("staleness_threshold_hours"),
        # Surfaced so ccc-index.md's fresh-index branch can carry the count
        # forward instead of leaving `{ccc_file_count}` unbound (or nulling a
        # value the index still has) when nothing re-indexes this run.
        "previous_ccc_file_count": ccc_index.get("file_count"),
    }


def _parse_iso_timestamp(value) -> datetime | None:
    """Parse an ISO 8601 timestamp into a timezone-aware datetime, or None.

    Normalizes a trailing 'Z' or 'z' (UTC designator) to '+00:00' because
    `datetime.fromisoformat` accepts 'Z' from Python 3.11 on (this script's
    floor) but still rejects 'z'. A naive result (no tzinfo) is assumed to be
    UTC so it can be compared against a tz-aware `now` without raising. Returns
    None on any parse failure (non-string, empty, malformed).
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text[-1] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_ccc_index_fresh(prior: dict, project_root, now: datetime) -> bool:
    """Deterministic freshness verdict for a prior CCC index.

    Replaces the ISO-8601 datetime arithmetic that ccc-index.md §2 used to ask
    the model to perform (parse a timestamp, subtract from now, convert to
    hours, compare against a threshold). Same inputs → same boolean.

    Returns True only when ALL hold:
      - the prior index covered this same project (indexed_path == project_root)
      - the prior index status is "fresh" or "created"
      - last_indexed parses AND (now - last_indexed) <= staleness threshold

    The staleness threshold defaults to 24 hours when the prior field is null
    (the staleness default in knowledge/ccc-bridge.md). Any null/unparseable required field
    (indexed_path, status, last_indexed), path mismatch, non-fresh status,
    unparseable threshold, or over-threshold delta yields False.
    """
    if not project_root:
        return False
    if prior.get("previous_ccc_indexed_path") != project_root:
        return False
    if prior.get("previous_ccc_index_status") not in ("fresh", "created"):
        return False

    last_indexed = _parse_iso_timestamp(prior.get("previous_ccc_last_indexed"))
    if last_indexed is None:
        return False

    threshold = prior.get("previous_ccc_staleness_threshold_hours")
    if threshold is None:
        threshold = 24
    try:
        threshold_hours = float(threshold)
    except (ValueError, TypeError):
        return False

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta_hours = (now - last_indexed).total_seconds() / 3600.0
    return delta_hours <= threshold_hours


def detect(args: argparse.Namespace) -> dict:
    # A --require-tier that names no tier is a user error: stop before
    # probing anything, so the caller's halt comes at once.
    if args.require_tier is not None:
        error = require_tier_error(args.require_tier)
        if error:
            _die(1, error)

    tools: dict = {}
    with ThreadPoolExecutor(max_workers=7) as ex:
        futures = {
            "ast_grep": ex.submit(probe_ast_grep),
            "gh_cli":   ex.submit(probe_gh_cli),
            "qmd":      ex.submit(probe_qmd),
            "ccc":      ex.submit(probe_ccc),
            "git":      ex.submit(probe_git),
            "uv":       ex.submit(probe_uv),
        }
        ccc_version = ex.submit(probe_ccc_version)
        for key, fut in futures.items():
            tools[key] = fut.result()
        if tools["ccc"]["available"]:
            tools["ccc"]["version"] = ccc_version.result()
    tools_below_minimum = apply_minimums(tools, load_requirements())
    tools["security_scan"] = probe_security_scan(args.snyk_env_var)

    detected = calculate_tier(tools)

    # Tier override handling
    override_applied = False
    override_value: str | None = None
    override_invalid = False
    override_invalid_value: str | None = None
    override_invalid_suggestion: str | None = None
    override_unsafe = False
    override_unsafe_missing: list[str] = []

    if args.tier_override is not None:
        if args.tier_override in VALID_TIERS:
            override_applied = True
            override_value = args.tier_override
            calculated = args.tier_override
            satisfied, missing = tier_prerequisites_met(calculated, tools)
            if not satisfied:
                override_unsafe = True
                override_unsafe_missing = missing
        else:
            override_invalid = True
            override_invalid_value = args.tier_override
            override_invalid_suggestion = suggest_valid_tier(args.tier_override)
            calculated = detected
    else:
        calculated = detected

    # Require-tier evaluation
    require_satisfied: bool | None
    require_missing: list[str] = []
    if args.require_tier is not None:
        require_satisfied, require_missing = tier_prerequisites_met(args.require_tier, tools)
    else:
        require_satisfied = None

    prior = read_prior_state(getattr(args, "prior_state_from", None))
    prior["ccc_index_fresh"] = compute_ccc_index_fresh(
        prior, getattr(args, "project_root", None), datetime.now(timezone.utc)
    )
    deltas = compute_deltas(tools, prior, calculated)

    return {
        "tools": tools,
        "tools_below_minimum": tools_below_minimum,
        "tier": {
            "calculated": calculated,
            "detected": detected,
            "override_applied": override_applied,
            "override_value": override_value,
            "override_invalid": override_invalid,
            "override_invalid_value": override_invalid_value,
            "override_invalid_suggestion": override_invalid_suggestion,
            "override_unsafe": override_unsafe,
            "override_unsafe_missing": override_unsafe_missing,
        },
        "require_tier": {
            "requested": args.require_tier,
            "satisfied": require_satisfied,
            "missing_tools": require_missing,
        },
        "prior": prior,
        "deltas": deltas,
    }


def compute_deltas(current_tools: dict, prior: dict, calculated_tier: str) -> dict:
    """Compute re-run deltas (tools added/removed, tier_changed, ccc_index_is_fresh).

    Removes ~80 tokens of LLM-side set arithmetic + string compare from the
    interactive banner branch in references/report.md. First-run convention
    (prior.previous_tier is null): tools_added = currently-available tools,
    tools_removed = [], tier_changed = false.
    """
    tool_keys = ("ast_grep", "gh_cli", "qmd", "ccc")
    cur_avail = {k: bool((current_tools.get(k) or {}).get("available")) for k in tool_keys}

    prev_tools_raw = prior.get("previous_tools") or {}
    if prev_tools_raw:
        prev_avail = {k: bool(prev_tools_raw.get(k, False)) for k in tool_keys}
        tools_added = sorted(k for k in tool_keys if cur_avail[k] and not prev_avail[k])
        tools_removed = sorted(k for k in tool_keys if prev_avail[k] and not cur_avail[k])
    else:
        tools_added = sorted(k for k in tool_keys if cur_avail[k])
        tools_removed = []

    prior_tier = prior.get("previous_tier")
    tier_changed = bool(prior_tier and prior_tier != calculated_tier)

    return {
        "tools_added": tools_added,
        "tools_removed": tools_removed,
        "tier_changed": tier_changed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect SKF tools and calculate capability tier.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tier-override",
        default=None,
        help="Force a specific tier (must be one of Quick, Forge, Forge+, Deep — case-sensitive)."
             " Invalid values are flagged in the output rather than rejected, so step 4 can"
             " surface the warning to the user.",
    )
    parser.add_argument(
        "--require-tier",
        default=None,
        help="Require the calculated tier to satisfy this requirement (uses tool-prerequisite"
             " check, not tier-name comparison: Deep does not subsume Forge+ because Deep"
             " does not require ccc). Output reports satisfied/missing-tools; caller decides"
             " whether to halt. A value that is not exactly Quick, Forge, Forge+ or Deep exits 1"
             " before any probe runs, naming the valid tiers.",
    )
    parser.add_argument(
        "--snyk-env-var",
        default="SNYK_TOKEN",
        help="Environment variable name to check for security-scan availability"
             " (informational only — does NOT affect tier). Default: SNYK_TOKEN.",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Absolute project root of the current run. Used only to compute"
             " prior.ccc_index_fresh: the prior CCC index counts as fresh only"
             " when its indexed_path equals this value (and its status/timestamp"
             " still qualify). Omitted → ccc_index_fresh is always false.",
    )
    parser.add_argument(
        "--prior-state-from",
        default=None,
        help="Optional path to a previous-run forge-tier.yaml. When provided,"
             " the script reads it and surfaces previous_tier, previous_tools,"
             " previous_detection_date, and previous_ccc_* fields under the 'prior'"
             " key — removing YAML-parse responsibility from the step prompt."
             " Missing file or unreadable YAML returns the first-run shape (all"
             " null/empty) without erroring.",
    )
    args = parser.parse_args()

    payload = detect(args)
    _ok(payload)


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    of the --help text, so --help would stop with UnicodeEncodeError.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    main()
