#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic combined external-validation score.

Arithmetic helper for the SKF test-skill workflow (external-validators.md §4).
The combined external score feeds compute-score.py as the `externalValidation`
category input, so — like every other scoring input in this skill — the mean is
computed once by a script rather than by hand, keeping the verdict reproducible
run-to-run (an odd-sum average such as (80 + 73) / 2 = 76.5 is exactly where an
in-prompt round swings).

Rule (external-validators.md §4):
  * both tools ran  -> mean of skill-check + tessl review scores
  * one tool ran    -> that tool's score
  * neither ran     -> null (scoring step redistributes the external weight)

Both scores are on the same 0-100 scale (skill-check quality score; tessl review
percentage). Rounding matches compute-score.py (JS-compatible half-up) so the
number this script emits and the one compute-score.py weights agree to the digit.

Input schema (one JSON object; a tool that did not run is null or omitted):
  {
    "skillCheckScore":  <0-100 | null>,
    "tesslReviewScore": <0-100 | null>
  }

Output (stdout, one object):
  {
    "externalScore": <0-100 float | null>,   # null when neither tool ran
    "toolsUsed":     ["skill-check", "tessl"],  # tools that contributed
    "available":     <bool>                    # at least one tool ran
  }
  or {"error": ..., "code": "INVALID_INPUT"} on a schema violation.

CLI usage (mirrors compute-score.py):
  uv run combine-external-scores.py '<JSON>'                  # positional
  uv run combine-external-scores.py --json-input '<JSON>'     # explicit flag
  cat input.json | uv run combine-external-scores.py --stdin  # piped input

Exit codes:
  0  — score emitted successfully
  1  — no input / input could not be parsed as JSON
  2  — input parsed but schema/semantics invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import json
import math
import sys

SKILL_CHECK = "skill-check"
TESSL = "tessl"


def round2(value):
    """Round to 2 decimals with JS-compatible half-up rounding (matches compute-score.py)."""
    return math.floor(value * 100 + 0.5) / 100


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


def _as_score(value, label, errors):
    """Return value if it is a 0-100 number (not bool), None if absent, else record an error."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{label} must be a number between 0 and 100 or null (got {value!r})")
        return None
    if value < 0 or value > 100:
        errors.append(f"{label} must be between 0 and 100 (got {value})")
        return None
    return value


def combine(inp):
    """Pure combined-external-score computation. Returns the result (or error) object."""
    if inp is None or not isinstance(inp, dict):
        return make_error("Input must be a JSON object")

    errors: list[str] = []
    skill_check = _as_score(inp.get("skillCheckScore"), "skillCheckScore", errors)
    tessl = _as_score(inp.get("tesslReviewScore"), "tesslReviewScore", errors)
    if errors:
        return make_error("; ".join(errors))

    tools_used = []
    present = []
    if skill_check is not None:
        tools_used.append(SKILL_CHECK)
        present.append(skill_check)
    if tessl is not None:
        tools_used.append(TESSL)
        present.append(tessl)

    if not present:
        external_score = None
    elif len(present) == 1:
        external_score = round2(present[0])
    else:
        external_score = round2(sum(present) / len(present))

    return {
        "externalScore": external_score,
        "toolsUsed": tools_used,
        "available": bool(present),
    }


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="combine-external-scores",
        description=(
            "Deterministic combined external-validation score "
            "(external-validators.md §4). Averages the skill-check and tessl "
            "review scores (or passes a single available score through) into the "
            "`externalValidation` scoring input."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run combine-external-scores.py "
            "'{\"skillCheckScore\":80,\"tesslReviewScore\":73}'"
        ),
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "json_input",
        nargs="?",
        help="JSON object as a positional argument (single-quote it on the shell).",
    )
    src.add_argument(
        "--json-input",
        dest="json_input_flag",
        help="JSON object passed via flag (overrides positional).",
    )
    src.add_argument(
        "--stdin",
        action="store_true",
        help="Read the JSON object from stdin.",
    )
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

    result = combine(data)
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
