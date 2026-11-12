#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
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
  * both tools ran  -> mean of the skill-check and Tessl Review scores
  * one tool ran    -> that tool's score
  * neither ran     -> null (scoring step redistributes the external weight)

Both scores are on the same 0-100 scale (skill-check's quality score; the Tessl
Review score, `review_score` from skf-tessl-review.py, when the user opted in). Rounding matches compute-score.py (JS-compatible half-up) so the
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

--output <file> writes the result to a file (UTF-8 JSON), the one
compute-score.py --external reads, and prints only its summary,
{"externalScore", "toolsUsed", "output": the --output path}: the two fields
external-validators.md §4 binds (#1063). A refused input prints its error
object either way and removes a file left there earlier.

File mode (external-validators.md §4, #1120): the saved outputs of the two
tools in place of a JSON input.

  uv run combine-external-scores.py --skill-check <file> --tessl <file>
      --skill-dir <dir> [--output <file>]

--skill-check is skill-check's `check --format json` stdout and --tessl the
last skf-tessl-review.py JSON; --skill-dir, the skill folder skill-check
checked, is needed with either. A file that is missing, or that does not
start with a JSON object (an empty file from a call the shell tool
stopped), is a tool that did not run. The skill-check score is the one
skf-summarize-validation.py's quality_score() picks for --skill-dir: this
script loads that file from <its folder>/../../shared/scripts/, the same
place in an installed module and in src/, and without it prints
{"error", "code": "HELPER_MISSING"} and exits 1. The Tessl scores are the
file's `review_score` and `description_score` when its `status` is
`reviewed`, else null. Then combine() runs on the two scores as above, so
an out-of-range score is still INVALID_INPUT. The file flags beside a JSON
input are INVALID_INPUT (exit 2, a file left at --output removed).

The result holds combine()'s three keys, then what the run's later steps
read from external.json:
  skillCheckScore          the skill-check score, or null
  skillCheckErrorCount     summary.errorCount, null unless skill-check
  skillCheckWarningCount   summary.warningCount  validated (wrote its JSON)
  descriptionIssues        true when a diagnostic's ruleId starts with
                           `description.` or is
                           `frontmatter.description_required`, the
                           description rules of skill-check 1.2.0
  skillCheckDiagnostics    each diagnostic as {ruleId, severity, message,
                           file, line, suggestion}; `file` relative to
                           --skill-dir with `/` when it resolves inside it,
                           else as skill-check gave it
  tesslReviewScore         the Tessl scores above
  tesslDescriptionScore
  tesslValidationFindings  `validation.findings`
  tesslDescriptionSuggestions, tesslContentSuggestions
                           `description_suggestions`, `content_suggestions`
                           (the three lists empty unless `reviewed`)
With --output it prints {"externalScore", "toolsUsed", "skillCheckScore",
"skillCheckErrorCount", "skillCheckWarningCount", "descriptionIssues",
"output"}: what external-validators.md §4 binds. gap-ledger.py's `external`
adapter records the gaps from the lists.

Exit codes:
  0  — score emitted successfully
  1  — no input / input could not be parsed as JSON
  2  — input parsed but schema/semantics invalid (error object emitted as JSON)
File mode also exits 1 on HELPER_MISSING.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

SKILL_CHECK = "skill-check"
TESSL = "tessl"
# skf-summarize-validation.py, whose quality_score() Quick Skill's validation summary also uses.
SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "shared" / "scripts"
READER = "skf-summarize-validation.py"
# skill-check 1.2.0's description rules (dist/rules/core/description.js, frontmatter.js).
DESCRIPTION_RULE_PREFIX = "description."
DESCRIPTION_RULES = frozenset({"frontmatter.description_required"})
FILE_FLAGS = ("skill_check", "tessl", "skill_dir")


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
            "(external-validators.md §4). Averages the skill-check and Tessl "
            "Review scores (or passes a single available score through) into the "
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
    parser.add_argument("--output", metavar="PATH", help="write the result to this file and print only its summary")
    files = parser.add_argument_group("file mode (in place of a JSON input)")
    files.add_argument("--skill-check", metavar="FILE", help="skill-check's `check --format json` stdout")
    files.add_argument("--tessl", metavar="FILE", help="skf-tessl-review.py's last JSON")
    files.add_argument("--skill-dir", metavar="DIR", help="the skill folder skill-check checked")
    return parser


def _write_output(path, result):
    target = Path(path)
    if result.get("code") == "INVALID_INPUT":
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))


def _summary(result, output):
    """What main prints when --output holds the result: the two fields external-validators §4 binds, `toolsUsed`
    kept a list since the step binds its names, and the file's path as `output` (#1063)."""
    return {"externalScore": result["externalScore"], "toolsUsed": result["toolsUsed"], "output": output}


def _load_reader():
    """skf-summarize-validation.py from the shared scripts folder, or None when it is not there."""
    path = SHARED_SCRIPTS / READER
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("skf_summarize_validation", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value):
    return None if isinstance(value, bool) or not isinstance(value, (int, float)) else value


def _relative_file(file, skill_dir):
    """`file` (relative to the folder skill-check ran in) relative to the skill folder, with `/`, when it is in it."""
    if not isinstance(file, str) or not file:
        return None
    try:
        target = (Path.cwd() / file.replace("\\", "/")).resolve()
        return target.relative_to(Path(skill_dir).resolve()).as_posix()
    except (ValueError, OSError, RuntimeError):
        return file


def _diagnostics(checked, skill_dir):
    raw = checked.get("diagnostics") if isinstance(checked, dict) else None
    return [{"ruleId": d.get("ruleId"), "severity": d.get("severity"), "message": d.get("message"),
             "file": _relative_file(d.get("file"), skill_dir), "line": _count(d.get("line")),
             "suggestion": d.get("suggestion") if isinstance(d.get("suggestion"), str) else None}
            for d in (raw if isinstance(raw, list) else []) if isinstance(d, dict)]


def _description_issue(rule):
    return isinstance(rule, str) and (rule.startswith(DESCRIPTION_RULE_PREFIX) or rule in DESCRIPTION_RULES)


def _listed(data, key):
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, list) else []


def from_files(reader, skill_check, tessl, skill_dir):
    """The file-mode result (module docstring), or combine()'s error object."""
    checked = reader.read_json_object(skill_check)
    review = reader.read_json_object(tessl)
    score, _ = reader.quality_score(checked, skill_dir)
    reviewed = isinstance(review, dict) and review.get("status") == "reviewed"
    review_score = review.get("review_score") if reviewed else None
    result = combine({"skillCheckScore": score, "tesslReviewScore": review_score})
    if result.get("code") == "INVALID_INPUT":
        return result
    summary = checked.get("summary") if isinstance(checked, dict) else None
    summary = summary if isinstance(summary, dict) else {}
    diagnostics = _diagnostics(checked, skill_dir)
    validation = review.get("validation") if reviewed and isinstance(review.get("validation"), dict) else {}
    return {
        **result,
        "skillCheckScore": score,
        "skillCheckErrorCount": _count(summary.get("errorCount")) if checked is not None else None,
        "skillCheckWarningCount": _count(summary.get("warningCount")) if checked is not None else None,
        "descriptionIssues": any(_description_issue(d["ruleId"]) for d in diagnostics),
        "skillCheckDiagnostics": diagnostics,
        "tesslReviewScore": review_score,
        "tesslDescriptionScore": _number(review.get("description_score")) if reviewed else None,
        "tesslValidationFindings": [f for f in _listed(validation, "findings") if isinstance(f, dict)],
        "tesslDescriptionSuggestions": _listed(review, "description_suggestions") if reviewed else [],
        "tesslContentSuggestions": _listed(review, "content_suggestions") if reviewed else [],
    }


def _file_summary(result, output):
    """What main prints when file mode wrote --output: what external-validators.md §4 binds."""
    keys = ("externalScore", "toolsUsed", "skillCheckScore", "skillCheckErrorCount", "skillCheckWarningCount",
            "descriptionIssues")
    return {**{key: result[key] for key in keys}, "output": output}


def _file_mode(args):
    """Run file mode: print the result or a refusal, write --output, return the exit code."""
    def refuse(error, code=2):
        if args.output:
            Path(args.output).unlink(missing_ok=True)
        print(json.dumps(error, indent=2))
        return code

    if args.stdin or args.json_input_flag is not None or args.json_input is not None:
        return refuse(make_error("--skill-check, --tessl and --skill-dir read the tools' files in place of a JSON "
                                 "input: pass one or the other"))
    if args.skill_check is None and args.tessl is None:
        return refuse(make_error("--skill-dir goes with --skill-check or --tessl"))
    if args.skill_dir is None:
        return refuse(make_error("--skill-check and --tessl need --skill-dir, the skill folder skill-check checked"))
    reader = _load_reader()
    if reader is None:
        return refuse({"error": f"{READER} is missing from {SHARED_SCRIPTS}: re-install SKF",
                       "code": "HELPER_MISSING"}, code=1)
    result = from_files(reader, args.skill_check, args.tessl, args.skill_dir)
    if result.get("code") == "INVALID_INPUT":
        return refuse(result)
    if args.output:
        _write_output(args.output, result)
    print(json.dumps(_file_summary(result, args.output) if args.output else result, indent=2))
    return 0


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
    if any(getattr(args, flag) is not None for flag in FILE_FLAGS):
        return _file_mode(args)
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
    refused = isinstance(result, dict) and result.get("code") == "INVALID_INPUT"
    if args.output:
        _write_output(args.output, result)
    print(json.dumps(result if refused or not args.output else _summary(result, args.output), indent=2))
    return 2 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
