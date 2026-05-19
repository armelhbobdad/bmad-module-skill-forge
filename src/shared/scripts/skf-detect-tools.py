# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Detect Tools — Parallel tool detection + tier calculation for skf-setup.

Replaces the prose-driven tool-detection sequence in `src/skf-setup/references/
detect-and-tier.md` §3-§8b with one Python invocation. Probes ast-grep,
gh, qmd, and ccc concurrently, applies the 4-rule tier decision table (see
`src/skf-setup/references/tier-rules.md`), evaluates --tier-override (with
sanity check) and --require-tier (with tool-prerequisite check independent of
the tier name), and emits one JSON document on stdout.

Schema documented in DETECT_OUTPUT_SCHEMA at the bottom of this docstring.
The output is consumed by step 1 prose, step 2 (forge-tier.yaml writer),
and step 4 (status report + envelope).

Tier rules (first match wins):
  Deep   = ast-grep + gh-cli + qmd (all healthy)
  Forge+ = ast-grep + ccc (regardless of gh/qmd)
  Forge  = ast-grep
  Quick  = otherwise

CCC verification is two-step (matches step 1 §7):
  Step A: `ccc --help` exits 0 AND output contains "CocoIndex Code" marker.
          Rejects code2prompt-aliased-as-ccc and similar PATH shadowing.
  Step B: `ccc doctor` succeeds (daemon healthy).

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

Bare `python3` works when dependencies = [] (this script's case) but
becomes brittle the moment a non-stdlib dep is added — prefer `uv run`
for invocation consistency with sibling scripts that DO require pyyaml.

DETECT_OUTPUT_SCHEMA (v1):
  {
    "status": "ok",
    "version": "v1",
    "tools": {
      "ast_grep":      {"available": bool, "version": str|null},
      "gh_cli":        {"available": bool, "version": str|null},
      "qmd":           {"available": bool, "status": "absent"|"daemon_stopped"|"healthy",
                        "version": str|null},
      "ccc":           {"available": bool, "daemon": "healthy"|"stopped"|"error"|null,
                        "version": str|null},
      "security_scan": {"available": bool}
    },
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
    }
  }
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor


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


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
    sys.exit(code)


def _ok(payload: dict) -> None:
    payload.setdefault("status", "ok")
    payload.setdefault("version", "v1")
    print(json.dumps(payload))


def _run(cmd: list[str], timeout: int = PROBE_TIMEOUT_SEC) -> tuple[int, str, str]:
    """Run a subprocess. Return (returncode, stdout, stderr). Never raises.

    Treats every failure mode (FileNotFoundError, TimeoutExpired, OSError,
    CalledProcessError) as a failed probe — returns rc=127 and an empty
    stdout/stderr. Tool detection should never crash the workflow.

    The child is wrapped in the OS `timeout(1)` utility (when available) so a
    daemon-backed probe blocked in an uninterruptible syscall (e.g.
    `qmd status` waiting on its daemon socket) is reaped at the OS level —
    `subprocess.run`'s own post-timeout `process.wait()` is unbounded and
    would otherwise never return, hanging the whole detector. Child
    stdout/stderr are redirected to temp files (no pipe to drain), and
    `start_new_session=True` isolates the child's process group; the
    Python-level timeout is a secondary net set slightly above the OS one.
    """
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


def probe_ast_grep() -> dict:
    rc, stdout, _ = _run(["ast-grep", "--version"])
    if rc != 0:
        return {"available": False, "version": None}
    return {"available": True, "version": _first_line(stdout)}


def probe_gh_cli() -> dict:
    rc, stdout, _ = _run(["gh", "--version"])
    if rc != 0:
        return {"available": False, "version": None}
    return {"available": True, "version": _first_line(stdout)}


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

    rc_doctor, doctor_stdout, _ = _run(["ccc", "doctor"])
    version = _first_line(doctor_stdout) or _first_line(stdout)
    if rc_doctor == 0:
        return {"available": True, "daemon": "healthy", "version": version}
    # Distinguishing "stopped" from "error" requires parsing doctor output;
    # without a documented contract, default to "error" and let the caller
    # treat both as operational unavailability with daemon-level remediation.
    return {"available": True, "daemon": "error", "version": version}


def probe_security_scan(env_var: str) -> dict:
    """Informational only — does NOT affect tier."""
    return {"available": bool(os.environ.get(env_var, "").strip())}


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
    """For an invalid --tier-override value, return the closest valid tier name.

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
    }


def detect(args: argparse.Namespace) -> dict:
    tools: dict = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            "ast_grep": ex.submit(probe_ast_grep),
            "gh_cli":   ex.submit(probe_gh_cli),
            "qmd":      ex.submit(probe_qmd),
            "ccc":      ex.submit(probe_ccc),
        }
        for key, fut in futures.items():
            tools[key] = fut.result()
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
        if args.require_tier not in VALID_TIERS:
            _die(1, f"--require-tier must be one of {VALID_TIERS}, got {args.require_tier!r}")
        require_satisfied, require_missing = tier_prerequisites_met(args.require_tier, tools)
    else:
        require_satisfied = None

    prior = read_prior_state(getattr(args, "prior_state_from", None))
    deltas = compute_deltas(tools, prior, calculated)

    return {
        "tools": tools,
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
             " check, not tier-name comparison — Deep does not subsume Forge+ because Deep"
             " does not require ccc). Output reports satisfied/missing-tools; caller decides"
             " whether to halt.",
    )
    parser.add_argument(
        "--snyk-env-var",
        default="SNYK_TOKEN",
        help="Environment variable name to check for security-scan availability"
             " (informational only — does NOT affect tier). Default: SNYK_TOKEN.",
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


if __name__ == "__main__":
    main()
