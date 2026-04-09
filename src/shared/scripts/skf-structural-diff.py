#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Structural Diff — Deterministic comparison of skill export inventories.

Compares a baseline export inventory against a current export inventory and
produces a structured JSON diff showing added, removed, and changed entries.
Used by audit-skill and update-skill to replace LLM-based inventory comparison.

CLI:
  python3 skf-structural-diff.py baseline.json current.json
  python3 skf-structural-diff.py baseline.json current.json -o diff-result.json

Input:
  Two JSON files. Each file must be either:
    - An object with an "exports" array  (provenance-map / extraction-snapshot format)
    - A plain array of export entries

  Each export entry must have at minimum:
    - name: string   (primary key for matching)
    - type: string   (function/class/type/const/interface/etc.)

  Optional fields used for change detection:
    - signature: string
    - file: string
    - line: number
    - confidence: string

Output:
  JSON object:
    summary:          { added, removed, changed, moved, unchanged }
    added:            list of entries present in current but not baseline
    removed:          list of entries present in baseline but not current
    changed:          list of { name, field, baseline_value, current_value }
    moved:            list of { name, previous_file, current_file }
    unchanged_count:  number of entries that matched exactly

Exit codes:
  0  — inventories are identical (no diff)
  1  — differences found (or error)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# Fields compared for change detection (in order).
# "name" is the primary key and is not diffed as a field.
# "file" is excluded — file moves are tracked separately in the "moved" list.
DIFF_FIELDS = ["type", "signature", "line", "confidence"]


def load_inventory(path: Path) -> tuple[list[dict], str | None]:
    """Load an export inventory from a JSON file.

    Accepts either:
      - {"exports": [...]}  (provenance-map / extraction-snapshot)
      - [...]               (plain array)

    Returns (exports, error_message).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], f"Cannot read file '{path}': {exc}"

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], f"Invalid JSON in '{path}': {exc}"

    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        if "exports" in data and isinstance(data["exports"], list):
            return data["exports"], None
        # If it's a plain object without "exports", treat values as entries
        # (some inventory formats are name-keyed objects)
        if all(isinstance(v, dict) for v in data.values()):
            return list(data.values()), None
        return [], f"Unrecognised inventory format in '{path}': expected array or object with 'exports' key"

    return [], f"Unrecognised inventory format in '{path}': top-level value must be array or object"


def index_by_name(entries: list[dict]) -> dict[str, dict]:
    """Build a name-keyed dict from an export list, skipping nameless entries."""
    result: dict[str, dict] = {}
    for entry in entries:
        name = entry.get("name", "").strip()
        if name:
            result[name] = entry
    return result


def entry_matches(base: dict, curr: dict) -> bool:
    """Return True if two entries are identical across all DIFF_FIELDS."""
    for field in DIFF_FIELDS:
        if base.get(field) != curr.get(field):
            return False
    return True


def diff_inventories(
    baseline_entries: list[dict],
    current_entries: list[dict],
) -> dict:
    """Compute the structural diff between two export inventories.

    Returns a dict with keys: summary, added, removed, changed, unchanged_count.
    """
    baseline = index_by_name(baseline_entries)
    current = index_by_name(current_entries)

    baseline_names = set(baseline.keys())
    current_names = set(current.keys())

    added_names = current_names - baseline_names
    removed_names = baseline_names - current_names
    common_names = baseline_names & current_names

    added = [current[n] for n in sorted(added_names)]
    removed = [baseline[n] for n in sorted(removed_names)]

    changed: list[dict] = []
    moved: list[dict] = []
    unchanged_count = 0

    for name in sorted(common_names):
        base_entry = baseline[name]
        curr_entry = current[name]

        # Detect file moves separately
        base_file = base_entry.get("file")
        curr_file = curr_entry.get("file")
        if base_file and curr_file and base_file != curr_file:
            moved.append({
                "name": name,
                "previous_file": base_file,
                "current_file": curr_file,
            })

        entry_changed = False
        for field in DIFF_FIELDS:
            base_val = base_entry.get(field)
            curr_val = curr_entry.get(field)
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

    # Count distinct names that have at least one field change
    changed_names = len({c["name"] for c in changed})

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
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="skf-structural-diff.py",
        description=(
            "Compare two JSON export inventories and produce a structured diff.\n"
            "\n"
            "Each inventory file must be either a JSON array of export entries\n"
            "or a JSON object with an 'exports' key containing such an array.\n"
            "Every entry must have at minimum 'name' and 'type' fields.\n"
            "\n"
            "Exit code 0 means no differences were found.\n"
            "Exit code 1 means differences were found (or an error occurred)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 skf-structural-diff.py provenance-map.json current-snapshot.json\n"
            "  python3 skf-structural-diff.py baseline.json current.json -o diff.json\n"
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
        "-o",
        "--output",
        metavar="FILE",
        help="write JSON output to FILE instead of stdout",
    )

    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)

    baseline_entries, err = load_inventory(baseline_path)
    if err:
        print(json.dumps({"status": "error", "error": err}, indent=2))
        return 1

    current_entries, err = load_inventory(current_path)
    if err:
        print(json.dumps({"status": "error", "error": err}, indent=2))
        return 1

    result = diff_inventories(baseline_entries, current_entries)
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
