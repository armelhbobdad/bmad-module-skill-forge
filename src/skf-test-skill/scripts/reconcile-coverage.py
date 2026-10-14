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

  * "scalar"  (§2b priority-1 effective_denominator, no enumerated name set):
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
    "documentedNames": [names],  # enumerated only: the documented names the denominator counts
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

Subcommand render (coverage-check.md §5 writes its output unchanged):
  uv run reconcile-coverage.py render --coverage <coverage.json>
      [--surface <surface.json>] [--signatures <signatures.json>]

prints the Markdown of the Coverage Analysis section that follows its
header lines, from the run files:
  **Files Analyzed:**  the distinct files the --surface export records name
                       (N/A without --surface: a docs-only run has none)
  ### Export Coverage  on the enumerated branch, one row per name the
                       denominator counts, per stale name and per name whose
                       signature mismatches, by name:
      Type             the first kind the surface records for the name, else -
      Documented       no for a missing name, else yes
      Signature        no for a mismatch, yes for a compared name that
                       matches, unverified for a documented name when no
                       --signatures was given, - otherwise
      Source Location  the file:line the surface records for the name, a
                       record with a line preferred (gap-ledger.py's rule
                       for a missing export's Source), else -
      Status           FAIL for a signature mismatch, WARN for a missing or
                       stale name, PASS otherwise
                       The scalar and stack branches count without naming
                       the exports, and a docs-only run has no source
                       surface: one line says so instead (NO_TABLE).
  ### Coverage Summary the --coverage counts, the --signatures mismatch count
                       and warnings, the numerator surplus when the ratio
                       was capped, and the names the --surface leaves out
                       or puts back: `excluded.outsideScope` (scoped out
                       by the brief), `excluded.nestedEntries` (a nested
                       Python entry point's names) and
                       `guards.staleScope.restored`, each line only when
                       it names one
  ### Category Scores  Export Coverage, and Signature Accuracy and Type
                       Coverage from --signatures (N/A without it)
Exit 0 when it printed; 1 when an input cannot be read or is not the
result of the script that writes it (one line on stderr); 2 a usage error.
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
            "documentedNames": sorted(documented_names),
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
        # §2b's numerator ground truth found the declared count padded: its
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


# --- The Coverage Analysis section (render) -----------------------------------

BRANCHES = ("enumerated", "scalar", "stack", "docsOnly")
# Why a branch names no export: the line it writes in place of the table, and its stale count.
NO_NAMES = {
    "scalar": "the scalar denominator (`stats.effective_denominator`) counts the exports without naming them",
    "stack": "the stack denominator counts the composition surface without naming each export",
    "docsOnly": "a docs-only run has no source surface",
}
NO_TABLE = {
    "scalar": f"No per-export table: {NO_NAMES['scalar']}. The summary below gives the counts.",
    "stack": f"No per-export table: {NO_NAMES['stack']}. The summary below gives the counts.",
    "docsOnly": f"No per-export table: {NO_NAMES['docsOnly']} to compare against. The summary below gives its "
                "documentation completeness.",
}

_GAP_LEDGER_MODULE = None


class RenderError(Exception):
    """A render input that is not the result of the script that writes it."""


def _gap_ledger():
    """gap-ledger.py beside this script: its rule for a missing export's Source gives the Source Location."""
    global _GAP_LEDGER_MODULE
    if _GAP_LEDGER_MODULE is None:
        sibling = Path(__file__).resolve().parent / "gap-ledger.py"
        spec = importlib.util.spec_from_file_location("skf_gap_ledger_render", sibling)
        if spec is None or spec.loader is None or not sibling.is_file():
            raise RenderError(f"gap-ledger.py not found beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _GAP_LEDGER_MODULE = module
    return _GAP_LEDGER_MODULE


def _pct(value):
    """A score as the report writes it.

    >>> _pct(60.0), _pct(66.67), _pct(None)
    ('60%', '66.67%', 'N/A')
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "N/A"
    return f"{int(value)}%" if float(value).is_integer() else f"{value}%"


def _cell(text):
    """A table cell: a `|` would end it."""
    return str(text).replace("|", "\\|")


def _string_list(data, key, label):
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise RenderError(f"{label}: `{key}` is not a list")
    return [v for v in value if isinstance(v, str) and v]


def _incomplete(item):
    """A docs-only item and the fields it lacks.

    >>> _incomplete({"name": "load", "kind": "function", "missing": ["params", "return_type"]})
    '`load` (function) lacks `params`, `return_type`'
    """
    fields = ", ".join(f"`{field}`" for field in item.get("missing") or [])
    return f"`{item.get('name')}` ({item.get('kind')}) lacks {fields}"


def _left_out(surface):
    """The Coverage Summary lines for the names the surface leaves out or puts back, each only when it names one.

    >>> for line in _left_out({
    ...         "excluded": {"outsideScope": [{"name": "gen", "file": "src/gen.ts"}],
    ...                      "nestedEntries": [{"entry": "pkg/api/__init__.py", "within": "pkg/__init__.py",
    ...                                         "names": ["router"]}]},
    ...         "guards": {"staleScope": {"restored": [{"name": "old", "file": "src/old.ts", "line": 4}]}}}):
    ...     print(line)
    - **Scoped Out by the Brief:** `gen` (src/gen.ts)
    - **Nested Entry Points:** `pkg/api/__init__.py` inside `pkg/__init__.py`: `router`
    - **Restored by the Stale-Scope Guard:** `old` (src/old.ts:4)
    >>> _left_out({"excluded": {"outsideScope": [], "nestedEntries": []}, "guards": None})
    []
    """
    def items(value):
        return [i for i in value if isinstance(i, dict)] if isinstance(value, list) else []

    def where(item):
        file, line = item.get("file"), item.get("line")
        if not isinstance(file, str) or not file:
            return ""
        return f" ({file}:{line})" if isinstance(line, int) and not isinstance(line, bool) else f" ({file})"

    excluded = surface.get("excluded") if isinstance(surface.get("excluded"), dict) else {}
    guards = surface.get("guards") if isinstance(surface.get("guards"), dict) else {}
    stale_scope = guards.get("staleScope") if isinstance(guards.get("staleScope"), dict) else {}
    lines = []
    scoped = [f"`{i['name']}`{where(i)}" for i in items(excluded.get("outsideScope"))
              if isinstance(i.get("name"), str)]
    if scoped:
        lines.append(f"- **Scoped Out by the Brief:** {', '.join(scoped)}")
    nested = [f"`{i['entry']}` inside `{i.get('within')}`: "
              + ", ".join(f"`{n}`" for n in i.get("names") or [] if isinstance(n, str))
              for i in items(excluded.get("nestedEntries")) if isinstance(i.get("entry"), str)]
    if nested:
        lines.append(f"- **Nested Entry Points:** {'; '.join(nested)}")
    restored = [f"`{i['name']}`{where(i)}" for i in items(stale_scope.get("restored"))
                if isinstance(i.get("name"), str)]
    if restored:
        lines.append(f"- **Restored by the Stale-Scope Guard:** {', '.join(restored)}")
    return lines


def _rows(coverage, surface, signatures):
    """The Export Coverage table of the enumerated branch."""
    if "documentedNames" not in coverage:
        raise RenderError("--coverage has no `documentedNames`: write it again with this reconcile-coverage.py")
    documented = set(_string_list(coverage, "documentedNames", "--coverage"))
    missing = set(_string_list(coverage, "missing", "--coverage"))
    stale = set(_string_list(coverage, "stale", "--coverage"))
    mismatched, compared = set(), set()
    if signatures is not None:
        mismatched = {m["name"] for m in signatures.get("mismatches") or []
                      if isinstance(m, dict) and isinstance(m.get("name"), str)}
        compared = set(_string_list(signatures, "comparedNames", "--signatures"))
    kinds, sources = {}, {}
    if surface is not None:
        for record in surface["exports"]:
            if isinstance(record, dict) and isinstance(record.get("name"), str) and record.get("kind"):
                kinds.setdefault(record["name"], str(record["kind"]))
        sources = _gap_ledger()._surface_sources(surface)
    rows = ["| Export | Type | Documented | Signature | Source Location | Status |",
            "|--------|------|------------|-----------|-----------------|--------|"]
    for name in sorted(documented | missing | stale | mismatched):
        if name in mismatched:
            signature = "no"
        elif name in compared:
            signature = "yes"
        elif signatures is None and name not in missing:
            signature = "unverified"
        else:
            signature = "-"
        status = "FAIL" if name in mismatched else "WARN" if name in missing or name in stale else "PASS"
        rows.append(f"| `{_cell(name)}` | {_cell(kinds.get(name, '-'))} | {'no' if name in missing else 'yes'} "
                    f"| {signature} | {_cell(sources.get(name, '-'))} | {status} |")
    return rows


def render(coverage, surface=None, signatures=None):
    """The Coverage Analysis section after its header lines, as Markdown (see the module docstring)."""
    if not isinstance(coverage, dict) or coverage.get("branch") not in BRANCHES:
        raise RenderError("--coverage is not reconcile-coverage.py's result (no known `branch`)")
    if surface is not None and not (isinstance(surface, dict) and isinstance(surface.get("exports"), list)):
        raise RenderError("--surface is not load-coverage-inputs.py surface's result (no `exports` list)")
    if signatures is not None and not (isinstance(signatures, dict) and signatures.get("valid") is True):
        raise RenderError("--signatures is not score-signatures.py score's result (no `valid: true`)")
    branch = coverage["branch"]
    docs_only = branch == "docsOnly"

    if surface is None:
        files = "N/A: no source surface"
    else:
        files = len({r["file"] for r in surface["exports"]
                     if isinstance(r, dict) and isinstance(r.get("file"), str) and r["file"]})
    lines = [f"**Files Analyzed:** {files}", "", "### Export Coverage", ""]
    lines += _rows(coverage, surface, signatures) if branch == "enumerated" else [NO_TABLE[branch]]

    denominator, documented = coverage.get("denominator"), coverage.get("documented")
    missing_count, coverage_pct = coverage.get("missingCount"), _pct(coverage.get("exportCoverage"))
    lines += ["", "### Coverage Summary", ""]
    if docs_only:
        incomplete = [_incomplete(item) for item in coverage.get("incomplete") or [] if isinstance(item, dict)]
        lines += [f"- **Exports Found:** {denominator} documented items",
                  f"- **Documented:** {documented} complete ({coverage_pct})",
                  f"- **Missing Documentation:** {missing_count} incomplete"
                  + (f": {'; '.join(incomplete)}" if incomplete else "")]
    else:
        capped = coverage.get("coverageCapped")
        floored = " (a floored residual: the numerator exceeds the denominator)" if capped else ""
        lines += [f"- **Exports Found:** {denominator}",
                  f"- **Documented:** {documented} ({coverage_pct})",
                  f"- **Missing Documentation:** {missing_count}{floored}"]
    mismatches = signatures.get("mismatches") if signatures is not None else None
    lines.append(f"- **Signature Mismatches:** {len(mismatches) if isinstance(mismatches, list) else 'N/A'}")
    if coverage.get("staleApplicable"):
        lines.append(f"- **Stale Documentation:** {coverage.get('staleCount')}, documented extras included")
    else:
        lines.append(f"- **Stale Documentation:** N/A: {NO_NAMES.get(branch, 'the denominator names no stale export')}")
    warnings = _string_list(signatures, "warnings", "--signatures") if signatures is not None else []
    if warnings:
        lines.append("- **Scoring Warnings:**")
        lines += [f"  - {w}" for w in warnings]
    if coverage.get("coverageCapped"):
        lines.append(f"- **Numerator Surplus:** {coverage.get('numeratorSurplus')}, uncapped coverage "
                     f"{_pct(coverage.get('coverageUncapped'))}")
    if surface is not None:
        lines += _left_out(surface)

    scores = signatures or {}
    lines += ["", "### Category Scores", "", "| Category | Score |", "|----------|-------|",
              f"| Export Coverage | {coverage_pct} |",
              f"| Signature Accuracy | {_pct(scores.get('signatureAccuracy'))} |",
              f"| Type Coverage | {_pct(scores.get('typeCoverage'))} |"]
    return "\n".join(lines) + "\n"


def _render_main(argv):
    parser = argparse.ArgumentParser(
        prog="reconcile-coverage render",
        description="Print the Coverage Analysis section's Markdown from the run files (coverage-check.md §5).",
    )
    parser.add_argument("--coverage", required=True, metavar="PATH", help="this script's result (coverage.json)")
    parser.add_argument("--surface", metavar="PATH", help="load-coverage-inputs.py surface output (surface.json)")
    parser.add_argument("--signatures", metavar="PATH", help="score-signatures.py score output (signatures.json)")
    args = parser.parse_args(argv)
    try:
        text = render(_read_json_file(args.coverage, "--coverage"),
                      _read_json_file(args.surface, "--surface") if args.surface else None,
                      _read_json_file(args.signatures, "--signatures") if args.signatures else None)
    except (InputFileError, RenderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(text)
    return 0


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
            "--inventory run/inventory.json --surface run/surface.json --output run/coverage.json\n"
            "Render the Coverage Analysis section (see `render --help`):\n"
            "  uv run reconcile-coverage.py render --coverage run/coverage.json "
            "[--surface run/surface.json] [--signatures run/signatures.json]"
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
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["render"]:
        return _render_main(argv[1:])
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
