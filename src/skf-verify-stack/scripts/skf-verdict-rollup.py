#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic overall-feasibility verdict rollup for skf-verify-stack (synthesize.md §1).

Deciding each individual finding — is this integration Blocked, is that technology
Missing, is a requirement Not Addressed — is judgment and happens upstream in
Steps 02-04, persisted to the report frontmatter/tables. Rolling those already-decided
counts up into the single overall verdict is *not* judgment: it is a fixed threshold
ladder with one correct answer per input. Walking a five-tier ordered ladder (with a
short-circuit, a downgrade rule, and a post-verdict guard) in-prompt lets the headline
verdict drift between runs, so the token computation lives here. The rationale prose —
which co-occurring problems to name, how to phrase the recommendation — stays in the
prompt; this script emits only the token plus the stable condition codes the prompt
cites when it writes that rationale.

The ladder (synthesize.md §1 runs it and cites its condition codes; evaluate top-to-bottom,
first match wins):

  1. Zero-coverage short-circuit  — coveragePercentage == 0  -> NOT_FEASIBLE
     (no live coverage: analysis is vacuous; the remainder of the ladder is skipped).
  2. NOT_FEASIBLE                  — any integration Blocked (pairsBlocked > 0).
  3. CONDITIONALLY_FEASIBLE        — ANY of: a Missing technology (missingCount > 0),
     a Risky integration (pairsRisky > 0), or — only when the requirements pass ran —
     a Not Addressed or Partially Fulfilled requirement.
  4. FEASIBLE                      — none of the above AND zero pairs capped at
     Plausible (pairsPlausible == 0). If any pair sits at Plausible, downgrade to
     CONDITIONALLY_FEASIBLE.

  Post-verdict zero-integration-pairs guard (applied after ANY verdict): when all four
  integration counts are 0 AND two or more live technologies are Covered
  (coveredCount >= 2), no integration was verified although one could have been, so
  the guard fires: a FEASIBLE verdict is overridden to CONDITIONALLY_FEASIBLE, and
  regardless of verdict the prompt appends the "no integration pair found" note. With
  one Covered technology there is no pair to find, so the guard stays off.

Note that coveragePercentage and missingCount are independent inputs on purpose: half-up
rounding means a stack with covered=199, missing=1 rounds to coveragePercentage == 100
while missingCount is still > 0, so the Missing trigger reads missingCount directly.
coveredCount is checked against coveragePercentage only where they cannot disagree: no
Covered technology means 0% coverage, so coveredCount 0 with a percentage above 0 is
rejected (a caller that left the count at 0 would silently switch the guard off).

CLI usage:
  uv run skf-verdict-rollup.py '<JSON>'                  # JSON literal positional
  uv run skf-verdict-rollup.py --json-input '<JSON>'     # explicit flag form
  cat input.json | uv run skf-verdict-rollup.py --stdin  # piped input

Input schema (one object; counts come straight from the report frontmatter/tables):
  {
    "coveragePercentage": <int 0..100>,      # from coverage.md (coverage-tally)
    "missingCount": <int>,                   # Missing technologies (Replaced excluded)
    "coveredCount": <int>,                   # Covered technologies (the coverage tally's covered_count)
    "pairsBlocked": <int>,                   # from integrations.md
    "pairsRisky": <int>,
    "pairsPlausible": <int>,                 # includes Check-4-missing caps
    "pairsVerified": <int>,
    "requirementsEvaluated": <bool>,         # optional (default false): requirementsPass == "completed"
    "requirementsNotAddressed": <int>,       # optional (default 0); ignored unless evaluated
    "requirementsPartial": <int>             # optional (default 0); ignored unless evaluated
  }

Output (stdout, one object):
  {
    "overallVerdict": "FEASIBLE" | "CONDITIONALLY_FEASIBLE" | "NOT_FEASIBLE",
    "matchedConditions": [<condition codes, in ladder order>],
    "zeroPairsGuardFired": <bool>
  }

Condition codes (stable; the prompt cites these when synthesizing the rationale):
  zero-coverage · blocked-integration · missing-coverage · risky-integration ·
  requirements-not-addressed · requirements-partial · plausible-cap · zero-integration-pairs

Exit codes:
  0  — verdict emitted successfully
  1  — no input / input could not be parsed as JSON
  2  — input parsed but schema/semantics invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import json
import sys

VERDICTS = ("FEASIBLE", "CONDITIONALLY_FEASIBLE", "NOT_FEASIBLE")
REQUIRED_COUNTS = (
    "missingCount",
    "coveredCount",
    "pairsBlocked",
    "pairsRisky",
    "pairsPlausible",
    "pairsVerified",
)
OPTIONAL_COUNTS = ("requirementsNotAddressed", "requirementsPartial")

# The zero-pairs guard needs a pair that could have been found: two Covered
# technologies (the schema's "two or more live technologies", all of them Covered
# whenever the verdict could otherwise be FEASIBLE).
ZERO_PAIRS_MIN_COVERED = 2


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


def _is_nonneg_int(value):
    # bool is a subclass of int; reject it so a stray true/false can't pose as a count.
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate(inp):
    if inp is None or not isinstance(inp, dict):
        return "Input must be a JSON object"

    pct = inp.get("coveragePercentage")
    if not isinstance(pct, int) or isinstance(pct, bool) or not (0 <= pct <= 100):
        return "coveragePercentage must be an integer in 0..100"

    for field in REQUIRED_COUNTS:
        if field not in inp:
            return f"missing required field: {field}"
        if not _is_nonneg_int(inp[field]):
            return f"{field} must be a non-negative integer"

    for field in OPTIONAL_COUNTS:
        if field in inp and inp[field] is not None and not _is_nonneg_int(inp[field]):
            return f"{field} must be a non-negative integer when present"

    if "requirementsEvaluated" in inp and not isinstance(inp["requirementsEvaluated"], bool):
        return "requirementsEvaluated must be a boolean when present"

    if inp["coveredCount"] == 0 and pct > 0:
        return "coveredCount is 0 but coveragePercentage is above 0: pass the coverage tally's covered_count"

    return None


def rollup(inp):
    """Pure verdict rollup over the persisted counts. See module docstring for the ladder."""
    err = _validate(inp)
    if err:
        return make_error(err)

    pct = inp["coveragePercentage"]
    missing = inp["missingCount"]
    blocked = inp["pairsBlocked"]
    risky = inp["pairsRisky"]
    plausible = inp["pairsPlausible"]
    verified = inp["pairsVerified"]
    req_eval = bool(inp.get("requirementsEvaluated", False))
    not_addressed = inp.get("requirementsNotAddressed") or 0
    partial = inp.get("requirementsPartial") or 0
    covered = inp["coveredCount"]

    matched: list[str] = []

    # 1. Zero-coverage short-circuit — wins over everything else.
    if pct == 0:
        verdict = "NOT_FEASIBLE"
        matched.append("zero-coverage")
    # 2. Any Blocked integration is a fundamental incompatibility.
    elif blocked > 0:
        verdict = "NOT_FEASIBLE"
        matched.append("blocked-integration")
        # Co-occurring problems the rationale should also name (§1).
        if missing > 0:
            matched.append("missing-coverage")
        if risky > 0:
            matched.append("risky-integration")
    else:
        # 3. Any gap / risk / unmet requirement -> conditional.
        conditional: list[str] = []
        if missing > 0:
            conditional.append("missing-coverage")
        if risky > 0:
            conditional.append("risky-integration")
        if req_eval and not_addressed > 0:
            conditional.append("requirements-not-addressed")
        if req_eval and partial > 0:
            conditional.append("requirements-partial")
        if conditional:
            verdict = "CONDITIONALLY_FEASIBLE"
            matched.extend(conditional)
        elif plausible > 0:
            # 4. Clean bar except for Check-4-missing caps -> downgrade.
            verdict = "CONDITIONALLY_FEASIBLE"
            matched.append("plausible-cap")
        else:
            verdict = "FEASIBLE"

    # Post-verdict zero-integration-pairs guard.
    zero_pairs = blocked == 0 and risky == 0 and plausible == 0 and verified == 0
    guard_fired = zero_pairs and covered >= ZERO_PAIRS_MIN_COVERED
    if guard_fired:
        if verdict == "FEASIBLE":
            verdict = "CONDITIONALLY_FEASIBLE"
        matched.append("zero-integration-pairs")

    return {
        "overallVerdict": verdict,
        "matchedConditions": matched,
        "zeroPairsGuardFired": guard_fired,
    }


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="skf-verdict-rollup",
        # The module docstring is the contract synthesize.md points --help at:
        # the ladder, the input and output schemas and the condition codes.
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run skf-verdict-rollup.py "
            "'{\"coveragePercentage\":100,\"missingCount\":0,\"coveredCount\":4,"
            "\"pairsBlocked\":0,\"pairsRisky\":0,\"pairsPlausible\":0,\"pairsVerified\":3}'"
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

    result = rollup(data)
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
