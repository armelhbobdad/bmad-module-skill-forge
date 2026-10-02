#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
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
  uv run skf-verdict-rollup.py --report <feasibility-report.md>  # the report's frontmatter
  uv run skf-verdict-rollup.py '<JSON>'                  # JSON literal positional
  uv run skf-verdict-rollup.py --json-input '<JSON>'     # explicit flag form
  cat input.json | uv run skf-verdict-rollup.py --stdin  # piped input

Reading the report (--report, the call synthesize.md section 1 makes): the
input below comes from the report's frontmatter, read with split_frontmatter()
of the shared skf-validate-feasibility-report.py, the reader the report's
consumers use. coveragePercentage and the four pair counts keep their names;
coverageCovered gives coveredCount, coverageMissing missingCount and
coverageReplaced replacedCount; requirementsPass gives requirementsEvaluated
(true for `completed`, false for `skipped`), and with `completed`,
requirementsNotAddressed and requirementsPartial come in too. Every one of
those keys must hold a whole number (requirementsPass one of its two
values): a key missing from the frontmatter, or still at the template's null
or empty value, fails the run (INVALID_REPORT) rather than reading as 0 or
false, so the defaults below serve only the callers that pass JSON. The
template starts coveragePercentage and the four pair counts at 0, a value
no stage need have written, so the frontmatter's stepsCompleted list
(read with the shared reader's frontmatter_list()) must name coverage,
integrations and requirements, the three stages that write the counts: a
report whose list lacks one fails the same way.

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
    "requirementsPartial": <int>,            # optional (default 0); ignored unless evaluated
    "replacedCount": <int>                   # optional (default 0): Replaced technologies (the coverage tally's replaced_count)
  }

Output (stdout, one object):
  {
    "overallVerdict": "FEASIBLE" | "CONDITIONALLY_FEASIBLE" | "NOT_FEASIBLE",
    "matchedConditions": [<condition codes, in ladder order>],
    "zeroPairsGuardFired": <bool>,
    "recommendationCount": <int>,            # the sum of `recommendations`
    "recommendations": {"blocked": <int>, "missing": <int>, "replaced": <int>,
                        "risky": <int>, "plausible": <int>, "zeroPairs": 0 | 1,
                        "notAddressed": <int>, "partial": <int>}
  }

Recommendation count: synthesize.md section 2 writes one recommendation per
finding that is not verified, so their number has one correct answer per input
too: one per Blocked, Missing, Replaced, Risky (each circular-dependency row
included, as the Risky count holds it) and Plausible item, one when the
zero-integration-pairs guard fired, and, only when the requirements pass ran, one
per Not Addressed or Partially Fulfilled requirement. `recommendations` gives each
kind's share in the order synthesize.md lists them, and `recommendationCount` is
their sum: the report's recommendationCount and the envelope's
recommendation_count.

Condition codes (stable; the prompt cites these when synthesizing the rationale):
  zero-coverage · blocked-integration · missing-coverage · risky-integration ·
  requirements-not-addressed · requirements-partial · plausible-cap · zero-integration-pairs

Errors (stdout, one object): {"error": "<why>", "code": "<code>"}:
  INVALID_INPUT   the counts do not fit the input schema above
  INVALID_REPORT  --report: the report cannot be read, a key above is
                  missing or holds no count, or stepsCompleted does not
                  list a stage that writes them
  HELPER_MISSING  --report: the shared skf-validate-feasibility-report.py is
                  not in the shared scripts folder beside this skill's folder

Exit codes:
  0  verdict emitted successfully
  1  no input, input that could not be parsed as JSON, or HELPER_MISSING
  2  input parsed but schema/semantics invalid: INVALID_INPUT or
     INVALID_REPORT (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

VERDICTS = ("FEASIBLE", "CONDITIONALLY_FEASIBLE", "NOT_FEASIBLE")
REQUIRED_COUNTS = (
    "missingCount",
    "coveredCount",
    "pairsBlocked",
    "pairsRisky",
    "pairsPlausible",
    "pairsVerified",
)
OPTIONAL_COUNTS = ("requirementsNotAddressed", "requirementsPartial", "replacedCount")

# --report: each frontmatter key the stages persist, with the input it fills.
REPORT_COUNTS = (
    ("coveragePercentage", "coveragePercentage"),
    ("coverageMissing", "missingCount"),
    ("coverageCovered", "coveredCount"),
    ("coverageReplaced", "replacedCount"),
    ("pairsBlocked", "pairsBlocked"),
    ("pairsRisky", "pairsRisky"),
    ("pairsPlausible", "pairsPlausible"),
    ("pairsVerified", "pairsVerified"),
)
# --report: the stages that write those counts, each of which the frontmatter's
# stepsCompleted must list: the template's 0 is no count until its stage ran.
STEPS_COMPLETED_KEY = "stepsCompleted"
REPORT_STAGES = ("coverage", "integrations", "requirements")
REQUIREMENTS_PASS_KEY = "requirementsPass"
REQUIREMENTS_PASSES = ("completed", "skipped")
# Read only when requirementsPass is `completed`.
REQUIREMENT_COUNTS = ("requirementsNotAddressed", "requirementsPartial")
INVALID_REPORT = "INVALID_REPORT"
HELPER_MISSING = "HELPER_MISSING"
# A frontmatter count: a whole number, a trailing comment allowed.
_COUNT_RE = re.compile(r"([0-9]+)(?:\s+#.*)?")

# The shared feasibility-report reader. Installed (under _bmad/skf/ or an
# IDE's skills folder) and in a dev checkout (src/), shared/ sits beside
# this skill's folder.
SHARED_READER = (
    Path(__file__).resolve().parent.parent.parent
    / "shared"
    / "scripts"
    / "skf-validate-feasibility-report.py"
)

# The zero-pairs guard needs a pair that could have been found: two Covered
# technologies (the schema's "two or more live technologies", all of them Covered
# whenever the verdict could otherwise be FEASIBLE).
ZERO_PAIRS_MIN_COVERED = 2


def make_error(message, code="INVALID_INPUT"):
    return {"error": message, "code": code}


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
    replaced = inp.get("replacedCount") or 0
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

    # One recommendation per finding that is not verified (synthesize.md section 2),
    # in the order its recommendation list gives them.
    recommendations = {
        "blocked": blocked,
        "missing": missing,
        "replaced": replaced,
        "risky": risky,
        "plausible": plausible,
        "zeroPairs": 1 if guard_fired else 0,
        "notAddressed": not_addressed if req_eval else 0,
        "partial": partial if req_eval else 0,
    }
    return {
        "overallVerdict": verdict,
        "matchedConditions": matched,
        "zeroPairsGuardFired": guard_fired,
        "recommendationCount": sum(recommendations.values()),
        "recommendations": recommendations,
    }


# --- Reading the report -------------------------------------------------------


def load_reader():
    """Import the shared feasibility-report reader, or None when it is missing."""
    try:
        if not SHARED_READER.is_file():
            return None
    except OSError:
        return None  # a folder on the way that cannot be searched
    spec = importlib.util.spec_from_file_location("skf_validate_feasibility_report", SHARED_READER)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report_count(frontmatter, key):
    """A frontmatter key's whole number, or (None, why it holds none)."""
    if key not in frontmatter:
        return None, f"the report frontmatter has no {key}: the stage that writes it did not record it"
    match = _COUNT_RE.fullmatch(frontmatter[key].strip())
    if match is None:
        return None, (f"the report frontmatter's {key} is {frontmatter[key]!r}, not a whole number: "
                      "the stage that writes it did not record it")
    return int(match.group(1)), None


def counts_from_report(frontmatter, steps):
    """The rollup input from a report's frontmatter scalars (split_frontmatter())
    and its stepsCompleted items (frontmatter_list(), None when it has none).

    Returns (input, None), or (None, error) when a stage that writes the counts
    is not in `steps`, or a key the stages persist is missing or holds no count.
    Unlike rollup(), nothing defaults: requirementsPass must be `completed` or
    `skipped`, and `completed` needs both requirement counts.
    """
    for stage in REPORT_STAGES:
        if stage not in (steps or ()):
            return None, (f"the report frontmatter's {STEPS_COMPLETED_KEY} does not list {stage}: "
                          "that stage did not finish, so its counts are the template's")
    inp = {}
    for key, field in REPORT_COUNTS:
        inp[field], err = _report_count(frontmatter, key)
        if err:
            return None, err
    passed = frontmatter.get(REQUIREMENTS_PASS_KEY, "").split("#", 1)[0].strip()
    if passed not in REQUIREMENTS_PASSES:
        return None, (f"the report frontmatter's {REQUIREMENTS_PASS_KEY} is {passed!r}, not completed or "
                      "skipped: the requirements stage did not record its pass")
    inp["requirementsEvaluated"] = passed == "completed"
    if inp["requirementsEvaluated"]:
        for key in REQUIREMENT_COUNTS:
            inp[key], err = _report_count(frontmatter, key)
            if err:
                return None, err
    return inp, None


def rollup_report(path, reader):
    """(result, exit code) of the rollup over the report at `path`, read with `reader`."""
    try:
        # utf-8-sig drops a byte order mark, as the shared reader does.
        content = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return make_error(f"cannot read the report {path}: {exc}", INVALID_REPORT), 2
    frontmatter, _body = reader.split_frontmatter(content)
    inp, err = counts_from_report(frontmatter, reader.frontmatter_list(content, STEPS_COMPLETED_KEY))
    if err:
        return make_error(err, INVALID_REPORT), 2
    result = rollup(inp)
    return result, 2 if result.get("code") == "INVALID_INPUT" else 0


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="skf-verdict-rollup",
        # The module docstring is the contract synthesize.md points --help at:
        # the ladder, the input and output schemas and the condition codes.
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run skf-verdict-rollup.py --report feasibility-report-my-app-20261002-101500.md\n"
            "  uv run skf-verdict-rollup.py "
            "'{\"coveragePercentage\":100,\"missingCount\":0,\"coveredCount\":4,"
            "\"pairsBlocked\":0,\"pairsRisky\":0,\"pairsPlausible\":0,\"pairsVerified\":3}'"
        ),
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("json_input", nargs="?", help="JSON object as a positional argument.")
    src.add_argument("--json-input", dest="json_input_flag", help="JSON object passed via flag.")
    src.add_argument("--stdin", action="store_true", help="Read the JSON object from stdin.")
    src.add_argument(
        "--report",
        metavar="REPORT",
        help="Read the counts from this feasibility report's frontmatter; a missing count fails.",
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
    if args.report is not None:
        reader = load_reader()
        if reader is None:
            message = f"the shared report reader {SHARED_READER.name} is not installed beside this skill"
            print(json.dumps(make_error(message, HELPER_MISSING), indent=2))
            return 1
        result, code = rollup_report(args.report, reader)
        print(json.dumps(result, indent=2))
        return code
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


def _force_utf8(*streams) -> None:
    """Reconfigure the given streams to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    of the --help text this module docstring supplies, and which garbles UTF-8
    JSON piped into --stdin.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    raise SystemExit(main())
