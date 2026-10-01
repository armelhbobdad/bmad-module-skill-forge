#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic contextual-coherence aggregator.

Pure-function tally + weighted mean for the SKF test-skill workflow
(step-04, coherence-check.md §5c). The prompt keeps the judgment — deciding
which skill, type-import and integration-pattern references are accurate
(§4) and which integration patterns are complete (§5). This script does the
counting and the arithmetic those judgments feed: it counts the valid
references from the per-reference results, then computes the
reference-validity ratio, the integration-completeness ratio, and their
fixed 0.6 / 0.4 weighted mean. That way the 18%-weight `coherence` input to
compute-score.py is computed once, deterministically, instead of by hand on
every run (this skill grades other skills — a false PASS is catastrophic, so
every scoring input is scripted for run-to-run reproducibility).

Per-reference input (the files coherence-check.md §5c passes):
  --references   skf-scan-skill-md-structure.py reference-check output: its
                 `references[]` hold the file-path and script/asset
                 references, each valid when its `status` is "ok"
                 ("missing": no file inside an allowed root; "escapes":
                 outside every root)
  --judged       the §4 subagent results for the other references (skill,
                 type-import, integration-pattern), as the subagent returned
                 them (a wrapping markdown fence is stripped): a JSON array,
                 or an object with a `references` array, of
                 {"reference", "line", "target_exists", "type_match",
                  "signature_match", "issues"}; valid when the three
                 booleans are true and `issues` is empty. Optional: a skill
                 with no such reference has no file.
  --integration  the §5 integration JSON ({"patterns_documented",
                 "patterns_complete", ...}, fence stripped)
  `total_references` is the number of entries in both, `valid_references`
  the number of valid ones, and `invalidReferences[]` lists each invalid
  one with its `status`: "missing" or "escapes" from the scan, and for a
  judged one "missing" (target_exists false) or "inaccurate". Each entry
  also carries what coherence-check.md §5c needs for its gap, so the
  caller never matches it back to the per-reference files: a scanned
  one's `canonical` (the realpath the scanner checked, which an escape
  names) and `root`, and a judged one's `issues` (when the subagent gave
  none, the flags that are false, such as "type_match: false").

Formula (this script is its one home: scoring-rules.md points here, and
coherence-check.md §5 defines what makes a pattern complete):

    reference_validity       = (valid_references / total_references) * 100
    integration_completeness = (complete_patterns / total_patterns) * 100
    combined_coherence       = reference_validity * 0.6 + integration_completeness * 0.4

Field-name mapping: the step-04 §5 integration JSON calls the pattern counts
`patterns_documented` (= total_patterns) and `patterns_complete`
(= complete_patterns); this script's input uses those step-04 names directly
so §5c passes them through unrenamed.

Edge cases (absence is never penalized):
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
    "input": { ...echo, or the counts the files gave... },
    "referenceValidity":       <0-100>,
    "integrationCompleteness": <0-100 | null when patterns_documented == 0>,
    "combinedCoherence":       <0-100>,
    "patternsScored":          <bool>,
    "invalidReferences":       [{"source": "scan" | "judged", "line": N | null,
                                 "target": "...", "status": "...",
                                 "canonical": "..." | null, "root": "..." | null,
                                 "issues": ["..."]}]
                               # with the per-reference files only; canonical
                               # and root are null for a judged entry, and
                               # issues is empty for a scanned one
  }
  or {"error": ..., "code": "INVALID_INPUT"} on a schema violation.

Percentages use the same JavaScript-compatible 2-decimal rounding as
compute-score.py so the two scoring scripts agree to the last digit.

CLI usage (mirrors compute-score.py):
  uv run aggregate-coherence.py --references <scan.json> [--judged <file>] --integration <file>
  uv run aggregate-coherence.py '<JSON>'                  # counts, positional arg
  uv run aggregate-coherence.py --json-input '<JSON>'     # counts, explicit flag form
  cat input.json | uv run aggregate-coherence.py --stdin  # counts, piped input

--output <file> also writes the result to a file (UTF-8 JSON), the one
compute-score.py --coherence reads; a refused input removes a file left
there earlier.

Exit codes (same convention as compute-score.py / reconcile-coverage.py):
  0  a result object was emitted
  1  input could not be parsed at all (no input provided, malformed JSON,
     or a file that cannot be read)
  2  input parsed but schema/semantics invalid

Both 1 and 2 emit an {"error": ..., "code": "INVALID_INPUT"} envelope on stdout,
so the envelope's presence — not the specific code — tells a caller the input was
refused rather than scored.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

# Weights for the combined-coherence mean. Kept as
# named constants so the 0.6 / 0.4 split lives in exactly one place.
REFERENCE_VALIDITY_WEIGHT = 0.6
INTEGRATION_COMPLETENESS_WEIGHT = 0.4

COUNT_FIELDS = (
    "valid_references",
    "total_references",
    "patterns_documented",
    "patterns_complete",
)

# reference-check statuses (skf-scan-skill-md-structure.py); only "ok" is valid.
SCAN_STATUSES = ("ok", "missing", "escapes")
JUDGED_FLAGS = ("target_exists", "type_match", "signature_match")

_INVENTORY_MODULE = None


def _inventory_module():
    """validate-inventory.py beside this script: the fence rule lives there."""
    global _INVENTORY_MODULE
    if _INVENTORY_MODULE is None:
        sibling = Path(__file__).resolve().parent / "validate-inventory.py"
        spec = importlib.util.spec_from_file_location("skf_validate_inventory", sibling)
        if spec is None or spec.loader is None or not sibling.is_file():
            raise ImportError(f"validate-inventory.py not found beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _INVENTORY_MODULE = module
    return _INVENTORY_MODULE


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


def count_references(scan, judged):
    """Count the valid references from the per-reference results.

    `scan` is the reference-check output (an object with `references[]`),
    `judged` the list of subagent results (or None). Returns
    (valid, total, invalid[]) or an error string.

    >>> scan = {"references": [{"line": 3, "target": "a.md", "status": "ok"},
    ...                        {"line": 5, "target": "../x", "status": "escapes"}]}
    >>> judged = [{"reference": "react", "line": 9, "target_exists": True, "type_match": True,
    ...            "signature_match": True, "issues": []},
    ...           {"reference": "./types", "line": 12, "target_exists": True, "type_match": False,
    ...            "signature_match": True, "issues": []}]
    >>> valid, total, invalid = count_references(scan, judged)
    >>> valid, total, [(i["target"], i["status"]) for i in invalid]
    (2, 4, [('../x', 'escapes'), ('./types', 'inaccurate')])
    >>> invalid[1]["issues"], invalid[1]["canonical"]
    (['type_match: false'], None)
    """
    refs = scan.get("references") if isinstance(scan, dict) else None
    if not isinstance(refs, list):
        return "--references holds no `references` array (pass the reference-check output)"
    valid, invalid = 0, []
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict) or ref.get("status") not in SCAN_STATUSES:
            return f"--references references[{index}] has no status in {list(SCAN_STATUSES)}"
        if ref["status"] == "ok":
            valid += 1
        else:
            invalid.append({"source": "scan", "line": ref.get("line"),
                            "target": ref.get("target"), "status": ref["status"],
                            "canonical": ref.get("canonical"), "root": ref.get("root"),
                            "issues": []})
    for index, ref in enumerate(judged or []):
        if not isinstance(ref, dict):
            return f"--judged [{index}] is not an object"
        for flag in JUDGED_FLAGS:
            if not isinstance(ref.get(flag), bool):
                return f"--judged [{index}] `{flag}` must be true or false"
        issues = ref.get("issues", [])
        if not isinstance(issues, list):
            return f"--judged [{index}] `issues` must be a list"
        if all(ref[flag] for flag in JUDGED_FLAGS) and not issues:
            valid += 1
        else:
            invalid.append({"source": "judged", "line": ref.get("line"), "target": ref.get("reference"),
                            "status": "missing" if not ref["target_exists"] else "inaccurate",
                            "canonical": None, "root": None,
                            "issues": [str(i) for i in issues]
                            or [f"{flag}: false" for flag in JUDGED_FLAGS if not ref[flag]]})
    return valid, len(refs) + len(judged or []), invalid


def _read_json_file(path, label, fenced=False):
    """Parse a JSON file; a subagent response may come wrapped in a markdown fence."""
    text = Path(path).read_bytes().decode("utf-8-sig")
    if fenced:
        text = _inventory_module().strip_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} {path} is not valid JSON: {exc.msg}") from exc


def aggregate_from_files(references, judged=None, integration=None):
    """Aggregate from the per-reference files and the §5 integration JSON."""
    scan = _read_json_file(references, "--references")
    results = None
    if judged is not None:
        results = _read_json_file(judged, "--judged", fenced=True)
        if isinstance(results, dict):
            results = results.get("references")
        if not isinstance(results, list):
            return make_error(f"--judged {judged} holds no array of reference results")
    patterns = _read_json_file(integration, "--integration", fenced=True)
    if not isinstance(patterns, dict):
        return make_error(f"--integration {integration} is not a JSON object")
    counted = count_references(scan, results)
    if isinstance(counted, str):
        return make_error(counted)
    valid, total, invalid = counted
    result = aggregate_coherence({
        "valid_references": valid,
        "total_references": total,
        "patterns_documented": patterns.get("patterns_documented"),
        "patterns_complete": patterns.get("patterns_complete"),
    })
    if result.get("code") != "INVALID_INPUT":
        result["invalidReferences"] = invalid
    return result


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
    parser.add_argument("--references", metavar="PATH",
                        help="skf-scan-skill-md-structure.py reference-check output")
    parser.add_argument("--judged", metavar="PATH",
                        help="the subagent results for the skill, type-import and integration references")
    parser.add_argument("--integration", metavar="PATH",
                        help="the integration JSON (patterns_documented, patterns_complete)")
    parser.add_argument("--output", metavar="PATH", help="also write the result to this file")
    return parser


def _write_output(path, result):
    target = Path(path)
    if result.get("code") == "INVALID_INPUT":
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))


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
    files = (args.references, args.judged, args.integration)
    if any(f is not None for f in files):
        if args.stdin or args.json_input_flag is not None or args.json_input is not None:
            parser.error("pass the counts or the files (--references, --judged, --integration), not both")
        if args.references is None or args.integration is None:
            parser.error("--references and --integration go together (--judged is optional)")
        try:
            result = aggregate_from_files(*files)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print(json.dumps(make_error(str(exc)), indent=2))
            if args.output:
                Path(args.output).unlink(missing_ok=True)
            return 1
    else:
        raw = _resolve_input(args)
        if not raw.strip():
            parser.print_usage(file=sys.stderr)
            print(
                "error: no input provided (--references and --integration, positional arg, "
                "--json-input, or --stdin)",
                file=sys.stderr,
            )
            return 1

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(json.dumps(make_error(f"Invalid JSON: {exc.msg}"), indent=2))
            return 1

        result = aggregate_coherence(data)
    if args.output:
        _write_output(args.output, result)
    print(json.dumps(result, indent=2))
    # Same convention as compute-score.py / reconcile-coverage.py. This script
    # produces the coherence percentage that score.md §3a feeds to
    # compute-score.py, so a silently-rejected run here would hand a bogus or
    # absent number to the gate one layer downstream.
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
