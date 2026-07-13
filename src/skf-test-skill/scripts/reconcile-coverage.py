#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic Documented-vs-Source coverage reconciliation.

Set-reconciliation helper for the SKF test-skill workflow (coverage-check.md
§2c). Distinct from compute-score.py (which owns weight tables, redistribution,
and the INCONCLUSIVE floor): this script performs the coverage *numerator*
arithmetic that §2c calls the "Deterministic Intersection" — turning two
already-extracted name lists (the §1 documented inventory and the §2 source
barrel) into a reproducible {documented, missing, stale, exportCoverage}
result, so the numerator no longer swings between runs on split-body skills.

It covers the three branches §2c enumerates:

  * "barrel"  (enumerated path) — intersect documented_set against the source
    barrel_set: Documented = |documented_set ∩ barrel_set|,
    Missing = barrel_set − documented_set, Stale = documented_set − barrel_set,
    Export Coverage = |Documented| / |barrel_set| * 100.

  * "scalar"  (§4 priority-1 effective_denominator, no enumerated name set) —
    grep each documented name across SKILL.md ∪ references/*.md;
    Documented = count present, denominator = effective_denominator,
    Missing = denominator − Documented, Stale not enumerable (empty),
    Export Coverage = Documented / denominator * 100.

  * "stack"   (skill_type == "stack", empty source barrel) — grep each
    composition-surface name (provenance-map cited contracts, ::-excluded, or
    libraries + integration_pairs — resolved upstream) across
    SKILL.md ∪ references/*.md; denominator = stack_denominator,
    Missing = denominator − Documented, Stale not enumerable,
    Export Coverage = Documented / stack_denominator * 100.

CLI usage:
  uv run reconcile-coverage.py '<JSON>'                  # JSON literal positional
  uv run reconcile-coverage.py --json-input '<JSON>'     # explicit flag form
  cat input.json | uv run reconcile-coverage.py --stdin  # piped input

Input schema (one object):
  {
    "denominatorSource": "barrel" | "scalar" | "stack",   # required
    "exports": [ {"name": "...", "kind": "..."}, ... ],    # §1 inventory
    "barrelSet": ["a", "b", ...],                          # barrel: resolved name set
    "perFileResults": [ {"exports_found": ["a", ...]} ],   # barrel: union'd if no barrelSet
    "denominatorValue": <int>,                             # scalar/stack: resolved denominator
    "compositionNames": ["lib::x", ...],                   # stack: names to grep
    "skillPackagePath": "/path/to/skill"                   # scalar/stack: SKILL.md ∪ references
  }

Output (stdout, one object):
  {
    "branch": "enumerated" | "scalar" | "stack",
    "denominatorSource": "barrel" | "scalar" | "stack",
    "denominator": <int>,
    "documented": <int>,
    "missing": [names],          # enumerated: source names not documented; scalar/stack: []
    "missingCount": <int>,       # always present
    "stale": [names],            # enumerated: documented names not in source; scalar/stack: []
    "staleCount": <int>,         # always present
    "staleApplicable": <bool>,   # false for scalar/stack (no barrel to enumerate)
    "exportCoverage": <float>
  }

Exit codes:
  0  — reconciliation emitted successfully
  1  — no input / input could not be parsed as JSON
  2  — input parsed but schema/semantics invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

VALID_SOURCES = ("barrel", "scalar", "stack")


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


# --- Grep (documented-name presence) ---------------------------------------


def load_doc_text(skill_package_path):
    """Concatenate SKILL.md ∪ references/*.md text for name-presence grepping.

    Deterministic: references are read in sorted order. Reads as UTF-8 so
    non-ASCII exports do not mojibake on Windows (cp1252 default).
    """
    root = Path(skill_package_path)
    parts = []
    skill_md = root / "SKILL.md"
    if skill_md.is_file():
        parts.append(skill_md.read_text(encoding="utf-8"))
    refs_dir = root / "references"
    if refs_dir.is_dir():
        for ref in sorted(refs_dir.glob("*.md")):
            parts.append(ref.read_text(encoding="utf-8"))
    return "\n".join(parts)


def names_present(names, doc_text):
    """Return the sorted, de-duplicated set of `names` that appear in doc_text.

    Substring containment, case-sensitive — mirrors `grep "{name}"`.
    """
    present = {n for n in names if isinstance(n, str) and n and n in doc_text}
    return sorted(present)


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
    else:  # scalar / stack
        dv = inp.get("denominatorValue")
        if not isinstance(dv, int) or isinstance(dv, bool) or dv < 0:
            return f"{source} branch requires integer `denominatorValue` >= 0"
        if not inp.get("skillPackagePath"):
            return f"{source} branch requires `skillPackagePath` to grep SKILL.md ∪ references"
        if source == "stack" and inp.get("compositionNames") is None:
            return "stack branch requires `compositionNames` (composition-surface names to grep)"
    return None


def reconcile(inp, doc_text=None):
    """Pure reconciliation. `doc_text` may be injected (tests); else loaded from disk."""
    err = _validate(inp)
    if err:
        return make_error(err)

    source = inp["denominatorSource"]

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

    # scalar / stack — grep-based numerator against SKILL.md ∪ references
    denominator = inp["denominatorValue"]
    if doc_text is None:
        doc_text = load_doc_text(inp["skillPackagePath"])

    if source == "scalar":
        candidates = sorted(build_documented_set(inp.get("exports")))
    else:  # stack
        candidates = [n for n in inp["compositionNames"] if isinstance(n, str) and n]

    present = names_present(candidates, doc_text)
    documented = len(present)

    if denominator == 0:
        return make_error(
            f"{source} branch: denominatorValue is 0 — Export Coverage is undefined; "
            "upstream §2b guard should HALT before reconciliation"
        )

    missing_count = denominator - documented
    return {
        "branch": source,
        "denominatorSource": source,
        "denominator": denominator,
        "documented": documented,
        "missing": [],
        "missingCount": missing_count,
        "stale": [],
        "staleCount": 0,
        "staleApplicable": False,
        "exportCoverage": round2(documented / denominator * 100),
    }


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="reconcile-coverage",
        description=(
            "Deterministic Documented-vs-Source coverage reconciliation "
            "(coverage-check.md §2c). Consumes the §1 documented inventory and "
            "the §2 source barrel (or a resolved scalar/stack denominator + the "
            "skill package path) and emits {documented, missing, stale, "
            "exportCoverage} so the coverage numerator is reproducible."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example (barrel branch):\n"
            "  uv run reconcile-coverage.py "
            "'{\"denominatorSource\":\"barrel\","
            "\"exports\":[{\"name\":\"a\",\"kind\":\"function\"}],"
            "\"barrelSet\":[\"a\",\"b\"]}'"
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

    result = reconcile(data)
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("code") == "INVALID_INPUT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
