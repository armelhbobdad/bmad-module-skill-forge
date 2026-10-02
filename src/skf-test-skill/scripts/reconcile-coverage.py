#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Deterministic Documented-vs-Source coverage reconciliation.

Set-reconciliation helper for the SKF test-skill workflow (coverage-check.md
§2c). Distinct from compute-score.py (which owns weight tables, redistribution,
and the INCONCLUSIVE floor): this script performs the coverage *numerator*
arithmetic that §2c calls the "Deterministic Intersection" — turning two
already-extracted name lists (the §1 documented inventory and the §2 source
barrel) into a reproducible {documented, missing, stale, exportCoverage}
result, so the numerator no longer swings between runs on split-body skills.

It covers the four branches §2c enumerates:

  * "barrel"  (enumerated path) — intersect documented_set against the source
    barrel_set: Documented = |documented_set ∩ barrel_set|,
    Missing = barrel_set − documented_set, Stale = documented_set − barrel_set,
    Export Coverage = |Documented| / |barrel_set| * 100.

  * "scalar"  (§4 priority-1 effective_denominator, no enumerated name set) —
    look each documented name up in SKILL.md ∪ references/*.md;
    Documented = count present, denominator = effective_denominator,
    Missing = max(0, denominator − Documented), Stale not enumerable (empty),
    Export Coverage = min(100, Documented / denominator * 100).

  * "stack"   (skill_type == "stack", empty source barrel): look each
    composition-surface name (provenance-map cited contracts, ::-excluded, or
    libraries + integration_pairs, from load-coverage-inputs.py) up in
    SKILL.md ∪ references/*.md; denominator = stack_denominator,
    Missing = max(0, denominator − Documented), Stale not enumerable,
    Export Coverage = min(100, Documented / stack_denominator * 100).

  * "docsOnly" (a skill whose citations are all [EXT:...], or no source
    access): no source to compare against, so Export Coverage measures
    documentation completeness: complete items / documented items * 100,
    one item per name and kind of the §1 inventory, complete when it has a
    description and, for a function or method, params and a return type
    (validate-inventory.py's rule).

The two lookup branches bound their outputs because the numerator and the
denominator are independent measures of different sets: the lookup count can
exceed a consumer-surface denominator without either being wrong. Unbounded,
that produced a negative Missing and a >100% coverage that compute-score.py
rejects as out of range. `documented` is left as the true count (it is reported
verbatim as "Documented in SKILL.md"); the derived ratio is what gets bounded,
and `numeratorSurplus` / `coverageUncapped` / `coverageCapped` report the
overshoot so a deflated denominator stays visible instead of being swallowed.

A name counts as written when SKILL.md or a .md file directly in references/
holds it as a fixed string, case-sensitive, never inside a longer identifier
(`get` is not found in `target` or `getAll`): the rule validate-inventory.py
defines, which this script loads from beside it.

CLI usage:
  uv run reconcile-coverage.py --denominator-source <source> [file flags] --output <file>
  uv run reconcile-coverage.py '<JSON>'                  # JSON literal positional
  uv run reconcile-coverage.py --json-input '<JSON>'     # explicit flag form
  cat input.json | uv run reconcile-coverage.py --stdin  # piped input

File flags read the inputs from the run folder instead of a JSON payload;
each sets the input field it names and wins over the same field in the JSON:
  --denominator-source  denominatorSource
  --denominator-value   denominatorValue (scalar), when no --coverage-inputs
                        file gives it
  --skill-dir           skillPackagePath (scalar, stack)
  --inventory PATH      exports: the validated inventory validate-inventory.py
                        wrote with --output
  --surface PATH        barrelSet: one name set of load-coverage-inputs.py
                        surface, chosen by --surface-set (default "all")
  --coverage-inputs PATH  load-coverage-inputs.py metadata output: for the
                        scalar branch, denominatorValue from its
                        `effectiveDenominator` (stats.effective_denominator);
                        for the stack branch, compositionNames and
                        denominatorValue from its `stack` object
  --verified PATH       scalar: verify-declared-numerator.py's result; when it
                        found the declared count inflated, its `verified`
                        count is the numerator
  --output PATH         also write the result to this file (UTF-8 JSON); a
                        refused input removes a file left there earlier

Input schema (one object):
  {
    "denominatorSource": "barrel" | "scalar" | "stack" | "docsOnly",  # required
    "exports": [ {"name": "...", "kind": "..."}, ... ],    # §1 inventory
    "barrelSet": ["a", "b", ...],                          # barrel: resolved name set
    "perFileResults": [ {"exports_found": ["a", ...]} ],   # barrel: union'd if no barrelSet
    "denominatorValue": <int>,                             # scalar/stack: resolved denominator
    "compositionNames": ["lib::x", ...],                   # stack: names to look up
    "skillPackagePath": "/path/to/skill",                  # scalar/stack: SKILL.md ∪ references
    "verifiedNumerator": <int>                             # scalar: overrides the lookup count
  }

Output (stdout, one object):
  {
    "branch": "enumerated" | "scalar" | "stack" | "docsOnly",
    "denominatorSource": "barrel" | "scalar" | "stack" | "docsOnly",
    "denominator": <int>,
    "documented": <int>,
    "missing": [names],          # enumerated: source names not documented; others: []
    "missingCount": <int>,       # always present; never negative
    "stale": [names],            # enumerated: documented names not in source; others: []
    "staleCount": <int>,         # always present
    "staleApplicable": <bool>,   # false for scalar/stack/docsOnly (no barrel to enumerate)
    "exportCoverage": <float>,   # scalar/stack: capped at 100
    "numeratorSurplus": <int>,   # scalar/stack only: max(0, documented − denominator)
    "coverageUncapped": <float>, # scalar/stack only: the ratio before the cap
    "coverageCapped": <bool>,    # scalar/stack only: true when the cap bound the ratio
    "numeratorSource": "lookup" | "verified",  # scalar only
    "incomplete": [{"name", "kind", "missing"}]  # docsOnly only: the incomplete items
  }

Exit codes:
  0  reconciliation emitted successfully
  1  no input, input that does not parse as JSON, or an input file that cannot be read
  2  input parsed but schema/semantics invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

VALID_SOURCES = ("barrel", "scalar", "stack", "docsOnly")

_INVENTORY_MODULE = None


def _inventory():
    """validate-inventory.py beside this script: the name match and completeness rules live there."""
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
    """Round to 2 decimals with JS-compatible half-up rounding (matches compute-score.py)."""
    return math.floor(value * 100 + 0.5) / 100


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


# --- Documented-set derivation ---------------------------------------------


def build_documented_set(exports):
    """De-duplicated set of `name` from the §1 inventory, excluding kind:"method".

    Methods are members of an already-counted class/type, not top-level barrel
    exports (coverage-check.md §2c step 1).
    """
    names = set()
    for entry in exports or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") == "method":
            continue
        name = entry.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return names


def build_barrel_set(inp):
    """barrel_set = explicit `barrelSet` if given, else union of exports_found[]."""
    if inp.get("barrelSet") is not None:
        return {n for n in inp["barrelSet"] if isinstance(n, str) and n}
    barrel = set()
    for result in inp.get("perFileResults") or []:
        if not isinstance(result, dict):
            continue
        for name in result.get("exports_found") or []:
            if isinstance(name, str) and name:
                barrel.add(name)
    return barrel


# --- Documented-name lookup ---------------------------------------------------


def load_doc_text(skill_package_path):
    """SKILL.md ∪ references/*.md text, as validate-inventory.py reads it."""
    return _inventory().load_doc_text(skill_package_path)


def names_present(names, doc_text):
    """The sorted, de-duplicated `names` the doc text writes (validate-inventory.py's match)."""
    return _inventory().names_present(names, doc_text)


# --- Core reconciliation ----------------------------------------------------


def _validate(inp):
    if inp is None or not isinstance(inp, dict):
        return "Input must be a JSON object"
    source = inp.get("denominatorSource")
    if source not in VALID_SOURCES:
        return (
            "Missing or invalid required field: denominatorSource "
            f"(must be one of: {', '.join(VALID_SOURCES)})"
        )
    if source == "barrel":
        if inp.get("barrelSet") is None and inp.get("perFileResults") is None:
            return "barrel branch requires either `barrelSet` or `perFileResults`"
    elif source == "docsOnly":
        if not isinstance(inp.get("exports"), list):
            return "docsOnly branch requires the §1 inventory `exports` (or --inventory)"
    else:  # scalar / stack
        dv = inp.get("denominatorValue")
        if not isinstance(dv, int) or isinstance(dv, bool) or dv < 0:
            return f"{source} branch requires integer `denominatorValue` >= 0"
        if not inp.get("skillPackagePath"):
            return f"{source} branch requires `skillPackagePath` to read SKILL.md ∪ references"
        if source == "stack" and inp.get("compositionNames") is None:
            return "stack branch requires `compositionNames` (composition-surface names to look up)"
        verified = inp.get("verifiedNumerator")
        if verified is not None and (not isinstance(verified, int) or isinstance(verified, bool) or verified < 0):
            return "verifiedNumerator must be an integer >= 0"
    return None


def _docs_only(inp):
    tally = _inventory().completeness(inp["exports"])
    total = tally["total"]
    if total == 0:
        return make_error(
            "docsOnly branch: the inventory documents no item, so Export Coverage is "
            "undefined; the §2b docs-only guard should HALT"
        )
    return {
        "branch": "docsOnly",
        "denominatorSource": "docsOnly",
        "denominator": total,
        "documented": tally["complete"],
        "missing": [],
        "missingCount": total - tally["complete"],
        "stale": [],
        "staleCount": 0,
        "staleApplicable": False,
        "exportCoverage": round2(tally["complete"] / total * 100),
        "incomplete": tally["incomplete"],
    }


def reconcile(inp, doc_text=None):
    """Pure reconciliation. `doc_text` may be injected (tests); else loaded from disk."""
    err = _validate(inp)
    if err:
        return make_error(err)

    source = inp["denominatorSource"]

    if source == "docsOnly":
        return _docs_only(inp)

    if source == "barrel":
        documented_set = build_documented_set(inp.get("exports"))
        barrel_set = build_barrel_set(inp)
        if not barrel_set:
            return make_error(
                "barrel branch: barrel_set is empty (denominator 0) — "
                "Export Coverage is undefined; upstream §2b zero-exports guard should HALT"
            )
        documented_names = documented_set & barrel_set
        missing = sorted(barrel_set - documented_set)
        stale = sorted(documented_set - barrel_set)
        denominator = len(barrel_set)
        documented = len(documented_names)
        return {
            "branch": "enumerated",
            "denominatorSource": source,
            "denominator": denominator,
            "documented": documented,
            "missing": missing,
            "missingCount": len(missing),
            "stale": stale,
            "staleCount": len(stale),
            "staleApplicable": True,
            "exportCoverage": round2(documented / denominator * 100),
        }

    # scalar / stack: looked-up numerator against SKILL.md ∪ references
    denominator = inp["denominatorValue"]
    if denominator == 0:
        return make_error(
            f"{source} branch: denominatorValue is 0 — Export Coverage is undefined; "
            "upstream §2b guard should HALT before reconciliation"
        )

    numerator_source = "lookup"
    if source == "scalar" and inp.get("verifiedNumerator") is not None:
        # §4b's numerator ground truth found the declared count padded: its
        # verified count is authoritative and replaces the lookup.
        documented = inp["verifiedNumerator"]
        numerator_source = "verified"
    else:
        if doc_text is None:
            doc_text = load_doc_text(inp["skillPackagePath"])
        if source == "scalar":
            candidates = sorted(build_documented_set(inp.get("exports")))
        else:  # stack
            candidates = [n for n in inp["compositionNames"] if isinstance(n, str) and n]
        documented = len(names_present(candidates, doc_text))

    # The looked-up numerator and the resolved denominator are independent
    # measures, so `documented` can legitimately exceed `denominator`: a
    # consumer-surface denominator counts one surface while the documented body
    # may also name migration aliases, re-exported sibling symbols, and other
    # extras. Left unbounded that yields a negative Missing and >100% coverage
    # (which compute-score.py then rejects outright as out of range).
    #
    # `documented` stays the true count: it is reported as "Documented in
    # SKILL.md", so capping it would print a number that was never measured.
    # The derived ratio is what gets bounded, and the surplus is surfaced rather
    # than swallowed so a deflated denominator stays visible.
    surplus = max(0, documented - denominator)
    coverage_uncapped = round2(documented / denominator * 100)
    result = {
        "branch": source,
        "denominatorSource": source,
        "denominator": denominator,
        "documented": documented,
        "missing": [],
        "missingCount": max(0, denominator - documented),
        "numeratorSurplus": surplus,
        "stale": [],
        "staleCount": 0,
        "staleApplicable": False,
        "exportCoverage": min(100.0, coverage_uncapped),
        "coverageUncapped": coverage_uncapped,
        "coverageCapped": surplus > 0,
    }
    if source == "scalar":
        result["numeratorSource"] = numerator_source
    return result


# --- Run-folder inputs --------------------------------------------------------


class InputFileError(Exception):
    """A file flag names a file that cannot be read or does not hold what it should."""


def _read_json_file(path, flag):
    try:
        return json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise InputFileError(f"cannot read {flag} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputFileError(f"{flag} {path} is not JSON: {exc.msg}") from exc


def apply_file_inputs(inp, args):
    """Fill the input object from the file flags; each flag wins over the JSON field."""
    if args.denominator_source is not None:
        inp["denominatorSource"] = args.denominator_source
    if args.denominator_value is not None:
        inp["denominatorValue"] = args.denominator_value
    if args.skill_dir is not None:
        inp["skillPackagePath"] = args.skill_dir
    if args.inventory is not None:
        data = _read_json_file(args.inventory, "--inventory")
        if isinstance(data, dict) and isinstance(data.get("inventory"), dict):
            data = data["inventory"]  # validate-inventory.py's whole result
        if not isinstance(data, dict) or not isinstance(data.get("exports"), list):
            raise InputFileError(f"--inventory {args.inventory} holds no `exports` list")
        inp["exports"] = data["exports"]
    if args.surface is not None:
        data = _read_json_file(args.surface, "--surface")
        sets = data.get("sets") if isinstance(data, dict) else None
        names = sets.get(args.surface_set) if isinstance(sets, dict) else None
        if not isinstance(names, list):
            raise InputFileError(f"--surface {args.surface} has no name set `{args.surface_set}`")
        inp["barrelSet"] = names
    if args.coverage_inputs is not None:
        data = _read_json_file(args.coverage_inputs, "--coverage-inputs")
        if not isinstance(data, dict):
            raise InputFileError(f"--coverage-inputs {args.coverage_inputs} is not a JSON object")
        if inp.get("denominatorSource") == "scalar":
            if args.denominator_value is None:
                if data.get("effectiveDenominator") is None:
                    raise InputFileError(f"--coverage-inputs {args.coverage_inputs} has no "
                                         "`effectiveDenominator`: metadata.json has no stats.effective_denominator")
                inp["denominatorValue"] = data["effectiveDenominator"]
        else:
            stack = data.get("stack")
            if not isinstance(stack, dict):
                raise InputFileError(f"--coverage-inputs {args.coverage_inputs} has no `stack` object")
            inp["compositionNames"] = stack.get("compositionNames")
            if args.denominator_value is None:
                inp["denominatorValue"] = stack.get("denominator")
    if args.verified is not None:
        data = _read_json_file(args.verified, "--verified")
        if not isinstance(data, dict):
            raise InputFileError(f"--verified {args.verified} is not a verify-declared-numerator.py result")
        if data.get("inflated") is True:
            inp["verifiedNumerator"] = data.get("verified")
    return inp


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="reconcile-coverage",
        description=(
            "Deterministic Documented-vs-Source coverage reconciliation "
            "(coverage-check.md §2c). Consumes the §1 documented inventory and "
            "the §2 source surface (or a resolved scalar/stack denominator + the "
            "skill package path, or the inventory alone for a docs-only skill) and "
            "emits {documented, missing, stale, exportCoverage} so the coverage "
            "numerator is reproducible."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example (barrel branch):\n"
            "  uv run reconcile-coverage.py --denominator-source barrel "
            "--inventory run/inventory.json --surface run/surface.json --output run/coverage.json"
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
    files = parser.add_argument_group("inputs read from files (each wins over the same JSON field)")
    files.add_argument("--denominator-source", choices=VALID_SOURCES, help="the §2c branch")
    files.add_argument("--denominator-value", type=int, metavar="N",
                       help="the resolved scalar denominator")
    files.add_argument("--skill-dir", metavar="DIR", help="the skill package: SKILL.md and references/")
    files.add_argument("--inventory", metavar="PATH", help="the validated inventory file")
    files.add_argument("--surface", metavar="PATH", help="load-coverage-inputs.py surface output")
    files.add_argument("--surface-set", default="all", metavar="NAME",
                       help="the name set of --surface to intersect against (default: all)")
    files.add_argument("--coverage-inputs", metavar="PATH",
                       help="load-coverage-inputs.py metadata output (scalar and stack branches)")
    files.add_argument("--verified", metavar="PATH",
                       help="verify-declared-numerator.py output (scalar branch)")
    parser.add_argument("--output", metavar="PATH", help="also write the result to this file")
    return parser


FILE_FLAGS = ("denominator_source", "denominator_value", "skill_dir", "inventory", "surface",
              "coverage_inputs", "verified")


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.json_input_flag is not None:
        return args.json_input_flag
    if args.json_input is not None:
        return args.json_input
    return ""


def _write_output(path, result):
    target = Path(path)
    if result.get("code") == "INVALID_INPUT":
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw = _resolve_input(args)
    from_files = any(getattr(args, flag) is not None for flag in FILE_FLAGS)
    if not raw.strip() and not from_files:
        parser.print_usage(file=sys.stderr)
        print(
            "error: no input provided (positional arg, --json-input, --stdin or the file flags)",
            file=sys.stderr,
        )
        return 1

    data = {}
    if raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(json.dumps(make_error(f"Invalid JSON: {exc.msg}"), indent=2))
            return 1

    if isinstance(data, dict):
        try:
            data = apply_file_inputs(data, args)
        except InputFileError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    result = reconcile(data)
    if args.output:
        _write_output(args.output, result)
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    of the --help text, so --help would stop with UnicodeEncodeError.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    raise SystemExit(main())
