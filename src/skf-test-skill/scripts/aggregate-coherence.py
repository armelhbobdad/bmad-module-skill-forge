#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic contextual-coherence aggregator.

Pure-function tally + weighted mean for the SKF test-skill workflow
(step-04, coherence-check.md §5c). The prompt keeps the judgment — deciding
which cross-references are valid (§4) and which integration patterns are
complete (§5). This script does ONLY the arithmetic those judgments feed:
the reference-validity ratio, the integration-completeness ratio, and their
fixed 0.6 / 0.4 weighted mean. That way the 18%-weight `coherence` input to
compute-score.py is computed once, deterministically, instead of by hand on
every run (this skill grades other skills — a false PASS is catastrophic, so
every scoring input is scripted for run-to-run reproducibility).

Formula (mirrors scoring-rules.md "Coherence Score Aggregation (Contextual
Mode)" — the prose there remains the documented contract):

    reference_validity       = (valid_references / total_references) * 100
    integration_completeness = (complete_patterns / total_patterns) * 100
    combined_coherence       = reference_validity * 0.6 + integration_completeness * 0.4

Field-name mapping: the step-04 §5 integration JSON calls the pattern counts
`patterns_documented` (= total_patterns) and `patterns_complete`
(= complete_patterns); this script's input uses those step-04 names directly
so §5c passes them through unrenamed.

Edge cases (both documented in scoring-rules.md — absence is never penalized):
  * patterns_documented == 0 -> no integration patterns to weigh, so
    combined_coherence == reference_validity and integrationCompleteness is
    null. (Do not divide by zero.)
  * total_references == 0 -> no references means no broken references, so
    reference_validity == 100.0 (vacuously coherent). Unreachable on the normal
    contextual path — §3 always extracts at least one reference — but handled so
    the arithmetic never divides by zero.

Input schema (one JSON object):
  {
    "valid_references":    <int >= 0, <= total_references>,
    "total_references":    <int >= 0>,
    "patterns_documented": <int >= 0>,
    "patterns_complete":   <int >= 0, <= patterns_documented>
  }

Output (JSON):
  {
    "input": { ...echo... },
    "referenceValidity":       <0-100>,
    "integrationCompleteness": <0-100 | null when patterns_documented == 0>,
    "combinedCoherence":       <0-100>,
    "patternsScored":          <bool>
  }
  or {"error": ..., "code": "INVALID_INPUT"} on a schema violation.

Percentages use the same JavaScript-compatible 2-decimal rounding as
compute-score.py so the two scoring scripts agree to the last digit.

CLI usage (mirrors compute-score.py):
  uv run aggregate-coherence.py '<JSON>'                  # positional arg
  uv run aggregate-coherence.py --json-input '<JSON>'     # explicit flag form
  cat input.json | uv run aggregate-coherence.py --stdin  # piped input

Exit codes:
  0  — input was parsed; either a result object or a schema-validation error
       object ({"error": ..., "code": "INVALID_INPUT"}) was emitted as JSON
  1  — input could not be parsed at all (no input provided, or malformed JSON)
"""

from __future__ import annotations

import argparse
import json
import math
import sys

# Weights for the combined-coherence mean (from scoring-rules.md). Kept as
# named constants so the 0.6 / 0.4 split lives in exactly one place.
REFERENCE_VALIDITY_WEIGHT = 0.6
INTEGRATION_COMPLETENESS_WEIGHT = 0.4

COUNT_FIELDS = (
    "valid_references",
    "total_references",
    "patterns_documented",
    "patterns_complete",
)


def round2(value):
    """Round to 2 decimals with JavaScript-compatible half-up rounding.

    Matches compute-score.py.round2 so both scoring scripts produce identical
    numbers. JS Math.round rounds .5 away from zero for positives; Python's
    built-in round uses banker's rounding. We replicate JS: floor(x*100+0.5)/100.
    """
    return math.floor(value * 100 + 0.5) / 100


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


def validate_input(inp):
    if inp is None or not isinstance(inp, dict):
        return "Input must be a JSON object"

    for field in COUNT_FIELDS:
        if field not in inp or inp[field] is None:
            return f"Missing required field: {field} (non-negative integer)"
        value = inp[field]
        # bool is a subclass of int; reject it so true/false can't pose as 1/0.
        if isinstance(value, bool) or not isinstance(value, int):
            return (
                f"Field `{field}` must be a non-negative integer, "
                f"got {type(value).__name__}: {value!r}"
            )
        if value < 0:
            return f"Field `{field}` must be >= 0, got {value}"

    if inp["valid_references"] > inp["total_references"]:
        return (
            "valid_references cannot exceed total_references "
            f"({inp['valid_references']} > {inp['total_references']})"
        )

    if inp["patterns_complete"] > inp["patterns_documented"]:
        return (
            "patterns_complete cannot exceed patterns_documented "
            f"({inp['patterns_complete']} > {inp['patterns_documented']})"
        )

    return None


def aggregate_coherence(inp):
    """Compute reference validity, integration completeness, and combined coherence.

    Weighted mean of the two ratios (0.6 / 0.4), JS-compatible 2-decimal rounding:
    >>> out = aggregate_coherence({"valid_references": 6, "total_references": 7,
    ...                            "patterns_documented": 5, "patterns_complete": 4})
    >>> out["referenceValidity"], out["integrationCompleteness"], out["combinedCoherence"]
    (85.71, 80.0, 83.43)
    >>> out["patternsScored"]
    True

    Zero integration patterns -> combined equals reference validity, no divide-by-zero:
    >>> out = aggregate_coherence({"valid_references": 9, "total_references": 10,
    ...                            "patterns_documented": 0, "patterns_complete": 0})
    >>> out["integrationCompleteness"] is None
    True
    >>> out["patternsScored"]
    False
    >>> out["referenceValidity"], out["combinedCoherence"]
    (90.0, 90.0)

    Zero references -> vacuously perfect reference validity, never a ZeroDivision:
    >>> aggregate_coherence({"valid_references": 0, "total_references": 0,
    ...                      "patterns_documented": 2, "patterns_complete": 1})["referenceValidity"]
    100.0

    A schema violation returns an error object, not an exception:
    >>> aggregate_coherence({"valid_references": 5, "total_references": 3,
    ...                      "patterns_documented": 0, "patterns_complete": 0})["code"]
    'INVALID_INPUT'
    """
    validation_error = validate_input(inp)
    if validation_error:
        return make_error(validation_error)

    valid_references = inp["valid_references"]
    total_references = inp["total_references"]
    patterns_documented = inp["patterns_documented"]
    patterns_complete = inp["patterns_complete"]

    # Reference validity — vacuously 100 when there are no references at all.
    if total_references == 0:
        reference_validity = 100.0
    else:
        reference_validity = round2((valid_references / total_references) * 100)

    # Integration completeness — absent when no patterns are documented.
    patterns_scored = patterns_documented > 0
    if patterns_scored:
        integration_completeness = round2(
            (patterns_complete / patterns_documented) * 100
        )
        combined_coherence = round2(
            reference_validity * REFERENCE_VALIDITY_WEIGHT
            + integration_completeness * INTEGRATION_COMPLETENESS_WEIGHT
        )
    else:
        integration_completeness = None
        combined_coherence = reference_validity

    return {
        "input": {field: inp[field] for field in COUNT_FIELDS},
        "referenceValidity": reference_validity,
        "integrationCompleteness": integration_completeness,
        "combinedCoherence": combined_coherence,
        "patternsScored": patterns_scored,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aggregate-coherence",
        description=(
            "Deterministic contextual-coherence aggregator. Input is a single "
            "JSON object of reference + integration-pattern counts; output is the "
            "reference-validity, integration-completeness, and combined-coherence "
            "percentages that feed the `coherence` scoring input."
        ),
        epilog=(
            "Example:\n"
            "  uv run aggregate-coherence.py "
            "'{\"valid_references\":6,\"total_references\":7,"
            "\"patterns_documented\":5,\"patterns_complete\":4}'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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


def _resolve_input(args: argparse.Namespace) -> str:
    if args.stdin:
        return sys.stdin.read()
    if args.json_input_flag is not None:
        return args.json_input_flag
    if args.json_input is not None:
        return args.json_input
    return ""


def main(argv: list[str] | None = None) -> int:
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

    result = aggregate_coherence(data)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
