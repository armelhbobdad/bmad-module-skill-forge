#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Render Metadata Stats — derive metadata.json's computed stats block and
confidence_distribution deterministically from the staged provenance-map.

Two places in `skf-create-skill` do the same pure arithmetic over the staged
staging JSON, by hand, every run:

  1. **compile.md §4 (Build metadata.json)** bins each provenance entry by its
     `signature_source` tier into `confidence_distribution.{t1,t1_low,t2,t3}`,
     counts documented exports, and computes the coverage ratios. This is the
     step where the LLM made its recurring miscount, binning ~8 T2
     annotations + ~80 T3 doc items *on top of* 59 exports and getting a
     distribution that sums to 147 ≠ 59.

  2. **validate.md §7 (Validate metadata.json)** re-derives the same sums,
     ratios, and array-length counts to auto-fix any drift ("these are
     computed values").

Both are pure projections over the provenance-map plus a small judgment
payload — the values the prompt genuinely decides (which count feeds
`exports_public_api`, the gated `effective_denominator`). This script owns the
arithmetic so the prompt stops doing it by hand; the judgment stays in the
prompt and is passed in.

Because the distribution is a `Counter` over `entries[]` — one entry counted
once by its tier — the script **cannot** reproduce the 147≠59 miscount: the
four bins always sum to the number of entries with a recognized
`signature_source`, never to an enrichment total.

Shape carve-outs (mirroring `skf-test-skill` coverage-check §4b): the
distribution ALWAYS bins `entries[]`, so it always sums to `len(entries)`. What
`exports_documented` equals is what differs by shape:

  - **library** — `exports_documented = len(entries)`; the four bins sum to it.
  - **reference-app** — `entries[]` are per-citation, so the distribution sums
    to the *citation count* (= `len(entries)`), NOT to `exports_documented`
    (which is the pattern-surface proxy `pattern_surfaces_documented`: with
    `--skill-md`, the Pattern Surface table's data rows, read; see below).
    `effective_denominator` is never emitted.
  - **stack**: `exports_documented` comes from the payload (a stack's own
    barrel is empty by design), and the distribution still sums to the
    *entry count* (= `len(entries)`), one per provenance entry. A stack's
    metadata.json counts libraries instead: its `confidence_distribution`
    bins each library once, by the library's tier, and sums to
    `library_count`. So create-stack-skill runs this shape in compute mode
    for the label check (`coherence`) and for its evidence report's
    per-entry counts, and writes neither `stats` nor
    `confidence_distribution` into metadata.json; `--check` does not fit a
    stack.

Modes
-----

Default (compute) — read the provenance-map path + a judgment payload on stdin;
emit the derived `stats` + `confidence_distribution` + a `coherence` report.
`compile.md §4` writes the returned values verbatim.

`--check <metadata.json>` — read the provenance-map path + the on-disk
metadata.json; re-derive the computed values (taking the judgment values —
`exports_public_api`, `exports_internal`, `effective_denominator` — from the
on-disk metadata itself) and compare against what is on disk. `coherence.ok`
is false with a `violations[]` list when the on-disk file drifted; the emitted
`stats`/`confidence_distribution` are the corrected values `validate.md §7`
writes back. While label violations are present (see Label agreement below)
they are not: the distribution is binned from the mislabeled
`signature_source`, so the caller relabels the provenance-map, re-runs the
helper, and writes the re-run's values.

`--check <metadata.json> --fix`: also writes the `expected` value of each
`stats.*` violation into that metadata.json, and of each
`confidence_distribution.*` violation unless a
`provenance.entries[<i>].signature_source` or `.extraction_method` violation
is present (the distribution is binned from that label, so the relabel and
re-run write it), and prints `fixed`: the fields written, `[]` when none. An
`ast_node_type` or `confidence` violation holds back no fix. Every other key
keeps its place and value.

`--check <metadata.json> --validation-status manual-only|schema-unavailable`:
also writes `validation_status` into that metadata.json, whatever the
violations, in the same write as `--fix`.

A write goes through a temporary file and one rename, in the format the
extraction inventory writes metadata.json (2-space indent, UTF-8 kept,
trailing newline). A write that fails exits 2 and leaves the file as it was;
otherwise the exit code is the one the check gives. `--fix` and
`--validation-status` need `--check`.

Judgment payload (stdin JSON, compute mode)::

    {
      "exports_public_api":  40,          # int  — public-entry-point export count (judgment)
      "exports_internal":    19,          # int: internal export count, Python/Rust/Dart `_` names left out (judgment)
      "effective_denominator": 12,        # int|null — optional, curated-subset scopes only
      "pattern_surfaces_documented": 8,   # int: reference-app only (exports_documented proxy);
                                          #      leave it out with --skill-md, which counts it
      "exports_documented":  0,           # int  — stack only (own-barrel count, usually 0)
      "scripts": [ ... ],                 # list — scripts[] array (or "scripts_count": int)
      "assets":  [ ... ]                  # list — assets[]  array (or "assets_count":  int)
    }

Output JSON (both modes)::

    {
      "stats": {
        "exports_documented":  59,
        "exports_public_api":  40,
        "exports_internal":    19,
        "exports_total":       59,
        "public_api_coverage": 1.475,     # documented/public_api, null if public_api == 0
        "total_coverage":      1.0,        # documented/total,      null if total == 0
        "scripts_count":       0,
        "assets_count":        0
      },
      "confidence_distribution": {"t1": 40, "t1_low": 5, "t2": 10, "t3": 4},
      "primary_confidence": "T1",         # the largest bin's label, see below
      "coherence": {"ok": true, "violations": []},
      "fixed": ["stats.exports_total"]    # --fix only
    }

`primary_confidence` is the label (T1, T1-low, T2, T3) of the largest bin
of `confidence_distribution`; a tie goes to the later, weaker label, and it
is null when every bin is 0.

Pattern Surface count (`--skill-md PATH`, compute mode, `--shape
reference-app` only)
-----------------------------------------------------------------------

The helper reads `pattern_surfaces_documented` from the SKILL.md at PATH
instead of taking a count typed into the payload: it counts the data rows of
every table block under a heading whose text is `Pattern Surface`, the
header row and a separator second row left out, walking the tables with
skf-scan-skill-md-structure.py's `iter_table_blocks` (loaded from this
folder), the walker its table-drift check reads. A payload that also gives
`pattern_surfaces_documented` must give that count. Exit 2, with one stderr
line naming the cause and nothing written, when the payload's count differs,
the file has no `Pattern Surface` heading, it cannot be read, the scan
helper is not beside this one, or `--skill-md` comes with `--check` or
another shape.

Label agreement (both modes)
---------------------------

Every `entries[]` row whose `confidence` is T1 or T1-low (case-insensitive)
must carry the labels its `extraction_method` implies, so a label always names
the tool that produced the entry, never the forge tier:

  - `extraction_method` is one of ast-grep, source-read, ast_bridge,
    source_reading, qmd_bridge, compose-from-skill.
  - ast-grep and ast_bridge need confidence T1; ast-grep also needs a
    non-null `ast_node_type` (the `kind` the matching ast-grep recipe declares
    in create-skill's extraction-patterns.md).
  - source-read and source_reading need confidence T1-low and a
    `signature_source` other than T1; source-read also needs `ast_node_type`
    null (an absent key counts as null).
  - qmd_bridge and compose-from-skill carry no pairing.

A row read by eye (source-read, source_reading) is checked at any other
`confidence` (T2, T3, none) too, for its `signature_source` alone: the
distribution bins every row by `signature_source`, so a T1 there would count
a signature read by eye as T1. The other rows with another confidence
(ast-grep, ast_bridge, qmd_bridge, compose-from-skill, an unknown method)
and `file_entries[]` are not checked. Each disagreement is a violation keyed
by the row's index, because reference-app and stack maps repeat export
names::

    {"field": "provenance.entries[12].confidence", "export_name": "search",
     "expected": "T1-low", "actual": "T1",
     "note": "extraction_method source-read pairs with confidence T1-low"}

The step that runs the helper relabels the entry to match its method (never
the reverse) and runs the helper again.

Exit codes:
  0: coherence ok (no violations)
  1: coherence violations present (drift to auto-fix, a bad signature_source,
     or a label that disagrees with extraction_method); the JSON on stdout is
     still authoritative, so rely on it, not the code
  2: usage, IO or JSON-decode error, or a `--skill-md` count refused (see
     Pattern Surface count above)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path


# Canonical signature_source tiers → distribution bin keys. Compared
# case-insensitively so "T1-low" / "t1-low" both land in t1_low.
_SIG_MAP = {"T1": "t1", "T1-LOW": "t1_low", "T2": "t2", "T3": "t3"}
_VALID_SHAPES = ("library", "stack", "reference-app")
_DIST_KEYS = ("t1", "t1_low", "t2", "t3")
# Each distribution bin's label, in the order a tie is broken (the later wins).
_DIST_LABELS = {"t1": "T1", "t1_low": "T1-low", "t2": "T2", "t3": "T3"}
# The validation_status values --validation-status writes.
_VALIDATION_STATUSES = ("manual-only", "schema-unavailable")
# The violation fields --fix writes into metadata.json.
_FIXABLE_PREFIXES = ("stats.", "confidence_distribution.")
# The distribution fields --fix holds back while an entry's signature_source or
# extraction_method label disagrees: binning reads signature_source, and the
# relabel settles both before the re-run writes the distribution.
_DIST_PREFIX = "confidence_distribution."
_BINNING_LABEL_FIELD = re.compile(r"^provenance\.entries\[\d+\]\.(?:signature_source|extraction_method)$")

# extraction_method values a T1 or T1-low entry may carry, and the labels
# each one implies. ast-grep / source-read are what create-skill and
# update-skill write; the other four come from stack maps.
_KNOWN_METHODS = (
    "ast-grep", "source-read", "ast_bridge", "source_reading", "qmd_bridge", "compose-from-skill",
)
_T1_METHODS = ("ast-grep", "ast_bridge")            # confidence T1
_T1_LOW_METHODS = ("source-read", "source_reading")  # confidence T1-low, signature_source never T1
_LABELED_CONFIDENCE = ("T1", "T1-LOW")

# --skill-md: the table walker's script, beside this one, and the heading whose
# tables a reference app's pattern surfaces are the data rows of.
_SCAN_HELPER = "skf-scan-skill-md-structure.py"
_PATTERN_SURFACE_HEADING = "Pattern Surface"


# --------------------------------------------------------------------------
# IO
# --------------------------------------------------------------------------


def load_json(path: Path) -> object:
    """Read + parse a JSON file. Raises ValueError on any failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"failed to read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path}: {exc}") from exc


# --------------------------------------------------------------------------
# Pure derivations
# --------------------------------------------------------------------------


def bin_signature_sources(entries: list) -> tuple[dict[str, int], int]:
    """Counter over provenance entries by signature_source tier.

    Returns (distribution, unrecognized) where distribution has the four
    canonical bin keys and `unrecognized` counts entries whose
    `signature_source` is missing or not one of T1/T1-low/T2/T3. Counting
    entries (each exactly once, by its own tier) is what makes the 147≠59
    enrichment-fold miscount structurally impossible.
    """
    dist = {k: 0 for k in _DIST_KEYS}
    unrecognized = 0
    if not isinstance(entries, list):
        return dist, unrecognized
    for entry in entries:
        raw = entry.get("signature_source") if isinstance(entry, dict) else None
        key = _SIG_MAP.get(raw.strip().upper()) if isinstance(raw, str) else None
        if key is not None:
            dist[key] += 1
        else:
            unrecognized += 1
    return dist, unrecognized


def ratio(numerator: int, denominator: int) -> float | None:
    """Coverage ratio; None when the denominator is 0 (per the spec's
    null-when-empty rule). Rounded to 4 dp for deterministic output."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _int(value: object, default: int = 0) -> int:
    """Coerce a judgment value to int, tolerating None / bad types."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _count(judgment: dict, arr_key: str, count_key: str) -> int:
    """Length of an array field if present, else the scalar count field."""
    arr = judgment.get(arr_key)
    if isinstance(arr, list):
        return len(arr)
    return _int(judgment.get(count_key), 0)


def count_file_entries_by_type(prov: dict) -> dict[str, int]:
    """Count provenance-map file_entries[] by file_type."""
    counts = {"script": 0, "asset": 0, "doc": 0, "other": 0}
    fe = prov.get("file_entries")
    if isinstance(fe, list):
        for row in fe:
            if not isinstance(row, dict):
                counts["other"] += 1
                continue
            ft = row.get("file_type")
            counts[ft if ft in ("script", "asset", "doc") else "other"] += 1
    return counts


def derive_stats(prov: dict, judgment: dict, shape: str = "library") -> dict:
    """Derive the stats block + confidence_distribution for one skill.

    `prov` is the parsed provenance-map. `judgment` carries the values the
    prompt decides. `shape` selects how `exports_documented` is set. The
    distribution always bins `entries[]`.
    """
    entries = prov.get("entries")
    entries = entries if isinstance(entries, list) else []
    dist, unrecognized = bin_signature_sources(entries)
    entry_count = len(entries)

    if shape == "reference-app":
        exports_documented = _int(judgment.get("pattern_surfaces_documented"), 0)
    elif shape == "stack":
        exports_documented = _int(judgment.get("exports_documented"), 0)
    else:  # library
        exports_documented = entry_count

    exports_public_api = _int(judgment.get("exports_public_api"), 0)
    exports_internal = _int(judgment.get("exports_internal"), 0)
    exports_total = exports_public_api + exports_internal

    stats: dict[str, object] = {
        "exports_documented": exports_documented,
        "exports_public_api": exports_public_api,
        "exports_internal": exports_internal,
        "exports_total": exports_total,
        "public_api_coverage": ratio(exports_documented, exports_public_api),
        "total_coverage": ratio(exports_documented, exports_total),
        "scripts_count": _count(judgment, "scripts", "scripts_count"),
        "assets_count": _count(judgment, "assets", "assets_count"),
    }

    # reference-app: emit the pattern-surface proxy alongside exports_documented
    if shape == "reference-app":
        stats["pattern_surfaces_documented"] = exports_documented

    # effective_denominator: optional, and never for a reference app (its
    # coverage basis is pattern surfaces, not an export barrel).
    eff = judgment.get("effective_denominator")
    if eff is not None and shape != "reference-app":
        stats["effective_denominator"] = _int(eff, 0)

    return {
        "stats": stats,
        "confidence_distribution": dist,
        "_derivation": {
            "shape": shape,
            "entry_count": entry_count,
            "distribution_sum": sum(dist.values()),
            "unrecognized_signature_source": unrecognized,
        },
    }


def _scan_helper():
    """skf-scan-skill-md-structure.py, loaded from this script's folder.
    Raises ValueError when it is not there or cannot be loaded."""
    path = Path(__file__).resolve().parent / _SCAN_HELPER
    if not path.is_file():
        raise ValueError(f"{_SCAN_HELPER} not found beside {Path(__file__).name}; re-install SKF")
    try:
        spec = importlib.util.spec_from_file_location("skf_scan_skill_md_structure_stats", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"no import spec for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:  # whatever the script raises, the count cannot be read
        raise ValueError(f"cannot load {_SCAN_HELPER}: {exc}") from exc
    return module


def count_pattern_surfaces(skill_md: Path) -> int:
    """The data rows of every table block under a `Pattern Surface` heading
    of `skill_md` (see "Pattern Surface count" in the module docstring).
    Raises ValueError when the file cannot be read, the scan helper is
    missing or the file has no such heading."""
    scan = _scan_helper()
    try:
        text = scan._read_markdown(skill_md)
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read {skill_md}: {exc}") from exc
    headings = (scan._HEADING_RE.match(line) for line in text.splitlines())
    if not any(m is not None and m.group(2).strip() == _PATTERN_SURFACE_HEADING for m in headings):
        raise ValueError(f"{skill_md} has no `{_PATTERN_SURFACE_HEADING}` heading to count the pattern "
                         "surfaces of")
    return sum(len(body) for section, _header, body in scan.iter_table_blocks(text)
               if section == _PATTERN_SURFACE_HEADING)


# --------------------------------------------------------------------------
# Coherence
# --------------------------------------------------------------------------


def _cmp_int(violations: list, field: str, expected, actual, note: str | None = None) -> None:
    if expected != actual:
        v = {"field": field, "expected": expected, "actual": actual}
        if note:
            v["note"] = note
        violations.append(v)


def _cmp_ratio(violations: list, field: str, expected, actual) -> None:
    norm = round(float(actual), 4) if isinstance(actual, (int, float)) and not isinstance(actual, bool) else actual
    exp = round(expected, 4) if isinstance(expected, float) else expected
    if exp != norm:
        violations.append({"field": field, "expected": expected, "actual": actual})


def _upper(value: object) -> str | None:
    return value.strip().upper() if isinstance(value, str) else None


def check_label_agreement(prov: dict) -> list[dict]:
    """Check that each T1 / T1-low entry's labels match its extraction_method,
    and that no entry read by eye claims a T1 signature_source.

    Returns one violation per disagreeing field, keyed by the entry's index
    (`provenance.entries[<i>].<field>`) since export names repeat in
    reference-app and stack maps. `expected` is the value the method implies;
    the caller relabels the entry to it and never changes a known method.
    An entry read by eye (source-read, source_reading) with any other
    confidence is checked for its signature_source alone; the other entries
    with another confidence, and `file_entries[]`, are not checked.
    """
    entries = prov.get("entries")
    if not isinstance(entries, list):
        return []
    violations: list[dict] = []

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        confidence = entry.get("confidence")
        method = entry.get("extraction_method")
        labeled = _upper(confidence) in _LABELED_CONFIDENCE
        # Off T1 / T1-low only an entry read by eye is checked, for its
        # signature_source: binning reads that label whatever the confidence,
        # so a T1 there would count a signature read by eye as T1.
        if not labeled and method not in _T1_LOW_METHODS:
            continue
        name = entry.get("export_name")

        def flag(field: str, expected: object, actual: object, note: str) -> None:
            violations.append({
                "field": f"provenance.entries[{i}].{field}",
                "export_name": name,
                "expected": expected,
                "actual": actual,
                "note": note,
            })

        if method not in _KNOWN_METHODS:
            flag("extraction_method", sorted(_KNOWN_METHODS), method,
                 "a T1 or T1-low entry names the tool that produced it: set ast-grep for an "
                 "ast-grep match or source-read for an entry read by eye")
            continue

        if method in _T1_METHODS:
            if _upper(confidence) != "T1":
                flag("confidence", "T1", confidence,
                     f"extraction_method {method} pairs with confidence T1")
            node = entry.get("ast_node_type")
            # "non-null" is the violation's own expected value, not a node kind:
            # a fixer that copied it has still not recorded the kind.
            if method == "ast-grep" and (not (isinstance(node, str) and node.strip())
                                         or _upper(node) == "NON-NULL"):
                flag("ast_node_type", "non-null", node,
                     "extraction_method ast-grep pairs with a non-null ast_node_type: copy "
                     "the kind the matching recipe declares")
        elif method in _T1_LOW_METHODS:
            if labeled and _upper(confidence) != "T1-LOW":
                flag("confidence", "T1-low", confidence,
                     f"extraction_method {method} pairs with confidence T1-low")
            sig = entry.get("signature_source")
            if _upper(sig) == "T1":
                flag("signature_source", "T1-low", sig,
                     f"extraction_method {method} pairs with a signature_source other than T1 "
                     "(any tier but T1 passes)")
            node = entry.get("ast_node_type")
            if labeled and method == "source-read" and node is not None:
                flag("ast_node_type", None, node,
                     "extraction_method source-read pairs with ast_node_type null: no ast-grep "
                     "rule matched this entry")
        # qmd_bridge and compose-from-skill carry no pairing.

    return violations


def coherence_compute(derived: dict, prov: dict) -> dict:
    """Internal-consistency checks for compute mode.

    The distribution must account for every provenance entry (a bin-sum below
    the entry count means some entries carry a missing/unrecognized
    signature_source). When the provenance-map already tracks scripts/assets in
    file_entries[], those counts must agree with the stats counts. Every T1 or
    T1-low entry's labels must match its extraction_method, and no entry read
    by eye may claim a T1 signature_source (check_label_agreement).
    """
    violations: list[dict] = []
    entry_count = derived["_derivation"]["entry_count"]
    dist_sum = derived["_derivation"]["distribution_sum"]
    if dist_sum != entry_count:
        missing = entry_count - dist_sum
        violations.append({
            "field": "confidence_distribution",
            "expected": entry_count,
            "actual": dist_sum,
            "note": (
                f"{missing} provenance entr{'y' if abs(missing) == 1 else 'ies'} "
                "with missing or unrecognized signature_source"
            ),
        })

    fe = count_file_entries_by_type(prov)
    sc = derived["stats"]["scripts_count"]
    ac = derived["stats"]["assets_count"]
    # Conservative: only cross-check a type once the provenance-map actually
    # carries rows of that type (file_entries are written in a later compile
    # section, so an empty count is "not yet populated", not "zero").
    if fe["script"] > 0:
        _cmp_int(violations, "stats.scripts_count", fe["script"], sc,
                 "stats.scripts_count disagrees with provenance-map file_entries[file_type=script]")
    if fe["asset"] > 0:
        _cmp_int(violations, "stats.assets_count", fe["asset"], ac,
                 "stats.assets_count disagrees with provenance-map file_entries[file_type=asset]")

    violations.extend(check_label_agreement(prov))
    return {"ok": not violations, "violations": violations}


def check_stats(derived: dict, metadata: dict, prov: dict) -> dict:
    """Compare re-derived values against the on-disk metadata.json.

    Every mismatch is a `{field, expected, actual}` violation, where `expected`
    is the re-derived (correct) value and `actual` is what is on disk.
    validate.md §7 either writes `derived` verbatim or fixes each violation.
    Label violations from check_label_agreement are appended too; they concern
    the provenance-map, which is relabeled before the stats are fixed.
    """
    violations: list[dict] = []
    m_stats = metadata.get("stats") if isinstance(metadata.get("stats"), dict) else {}
    d_stats = derived["stats"]

    _cmp_int(violations, "stats.exports_documented", d_stats["exports_documented"],
             m_stats.get("exports_documented"))
    _cmp_int(violations, "stats.exports_total", d_stats["exports_total"],
             m_stats.get("exports_total"))
    _cmp_ratio(violations, "stats.public_api_coverage", d_stats["public_api_coverage"],
               m_stats.get("public_api_coverage"))
    _cmp_ratio(violations, "stats.total_coverage", d_stats["total_coverage"],
               m_stats.get("total_coverage"))

    m_dist = metadata.get("confidence_distribution") if isinstance(metadata.get("confidence_distribution"), dict) else {}
    for key in _DIST_KEYS:
        _cmp_int(violations, f"confidence_distribution.{key}",
                 derived["confidence_distribution"][key], m_dist.get(key))

    # array length vs its stats count (validate.md §7: "verify
    # stats.scripts_count/stats.assets_count match array lengths")
    scripts_arr = metadata.get("scripts")
    if isinstance(scripts_arr, list):
        _cmp_int(violations, "stats.scripts_count", len(scripts_arr),
                 m_stats.get("scripts_count"),
                 "stats.scripts_count does not match len(scripts[])")
    assets_arr = metadata.get("assets")
    if isinstance(assets_arr, list):
        _cmp_int(violations, "stats.assets_count", len(assets_arr),
                 m_stats.get("assets_count"),
                 "stats.assets_count does not match len(assets[])")

    # provenance-map file_entries count vs metadata scripts/assets counts
    if isinstance(scripts_arr, list) or isinstance(assets_arr, list):
        fe = count_file_entries_by_type(prov)
        claimed_sc = _int(m_stats.get("scripts_count"), 0)
        claimed_ac = _int(m_stats.get("assets_count"), 0)
        if fe["script"] != claimed_sc and (fe["script"] > 0 or claimed_sc > 0):
            _cmp_int(violations, "provenance.file_entries.script", claimed_sc, fe["script"],
                     "provenance-map file_entries[file_type=script] count disagrees with metadata scripts_count")
        if fe["asset"] != claimed_ac and (fe["asset"] > 0 or claimed_ac > 0):
            _cmp_int(violations, "provenance.file_entries.asset", claimed_ac, fe["asset"],
                     "provenance-map file_entries[file_type=asset] count disagrees with metadata assets_count")

    # provenance entry labels vs extraction_method (the map, not metadata.json)
    violations.extend(check_label_agreement(prov))
    return {"ok": not violations, "violations": violations}


def primary_confidence(dist: dict) -> str | None:
    """The label of the largest bin; a tie goes to the later (weaker) label, None when every bin is 0."""
    best, best_count = None, 0
    for key in _DIST_KEYS:
        count = _int(dist.get(key), 0)
        if count > 0 and count >= best_count:
            best, best_count = _DIST_LABELS[key], count
    return best


def fix_metadata(metadata: dict, violations: list) -> tuple[dict, list[str]]:
    """(metadata with each stats.* and confidence_distribution.* violation's expected value, fields written).

    The stats.* fixes are written whatever the labels. The
    confidence_distribution.* fixes are held back while a
    provenance.entries[<i>].signature_source or .extraction_method violation is
    present, since the distribution was binned from that label; an
    ast_node_type or confidence violation holds back nothing.
    """
    hold_dist = any(_BINNING_LABEL_FIELD.match(str(v.get("field", ""))) for v in violations)
    fixed: list[str] = []
    out = dict(metadata)
    for violation in violations:
        field = str(violation.get("field", ""))
        if not field.startswith(_FIXABLE_PREFIXES):
            continue
        if hold_dist and field.startswith(_DIST_PREFIX):
            continue
        block, key = field.split(".", 1)
        current = out.get(block)
        out[block] = {**(current if isinstance(current, dict) else {}), key: violation.get("expected")}
        if field not in fixed:
            fixed.append(field)
    return out, fixed


def write_metadata(path: Path, data: dict) -> None:
    """Write metadata.json as the extraction inventory does: a temporary file, then one rename."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def detect_shape(metadata: dict) -> str:
    """Infer the shape from an on-disk metadata.json (used by --check when
    --shape is not supplied)."""
    if metadata.get("scope_type") == "reference-app":
        return "reference-app"
    if metadata.get("skill_type") == "stack":
        return "stack"
    return "library"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_stdin_judgment() -> dict:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("stdin judgment payload must be a JSON object")
    return payload


def _emit(result: dict, out_path: str | None) -> None:
    text = json.dumps(result, indent=2)
    if out_path:
        Path(out_path).write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-render-metadata-stats",
        description=(
            "Derive metadata.json stats + confidence_distribution from the staged "
            "provenance-map (compute mode), or re-verify an on-disk metadata.json "
            "against the map (--check). Both modes also check that each T1 or "
            "T1-low entry's confidence, signature_source and ast_node_type match "
            "its extraction_method, and that no entry read by eye claims a T1 "
            "signature_source at any confidence. Replaces the hand-binning/summing "
            "in skf-create-skill compile.md §4 and validate.md §7."
        ),
    )
    parser.add_argument("provenance_map", help="path to the staged provenance-map.json")
    parser.add_argument(
        "--check", metavar="METADATA_JSON", dest="check",
        help="verify this on-disk metadata.json against the provenance-map instead of "
             "reading judgment from stdin; emits corrected stats + a violations list",
    )
    parser.add_argument(
        "--shape", choices=_VALID_SHAPES, default=None,
        help="assembly shape (default: library in compute mode; inferred from "
             "metadata.json in --check mode). Selects what exports_documented equals.",
    )
    parser.add_argument(
        "--skill-md", metavar="PATH", dest="skill_md", default=None,
        help="compute mode with --shape reference-app only: count pattern_surfaces_documented as the data "
             "rows of the SKILL.md's Pattern Surface tables; a payload count that differs exits 2",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="with --check: write the expected value of each stats.* violation "
             "into the metadata.json, and of each confidence_distribution.* one "
             "unless a provenance.entries signature_source or extraction_method "
             "violation is present",
    )
    parser.add_argument(
        "--validation-status", choices=_VALIDATION_STATUSES, default=None,
        help="with --check: write this validation_status into the metadata.json",
    )
    parser.add_argument("-o", "--output", dest="output", help="write JSON here (default: stdout)")
    parser.add_argument("--verbose", action="store_true", help="diagnostics to stderr")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.check and (args.fix or args.validation_status):
        parser.error("--fix and --validation-status need --check")

    prov_path = Path(args.provenance_map)
    if not prov_path.is_file():
        sys.stderr.write(f"error: provenance-map not found: {prov_path}\n")
        return 2
    try:
        prov = load_json(prov_path)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    if not isinstance(prov, dict):
        sys.stderr.write("error: provenance-map must be a JSON object at top level\n")
        return 2

    if args.skill_md is not None and (args.check or args.shape != "reference-app"):
        sys.stderr.write("error: --skill-md counts a reference app's pattern surfaces: pass it in compute mode "
                         "with --shape reference-app, never with --check or another shape\n")
        return 2

    if args.check:
        meta_path = Path(args.check)
        if not meta_path.is_file():
            sys.stderr.write(f"error: metadata.json not found: {meta_path}\n")
            return 2
        try:
            metadata = load_json(meta_path)
        except ValueError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 2
        if not isinstance(metadata, dict):
            sys.stderr.write("error: metadata.json must be a JSON object at top level\n")
            return 2
        shape = args.shape or detect_shape(metadata)
        m_stats = metadata.get("stats") if isinstance(metadata.get("stats"), dict) else {}
        judgment = {
            "exports_public_api": m_stats.get("exports_public_api"),
            "exports_internal": m_stats.get("exports_internal"),
            "effective_denominator": m_stats.get("effective_denominator"),
            "pattern_surfaces_documented": m_stats.get("pattern_surfaces_documented"),
            "exports_documented": m_stats.get("exports_documented"),
            "scripts": metadata.get("scripts"),
            "assets": metadata.get("assets"),
        }
        derived = derive_stats(prov, judgment, shape)
        coherence = check_stats(derived, metadata, prov)
    else:
        try:
            judgment = _read_stdin_judgment()
        except (ValueError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 2
        shape = args.shape or "library"
        if args.skill_md is not None:
            try:
                counted = count_pattern_surfaces(Path(args.skill_md))
            except ValueError as exc:
                sys.stderr.write(f"error: {exc}\n")
                return 2
            given = judgment.get("pattern_surfaces_documented")
            if given is not None and (isinstance(given, bool) or _int(given, -1) != counted):
                sys.stderr.write(
                    f"error: the payload's pattern_surfaces_documented ({given!r}) is not the {counted} data "
                    f"row(s) of the Pattern Surface tables in {args.skill_md}: leave the count out, "
                    "--skill-md counts it\n")
                return 2
            judgment = {**judgment, "pattern_surfaces_documented": counted}
        derived = derive_stats(prov, judgment, shape)
        coherence = coherence_compute(derived, prov)

    if args.verbose:
        sys.stderr.write(
            f"shape={shape} entries={derived['_derivation']['entry_count']} "
            f"dist_sum={derived['_derivation']['distribution_sum']} "
            f"unrecognized={derived['_derivation']['unrecognized_signature_source']} "
            f"violations={len(coherence['violations'])}\n"
        )

    result = {
        "stats": derived["stats"],
        "confidence_distribution": derived["confidence_distribution"],
        "primary_confidence": primary_confidence(derived["confidence_distribution"]),
        "coherence": coherence,
    }
    if args.check and (args.fix or args.validation_status):
        updated, fixed = fix_metadata(metadata, coherence["violations"]) if args.fix else (metadata, [])
        if args.validation_status:
            updated = {**updated, "validation_status": args.validation_status}
        if updated != metadata or args.validation_status:
            try:
                write_metadata(meta_path, updated)
            except OSError as exc:
                sys.stderr.write(f"error: cannot write {meta_path}: {exc}\n")
                return 2
        if args.fix:
            result["fixed"] = fixed
    _emit(result, args.output)
    return 0 if coherence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
