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
    Missing = barrel_set − documented_set, Export Coverage = |Documented| /
    |barrel_set| * 100, Stale = documented_set − (barrel_set ∪ `allSet`).
    `allSet` is the whole public surface: the `all` set and every name on
    the surface's export records, since a nested Python entry's names leave
    `all` but keep their records. So a documented name the counted set
    leaves out but the source exports (a Tier B name) is neither counted nor
    stale. Without `allSet`, Stale = documented_set − barrel_set.

  * "scalar"  (§2b's scalar branch, stats.effective_denominator): the
    denominator is effective_denominator, Missing = max(0, denominator −
    Documented), Export Coverage = min(100, Documented / denominator * 100).
    The numerator's set: when the surface counts its named set S
    (`setCounted`, the surface's `denominator.setCounted`: a scope set, not
    `all`, each of whose names sits at the file that defines it, read
    whole), Documented = |documented_set ∩ S| (`numeratorSource`
    "surface"; the doc-text lookup and `verifiedNumerator` are not read),
    `missing` = S − documented_set, and a warning when |S| differs from the
    denominator. Otherwise (`all`, a set read by eye or from an incomplete
    extraction, no surface, or an empty S, which warns): look each
    documented name up in SKILL.md ∪ references/*.md, Documented = count
    present, or `verifiedNumerator`; `missing` lists no name.
    Stale: on a surface read from the source (`sourceRead`, its
    `guards.deflation.applicable`, or a counted set), documented_set − (S ∪
    `allSet`, the whole public surface, as on the barrel branch), so a
    documented name outside S that the source exports is neither counted
    nor stale; else not enumerable (empty).

  * "stack"   (skill_type == "stack", empty source barrel): look each
    composition-surface name (provenance-map cited contracts, ::-excluded, or
    libraries + integration_pairs, from load-coverage-inputs.py) up in
    SKILL.md ∪ references/*.md; denominator = stack_denominator,
    Missing = max(0, denominator − Documented), Stale not enumerable,
    Export Coverage = min(100, Documented / stack_denominator * 100).
    On a `provenance` basis (`compositionBasis`, the loader's `stack.basis`)
    with the inventory's `exports` given, a cited name counts only when the
    inventory gives it an entry (validate-inventory.py's `listed_names`, so
    `cognee.add` has the entry of `add`) and the text writes it, as
    verify-declared-numerator.py counts (#1068): a name the skill writes only
    in a type position, only in a sentence saying it does not cover it, only
    as a local import alias or a name it says the source does not export, or
    only in a form marked removed or from an earlier version is missing. A
    name `moduleNames` holds (the provenance map types it `module` or
    `package`, which the inventory has no kind for) counts when the text
    writes it. On a `composition` basis the names are
    libraries and `a + b` integration pairs, which name no export, so no
    inventory entry lists them: they are looked up in the text alone.

  * "docsOnly" (a skill whose citations are all [EXT:...], or no source
    access): no source to compare against, so Export Coverage measures
    documentation completeness: complete items / documented items * 100,
    one item per name and kind of the §1 inventory, complete when it has a
    description and, for a function or method, params and a return type
    (validate-inventory.py's rule).

The two lookup branches (and a scalar set larger than its stored count)
bound their outputs because the numerator and the denominator are
independent measures of different sets: the lookup count can
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
                        wrote with --output; and its `undecided`, when it
                        gives one
  --surface PATH        barrelSet: one name set of load-coverage-inputs.py
                        surface, chosen by --surface-set (default "all");
                        allSet, the whole surface both branches find a
                        stale name against (its `all` set and every name on
                        its `exports` records, a nested entry's included);
                        and what the scalar branch reads: surfaceSet (that
                        name), sourceRead (its
                        `guards.deflation.applicable`) and setCounted (its
                        `denominator.setCounted`, when --surface-set names
                        its `denominator.surfaceSet`)
  --coverage-inputs PATH  load-coverage-inputs.py metadata output: for the
                        scalar branch, denominatorValue from its
                        `effectiveDenominator` (stats.effective_denominator);
                        for the stack branch, compositionNames,
                        compositionBasis (its `basis`) and
                        denominatorValue from its `stack` object, and
                        moduleNames from its own `moduleNames`
  --verified PATH       scalar: verify-declared-numerator.py's result; when it
                        found the declared count inflated, its `verified`
                        count is the numerator (not on a counted set)
  --output PATH         write the result to this file (UTF-8 JSON) and print
                        only its summary; a refused input removes a file
                        left there earlier

Input schema (one object):
  {
    "denominatorSource": "barrel" | "scalar" | "stack" | "docsOnly",  # required
    "exports": [ {"name": "...", "kind": "..."}, ... ],    # §1 inventory
    "barrelSet": ["a", "b", ...],                          # barrel, scalar: resolved name set
    "perFileResults": [ {"exports_found": ["a", ...]} ],   # barrel: union'd if no barrelSet
    "surfaceSet": "tier_a_include",                        # scalar: barrelSet's name (null or "" is "all")
    "allSet": ["a", "b", "c", ...],                        # barrel, scalar: the whole public surface (stale)
    "sourceRead": <bool>,                                  # scalar: the surface was read from the source
    "setCounted": <bool>,                                  # scalar: count barrelSet (a trusted scope set)
    "denominatorValue": <int>,                             # scalar/stack: resolved denominator
    "compositionNames": ["connect", ...],                  # stack: names to look up
    "compositionBasis": "provenance" | "composition",      # stack: stack.basis (null: no basis given)
    "moduleNames": ["connectors.localfs", ...],            # stack: names the map types module or package
    "skillPackagePath": "/path/to/skill",                  # scalar/stack: SKILL.md ∪ references
    "verifiedNumerator": <int>,                            # scalar: overrides the lookup count
    "undecided": [ {"export", "at", "rule", "reading", "other_gap"} ]  # any branch: the inventory's open readings
  }

Output (stdout, one object):
  {
    "branch": "enumerated" | "scalar" | "stack" | "docsOnly",
    "denominatorSource": "barrel" | "scalar" | "stack" | "docsOnly",
    "denominator": <int>,
    "documented": <int>,
    "documentedNames": [names],  # enumerated, scalar counting its set: the documented names the numerator counts
    "missing": [names],          # enumerated, scalar counting its set: source names not documented; others: []
    "missingCount": <int>,       # always present; never negative
    "stale": [names],            # enumerated, scalar on a source-read surface: documented names not in source
    "staleCount": <int>,         # always present
    "staleApplicable": <bool>,   # true for enumerated and scalar on a source-read surface
    "exportCoverage": <float>,   # scalar/stack: capped at 100
    "numeratorSurplus": <int>,   # scalar/stack only: max(0, documented − denominator)
    "coverageUncapped": <float>, # scalar/stack only: the ratio before the cap
    "coverageCapped": <bool>,    # scalar/stack only: true when the cap bound the ratio
    "numeratorSource": "lookup" | "verified" | "surface",  # scalar only
    "surfaceSet": "<name>",      # scalar counting its set: the set it counted
    "surfaceSetSize": <int>,     # scalar counting its set: |S|
    "warnings": [str],           # scalar on a source-read surface: an empty S, or |S| unlike the denominator
    "incomplete": [{"name", "kind", "missing"}],  # docsOnly only: the incomplete items
    "undecided": [{...}]         # any branch, when the input gives a non-empty one: copied unchanged (#1021)
  }
  With --output the file holds that object and stdout is its summary: each
  field as the file gives it, a list as its length, and "output": the
  --output path (#1063). A refused input prints its error object either way.

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
      Signature        no for a Critical mismatch, yes (Low) or yes (Info)
                       for a name whose mismatches score-signatures.py
                       graded Low or Info alone (they count as matching;
                       Low when it has both), yes for a compared name that
                       matches, unverified for a documented name when no
                       --signatures was given, - otherwise
      Source Location  for a name whose signature mismatches, the file:line
                       of its most severe mismatch (the declaration it was
                       compared with); else the file:line the surface
                       records for the name, a record with a line preferred
                       (gap-ledger.py's rule for a missing export's
                       Source), else -
      Status           FAIL for a Critical signature mismatch (a mismatch
                       with no `severity`, from an older signatures.json,
                       counts as one), WARN for a missing or stale name or
                       a mismatch graded Low or Info alone, PASS otherwise
                       A scalar result with `documentedNames` (a counted
                       set) gets the same table. The stack branch, and the
                       scalar one with no set, count without naming the
                       exports, and a docs-only run has no source
                       surface: one line says so instead (NO_TABLE).
  ### Coverage Summary the --coverage counts and warnings, the
                       --signatures count of
                       Critical mismatches (with the Low and Info ones,
                       counted as matching, beside it when there are any)
                       and warnings, the numerator surplus when the ratio
                       was capped, and the names the --surface leaves out
                       or puts back: `excluded.outsideScope` (scoped out
                       by the brief), `excluded.nestedEntries` (a nested
                       Python entry point's names) and
                       `guards.staleScope.restored`, and the names no
                       recipe found (`extractionGaps`, each at its file
                       and line, one with no file listed as not located,
                       #1048), each line only when it names one
  ### Category Scores  Export Coverage, and Signature Accuracy and Type
                       Coverage from --signatures (N/A without it)
  Borderline Calls     a Coverage Summary line after the warnings, only
                       when one is given (#1021): each `undecided` item of
                       --coverage (the inventory reader's), then of
                       --signatures (the signature judges'), with its
                       export, place, reading, the rule that leaves it open
                       and what the other reading gives
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
# load-coverage-inputs.py metadata's `stack.basis`: the provenance map's cited export names, or the libraries
# and integration pairs the stack composes.
STACK_BASES = ("provenance", "composition")
# The grades score-signatures.py gives a caller-invisible signature difference, most severe first.
NON_BLOCKING_MISMATCH = ("Low", "Info")

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
    if inp.get("undecided") is not None and not isinstance(inp["undecided"], list):
        return "`undecided` must be a list (the inventory's open readings) when present"
    if source == "barrel":
        if inp.get("barrelSet") is None and inp.get("perFileResults") is None:
            return "barrel branch requires either `barrelSet` or `perFileResults`"
        all_set = inp.get("allSet")
        if all_set is not None and not isinstance(all_set, list):
            return "barrel branch: `allSet` must be a list of names"
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
        if source == "stack" and inp.get("compositionBasis") not in STACK_BASES + (None,):
            return f"stack branch: `compositionBasis` must be one of {', '.join(STACK_BASES)} or null"
        if source == "stack" and inp.get("compositionBasis") == "provenance":
            if inp.get("exports") is not None and not isinstance(inp["exports"], list):
                return "stack branch: `exports` must be a list (the validated inventory's entries) when present"
            if inp.get("moduleNames") is not None and not isinstance(inp["moduleNames"], list):
                return "stack branch: `moduleNames` must be a list (names the map types module or package) when present"
        verified = inp.get("verifiedNumerator")
        if verified is not None and (not isinstance(verified, int) or isinstance(verified, bool) or verified < 0):
            return "verifiedNumerator must be an integer >= 0"
        if source == "scalar" and inp.get("barrelSet") is not None:
            if not isinstance(inp["barrelSet"], list):
                return "scalar branch: `barrelSet` must be a list of names"
            set_name = _surface_set_name(inp)
            if set_name is None:
                return "scalar branch: `surfaceSet` must be a set name (a string)"
            all_set = inp.get("allSet")
            if all_set is not None and not isinstance(all_set, list):
                return "scalar branch: `allSet` must be a list of names"
            if all_set is None and set_name != "all" and _reads_surface(inp):
                return ("scalar branch on a surface read from the source requires `allSet` (the surface's "
                        "`all` set) to find the stale names")
    return None


def _surface_set_name(inp):
    """`surfaceSet`, normalized once: null or empty is `all`; None for a value that is not a string.

    >>> [_surface_set_name({"surfaceSet": v}) for v in (None, "", "tier_a_include", 3)]
    ['all', 'all', 'tier_a_include', None]
    """
    name = inp.get("surfaceSet")
    if name is None or name == "":
        return "all"
    return name if isinstance(name, str) else None


def _reads_surface(inp):
    """True when the scalar branch reads its surface: a `barrelSet` read from the source (a counted set is)."""
    return inp.get("barrelSet") is not None and (inp.get("sourceRead") is True or inp.get("setCounted") is True)


def _whole(inp, named):
    """The whole source surface both branches find a stale name against: the counted set `named` and `allSet`
    (from --surface, the `all` set and every name on the surface's export records, so a nested Python entry's
    names count though they leave `all`). The counted set is always part of it.

    >>> sorted(_whole({"allSet": ["alpha", "tierB", "nested", "", 3]}, {"alpha", "scoped"}))
    ['alpha', 'nested', 'scoped', 'tierB']
    >>> sorted(_whole({}, {"alpha"}))
    ['alpha']
    """
    return named | {n for n in inp.get("allSet") or [] if isinstance(n, str) and n}


def _scalar_surface(inp, denominator):
    """What the scalar branch reads from a surface read from the source: the stale names, the documented names
    the whole surface (`_whole`: S and `allSet`) lacks, and, when it counts its named set S (`setCounted`, a
    non-empty scope set), the documented names S holds, the names of S the skill does not document and the
    set's size, with the warnings. The denominator stays the stored count."""
    documented_set = build_documented_set(inp.get("exports"))
    named = {n for n in inp["barrelSet"] if isinstance(n, str) and n}
    set_name = _surface_set_name(inp)
    whole = _whole(inp, named)
    warnings = []
    counted = inp.get("setCounted") is True and set_name != "all"
    if counted and not named:
        # An empty set would read 0% by construction: the lookup counts instead.
        warnings.append(f"the `{set_name}` set names no export: the numerator is looked up in the skill instead")
        counted = False
    out = {"counted": counted, "stale": sorted(documented_set - whole), "warnings": warnings}
    if counted:
        if len(named) != denominator:
            warnings.append(
                f"the `{set_name}` set holds {len(named)} names and the stored count "
                f"(`stats.effective_denominator`) is {denominator}: the denominator stays the stored count, so "
                "`missing` and `missingCount` can differ")
        out.update({"documentedNames": sorted(documented_set & named), "missing": sorted(named - documented_set),
                    "surfaceSet": set_name, "surfaceSetSize": len(named)})
    return out


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
    """Pure reconciliation. `doc_text` may be injected (tests); else loaded from disk. The inventory's open
    readings, a non-empty `undecided` (#1021), ride along unchanged in every branch's result, for render."""
    result = _reconcile(inp, doc_text)
    if result.get("code") != "INVALID_INPUT" and inp.get("undecided"):
        result["undecided"] = inp["undecided"]
    return result


def _reconcile(inp, doc_text=None):
    """The branch `denominatorSource` picks (reconcile)."""
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
        # A documented name the counted set leaves out but the whole surface holds is neither counted nor stale.
        stale = sorted(documented_set - _whole(inp, barrel_set))
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
    surface = _scalar_surface(inp, denominator) if source == "scalar" and _reads_surface(inp) else None
    if surface is not None and surface["counted"]:
        # The named set the surface counts: the numerator counts only its documented names, so a documented
        # extra never offsets an undocumented export. Neither the doc-text lookup nor §2b's verified count is
        # read: both count names without knowing which the set holds.
        documented = len(surface["documentedNames"])
        numerator_source = "surface"
    elif source == "scalar" and inp.get("verifiedNumerator") is not None:
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
            if inp.get("compositionBasis") == "provenance" and isinstance(inp.get("exports"), list):
                # #1068: a cited export name counts only when the inventory gives it an entry, as §2b's
                # numerator check counts. Library and pair names (`composition`) name no export, so the
                # inventory never lists them and the text alone decides.
                candidates = _inventory().listed_names(candidates, inp["exports"], inp.get("moduleNames"))
        documented = len(names_present(candidates, doc_text))

    # The numerator and the resolved denominator can measure different sets,
    # so `documented` can legitimately exceed `denominator`: a looked-up
    # numerator counts every documented name the skill writes, migration
    # aliases, re-exported sibling symbols and other extras included, against
    # a consumer-surface denominator, and a counted set can hold more names
    # than the stored count. Left unbounded that yields a negative Missing and
    # >100% coverage (which compute-score.py then rejects outright as out of
    # range).
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
    if surface is not None:
        # Stale is valid against the whole surface whether or not the branch counts its set.
        result.update({"stale": surface["stale"], "staleCount": len(surface["stale"]), "staleApplicable": True})
        if surface["counted"]:
            result.update({key: surface[key] for key in ("documentedNames", "missing", "surfaceSet",
                                                         "surfaceSetSize")})
        result["warnings"] = surface["warnings"]
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


def _borderline(item, who):
    """One reading the rules leave open (#1021), as Borderline Calls lists it: each field on one line, a closing
    period dropped.

    >>> print(_borderline({"export": "run", "at": "SKILL.md:9", "rule": "Own code.", "reading": "a form",
    ...                    "other_gap": "no gap"}, "inventory reader"))
    `run` (SKILL.md:9), inventory reader: a form; left open by: Own code; the other reading gives: no gap
    >>> print(_borderline({"export": "x", "at": None, "rule": "r ...", "reading": "a", "other_gap": "g"}, "judge"))
    `x`, judge: a; left open by: r ...; the other reading gives: g
    """
    def text(field):
        value = " ".join(str(item.get(field) or "").split())
        return value[:-1] if value.endswith(".") and not value.endswith("..") else value

    place = f" ({text('at')})" if text("at") else ""
    return (f"`{text('export')}`{place}, {who}: {text('reading')}; left open by: {text('rule')}; "
            f"the other reading gives: {text('other_gap')}")


def _left_out(surface):
    """The Coverage Summary lines for the names the surface leaves out or puts back, and for the names no recipe
    found (one the runner's trace placed in no file is not located), each only when it names one.

    >>> for line in _left_out({
    ...         "excluded": {"outsideScope": [{"name": "gen", "file": "src/gen.ts"}],
    ...                      "nestedEntries": [{"entry": "pkg/api/__init__.py", "within": "pkg/__init__.py",
    ...                                         "names": ["router"]}]},
    ...         "guards": {"staleScope": {"restored": [{"name": "old", "file": "src/old.ts", "line": 4}]}},
    ...         "extractionGaps": [{"name": "fn", "file": "src/fn.ts", "line": 3},
    ...                            {"name": "Lance", "file": None, "line": None}]}):
    ...     print(line)
    - **Scoped Out by the Brief:** `gen` (src/gen.ts)
    - **Nested Entry Points:** `pkg/api/__init__.py` inside `pkg/__init__.py`: `router`
    - **Restored by the Stale-Scope Guard:** `old` (src/old.ts:4)
    - **Extraction Gaps:** `fn` (src/fn.ts:3), `Lance` (not located)
    >>> _left_out({"excluded": {"outsideScope": [], "nestedEntries": []}, "guards": None, "extractionGaps": []})
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
    # A name no recipe found is on the surface: the signature plan judges it when documented, and no step reads it
    # by eye, so the summary lists it (#1048).
    gaps = [f"`{i['name']}`{where(i) or ' (not located)'}" for i in items(surface.get("extractionGaps"))
            if isinstance(i.get("name"), str)]
    if gaps:
        lines.append(f"- **Extraction Gaps:** {', '.join(gaps)}")
    return lines


def _rows(coverage, surface, signatures):
    """The Export Coverage table of the enumerated branch."""
    if "documentedNames" not in coverage:
        raise RenderError("--coverage has no `documentedNames`: write it again with this reconcile-coverage.py")
    documented = set(_string_list(coverage, "documentedNames", "--coverage"))
    missing = set(_string_list(coverage, "missing", "--coverage"))
    stale = set(_string_list(coverage, "stale", "--coverage"))
    mismatched, critical, compared, graded, compared_at = set(), set(), set(), {}, {}
    if signatures is not None:
        named = [m for m in signatures.get("mismatches") or []
                 if isinstance(m, dict) and isinstance(m.get("name"), str)]
        mismatched = {m["name"] for m in named}
        # A Low or an Info mismatch (a caller-invisible difference) warns; any other fails.
        critical = {m["name"] for m in named if m.get("severity") not in NON_BLOCKING_MISMATCH}
        # The more severe non-blocking grade of each name: Low over Info.
        for severity in reversed(NON_BLOCKING_MISMATCH):
            graded.update({m["name"]: severity for m in named if m.get("severity") == severity})
        compared = set(_string_list(signatures, "comparedNames", "--signatures"))
        # A mismatched name sits at the declaration its most severe mismatch was compared with, which the
        # surface's first record of a name it records in several files need not be.
        for m in sorted(named, key=lambda m: (NON_BLOCKING_MISMATCH.index(m["severity"]) + 1
                                              if m.get("severity") in NON_BLOCKING_MISMATCH else 0)):
            if isinstance(m.get("file"), str) and m["file"] and isinstance(m.get("line"), int):
                compared_at.setdefault(m["name"], f"{m['file']}:{m['line']}")
    kinds, sources = {}, {}
    if surface is not None:
        for record in surface["exports"]:
            if isinstance(record, dict) and isinstance(record.get("name"), str) and record.get("kind"):
                kinds.setdefault(record["name"], str(record["kind"]))
        sources = _gap_ledger()._surface_sources(surface)
    sources.update(compared_at)
    rows = ["| Export | Type | Documented | Signature | Source Location | Status |",
            "|--------|------|------------|-----------|-----------------|--------|"]
    for name in sorted(documented | missing | stale | mismatched):
        if name in critical:
            signature = "no"
        elif name in mismatched:
            signature = f"yes ({graded[name]})"
        elif name in compared:
            signature = "yes"
        elif signatures is None and name not in missing:
            signature = "unverified"
        else:
            signature = "-"
        status = ("FAIL" if name in critical
                  else "WARN" if name in mismatched or name in missing or name in stale else "PASS")
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
    # A scalar result that counts its set names its exports as the enumerated branch does.
    named = branch == "enumerated" or (branch == "scalar" and "documentedNames" in coverage)
    lines += _rows(coverage, surface, signatures) if named else [NO_TABLE[branch]]

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
    if isinstance(mismatches, list):
        named = [m for m in mismatches if isinstance(m, dict)]
        lenient = sum(1 for m in named if m.get("severity") in NON_BLOCKING_MISMATCH)
        lines.append(f"- **Signature Mismatches:** {len(named) - lenient}"
                     + (f", plus {lenient} graded Low or Info and counted as matching" if lenient else ""))
    else:
        lines.append("- **Signature Mismatches:** N/A")
    if coverage.get("staleApplicable"):
        lines.append(f"- **Stale Documentation:** {coverage.get('staleCount')}, documented extras included")
    else:
        lines.append(f"- **Stale Documentation:** N/A: {NO_NAMES.get(branch, 'the denominator names no stale export')}")
    noted = _string_list(coverage, "warnings", "--coverage")
    if noted:
        lines.append("- **Coverage Warnings:**")
        lines += [f"  - {w}" for w in noted]
    warnings = _string_list(signatures, "warnings", "--signatures") if signatures is not None else []
    if warnings:
        lines.append("- **Scoring Warnings:**")
        lines += [f"  - {w}" for w in warnings]
    # The readings the rules leave open that this verdict rests on (#1021): the inventory reader's, then the judges'.
    calls = [_borderline(item, who) for data, who in ((coverage, "inventory reader"), (signatures, "signature judge"))
             if data is not None and isinstance(data.get("undecided"), list)
             for item in data["undecided"] if isinstance(item, dict)]
    if calls:
        lines.append("- **Borderline Calls:**")
        lines += [f"  - {call}" for call in calls]
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
        if data.get("undecided") is not None:
            inp["undecided"] = data["undecided"]
    if args.surface is not None:
        data = _read_json_file(args.surface, "--surface")
        sets = data.get("sets") if isinstance(data, dict) else None
        names = sets.get(args.surface_set) if isinstance(sets, dict) else None
        if not isinstance(names, list):
            raise InputFileError(f"--surface {args.surface} has no name set `{args.surface_set}`")
        inp["barrelSet"] = names
        # The scalar branch counts the set only when the surface trusts it (`denominator.setCounted`, for the set
        # it picked). Both branches find a stale name against the whole public surface (`allSet`), not the set
        # they count: the `all` set and every name on an `exports` record, since a nested Python entry's names
        # leave `all` but keep their records (score-signatures.py's `signature_universe` rule). A scoped-out
        # name has no record, so it stays stale.
        inp["surfaceSet"] = args.surface_set
        if isinstance(sets.get("all"), list):
            records = data.get("exports") if isinstance(data.get("exports"), list) else []
            on_records = [r.get("name") for r in records if isinstance(r, dict)]
            inp["allSet"] = sorted({n for n in sets["all"] + on_records if isinstance(n, str) and n})
        guards = data.get("guards")
        deflation = guards.get("deflation") if isinstance(guards, dict) else None
        inp["sourceRead"] = isinstance(deflation, dict) and deflation.get("applicable") is True
        picked = data.get("denominator") if isinstance(data.get("denominator"), dict) else {}
        inp["setCounted"] = picked.get("setCounted") is True and picked.get("surfaceSet") == args.surface_set
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
            inp["compositionBasis"] = stack.get("basis")
            inp["moduleNames"] = data.get("moduleNames")
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
                       help="the name set of --surface the barrel or scalar branch counts (default: all)")
    files.add_argument("--coverage-inputs", metavar="PATH",
                       help="load-coverage-inputs.py metadata output (scalar and stack branches)")
    files.add_argument("--verified", metavar="PATH",
                       help="verify-declared-numerator.py output (scalar branch)")
    parser.add_argument("--output", metavar="PATH", help="write the result to this file and print only its summary")
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


def _summary(result, output):
    """What main prints when --output holds the result: each field as the file gives it, a list as its length, and
    the file's path as `output`. coverage-check reads every name list from the file (#1063)."""
    return {**{key: len(value) if isinstance(value, list) else value for key, value in result.items()},
            "output": output}


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
    refused = isinstance(result, dict) and result.get("code") == "INVALID_INPUT"
    if args.output:
        _write_output(args.output, result)
    print(json.dumps(result if refused or not args.output else _summary(result, args.output), indent=2))
    return 2 if refused else 0


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
