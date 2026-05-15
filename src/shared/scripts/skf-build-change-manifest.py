# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Build Change Manifest — aggregate category A/B/C/D detection results.

`skf-update-skill/references/detect-changes.md §3` assembles the final
change manifest from four category result streams the LLM (or its
subprocess workers) produces upstream:

  - Category A — file-level changes (modified/added/deleted)
  - Category B — export-level changes (for MODIFIED files)
  - Category C — rename detection (cross-files and cross-exports)
  - Category D — script/asset file changes

The aggregation itself is purely deterministic: count rollups, grouping
exports under their owning file, deduplicating across categories, and
emitting the canonical manifest shape that downstream stages consume.
The §3 prose previously asked the LLM to count entries across four
streams every run — the helper makes it one bash call with stable
shape.

The same script also implements §2.2's Major-Version Scope
Reconciliation trigger (the deletion-ratio formula) — same input
schema, plus the provenance map for the denominator.

Subcommands:

  build [--input <file>] [--no-changes-on-empty]
      Reads category JSON from stdin or `--input <file>`, emits the
      unified manifest envelope.

  deletion-ratio --provenance-map <file> [--input <file>]
      Same category JSON input. Reads provenance entries[] from
      <file>, computes the §2.2 trigger envelope. Auto-skips when
      degraded_mode or update_mode==gap-driven is set in the input.

Input JSON shape (object on stdin or in --input file):

  {
    "category_a": {
      "modified": ["path1", ...],
      "added":    ["path2", ...],
      "deleted":  ["path3", ...]
    },
    "category_b": {
      "modified_exports": [{name, file, old_line, new_line}, ...],
      "new_exports":      [{name, file, line}, ...],
      "deleted_exports":  [{name, file, old_line}, ...],
      "moved_exports":    [{name, file, old_line, new_line}, ...]
    },
    "category_c": {
      "renamed_files":   [{old_path, new_path}, ...],
      "renamed_exports": [{old_name, new_name, file}, ...]
    },
    "category_d": {
      "scripts_modified": ["path", ...], "scripts_added": [...], "scripts_deleted": [...],
      "assets_modified": [...],          "assets_added": [...],  "assets_deleted":  [...]
    },
    "degraded_mode": false,
    "update_mode": "normal" | "gap-driven"  // optional; influences deletion-ratio only
  }

Every category and sub-key is optional — missing keys default to
empty lists. This lets gap-driven runs (which produce no Category D
results) and degraded runs (which skip Category B) feed the same
script without sentinel values.

Exit codes:
  0  — operation succeeded
  1  — user error (malformed JSON, bad path, malformed provenance file)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Input normalization
# --------------------------------------------------------------------------


def _get_list(d: dict, *path: str) -> list:
    """Pluck a list out of a nested dict, defaulting to []."""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return []
        cur = cur.get(key)
        if cur is None:
            return []
    return cur if isinstance(cur, list) else []


def _load_input(input_path: Path | None) -> dict:
    """Read JSON either from --input path or from stdin."""
    if input_path is not None:
        text = input_path.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"input must be a JSON object, got {type(data).__name__}")
    return data


# --------------------------------------------------------------------------
# Build manifest
# --------------------------------------------------------------------------


def build_manifest(payload: dict) -> dict:
    """Aggregate category A/B/C/D into the unified manifest envelope."""
    cat_a = payload.get("category_a", {}) or {}
    cat_b = payload.get("category_b", {}) or {}
    cat_c = payload.get("category_c", {}) or {}
    cat_d = payload.get("category_d", {}) or {}

    a_modified = _get_list(cat_a, "modified")
    a_added = _get_list(cat_a, "added")
    a_deleted = _get_list(cat_a, "deleted")

    b_modified = _get_list(cat_b, "modified_exports")
    b_new = _get_list(cat_b, "new_exports")
    b_deleted = _get_list(cat_b, "deleted_exports")
    b_moved = _get_list(cat_b, "moved_exports")

    c_renamed_files = _get_list(cat_c, "renamed_files")
    c_renamed_exports = _get_list(cat_c, "renamed_exports")

    d = {
        "scripts_modified": len(_get_list(cat_d, "scripts_modified")),
        "scripts_added": len(_get_list(cat_d, "scripts_added")),
        "scripts_deleted": len(_get_list(cat_d, "scripts_deleted")),
        "assets_modified": len(_get_list(cat_d, "assets_modified")),
        "assets_added": len(_get_list(cat_d, "assets_added")),
        "assets_deleted": len(_get_list(cat_d, "assets_deleted")),
    }

    counts = {
        "files_changed": len(a_modified),
        "files_added": len(a_added),
        "files_deleted": len(a_deleted),
        "files_moved": len(c_renamed_files),
        "exports_modified": len(b_modified),
        "exports_new": len(b_new),
        "exports_deleted": len(b_deleted),
        "exports_renamed": len(c_renamed_exports),
        "exports_moved": len(b_moved),
        **d,
    }

    per_file = _build_per_file(
        a_modified=a_modified,
        a_added=a_added,
        a_deleted=a_deleted,
        c_renamed_files=c_renamed_files,
        b_modified=b_modified,
        b_new=b_new,
        b_deleted=b_deleted,
        b_moved=b_moved,
    )

    total_export_changes = (
        counts["exports_modified"]
        + counts["exports_new"]
        + counts["exports_deleted"]
        + counts["exports_renamed"]
        + counts["exports_moved"]
    )

    no_changes = (
        sum(counts.values()) == 0  # every count is zero
    )

    return {
        "no_changes": no_changes,
        "degraded_mode": bool(payload.get("degraded_mode")),
        "counts": counts,
        "total_export_changes": total_export_changes,
        "per_file": per_file,
    }


def _build_per_file(
    *,
    a_modified: list,
    a_added: list,
    a_deleted: list,
    c_renamed_files: list,
    b_modified: list,
    b_new: list,
    b_deleted: list,
    b_moved: list,
) -> list[dict]:
    """Group exports under their owning file path. Preserves stable ordering:
    MODIFIED files first, then ADDED, then DELETED, then MOVED. Files within
    each status sorted alphabetically by path."""
    exports_by_file: dict[str, list[dict]] = {}

    def _record(entry: dict, change_type: str) -> None:
        path = entry.get("file")
        if not path:
            return
        exports_by_file.setdefault(path, []).append({
            "name": entry.get("name"),
            "change_type": change_type,
            "old_line": entry.get("old_line"),
            "new_line": entry.get("new_line") or entry.get("line"),
        })

    for e in b_modified:
        _record(e, "MODIFIED_EXPORT")
    for e in b_new:
        _record(e, "NEW_EXPORT")
    for e in b_deleted:
        _record(e, "DELETED_EXPORT")
    for e in b_moved:
        _record(e, "MOVED_EXPORT")

    out: list[dict] = []

    for path in sorted(a_modified):
        out.append({
            "file_path": path,
            "status": "MODIFIED",
            "exports_affected": exports_by_file.get(path, []),
        })

    for path in sorted(a_added):
        out.append({
            "file_path": path,
            "status": "ADDED",
            "exports_affected": exports_by_file.get(path, []),
        })

    for path in sorted(a_deleted):
        out.append({
            "file_path": path,
            "status": "DELETED",
            "exports_affected": exports_by_file.get(path, []),
        })

    # MOVED entries from Category C — emit one record per move with the new path
    for move in sorted(c_renamed_files, key=lambda m: m.get("new_path") or ""):
        new_path = move.get("new_path")
        if new_path is None:
            continue
        out.append({
            "file_path": new_path,
            "status": "MOVED",
            "old_path": move.get("old_path"),
            "exports_affected": exports_by_file.get(new_path, []),
        })

    return out


# --------------------------------------------------------------------------
# Deletion ratio (§2.2)
# --------------------------------------------------------------------------


def compute_deletion_ratio(payload: dict, provenance: dict) -> dict:
    """Compute the §2.2 deletion-ratio trigger envelope.

    Skip conditions (per the §2.2 prose):
      - update_mode == "gap-driven"
      - degraded_mode is True
      - provenance has zero entries (denominator would be zero)
    """
    if payload.get("update_mode") == "gap-driven":
        return _ratio_skip(skip_reason="gap-driven")
    if payload.get("degraded_mode"):
        return _ratio_skip(skip_reason="degraded-mode")

    entries = provenance.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("provenance `entries` must be an array")
    total = len(entries)
    if total == 0:
        return _ratio_skip(skip_reason="zero-provenance-exports")

    # Count exports under category A deleted files (via provenance lookup)
    by_source: dict[str, int] = {}
    for entry in entries:
        sf = entry.get("source_file")
        if isinstance(sf, str):
            by_source[sf] = by_source.get(sf, 0) + 1

    cat_a = payload.get("category_a", {}) or {}
    deleted_files = _get_list(cat_a, "deleted")
    deleted_in_files = sum(by_source.get(p, 0) for p in deleted_files)

    cat_b = payload.get("category_b", {}) or {}
    deleted_exports = len(_get_list(cat_b, "deleted_exports"))

    deleted_export_count = deleted_in_files + deleted_exports
    ratio = deleted_export_count / total

    cat_c = payload.get("category_c", {}) or {}
    renamed_or_moved = (
        len(_get_list(cat_c, "renamed_files"))
        + len(_get_list(cat_b, "moved_exports"))
        + len(_get_list(cat_c, "renamed_exports"))
    )

    return {
        "skip_reason": None,
        "deleted_export_count": deleted_export_count,
        "total_provenance_exports": total,
        "deletion_ratio": ratio,
        "deleted_file_count": len(deleted_files),
        "added_in_scope_count": len(_get_list(cat_a, "added")),
        "renamed_or_moved_count": renamed_or_moved,
        "should_trigger": ratio >= 0.50,
    }


def _ratio_skip(*, skip_reason: str) -> dict:
    return {
        "skip_reason": skip_reason,
        "deleted_export_count": 0,
        "total_provenance_exports": 0,
        "deletion_ratio": 0.0,
        "deleted_file_count": 0,
        "added_in_scope_count": 0,
        "renamed_or_moved_count": 0,
        "should_trigger": False,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_build(args: argparse.Namespace) -> int:
    try:
        payload = _load_input(Path(args.input) if args.input else None)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    manifest = build_manifest(payload)
    json.dump(manifest, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_deletion_ratio(args: argparse.Namespace) -> int:
    try:
        payload = _load_input(Path(args.input) if args.input else None)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    prov_path = Path(args.provenance_map)
    if not prov_path.is_file():
        print(f"error: provenance-map not found: {prov_path}", file=sys.stderr)
        return 1
    try:
        provenance = json.loads(prov_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: provenance-map is not valid JSON: {exc}", file=sys.stderr)
        return 1
    try:
        result = compute_deletion_ratio(payload, provenance)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-build-change-manifest",
        description=(
            "Aggregate category A/B/C/D detection results into the unified "
            "change manifest, OR compute the §2.2 deletion-ratio trigger."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="aggregate categories into manifest")
    p_build.add_argument(
        "--input", default=None, help="path to JSON input (default: stdin)"
    )
    p_build.set_defaults(func=_cmd_build)

    p_ratio = sub.add_parser(
        "deletion-ratio",
        help="compute §2.2 trigger; requires --provenance-map",
    )
    p_ratio.add_argument(
        "--input", default=None, help="path to JSON input (default: stdin)"
    )
    p_ratio.add_argument(
        "--provenance-map", required=True, help="path to provenance-map.json"
    )
    p_ratio.set_defaults(func=_cmd_deletion_ratio)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
