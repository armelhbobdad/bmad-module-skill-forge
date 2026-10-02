#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic verdict tallies for skf-verify-stack.

Each verdict itself is LLM judgment: matching an architecture technology to a
generated skill involves aliases and prose (coverage.md §3), and so does rating
an integration pair (integrations.md §4) or a requirement (requirements.md §3).
This script takes the rows the prompt already decided and does only the part
with one correct answer: counting each verdict class. --kind picks the rows.

coverage (the default; coverage.md §3, persisted in §6)
  Counts Covered, Missing and Replaced and turns the counts into
  `coveragePercentage`. Two gotchas make the in-prose version drift between
  runs, so they live here instead:

  * The denominator excludes Replaced. `live_count = Covered + Missing`;
    technologies flagged Replaced (intentionally being removed) are not a gap and
    must not dilute the percentage.
  * Rounding is pinned to half-up to the nearest integer, so the same matrix
    always yields the same `coveragePercentage` (the shared schema declares
    `coveragePercentage: <0..100 integer>` but not the rounding rule).

integrations (integrations.md §4, persisted in §6)
  Counts the rows of the canonical `| lib_a | lib_b | verdict | rationale |`
  table by verdict: one row per integration pair, plus one Risky row per
  circular dependency. --cycles names the JSON skf-find-cycles.py wrote
  ({"cycles": [[...], ...], ...}); each cycle is one more Risky row, so it
  counts toward `pairs_risky` and the frontmatter's `pairsRisky` matches the
  table. Pass the pair rows only: a cycle row in `rows` is counted twice.

requirements (requirements.md §3, persisted in §5)
  Counts Fulfilled, Partially Fulfilled and Not Addressed.

--render (coverage and integrations)
  Prints the report table's rows from the same rows instead of the counts,
  one Markdown table row per line and nothing else, so no stage types a row
  by hand: coverage.md §5 shows the coverage rows and §6 writes them under
  `| Technology | Source Section | Skill Match | Verdict |`, and
  integrations.md §6 writes the integration rows under the template's
  canonical `| lib_a | lib_b | verdict | rationale |` header. The input is
  checked as for the counts first. A coverage row gives its Source Section
  and Skill Match from `section` and `skill` (`none` when null).
  An integration row needs its `rationale`; after the pair rows comes one row
  per cycle --cycles lists: `cycle`, the cycle's arrow chain (`A → B → C →
  A`), Risky and "circular integration dependency detected: `<chain>`", so
  the delta, which keys rows on their two libraries, never merges a cycle
  into a pair. A cell holds its text on one line, each `|` behind a backslash.
  With no row, nothing is printed.

CLI usage:
  uv run skf-coverage-tally.py '<JSON>'                  # JSON literal positional
  uv run skf-coverage-tally.py --json-input '<JSON>'     # explicit flag form
  cat input.json | uv run skf-coverage-tally.py --stdin  # piped input
  uv run skf-coverage-tally.py --kind integrations --cycles cycles.json --stdin < rows.json
  uv run skf-coverage-tally.py --kind requirements --stdin < rows.json
  uv run skf-coverage-tally.py --render --stdin < coverage-rows.json
  uv run skf-coverage-tally.py --kind integrations --render --cycles cycles.json --stdin < rows.json

Input schema (one object), by kind:
  coverage:
    {"rows": [{"technology": "react",   "verdict": "Covered"},
              {"technology": "postgres","verdict": "Missing"},
              {"technology": "old-orm", "verdict": "Replaced"}]}
    Each technology once (compared trimmed and case-insensitively). A row may
    carry "section" and "skill", each a string or null (--render reads an
    absent one as null). A Covered row names its skill, a Missing or Replaced
    one none: --render checks that on every row and the counts on each row
    that carries "skill", so a rows file the tally accepts also renders.
  integrations:
    {"rows": [{"lib_a": "react", "lib_b": "zod", "verdict": "Verified",
               "rationale": "..."}, ...]}
    verdict: Verified, Plausible, Risky or Blocked (case-sensitive). Each
    pair once, in either order, and never a library paired with itself.
    rationale: the table's rationale cell, which --render requires.
  requirements:
    {"rows": [{"requirement_id": "R1", "verdict": "Fulfilled"}, ...]}
    verdict: Fulfilled, Partially Fulfilled or Not Addressed (case-sensitive).
    Each requirement_id once.

Output (stdout, one object), by kind:
  coverage:
    {
      "covered_count": <int>,
      "missing_count": <int>,
      "replaced_count": <int>,
      "live_count": <int>,          # Covered + Missing (denominator)
      "total_referenced": <int>,    # all rows after dedup
      "coverage_percentage": <int>  # round-half-up(covered/live*100); 0 when live==0
    }
  integrations:
    {
      "pairs_verified": <int>,
      "pairs_plausible": <int>,
      "pairs_risky": <int>,         # Risky pair rows + cycle_count
      "pairs_blocked": <int>,
      "pair_count": <int>,          # the pair rows
      "cycle_count": <int>,         # the cycles --cycles lists (0 without it)
      "row_count": <int>            # pair_count + cycle_count: the table's rows
    }
  requirements:
    {
      "requirements_fulfilled": <int>,
      "requirements_partial": <int>,
      "requirements_not_addressed": <int>,
      "requirement_count": <int>
    }

  --render: the rows as Markdown, one per line, in the order given (the
  cycle rows last), with no JSON.

Errors (stdout, one object): {"error": "<why>", "code": "INVALID_INPUT"}.

Exit codes:
  0  tally (or, with --render, the rows) emitted successfully
  1  no input, input that is not JSON, or a --cycles file that cannot be read
     or is not JSON
  2  input parsed but its schema or semantics are invalid (error object
     emitted as JSON); argparse usage errors, such as --cycles with another
     kind or --render with requirements, exit 2 too, with usage on stderr and
     no JSON
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

VALID_VERDICTS = ("Covered", "Missing", "Replaced")
INTEGRATION_VERDICTS = ("Verified", "Plausible", "Risky", "Blocked")
REQUIREMENT_VERDICTS = ("Fulfilled", "Partially Fulfilled", "Not Addressed")
KINDS = ("coverage", "integrations", "requirements")
# The kinds whose report table --render prints.
RENDER_KINDS = ("coverage", "integrations")
# The Source Section or Skill Match of a coverage row that names none.
NO_CELL = "none"
# A cycle row's lib_a, and how its lib_b chains the cycle's nodes.
CYCLE_LABEL = "cycle"
CYCLE_ARROW = " → "
CYCLE_RATIONALE = "circular integration dependency detected: `{chain}`"


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


def _rows(inp):
    """The `rows` list of an input object, or an error message."""
    if inp is None or not isinstance(inp, dict):
        return None, "Input must be a JSON object"
    rows = inp.get("rows")
    if not isinstance(rows, list):
        return None, "Missing or invalid required field: rows (must be a list)"
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            return None, f"rows[{i}] must be an object"
    return rows, None


def _name(row, i, key):
    """A row's trimmed, non-empty string `key`, or an error message."""
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        return None, f"rows[{i}] requires a non-empty string `{key}`"
    return value.strip(), None


def _verdict(row, i, allowed):
    verdict = row.get("verdict")
    if verdict not in allowed:
        return f"rows[{i}] verdict {verdict!r} is not one of: {', '.join(allowed)}"
    return None


def _optional_text(row, i, key):
    """A row's optional string `key`, trimmed (None when absent, null or blank), or an error message."""
    value = row.get(key)
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, f"rows[{i}] `{key}` must be a string or null"
    return value.strip() or None, None


def _cells(row, i, render):
    """A coverage row's Source Section and Skill Match (None for none), or an error message.

    A Covered row names its skill, a Missing or Replaced one none. The pairing
    is checked whenever the row carries `skill` (the rows file coverage.md §3
    writes always does), so the tally refuses a row --render would refuse.
    """
    section, err = _optional_text(row, i, "section")
    if err:
        return None, None, err
    skill, err = _optional_text(row, i, "skill")
    if err:
        return None, None, err
    if (render or "skill" in row) and (row["verdict"] == "Covered") != (skill is not None):
        return None, None, (
            f"rows[{i}] is {row['verdict']} but names {'no' if skill is None else 'a'} skill: "
            "a Covered row names its skill, a Missing or Replaced one none"
        )
    return section, skill, None


def _validate(inp, render=False):
    rows, err = _rows(inp)
    if err:
        return err
    seen = set()
    for i, row in enumerate(rows):
        tech, err = _name(row, i, "technology")
        if err:
            return err
        err = _verdict(row, i, VALID_VERDICTS)
        if err:
            return err
        norm = tech.lower()
        if norm in seen:
            return f"duplicate technology {row['technology']!r}: the coverage list must be deduplicated first"
        seen.add(norm)
        _, _, err = _cells(row, i, render)
        if err:
            return err
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


def _cycle_count(cycles):
    """The number of cycles in a skf-find-cycles.py result, or an error message.

    Each cycle is a closed node path: at least two non-empty names, the first
    repeated at the end (a self-loop is ["A", "A"]).
    """
    if not isinstance(cycles, dict) or not isinstance(cycles.get("cycles"), list):
        return None, "--cycles must hold the skf-find-cycles.py result, an object with a `cycles` list"
    for i, cycle in enumerate(cycles["cycles"]):
        if (
            not isinstance(cycle, list)
            or len(cycle) < 2
            or not all(isinstance(node, str) and node.strip() for node in cycle)
            or cycle[0] != cycle[-1]
        ):
            return None, f"--cycles cycles[{i}] is not a closed node path such as [\"A\", \"B\", \"A\"]: {cycle!r}"
    return len(cycles["cycles"]), None


def tally_integrations(inp, cycles=None):
    """Count the canonical verdict table's rows: the pair rows, and one Risky row per cycle."""
    rows, err = _rows(inp)
    if err:
        return make_error(err)
    counts = {verdict: 0 for verdict in INTEGRATION_VERDICTS}
    seen = set()
    for i, row in enumerate(rows):
        lib_a, err = _name(row, i, "lib_a")
        if err:
            return make_error(err)
        lib_b, err = _name(row, i, "lib_b")
        if err:
            return make_error(err)
        err = _verdict(row, i, INTEGRATION_VERDICTS)
        if err:
            return make_error(err)
        pair = frozenset((lib_a.lower(), lib_b.lower()))
        if len(pair) == 1:
            return make_error(f"rows[{i}] pairs {lib_a!r} with itself")
        if pair in seen:
            return make_error(f"duplicate pair {lib_a!r} / {lib_b!r}: list each integration pair once")
        seen.add(pair)
        counts[row["verdict"]] += 1

    cycle_count = 0
    if cycles is not None:
        cycle_count, err = _cycle_count(cycles)
        if err:
            return make_error(err)
    return {
        "pairs_verified": counts["Verified"],
        "pairs_plausible": counts["Plausible"],
        "pairs_risky": counts["Risky"] + cycle_count,
        "pairs_blocked": counts["Blocked"],
        "pair_count": len(rows),
        "cycle_count": cycle_count,
        "row_count": len(rows) + cycle_count,
    }


def tally_requirements(inp):
    """Count Fulfilled, Partially Fulfilled and Not Addressed requirements."""
    rows, err = _rows(inp)
    if err:
        return make_error(err)
    counts = {verdict: 0 for verdict in REQUIREMENT_VERDICTS}
    seen = set()
    for i, row in enumerate(rows):
        requirement, err = _name(row, i, "requirement_id")
        if err:
            return make_error(err)
        err = _verdict(row, i, REQUIREMENT_VERDICTS)
        if err:
            return make_error(err)
        if requirement.lower() in seen:
            return make_error(f"duplicate requirement_id {requirement!r}: list each requirement once")
        seen.add(requirement.lower())
        counts[row["verdict"]] += 1
    return {
        "requirements_fulfilled": counts["Fulfilled"],
        "requirements_partial": counts["Partially Fulfilled"],
        "requirements_not_addressed": counts["Not Addressed"],
        "requirement_count": len(rows),
    }


# --- Rendering the report rows ------------------------------------------------


def _cell(value):
    """One table cell: its text on one line, a pipe escaped so it stays in the cell."""
    return " ".join(str(value).split()).replace("|", "\\|")


def _table_row(cells):
    return "| " + " | ".join(_cell(cell) for cell in cells) + " |"


def render_coverage(inp):
    """The coverage table's rows (Technology, Source Section, Skill Match, Verdict), or an error object."""
    err = _validate(inp, render=True)
    if err:
        return make_error(err)
    lines = []
    for i, row in enumerate(inp["rows"]):
        section, skill, _ = _cells(row, i, render=True)
        lines.append(_table_row([row["technology"].strip(), section or NO_CELL, skill or NO_CELL, row["verdict"]]))
    return lines


def render_integrations(inp, cycles=None):
    """The canonical verdict table's rows (lib_a, lib_b, verdict, rationale), then one per cycle.

    The rows and --cycles are checked as tally_integrations() checks them;
    an error object comes back on the first problem.
    """
    counted = tally_integrations(inp, cycles)
    if "error" in counted:
        return counted
    lines = []
    for i, row in enumerate(inp["rows"]):
        rationale, err = _name(row, i, "rationale")
        if err:
            return make_error(err)
        lines.append(_table_row([row["lib_a"].strip(), row["lib_b"].strip(), row["verdict"], rationale]))
    for cycle in (cycles or {}).get("cycles", []):
        chain = CYCLE_ARROW.join(node.strip() for node in cycle)
        lines.append(_table_row([CYCLE_LABEL, chain, "Risky", CYCLE_RATIONALE.format(chain=chain)]))
    return lines


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="skf-coverage-tally",
        description=(
            "Deterministic verdict tallies for skf-verify-stack. --kind coverage "
            "(the default, coverage.md §3) counts Covered/Missing/Replaced verdicts "
            "and computes coveragePercentage with Replaced excluded from the "
            "denominator and half-up rounding. --kind integrations (integrations.md "
            "§4, persisted in §6) counts the verdict table's pair rows, plus one "
            "Risky row per cycle the --cycles file lists. --kind requirements "
            "(requirements.md §3, persisted in §5) counts Fulfilled/Partially "
            "Fulfilled/Not Addressed. --render prints the coverage or integration "
            "report rows instead of the counts."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run skf-coverage-tally.py "
            "'{\"rows\":[{\"technology\":\"react\",\"verdict\":\"Covered\"},"
            "{\"technology\":\"postgres\",\"verdict\":\"Missing\"}]}'\n"
            "  uv run skf-coverage-tally.py --kind integrations --cycles cycles.json "
            "--stdin < rows.json\n"
            "  uv run skf-coverage-tally.py --render --stdin < coverage-rows.json"
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
    parser.add_argument(
        "--kind",
        choices=KINDS,
        default="coverage",
        help="Which rows to count (default: coverage).",
    )
    parser.add_argument(
        "--cycles",
        metavar="FILE",
        help=(
            "With --kind integrations: the JSON skf-find-cycles.py wrote; each "
            "cycle counts as one more Risky row (with --render, one more row)."
        ),
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help=(
            "With --kind coverage or integrations: print the report table's rows, "
            "one Markdown row per line, instead of the counts."
        ),
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


def _read_cycles(path):
    """The parsed --cycles file, or (None, error) when it cannot be read or is not JSON."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot read the --cycles file {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"the --cycles file {path} is not JSON: {exc.msg}"


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cycles is not None and args.kind != "integrations":
        parser.error("--cycles applies only with --kind integrations")
    if args.render and args.kind not in RENDER_KINDS:
        parser.error("--render applies only with --kind coverage or integrations")
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

    if args.kind == "integrations":
        cycles = None
        if args.cycles is not None:
            cycles, err = _read_cycles(args.cycles)
            if err:
                print(json.dumps(make_error(err), indent=2))
                return 1
        result = (render_integrations if args.render else tally_integrations)(data, cycles)
    elif args.kind == "requirements":
        result = tally_requirements(data)
    else:
        result = (render_coverage if args.render else tally)(data)
    if isinstance(result, list):
        sys.stdout.write("".join(line + "\n" for line in result))
        return 0
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure the given streams to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    a --help text or an error message may hold, and which garbles the UTF-8 row
    files the stages redirect into --stdin.
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
