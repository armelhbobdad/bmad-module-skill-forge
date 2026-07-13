#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic technology-coverage tally for skf-verify-stack (coverage.md §6).

The coverage verdicts themselves (Covered / Missing / Replaced) are LLM judgment
— matching an architecture technology to a generated skill involves aliases and
prose. This script takes that already-decided coverage matrix and does only the
part with one correct answer: counting each verdict class and turning the counts
into `coveragePercentage`.

Two gotchas make the in-prose version drift between runs, so they live here
instead:

  * The denominator excludes Replaced. `live_count = Covered + Missing`;
    technologies flagged Replaced (intentionally being removed) are not a gap and
    must not dilute the percentage.
  * Rounding is pinned to half-up to the nearest integer, so the same matrix
    always yields the same `coveragePercentage` (the shared schema declares
    `coveragePercentage: <0..100 integer>` but not the rounding rule).

CLI usage:
  uv run skf-coverage-tally.py '<JSON>'                  # JSON literal positional
  uv run skf-coverage-tally.py --json-input '<JSON>'     # explicit flag form
  cat input.json | uv run skf-coverage-tally.py --stdin  # piped input

Input schema (one object):
  {
    "rows": [
      {"technology": "react",   "verdict": "Covered"},
      {"technology": "postgres","verdict": "Missing"},
      {"technology": "old-orm", "verdict": "Replaced"}
    ]
  }

Output (stdout, one object):
  {
    "covered_count": <int>,
    "missing_count": <int>,
    "replaced_count": <int>,
    "live_count": <int>,          # Covered + Missing (denominator)
    "total_referenced": <int>,    # all rows after dedup
    "coverage_percentage": <int>  # round-half-up(covered/live*100); 0 when live==0
  }

Exit codes:
  0  — tally emitted successfully
  1  — no input / input could not be parsed as JSON
  2  — input parsed but schema/semantics invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import json
import math
import sys

VALID_VERDICTS = ("Covered", "Missing", "Replaced")


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


def _validate(inp):
    if inp is None or not isinstance(inp, dict):
        return "Input must be a JSON object"
    rows = inp.get("rows")
    if not isinstance(rows, list):
        return "Missing or invalid required field: rows (must be a list)"
    seen = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            return f"rows[{i}] must be an object"
        tech = row.get("technology")
        if not isinstance(tech, str) or not tech.strip():
            return f"rows[{i}] requires a non-empty string `technology`"
        verdict = row.get("verdict")
        if verdict not in VALID_VERDICTS:
            return (
                f"rows[{i}] verdict {verdict!r} is not one of: "
                f"{', '.join(VALID_VERDICTS)}"
            )
        norm = tech.strip().lower()
        if norm in seen:
            return f"duplicate technology {tech!r} — the coverage list must be deduplicated first"
        seen.add(norm)
    return None


def tally(inp):
    """Pure tally. Counts each verdict class and computes coverage_percentage."""
    err = _validate(inp)
    if err:
        return make_error(err)

    covered = missing = replaced = 0
    for row in inp["rows"]:
        verdict = row["verdict"]
        if verdict == "Covered":
            covered += 1
        elif verdict == "Missing":
            missing += 1
        else:  # Replaced
            replaced += 1

    live = covered + missing
    percentage = math.floor(covered / live * 100 + 0.5) if live > 0 else 0
    return {
        "covered_count": covered,
        "missing_count": missing,
        "replaced_count": replaced,
        "live_count": live,
        "total_referenced": covered + missing + replaced,
        "coverage_percentage": percentage,
    }


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="skf-coverage-tally",
        description=(
            "Deterministic technology-coverage tally (coverage.md §6). Counts "
            "Covered/Missing/Replaced verdicts and computes coveragePercentage "
            "with Replaced excluded from the denominator and half-up rounding."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run skf-coverage-tally.py "
            "'{\"rows\":[{\"technology\":\"react\",\"verdict\":\"Covered\"},"
            "{\"technology\":\"postgres\",\"verdict\":\"Missing\"}]}'"
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

    result = tally(data)
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
