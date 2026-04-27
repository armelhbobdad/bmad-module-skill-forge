# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Detect Tools — Parallel tool detection + tier calculation for skf-setup.

Replaces the prose-driven tool-detection sequence in `src/skf-setup/steps-c/
step-01-detect-and-tier.md` §3-§8b with one Python invocation. Probes ast-grep,
gh, qmd, and ccc concurrently, applies the 4-rule tier decision table (see
`src/skf-setup/references/tier-rules.md`), evaluates --tier-override (with
sanity check) and --require-tier (with tool-prerequisite check independent of
the tier name), and emits one JSON document on stdout.

Schema documented in DETECT_OUTPUT_SCHEMA at the bottom of this docstring.
The output is consumed by step-01 prose, step-02 (forge-tier.yaml writer),
and step-04 (status report + envelope).

Tier rules (first match wins):
  Deep   = ast-grep + gh-cli + qmd (all healthy)
  Forge+ = ast-grep + ccc (regardless of gh/qmd)
  Forge  = ast-grep
  Quick  = otherwise

CCC verification is two-step (matches step-01 §7):
  Step A: `ccc --help` exits 0 AND output contains "CocoIndex Code" marker.
          Rejects code2prompt-aliased-as-ccc and similar PATH shadowing.
  Step B: `ccc doctor` succeeds (daemon healthy).

QMD verification is two-step (matches step-01 §5 post-PR-#248):
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
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


VALID_TIERS = ("Quick", "Forge", "Forge+", "Deep")
PROBE_TIMEOUT_SEC = 8  # per-tool subprocess.run timeout
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
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
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

    return {
        "tools": tools,
        "tier": {
            "calculated": calculated,
            "detected": detected,
            "override_applied": override_applied,
            "override_value": override_value,
            "override_invalid": override_invalid,
            "override_invalid_value": override_invalid_value,
            "override_unsafe": override_unsafe,
            "override_unsafe_missing": override_unsafe_missing,
        },
        "require_tier": {
            "requested": args.require_tier,
            "satisfied": require_satisfied,
            "missing_tools": require_missing,
        },
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
             " Invalid values are flagged in the output rather than rejected, so step-04 can"
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
    args = parser.parse_args()

    payload = detect(args)
    _ok(payload)


if __name__ == "__main__":
    main()
