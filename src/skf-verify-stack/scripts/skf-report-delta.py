#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic previous-vs-current delta for skf-verify-stack (synthesize.md §3).

Reading two feasibility reports and deciding each finding's verdict is judgment;
classifying how the two runs differ is not. Given the two already-extracted
finding sets, "improved / regressed / new / unchanged" is a set-diff plus a
fixed verdict ranking — one correct answer per input. Doing it in prose lets the
counts drift (mismatched pair keys, inconsistent ranking), so it lives here.

Verdict ranking (higher = healthier):
  * coverage    — Missing(0) < Covered(1). Replaced is intentional removal, not a
    gap; Replaced findings are bucketed separately and never scored improved/
    regressed (mirrors their exclusion from the coverage denominator).
  * integration — Blocked(0) < Risky(1) < Plausible(2) < Verified(3).
  * confidence tier — T2(1) < T1-low(2) < T1(3); a drop is a regression.

Matching keys are normalized so identity is stable across runs:
  * coverage findings match on technology.lower()
  * integration findings match on the unordered pair {libA, libB} (lowercased),
    so "A↔B" in one run equals "B↔A" in the other.

CLI usage:
  uv run skf-report-delta.py '<JSON>'                  # JSON literal positional
  uv run skf-report-delta.py --json-input '<JSON>'     # explicit flag form
  cat input.json | uv run skf-report-delta.py --stdin  # piped input

Input schema (one object):
  {
    "previous": {
      "coverage":    [{"technology": "react", "verdict": "Covered"}, ...],
      "integration": [{"libA": "react", "libB": "express", "verdict": "Verified"}, ...]
    },
    "current":  { ... same shape ... },
    "previousTiers": {"react": "T1", ...},   # optional, skill_name -> tier
    "currentTiers":  {"react": "T2", ...}     # optional
  }

Output (stdout, one object):
  {
    "improved": [labels], "improvedCount": <int>,
    "regressed": [labels], "regressedCount": <int>,
    "unchanged": [labels], "unchangedCount": <int>,
    "new": [labels], "newCount": <int>,
    "dropped": [labels], "droppedCount": <int>,
    "replaced": [labels], "replacedCount": <int>,
    "tierDowngrades": [{"skill": "...", "from": "T1", "to": "T2"}],
    "tierDowngradeCount": <int>
  }

Exit codes:
  0  — delta emitted successfully
  1  — no input / input could not be parsed as JSON
  2  — input parsed but schema/semantics invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import json
import sys

COVERAGE_RANK = {"Missing": 0, "Covered": 1}
COVERAGE_VERDICTS = ("Covered", "Missing", "Replaced")
INTEGRATION_RANK = {"Blocked": 0, "Risky": 1, "Plausible": 2, "Verified": 3}
INTEGRATION_VERDICTS = tuple(INTEGRATION_RANK)
TIER_RANK = {"T2": 1, "T1-LOW": 2, "T1": 3, "T3": 0}


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


def _validate_side(side, name):
    if not isinstance(side, dict):
        return f"`{name}` must be an object with `coverage`/`integration` lists"
    cov = side.get("coverage", [])
    integ = side.get("integration", [])
    if not isinstance(cov, list) or not isinstance(integ, list):
        return f"`{name}.coverage` and `{name}.integration` must be lists"
    for i, row in enumerate(cov):
        if not isinstance(row, dict) or not isinstance(row.get("technology"), str):
            return f"`{name}.coverage[{i}]` requires a string `technology`"
        if row.get("verdict") not in COVERAGE_VERDICTS:
            return (
                f"`{name}.coverage[{i}]` verdict {row.get('verdict')!r} not one of: "
                f"{', '.join(COVERAGE_VERDICTS)}"
            )
    for i, row in enumerate(integ):
        if not isinstance(row, dict) or not isinstance(row.get("libA"), str) or not isinstance(row.get("libB"), str):
            return f"`{name}.integration[{i}]` requires string `libA` and `libB`"
        if row.get("verdict") not in INTEGRATION_VERDICTS:
            return (
                f"`{name}.integration[{i}]` verdict {row.get('verdict')!r} not one of: "
                f"{', '.join(INTEGRATION_VERDICTS)}"
            )
    return None


def _validate(inp):
    if inp is None or not isinstance(inp, dict):
        return "Input must be a JSON object"
    if "previous" not in inp or "current" not in inp:
        return "Input requires `previous` and `current` objects"
    for name in ("previous", "current"):
        err = _validate_side(inp[name], name)
        if err:
            return err
    for key in ("previousTiers", "currentTiers"):
        tiers = inp.get(key)
        if tiers is not None and not isinstance(tiers, dict):
            return f"`{key}` must be an object mapping skill_name -> tier"
    return None


def _index(side):
    """Return {normalized_key: (label, domain, verdict)} for one report side."""
    out = {}
    for row in side.get("coverage", []):
        tech = row["technology"].strip()
        out[("cov", tech.lower())] = (tech, "coverage", row["verdict"])
    for row in side.get("integration", []):
        a, b = row["libA"].strip(), row["libB"].strip()
        pair = tuple(sorted([a.lower(), b.lower()]))
        out[("int", pair)] = (f"{a} ↔ {b}", "integration", row["verdict"])
    return out


def _rank(domain, verdict):
    return COVERAGE_RANK.get(verdict) if domain == "coverage" else INTEGRATION_RANK.get(verdict)


def compute(inp):
    """Pure delta over the two extracted finding sets."""
    err = _validate(inp)
    if err:
        return make_error(err)

    prev = _index(inp["previous"])
    curr = _index(inp["current"])

    buckets = {k: [] for k in ("improved", "regressed", "unchanged", "new", "dropped", "replaced")}

    for key, (label, domain, verdict) in curr.items():
        if key not in prev:
            # Replaced-on-arrival is informational, not a regression/new gap.
            if verdict == "Replaced":
                buckets["replaced"].append(label)
            else:
                buckets["new"].append(label)
            continue
        _, _, prev_verdict = prev[key]
        if verdict == "Replaced" or prev_verdict == "Replaced":
            buckets["replaced"].append(label)
            continue
        pr, cr = _rank(domain, prev_verdict), _rank(domain, verdict)
        if cr > pr:
            buckets["improved"].append(label)
        elif cr < pr:
            buckets["regressed"].append(label)
        else:
            buckets["unchanged"].append(label)

    for key, (label, _domain, verdict) in prev.items():
        if key not in curr:
            if verdict == "Replaced":
                buckets["replaced"].append(label)
            else:
                buckets["dropped"].append(label)

    tier_downgrades = []
    prev_tiers = inp.get("previousTiers") or {}
    curr_tiers = inp.get("currentTiers") or {}
    for skill in sorted(set(prev_tiers) & set(curr_tiers)):
        pr = TIER_RANK.get(str(prev_tiers[skill]).upper())
        cr = TIER_RANK.get(str(curr_tiers[skill]).upper())
        if pr is None or cr is None:
            continue
        if cr < pr:
            tier_downgrades.append({"skill": skill, "from": prev_tiers[skill], "to": curr_tiers[skill]})

    result = {}
    for name, items in buckets.items():
        result[name] = sorted(items)
        result[name + "Count"] = len(items)
    result["tierDowngrades"] = tier_downgrades
    result["tierDowngradeCount"] = len(tier_downgrades)
    return result


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="skf-report-delta",
        description=(
            "Deterministic previous-vs-current feasibility delta (synthesize.md "
            "§3). Consumes the two extracted finding sets and emits improved / "
            "regressed / unchanged / new / dropped counts plus tier downgrades."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run skf-report-delta.py "
            "'{\"previous\":{\"coverage\":[{\"technology\":\"react\",\"verdict\":\"Missing\"}]},"
            "\"current\":{\"coverage\":[{\"technology\":\"react\",\"verdict\":\"Covered\"}]}}'"
        ),
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("json_input", nargs="?", help="JSON object as a positional argument.")
    src.add_argument("--json-input", dest="json_input_flag", help="JSON object passed via flag.")
    src.add_argument("--stdin", action="store_true", help="Read the JSON object from stdin.")
    return parser


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.json_input_flag is not None:
        return args.json_input_flag
    if args.json_input is not None:
        return args.json_input
    return ""


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw = _resolve_input(args)
    if not raw.strip():
        parser.print_usage(file=sys.stderr)
        print(
            "error: no input provided (positional arg, --json-input, or --stdin)",
            file=sys.stderr,
        )
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps(make_error(f"Invalid JSON: {exc.msg}"), indent=2))
        return 1

    result = compute(data)
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
