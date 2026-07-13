#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Structural Diff — Deterministic comparison of skill export inventories.

Compares a baseline export inventory against a current export inventory and
produces a structured JSON diff showing added, removed, changed, and moved
entries. Used by audit-skill (structural-diff step) and update-skill to
replace LLM-based, token-spending inventory comparison — the LLM can silently
drop or mis-match entries when diffing dozens/hundreds of exports by hand.

CLI:
  python3 skf-structural-diff.py baseline.json current.json
  python3 skf-structural-diff.py baseline.json current.json -o diff-result.json
  python3 skf-structural-diff.py provenance-map.json snapshot.json --reexport-map map.json

Input:
  Two JSON files. Each file may be either:
    - An object with an "exports" array   (extraction-snapshot format)
    - An object with an "entries" array    (provenance-map.json format)
    - A plain array of export entries
    - A name-keyed object of entry objects

  Field-name aliasing (provenance-map entries[] vs extraction-snapshot
  exports[]) is handled transparently, so the two sides may use different
  shapes:
    - name        <- name        | export_name
    - type        <- type        | export_type
    - file        <- file        | source_file
    - line        <- line        | source_line
    - signature   <- signature
    - confidence  <- confidence

  "name" is the primary match key. Nameless entries are skipped.

Canonicalization (applied symmetrically to BOTH sides before matching):
  The baseline extractor (skf-create-skill) and the re-extractor (audit step 2)
  can differ in cosmetic detail that would otherwise surface as false-positive
  "Changed"/"Removed"/"Added" entries. These deterministic transforms collapse
  the cosmetic differences:
    - quote-style          : normalize string-literal quotes in signatures
                             (double -> single), so `= "Hnsw"` == `= 'Hnsw'`.
    - stdlib-prefix        : strip module prefixes on well-known stdlib helpers
                             (typing., dataclasses., collections[.abc]., enum.),
                             so `typing.Optional[int]` == `Optional[int]`.
                             User-defined namespaces (e.g. `pkg.typing.X`) are
                             NOT collapsed.
    - reexport-resolution  : rewrite internal symbol names to their public
                             re-export name via the reexport map, so a renamed
                             public re-export (`_Impl` -> `Public`) matches the
                             baseline entry instead of showing up as
                             Removed `_Impl` + Added `Public`.

  The reexport map is taken from --reexport-map when provided; otherwise it is
  derived from the baseline provenance map itself (top-level `reexport_map`
  plus any per-entry `reexported_as`) — the same projection produced by
  `skf-load-provenance.py normalize`.

Change detection:
  A field is only compared when present (non-null) on BOTH sides — a field
  absent on one side means "insufficient data", never an asserted change. This
  avoids false positives when the two inventories carry different metadata.

Output:
  JSON object:
    summary:            { added, removed, changed, moved, unchanged }
    added:              list of entries present in current but not baseline
    removed:            list of entries present in baseline but not current
    changed:            list of { name, field, baseline_value, current_value }
    moved:              list of { name, previous_file, current_file }
    unchanged_count:    number of entries that matched with no field change
    applied_transforms: list of { transform, count } — which canonicalization
                        transforms actually fired and how many values each
                        touched (empty when none fired). Surfaced by audit
                        step 6's Provenance section so a reviewer can tell
                        which differences the diff collapsed.

Exit codes:
  0  — inventories are identical (no diff)
  1  — differences found (or error)
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path


# Fields compared for change detection (in order).
# "name" is the primary key and is not diffed as a field.
# "file" is excluded — file moves are tracked separately in the "moved" list.
DIFF_FIELDS = ["type", "signature", "line", "confidence"]

# Well-known stdlib module prefixes whose unqualified form is importable at
# the call site. Longer prefixes must precede their own containing prefix
# (collections.abc before collections) so the alternation strips the longest.
# The negative lookbehind `(?<![\w.])` ensures we only strip a top-level module
# reference — never a user-defined namespace such as `pkg.typing.Foo`.
_STDLIB_PREFIX_RE = re.compile(
    r"(?<![\w.])(?:typing|dataclasses|collections\.abc|collections|enum)\."
)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_json(path: Path) -> tuple[object, str | None]:
    """Read and parse a JSON file. Returns (data, error_message)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"Cannot read file '{path}': {exc}"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON in '{path}': {exc}"


def entries_from_data(data: object, source: str = "") -> tuple[list[dict], str | None]:
    """Extract the export-entry list from an already-parsed inventory.

    Accepts:
      - [...]                 (plain array)
      - {"exports": [...]}    (extraction-snapshot format)
      - {"entries": [...]}    (provenance-map.json format)
      - {name: {...}, ...}    (name-keyed object of entry objects)

    Returns (entries, error_message).
    """
    where = f" in '{source}'" if source else ""
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        if isinstance(data.get("exports"), list):
            return data["exports"], None
        if isinstance(data.get("entries"), list):
            return data["entries"], None
        # A plain name-keyed object of entries (some inventory formats).
        values = list(data.values())
        if values and all(isinstance(v, dict) for v in values):
            return values, None
        return [], (
            f"Unrecognised inventory format{where}: expected array or object "
            f"with an 'exports' or 'entries' key"
        )
    return [], f"Unrecognised inventory format{where}: top-level value must be array or object"


def load_inventory(path: Path) -> tuple[list[dict], str | None]:
    """Load an export inventory from a JSON file (thin wrapper, back-compat).

    Returns (exports, error_message).
    """
    data, err = load_json(path)
    if err:
        return [], err
    return entries_from_data(data, str(path))


# --------------------------------------------------------------------------
# Re-export map
# --------------------------------------------------------------------------


def extract_reexport_map(data: object) -> dict[str, str]:
    """Derive the {internal -> public} re-export map from a provenance map.

    Mirrors skf-load-provenance.extract_reexport_map:
      1. top-level `reexport_map` object, plus
      2. per-entry `reexported_as` on `entries[]` items
         ({"export_name": "_Impl", "reexported_as": "Public"}).
    Non-string keys/values are skipped. Returns {} for non-dict input.
    """
    out: dict[str, str] = {}
    if not isinstance(data, dict):
        return out
    top = data.get("reexport_map")
    if isinstance(top, dict):
        for k, v in top.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
    entries = data.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            internal = entry.get("export_name")
            public = entry.get("reexported_as")
            if isinstance(internal, str) and isinstance(public, str):
                out.setdefault(internal, public)
    return out


def load_reexport_map(path: Path) -> tuple[dict[str, str], str | None]:
    """Load an explicit re-export map file.

    Accepts either a plain {internal: public} object or the full
    `skf-load-provenance.py normalize` output (which nests it under the
    `reexport_map` key). Non-string pairs are skipped.
    """
    data, err = load_json(path)
    if err:
        return {}, err
    if not isinstance(data, dict):
        return {}, f"reexport map '{path}' must be a JSON object"
    src = data["reexport_map"] if isinstance(data.get("reexport_map"), dict) else data
    return {k: v for k, v in src.items() if isinstance(k, str) and isinstance(v, str)}, None


# --------------------------------------------------------------------------
# Canonicalization
# --------------------------------------------------------------------------


def _first(entry: dict, *keys: str) -> object:
    """First non-null value among the given keys (field-name aliasing)."""
    for k in keys:
        v = entry.get(k)
        if v is not None:
            return v
    return None


def canon_signature(sig: object) -> tuple[object, set[str]]:
    """Canonicalize a signature string. Returns (canonical, transforms_fired).

    Non-string input passes through unchanged (empty transform set).
    """
    if not isinstance(sig, str):
        return sig, set()
    applied: set[str] = set()
    out = sig
    if '"' in out:
        out = out.replace('"', "'")
        applied.add("quote-style")
    stripped = _STDLIB_PREFIX_RE.sub("", out)
    if stripped != out:
        applied.add("stdlib-prefix")
        out = stripped
    return out, applied


def _normalize_entries(
    entries: list[dict],
    reexport_map: dict[str, str],
    transform_counts: collections.Counter,
) -> dict[str, dict]:
    """Build a name-keyed dict of canonicalized records.

    Applies field-name aliasing, signature canonicalization, and re-export
    name resolution. Accumulates fired-transform counts into transform_counts.
    Nameless entries are skipped. On duplicate resolved names, the last entry
    wins (consistent with prior behaviour).
    """
    result: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_name = _first(entry, "name", "export_name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        name = raw_name.strip()
        resolved = reexport_map.get(name, name)
        if resolved != name:
            transform_counts["reexport-resolution"] += 1
            name = resolved

        canon_sig, sig_transforms = canon_signature(entry.get("signature"))
        for t in sig_transforms:
            transform_counts[t] += 1

        # Normalized record — also the public entry shape emitted in
        # added[]/removed[], so both sides render into one consistent table
        # regardless of the input shape they came from.
        result[name] = {
            "name": name,
            "type": _first(entry, "type", "export_type"),
            "signature": canon_sig,
            "file": _first(entry, "file", "source_file"),
            "line": _first(entry, "line", "source_line"),
            "confidence": entry.get("confidence"),
        }
    return result


# --------------------------------------------------------------------------
# Diff
# --------------------------------------------------------------------------


def diff_inventories(
    baseline_entries: list[dict],
    current_entries: list[dict],
    reexport_map: dict[str, str] | None = None,
) -> dict:
    """Compute the structural diff between two export inventories.

    Returns a dict with keys: summary, added, removed, changed, moved,
    unchanged_count, applied_transforms.
    """
    reexport_map = reexport_map or {}
    transform_counts: collections.Counter = collections.Counter()

    baseline = _normalize_entries(baseline_entries, reexport_map, transform_counts)
    current = _normalize_entries(current_entries, reexport_map, transform_counts)

    baseline_names = set(baseline.keys())
    current_names = set(current.keys())

    added_names = current_names - baseline_names
    removed_names = baseline_names - current_names
    common_names = baseline_names & current_names

    # Emit normalized entries (uniform name/type/signature/file/line/confidence
    # shape) so added[] and removed[] render into the same report table even
    # though they originate from the snapshot and provenance-map shapes.
    added = [current[n] for n in sorted(added_names)]
    removed = [baseline[n] for n in sorted(removed_names)]

    changed: list[dict] = []
    moved: list[dict] = []
    unchanged_count = 0

    for name in sorted(common_names):
        base_rec = baseline[name]
        curr_rec = current[name]

        # File moves are tracked separately from field changes.
        base_file = base_rec.get("file")
        curr_file = curr_rec.get("file")
        if base_file and curr_file and base_file != curr_file:
            moved.append({
                "name": name,
                "previous_file": base_file,
                "current_file": curr_file,
            })

        entry_changed = False
        for field in DIFF_FIELDS:
            base_val = base_rec.get(field)
            curr_val = curr_rec.get(field)
            # Compare only when data is present on both sides; a missing value
            # on either side is insufficient evidence to assert a change.
            if base_val is None or curr_val is None:
                continue
            if base_val != curr_val:
                changed.append({
                    "name": name,
                    "field": field,
                    "baseline_value": base_val,
                    "current_value": curr_val,
                })
                entry_changed = True

        if not entry_changed:
            unchanged_count += 1

    changed_names = len({c["name"] for c in changed})

    applied_transforms = [
        {"transform": name, "count": transform_counts[name]}
        for name in sorted(transform_counts)
        if transform_counts[name] > 0
    ]

    return {
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": changed_names,
            "moved": len(moved),
            "unchanged": unchanged_count,
        },
        "added": added,
        "removed": removed,
        "changed": changed,
        "moved": moved,
        "unchanged_count": unchanged_count,
        "applied_transforms": applied_transforms,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="skf-structural-diff.py",
        description=(
            "Compare two JSON export inventories and produce a structured diff.\n"
            "\n"
            "Each inventory may be a JSON array of export entries, an object with\n"
            "an 'exports' key (extraction-snapshot), or an object with an 'entries'\n"
            "key (provenance-map.json). Field names are aliased across the two\n"
            "shapes, and signatures are canonicalized (quote style, stdlib module\n"
            "prefixes, public re-export names) symmetrically before matching.\n"
            "\n"
            "Exit code 0 means no differences were found.\n"
            "Exit code 1 means differences were found (or an error occurred)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 skf-structural-diff.py provenance-map.json extraction-snapshot.json\n"
            "  python3 skf-structural-diff.py baseline.json current.json -o diff.json\n"
            "  python3 skf-structural-diff.py provenance-map.json snapshot.json --reexport-map map.json\n"
        ),
    )
    parser.add_argument(
        "baseline",
        metavar="baseline.json",
        help="path to the baseline export inventory (e.g. provenance-map.json)",
    )
    parser.add_argument(
        "current",
        metavar="current.json",
        help="path to the current export inventory (e.g. extraction-snapshot.json)",
    )
    parser.add_argument(
        "--reexport-map",
        metavar="FILE",
        help=(
            "path to a JSON re-export map ({internal: public}) or a "
            "skf-load-provenance normalize output. When omitted, the map is "
            "derived from the baseline provenance map itself."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write JSON output to FILE instead of stdout",
    )

    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)

    baseline_data, err = load_json(baseline_path)
    if err:
        print(json.dumps({"status": "error", "error": err}, indent=2))
        return 1
    current_data, err = load_json(current_path)
    if err:
        print(json.dumps({"status": "error", "error": err}, indent=2))
        return 1

    baseline_entries, err = entries_from_data(baseline_data, str(baseline_path))
    if err:
        print(json.dumps({"status": "error", "error": err}, indent=2))
        return 1
    current_entries, err = entries_from_data(current_data, str(current_path))
    if err:
        print(json.dumps({"status": "error", "error": err}, indent=2))
        return 1

    if args.reexport_map:
        reexport_map, err = load_reexport_map(Path(args.reexport_map))
        if err:
            print(json.dumps({"status": "error", "error": err}, indent=2))
            return 1
    else:
        reexport_map = extract_reexport_map(baseline_data)

    result = diff_inventories(baseline_entries, current_entries, reexport_map)
    output_text = json.dumps(result, indent=2)

    if args.output:
        out_path = Path(args.output)
        try:
            out_path.write_text(output_text + "\n", encoding="utf-8")
        except OSError as exc:
            print(
                json.dumps({"status": "error", "error": f"Cannot write output: {exc}"}, indent=2)
            )
            return 1
    else:
        print(output_text)

    summary = result["summary"]
    has_diff = summary["added"] or summary["removed"] or summary["changed"] or summary["moved"]
    return 1 if has_diff else 0


if __name__ == "__main__":
    sys.exit(main())
