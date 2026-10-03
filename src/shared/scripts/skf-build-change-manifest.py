# /// script
# requires-python = ">=3.11"
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

  build [--input <file>] [--category-a <file>] [--category-b-diff <file>]
        [--category-c <file>] [--ccc-pairs <file>]
        [--file-compare <file> --provenance-map <file>] [--new-files <file>]
      Reads category JSON from stdin or `--input <file>`, emits the
      unified manifest envelope (see "Manifest" below).

  build --doc-hashes <file>
      A docs-only skill's manifest, from skf-detect-docs.py
      compare-hashes' output and nothing else (see "Docs-only" below).

  deletion-ratio --provenance-map <file> [--input <file>]
                 [--category-a <file>] [--category-b-diff <file>]
                 [--category-c <file>] [--ccc-pairs <file>]
      Same category JSON input. Reads provenance entries[] from
      <file>, computes the §2.2 trigger envelope. Auto-skips when
      degraded_mode or update_mode==gap-driven is set in the input.

  rename-candidates --category-a <file> --provenance-map <file>
                    --tier Quick|Forge|Forge+|Deep [--category-b-diff <file>]
                    [--extraction <file>] [--export-details <file>]
                    [--source-root <dir> [--sizes-commit <commit>]] [-o <file>]
      Category C by fixed rules (see "Rename candidates" below): pairs
      Category A's deleted files with its added ones, and the diff's
      removed exports with its added ones and the added files' exports.
      Prints {"category_c": {...}, "evidence": {...}, "unpaired": {...}}.

  apply --update-type incremental|gap-driven|full --skill-name <name>
        --generation-date <iso> --confidence-tier <tier>
        --manual-sections-preserved <n> -o <file> [inputs...]
      The provenance map an update writes (see "Apply" below): the old
      map with this run's changes, written to -o through a temporary file
      and a rename. Prints a summary with the warnings for a person.

  records [--extraction <file>] [--export-details <file>]
          [--files-from <file>] [--patches <dir>] -o <file>
      Step 3's re-extraction records (see "Records" below), written to -o
      through a temporary file and a rename. Prints {"status": "written",
      "output", "files_extracted", "exports_extracted",
      "confidence_breakdown": {"T1", "T1-low", "T2"}, "warnings"}.

Helper files in place of typed slices (update-skill detect-changes §2.1):

  --category-a <file>       the output of skf-classify-changed-files.py
                            classify: its category_a is the Category A
                            slice, and each of its moved_files (a
                            same-content move) is a category_c.renamed_files
                            item, ahead of the input's own
  --category-b-diff <file>  the output of skf-structural-diff.py over the
                            modified files: the Category B slice, mapped
                              removed[]  -> deleted_exports {name, file, old_line}
                              added[]    -> new_exports {name, file, line}
                              changed[]  -> modified_exports {name, file,
                                            old_line, new_line} for an export
                                            with a field other than `line`, or
                                            one signature_unverified[] lists
                                            (its lines null when no field
                                            changed); moved_exports for an
                                            export whose only field is `line`
                              moved[]    -> moved_exports {name, file:
                                            current_file, old_line:
                                            previous_line, new_line: line},
                                            unless it is a modified export
                            label_changes[] is not drift, and a name
                            ambiguous_names[] lists stays removed and added
  --category-c <file>       the output of rename-candidates: its category_c
                            is the Category C slice
  --ccc-pairs <file>        the pairs the update's CCC check added to what
                            rename-candidates left unpaired,
                            {"renamed_files": [...], "renamed_exports":
                            [...]}, appended to the Category C slice
  --file-compare <file>     build only: the output of skf-hash-content.py
                            compare, with --provenance-map (the map it
                            compared): each MODIFIED_FILE and DELETED_FILE
                            row goes to the {type}s_modified or
                            {type}s_deleted list of category_d, by the
                            file_type of the file_entries[] row of its
                            source_file (script, asset or doc; a row with
                            none takes the type its file_name's first
                            folder names, scripts/, assets/ or docs/, else
                            asset)
  --new-files <file>        build only: the output of skf-new-file-diff.py:
                            each new_files[] item goes to scripts_added or
                            assets_added by its kind
  Either Category D file makes the two files the category_d slice. A given
  file replaces the input's own slice. Either way, every category_c
  rename then takes its pair out of the lists it was found in: a renamed
  file's old_path out of category_a.deleted and new_path out of
  category_a.added; a renamed export's old_name out of
  category_b.deleted_exports (the one in its `old_file` when the item gives
  one, else preferably the one in its `file`) and its new_name out of
  category_b.new_exports (preferably the one in its `file`).

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
      "assets_modified": [...],          "assets_added": [...],  "assets_deleted":  [...],
      "docs_modified": [...],            "docs_deleted": [...]
    },
    "degraded_mode": false,
    "update_mode": "normal" | "gap-driven"  // optional; influences deletion-ratio only
  }

Manifest (build's output):

  {"no_changes": <every count is 0>, "degraded_mode": <bool>,
   "counts": {files_changed, files_added, files_deleted, files_moved,
              exports_modified, exports_new, exports_deleted,
              exports_renamed, exports_moved, and one count per
              category_d list},
   "total_export_changes": N, "per_file": [...],
   "category_d": {the eight category_d lists, each path once}}

  A tracked document (a doc row of file_entries[]) has no other detector:
  update-skill's Category A never lists it, so a document-only change still
  counts, and the update records its new hash.

Every category and sub-key is optional — missing keys default to
empty lists. This lets gap-driven runs (which produce no Category D
results) and degraded runs (which skip Category B) feed the same
script without sentinel values.

Docs-only (update-skill detect-changes §1): build --doc-hashes reads the
compare-hashes output and prints {"mode": "docs-only", "no_changes":
<changed[] is empty>, "changed_urls": [each changed[].url],
"fetch_failed": [each fetch_failed[].url], "counts": {"docs_changed",
"docs_fetch_failed"}}. It takes no other input.

Rename candidates (update-skill detect-changes Category C):

  Content similarity above 80% (fixed, not configurable) is a rename. A
  file moved with its content unchanged is Category A's moved_files and is
  left out here. For the rest:
    files, Quick tier   the added file's size is within 20% of the deleted
                        file's (the deleted size is `git cat-file -s` of
                        <commit>:<path> under --source-root; with no
                        --sizes-commit, a local source whose file is gone,
                        the size test is skipped) and the export names
                        overlap above 70% (shared names over all names of
                        the two files)
    files, Forge+       above 80% of the exports match: an export of the
                        added file with the deleted file's export name and
                        signature (export_type, params and return_type),
                        over the larger file's export count
    exports, Quick      the names are above 80% alike (difflib ratio) and
                        their export types agree
    exports, Forge+     the signatures are equal (export_type, params and
                        return_type, a parameter list or a return type
                        given) and the names differ
  A deleted file's exports come from the provenance map, an added file's
  from --extraction and --export-details. A pair is kept only when it is
  each side's best match: the highest similarity wins, and a tie between
  two candidates pairs neither. category_c.renamed_files holds {old_path,
  new_path}; renamed_exports holds {old_name, new_name, file, old_file?},
  with old_file only when it differs from file. evidence lists each pair
  with its rule and similarity, and unpaired the deleted and added files
  and the removed and added exports left over, for the judgment step.

Apply (update-skill write.md §3):

  Reads the provenance map the update started from (--provenance-map;
  without it, a degraded run's new map) and prints nothing but a summary:
  the new map goes to -o. Every entry the run leaves alone keeps its exact
  value; every entry it adds or rewrites carries signature_source, set
  from the tool that produced the signature: ast-grep gives T1 (with
  confidence T1 and the recipe's ast_node_type), a signature read by eye
  (source-read) gives T1-low (confidence T1-low, ast_node_type null).
  A rewritten entry keeps any key the update does not set (notes,
  deprecated). New entries take source_library from the map's entries,
  else --skill-name.

  incremental (normal mode) reads --manifest (build's output), the renamed
  exports of --category-c and --ccc-pairs (or of --input, the category
  JSON's category_c) and the fresh
  records: --reextract-records ({"mode": "normal", "files": [{file_path,
  exports: [...]}]}, the records `records` wrote), --extraction (the
  recipe runner's exports) and --export-details. A fresh record of an
  export takes its line, export_type and ast labels from the runner, then
  the details, then step 3's record; its params and return_type from the
  details, then step 3's record (the runner's in the map's typed form).
  Per file of the manifest:
    MODIFIED  NEW_EXPORT adds an entry, MODIFIED_EXPORT rewrites the
              export's fields from its fresh record, MOVED_EXPORT sets
              its line (and file), DELETED_EXPORT removes it
    ADDED     every fresh record of the file becomes an entry
    DELETED   every entry of the file is removed
    MOVED     the old path's entries are replaced by the new path's
              fresh records, each keeping the keys of the entry of its
              name it replaces
  and each renamed export takes its new name and fresh fields. A docs-only
  run's records ({"mode": "docs-only", "changed_urls": [...], "exports":
  [{name, type, params, return_type, url}]}) replace the entries of each
  changed URL (source_file is the URL; confidence and signature_source
  T3).

  gap-driven reads --reextract-records ({"mode": "gap-driven",
  "verification": [...], "files": [...]}) and --merge-records ({"exports":
  [{export_name, export_type, params, return_type}]}, merge's output for
  an export no fresh record holds). Each verification record names
  export_name, gap_category, severity, verification, in_map (the map holds
  an entry of that name), map_entry ({source_file, source_line} of the one
  entry the spot-check took, else null), source_citation, new_location,
  unknown_reason, pinned_definition_lines and reachability:
    verified (map_entry)    unchanged
    moved (map_entry)       source_line (and source_file) from new_location
    re-extracted            the entry from its `files` record (gap-driven.md §4a)
    verified/moved, not in_map, a NEW_EXPORT or MODIFIED_EXPORT whose
    reachability is not internal-unreachable
                            one source-read entry at the citation's line
                            (verified) or new_location (moved), at most one
                            per name and file, export_type and the
                            signature from --merge-records
    unknown, not in_map, a NEW_EXPORT or MODIFIED_EXPORT, a Medium, Low or
    Info severity           an entry from --merge-records with no
                            source_file or source_line
    unknown, not in_map, any other severity (a missing one included)
                            refused: exit 3, nothing written
    missing, unknown in_map, unknown on a MOVED_EXPORT
                            unchanged, with a warning for a person
    rescoped                the entry removed
  Under the drift override (--drift-head and --drift-pinned) each warning
  names the drift.

  full (degraded mode) makes every fresh record an entry.

  Every mode then applies the file changes: --file-compare (skf-hash-
  content.py compare's output) sets the content_hash of a MODIFIED_FILE
  row and removes a DELETED_FILE row; --new-files (skf-new-file-diff.py's
  output) adds a row per new script or asset ({kind}s/<file name>, hashed
  under --source-root, extraction_method file-copy); --promoted-docs (the
  documents step 2 promoted, with their hashes) adds a doc row each
  (docs/authoritative/<path>, promoted-authoritative). A row whose
  source_file the map already holds is never added twice.

  Last it sets the top-level source_commit and source_ref (when given)
  and the update block, replacing an earlier update's values in place:
  last_update (--generation-date), update_type, test_report_run_id,
  files_changed (the manifest's files, or in gap-driven mode the files of
  the entries this run changed), exports_affected (the manifest's export
  changes, or the verification records), confidence_tier and
  manual_sections_preserved. An older update-history key
  (update_operations, update_metadata) stays as it is.

  Summary on stdout: {"status": "written", "map": <-o>, "entries":
  {"added", "updated", "removed"}, "file_entries": {"added", "updated",
  "removed"}, "warnings": [...]}, or {"status": "refused",
  "blocking_unresolved": [{export_name, severity}]} with exit 3.

Records (update-skill re-extract.md §4, and gap-driven.md §4a for the files
it scans):

  Writes {"mode": "normal", "files": [{file_path, exports: [...]}]}, one
  block per file --files-from names (and per other file an export names),
  so the model never types a record a tool already wrote. Each export the
  recipe runner found (--extraction) is seeded with its name, type,
  signature, location (file:line), confidence T1, extraction_method
  ast-grep, ast_node_type and ast_recipe, return_type and params, each
  parameter in the provenance map's typed form (skf-extraction-
  inventory.py typed_param: `name: type`, `name?: type`, ` = default`).
  Where the runner left params or return_type null, --export-details
  fills them. An export only --export-details holds (one read by eye,
  with an export_type) is seeded from it as T1-low, source-read, with a
  null ast_node_type and ast_recipe.

  Then each worker patch in --patches (every *.json there, in name order:
  one block {file_path, exports: [{name, ...}]} or a list of them) is
  merged into the export of its name and file: signature, members,
  docstring and qmd_evidence replace the seed's, and params and
  return_type are set only where the seed has none. A patch for an export
  no seed holds is not added, with a warning. confidence_breakdown counts
  the exports by confidence, and T2 the exports with a qmd_evidence.

Exit codes:
  0  operation succeeded
  1  user error (malformed JSON, bad path, malformed provenance file, a
     helper file that is not the output it names)
  3  apply refused: a blocking gap reached the provenance write with no
     source line (nothing written)
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import subprocess
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
        try:
            text = input_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot read input {input_path}: {exc}") from exc
    else:
        text = sys.stdin.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"input must be a JSON object, got {type(data).__name__}")
    return data


def _load_helper_file(path: Path, what: str, key: str) -> dict:
    """A helper's JSON output: an object holding `key`. Raises ValueError."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {what} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{what} {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or key not in data:
        raise ValueError(f"{what} {path} has no `{key}`: is it the helper's output?")
    return data


# --------------------------------------------------------------------------
# Helper files (update-skill detect-changes §2.1)
# --------------------------------------------------------------------------


def category_b_from_diff(diff: dict) -> dict:
    """Category B's four lists from a skf-structural-diff.py diff of the
    modified files (see the module docstring for the mapping)."""
    lists: dict[str, list] = {
        "modified_exports": [], "new_exports": [], "deleted_exports": [], "moved_exports": [],
    }
    for item in _get_list(diff, "removed"):
        if isinstance(item, dict):
            lists["deleted_exports"].append(
                {"name": item.get("name"), "file": item.get("file"), "old_line": item.get("line")})
    for item in _get_list(diff, "added"):
        if isinstance(item, dict):
            lists["new_exports"].append({"name": item.get("name"), "file": item.get("file"), "line": item.get("line")})
    changed: dict[tuple, dict] = {}
    for item in _get_list(diff, "changed"):
        if not isinstance(item, dict):
            continue
        record = changed.setdefault(
            (item.get("name"), item.get("file")), {"fields": set(), "line": item.get("line"), "old_line": None})
        record["fields"].add(item.get("field"))
        if item.get("field") == "line":
            record["old_line"] = item.get("baseline_value")
    unverified = list(dict.fromkeys(
        (item.get("name"), item.get("file")) for item in _get_list(diff, "signature_unverified")
        if isinstance(item, dict)
    ))
    modified: set[tuple] = set()
    for key, record in changed.items():
        old_line = record["old_line"] if record["old_line"] is not None else record["line"]
        entry = {"name": key[0], "file": key[1], "old_line": old_line, "new_line": record["line"]}
        if record["fields"] - {"line"} or key in unverified:
            lists["modified_exports"].append(entry)
            modified.add(key)
        else:
            lists["moved_exports"].append(entry)
    for key in unverified:
        if key not in modified:
            lists["modified_exports"].append({"name": key[0], "file": key[1], "old_line": None, "new_line": None})
            modified.add(key)
    for item in _get_list(diff, "moved"):
        if isinstance(item, dict) and (item.get("name"), item.get("current_file")) not in modified:
            lists["moved_exports"].append({
                "name": item.get("name"), "file": item.get("current_file"),
                "old_line": item.get("previous_line"), "new_line": item.get("line"),
            })
    return lists


def _take_out(entries: list, name: object, files: tuple) -> None:
    """Remove the first entry named `name`, preferring one in the first of
    `files` that holds one (a None in `files` stands for any file)."""
    for wanted in files:
        for i, entry in enumerate(entries):
            if isinstance(entry, dict) and entry.get("name") == name and wanted in (None, entry.get("file")):
                del entries[i]
                return


def apply_renames(payload: dict) -> dict:
    """Take each Category C rename's pair out of the Category A and B lists
    it was found in (see the module docstring). payload holds category_a
    and category_b as objects, as assemble leaves them."""
    cat_a, cat_b = payload["category_a"], payload["category_b"]
    cat_c = payload.get("category_c", {}) or {}
    for move in _get_list(cat_c, "renamed_files"):
        if not isinstance(move, dict):
            continue
        for key, path in (("deleted", move.get("old_path")), ("added", move.get("new_path"))):
            listed = _get_list(cat_a, key)
            if path in listed:
                cat_a[key] = [p for p in listed if p != path]
    for rename in _get_list(cat_c, "renamed_exports"):
        if not isinstance(rename, dict):
            continue
        deleted = list(_get_list(cat_b, "deleted_exports"))
        new = list(_get_list(cat_b, "new_exports"))
        old_files = (rename["old_file"],) if rename.get("old_file") else (rename.get("file"), None)
        _take_out(deleted, rename.get("old_name"), old_files)
        _take_out(new, rename.get("new_name"), (rename.get("file"), None))
        cat_b["deleted_exports"], cat_b["new_exports"] = deleted, new
    return payload


def assemble(payload: dict, *, category_a_doc: dict | None = None, diff: dict | None = None) -> dict:
    """The category JSON build and deletion-ratio read: the input, with the
    helper files' slices in place of its own, and Category C's renames taken
    out of the A and B lists."""
    out = dict(payload)
    cat_c = dict(payload.get("category_c") or {})
    if category_a_doc is not None:
        out["category_a"] = {key: list(_get_list(category_a_doc, "category_a", key))
                             for key in ("modified", "added", "deleted")}
        moves = [m for m in _get_list(category_a_doc, "moved_files") if isinstance(m, dict)]
        cat_c["renamed_files"] = moves + list(_get_list(cat_c, "renamed_files"))
    else:
        out["category_a"] = {key: list(_get_list(payload, "category_a", key))
                             for key in ("modified", "added", "deleted")}
    if diff is not None:
        out["category_b"] = category_b_from_diff(diff)
    else:
        out["category_b"] = {key: list(_get_list(payload, "category_b", key))
                             for key in ("modified_exports", "new_exports", "deleted_exports", "moved_exports")}
    out["category_c"] = cat_c
    return apply_renames(out)


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

    d_lists = {key: list(dict.fromkeys(p for p in _get_list(cat_d, key) if isinstance(p, str))) for key in D_KEYS}
    d = {key: len(paths) for key, paths in d_lists.items()}

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
        "category_d": d_lists,
    }


# Category D's lists, in the order build counts them.
D_KEYS = ("scripts_modified", "scripts_added", "scripts_deleted", "assets_modified", "assets_added",
          "assets_deleted", "docs_modified", "docs_deleted")
FILE_TYPES = ("script", "asset", "doc")
_FILE_TYPE_OF_FOLDER = {"scripts": "script", "assets": "asset", "docs": "doc"}


def _file_type(row: dict) -> str:
    """A file_entries[] row's file_type, else the one its file_name's first folder names, else asset."""
    kind = row.get("file_type")
    if kind in FILE_TYPES:
        return kind
    name = row.get("file_name")
    folder = name.strip().replace("\\", "/").split("/", 1)[0] if isinstance(name, str) else ""
    return _FILE_TYPE_OF_FOLDER.get(folder, "asset")


def category_d_from_files(compare: dict | None, new_files: dict | None, provenance: dict | None) -> dict:
    """Category D's lists from skf-hash-content.py compare's rows, each typed by the file_entries[] row of its
    source_file in `provenance`, and from skf-new-file-diff.py's new files, by kind. Raises ValueError."""
    rows = (provenance or {}).get("file_entries") or []
    if not isinstance(rows, list):
        raise ValueError("provenance `file_entries` must be an array")
    types: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict) and _norm_path(row.get("source_file")):
            types.setdefault(_norm_path(row["source_file"]), _file_type(row))
    lists: dict[str, list] = {key: [] for key in D_KEYS}
    changes = {"MODIFIED_FILE": "modified", "DELETED_FILE": "deleted"}
    for row in _get_list(compare or {}, "comparisons"):
        if not isinstance(row, dict) or row.get("classification") not in changes:
            continue
        path = _norm_path(row.get("source_file"))
        if path:
            lists[f"{types.get(path, 'asset')}s_{changes[row['classification']]}"].append(path)
    for item in _get_list(new_files or {}, "new_files"):
        if isinstance(item, dict) and item.get("kind") in ("script", "asset") and _norm_path(item.get("source_file")):
            lists[f"{item['kind']}s_added"].append(_norm_path(item["source_file"]))
    return lists


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
# Shared readers (rename-candidates and apply)
# --------------------------------------------------------------------------


def _norm_path(path: object) -> str | None:
    """A file path compared as structural-diff compares it: `/` separators, no leading `./`."""
    if not isinstance(path, str) or not path.strip():
        return None
    text = path.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _load_json_file(path: Path, what: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {what} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{what} {path} is not valid JSON: {exc}") from exc


def _exports_of(doc, what: str) -> list[dict]:
    """The export records of an extraction or export-details file ({"exports": [...]})."""
    if doc is None:
        return []
    if not isinstance(doc, dict) or not isinstance(doc.get("exports"), list):
        raise ValueError(f"{what} has no `exports` array: is it the helper's output?")
    return [e for e in doc["exports"] if isinstance(e, dict)]


def _entries_of(provenance) -> list[dict]:
    if provenance is None:
        return []
    if not isinstance(provenance, dict):
        raise ValueError("the provenance map must be a JSON object")
    entries = provenance.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("provenance `entries` must be an array")
    return [e for e in entries if isinstance(e, dict)]


def _params(value) -> tuple | None:
    """A parameter list compared by its text, whitespace removed."""
    if value is None:
        return None
    if not isinstance(value, list):
        return (str(value),)
    out = []
    for item in value:
        if isinstance(item, dict):
            name, kind = item.get("name"), item.get("type")
            item = f"{name}: {kind}" if kind else str(name)
        out.append("".join(str(item).split()))
    return tuple(out)


def _signature(record: dict) -> tuple:
    """(export_type, params, return_type) of an export record, the parts a signature compares."""
    kind = record.get("export_type", record.get("type"))
    params = record.get("params", record.get("parameters"))
    ret = record.get("return_type")
    return (kind if isinstance(kind, str) else None, _params(params),
            "".join(ret.split()) if isinstance(ret, str) else None)


def _name_of(record: dict) -> str | None:
    name = record.get("export_name", record.get("name"))
    return name if isinstance(name, str) and name else None


def _file_of(record: dict) -> str | None:
    return _norm_path(record.get("source_file", record.get("file", record.get("file_path"))))


# --------------------------------------------------------------------------
# Rename candidates (update-skill detect-changes Category C)
# --------------------------------------------------------------------------


RENAME_SIMILARITY = 0.80  # content similarity above this is a rename (fixed)
SIZE_TOLERANCE = 0.20     # Quick tier: the added file's size within 20% of the deleted one's
NAME_OVERLAP = 0.70       # Quick tier: shared export names above 70%
TIERS = ("Quick", "Forge", "Forge+", "Deep")


def _git_size(source_root: Path, commit: str, path: str) -> int | None:
    """The size of `path` at `commit` (git cat-file -s), or None when git cannot tell."""
    try:
        proc = subprocess.run(["git", "-C", str(source_root), "cat-file", "-s", f"{commit}:{path}"],
                              capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def _file_size(source_root: Path | None, path: str) -> int | None:
    if source_root is None:
        return None
    try:
        return (source_root / path).stat().st_size
    except OSError:
        return None


def _best_pairs(candidates: list[tuple]) -> list[tuple]:
    """Each side's best match only: (score, left, right, rule) tuples, highest score first.

    A pair is kept when neither side is taken yet and no other candidate of
    either side ties its score, so a tie pairs neither.
    """
    out, used_left, used_right = [], set(), set()
    ordered = sorted(candidates, key=lambda c: (-c[0], c[1], c[2]))
    for score, left, right, rule in ordered:
        if left in used_left or right in used_right:
            continue
        rivals = [c for c in ordered if c[0] == score and (c[1] == left) != (c[2] == right)
                  and c[1] not in used_left and c[2] not in used_right]
        if rivals:
            used_left.add(left)
            used_right.add(right)
            for c in rivals:
                used_left.add(c[1])
                used_right.add(c[2])
            continue
        used_left.add(left)
        used_right.add(right)
        out.append((score, left, right, rule))
    return out


def rename_candidates(category_a_doc: dict, diff: dict | None, provenance: dict, extraction: dict | None,
                      details: dict | None, tier: str, *, source_root: Path | None = None,
                      sizes_commit: str | None = None) -> dict:
    """Category C by the fixed rules of the module docstring."""
    if tier not in TIERS:
        raise ValueError(f"--tier must be one of {', '.join(TIERS)}, got {tier!r}")
    forge = tier != "Quick"
    moves = [m for m in _get_list(category_a_doc, "moved_files") if isinstance(m, dict)]
    moved_old = {_norm_path(m.get("old_path")) for m in moves}
    moved_new = {_norm_path(m.get("new_path")) for m in moves}
    deleted = sorted({p for p in map(_norm_path, _get_list(category_a_doc, "category_a", "deleted"))
                      if p and p not in moved_old})
    added = sorted({p for p in map(_norm_path, _get_list(category_a_doc, "category_a", "added"))
                    if p and p not in moved_new})

    old_by_file: dict[str, dict[str, dict]] = {}
    for entry in _entries_of(provenance):
        name, path = _name_of(entry), _file_of(entry)
        if name and path:
            old_by_file.setdefault(path, {}).setdefault(name, entry)
    new_by_file: dict[str, dict[str, dict]] = {}
    for record in _exports_of(extraction, "--extraction file") + _exports_of(details, "--export-details file"):
        name, path = _name_of(record), _file_of(record)
        if name and path:
            merged = new_by_file.setdefault(path, {}).setdefault(name, {})
            for key, value in record.items():
                if merged.get(key) is None:
                    merged[key] = value

    file_candidates = []
    for old in deleted:
        old_exports = old_by_file.get(old, {})
        for new in added:
            new_exports = new_by_file.get(new, {})
            if not old_exports or not new_exports:
                continue
            if forge:
                matched = sum(1 for name, e in old_exports.items()
                              if name in new_exports and _signature(e) == _signature(new_exports[name]))
                score = matched / max(len(old_exports), len(new_exports))
                if score > RENAME_SIMILARITY:
                    file_candidates.append((round(score, 4), old, new, "signatures"))
                continue
            names_old, names_new = set(old_exports), set(new_exports)
            overlap = len(names_old & names_new) / len(names_old | names_new)
            if overlap <= NAME_OVERLAP:
                continue
            old_size = _git_size(source_root, sizes_commit, old) if (source_root and sizes_commit) else None
            new_size = _file_size(source_root, new)
            if old_size is not None:
                if new_size is None or max(old_size, new_size) == 0:
                    continue
                if min(old_size, new_size) / max(old_size, new_size) < 1 - SIZE_TOLERANCE:
                    continue
                rule = "size-and-names"
            else:
                rule = "names (size not checked)"
            file_candidates.append((round(overlap, 4), old, new, rule))
    file_pairs = _best_pairs(file_candidates)
    paired_old = {p[1] for p in file_pairs}
    paired_new = {p[2] for p in file_pairs}

    removed = []
    for item in _get_list(diff or {}, "removed"):
        if isinstance(item, dict) and _name_of(item) and _file_of(item):
            name, path = _name_of(item), _file_of(item)
            removed.append({**old_by_file.get(path, {}).get(name, {}), **{k: v for k, v in item.items()
                                                                         if v is not None},
                            "_key": (name, path)})
    candidates_new = []
    for item in _get_list(diff or {}, "added"):
        if isinstance(item, dict) and _name_of(item) and _file_of(item):
            name, path = _name_of(item), _file_of(item)
            candidates_new.append({**new_by_file.get(path, {}).get(name, {}),
                                   **{k: v for k, v in item.items() if v is not None}, "_key": (name, path)})
    seen_new = {c["_key"] for c in candidates_new}
    for path in added:
        if path in paired_new:
            continue
        for name, record in new_by_file.get(path, {}).items():
            if (name, path) not in seen_new:
                candidates_new.append({**record, "_key": (name, path)})

    export_candidates = []
    for old in removed:
        old_sig = _signature(old)
        for new in candidates_new:
            if old["_key"][0] == new["_key"][0]:
                continue
            new_sig = _signature(new)
            if forge:
                if old_sig[1] is None and old_sig[2] is None:
                    continue
                if old_sig == new_sig:
                    export_candidates.append((1.0, old["_key"], new["_key"], "signature-equal"))
                continue
            if old_sig[0] and new_sig[0] and old_sig[0] != new_sig[0]:
                continue
            ratio = difflib.SequenceMatcher(None, old["_key"][0], new["_key"][0]).ratio()
            if ratio > RENAME_SIMILARITY:
                export_candidates.append((round(ratio, 4), old["_key"], new["_key"], "name-similarity"))
    export_pairs = _best_pairs(export_candidates)

    renamed_exports = []
    for _score, (old_name, old_file), (new_name, new_file), _rule in export_pairs:
        item = {"old_name": old_name, "new_name": new_name, "file": new_file}
        if old_file != new_file:
            item["old_file"] = old_file
        renamed_exports.append(item)
    paired_removed = {p[1] for p in export_pairs}
    paired_added = {p[2] for p in export_pairs}
    return {
        "category_c": {
            "renamed_files": [{"old_path": old, "new_path": new} for _s, old, new, _r in file_pairs],
            "renamed_exports": renamed_exports,
        },
        "evidence": {
            "files": [{"old_path": old, "new_path": new, "rule": rule, "similarity": score}
                      for score, old, new, rule in file_pairs],
            "exports": [{"old_name": o[0], "new_name": n[0], "file": n[1], "rule": rule, "similarity": score}
                        for score, o, n, rule in export_pairs],
        },
        "unpaired": {
            "deleted_files": [p for p in deleted if p not in paired_old],
            "added_files": [p for p in added if p not in paired_new],
            "removed_exports": [{"name": r["_key"][0], "file": r["_key"][1]} for r in removed
                                if r["_key"] not in paired_removed],
            "added_exports": [{"name": c["_key"][0], "file": c["_key"][1]} for c in candidates_new
                              if c["_key"] not in paired_added],
        },
        "tier": tier,
    }


# --------------------------------------------------------------------------
# Apply (update-skill write.md §3)
# --------------------------------------------------------------------------


UPDATE_TYPES = ("incremental", "gap-driven", "full")
NON_BLOCKING = ("medium", "low", "info")
EXIT_REFUSED = 3
# The update block apply sets at the top level of the map, in this order.
UPDATE_BLOCK_KEYS = ("last_update", "update_type", "test_report_run_id", "files_changed", "exports_affected",
                     "confidence_tier", "manual_sections_preserved")


def _labels(method: object, node: object) -> dict:
    """The confidence labels an extraction method implies (create-skill's entry contract)."""
    if method in ("ast-grep", "ast_bridge"):
        return {"confidence": "T1", "extraction_method": "ast-grep", "ast_node_type": node,
                "signature_source": "T1"}
    return {"confidence": "T1-low", "extraction_method": "source-read", "ast_node_type": None,
            "signature_source": "T1-low"}


def _line_of(value: object) -> int | None:
    """A line number from an int, a digit string or a `file:line` / `file:start-end` location."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        tail = value.rsplit(":", 1)[-1].split("-", 1)[0].strip()
        if tail.isdigit():
            return int(tail)
    return None


def _location(value: object) -> tuple[str | None, int | None]:
    """(file, line) of a `file:line` string or a {file, line} object."""
    if isinstance(value, dict):
        return _norm_path(value.get("file") or value.get("source_file")), _line_of(
            value.get("line", value.get("source_line")))
    if isinstance(value, str) and ":" in value:
        path, _, rest = value.rpartition(":")
        return _norm_path(path), _line_of(rest)
    return None, None


class _Fresh:
    """The fresh records of one run, looked up by export name and file."""

    def __init__(self, worker_files: list, extraction: dict | None, details: dict | None):
        self.runner = {}
        self.details = {}
        self.worker = {}
        for record in _exports_of(extraction, "--extraction file"):
            key = (_name_of(record), _file_of(record))
            if all(key):
                self.runner.setdefault(key, record)
        for record in _exports_of(details, "--export-details file"):
            key = (_name_of(record), _file_of(record))
            if all(key):
                self.details.setdefault(key, record)
        for block in worker_files:
            if not isinstance(block, dict):
                continue
            path = _norm_path(block.get("file_path"))
            for record in block.get("exports") or []:
                if isinstance(record, dict) and _name_of(record) and path:
                    self.worker.setdefault((_name_of(record), path), record)

    def keys_of(self, path: str) -> list[tuple]:
        keys = {k for source in (self.runner, self.details, self.worker) for k in source if k[1] == path}
        return sorted(keys)

    def all_keys(self) -> list[tuple]:
        return sorted({k for source in (self.runner, self.details, self.worker) for k in source})

    def record(self, name: str, path: str) -> dict | None:
        """The entry fields of an export's fresh record, or None when no source holds it."""
        key = (name, path)
        runner, detail, worker = self.runner.get(key), self.details.get(key), self.worker.get(key)
        if runner is None and detail is None and worker is None:
            return None
        sources = [r for r in (runner, detail, worker) if r is not None]

        def first(*fields):
            for record in sources:
                for field in fields:
                    value = record.get(field)
                    if value is not None:
                        return value
            return None

        line = None
        for record in sources:
            line = _line_of(record.get("source_line"))
            if line is None and record is worker:
                line = _line_of(record.get("location"))
            if line is not None:
                break
        method = first("extraction_method")
        node = first("ast_node_type") if method in ("ast-grep", "ast_bridge") else None
        params = None
        for record in (detail, worker, runner):
            if record is None:
                continue
            value = record.get("params", record.get("parameters"))
            if value is not None:
                params = value
                break
        return {
            "export_name": name,
            "export_type": first("export_type", "type"),
            "params": params,
            "return_type": first("return_type"),
            "source_file": path,
            "source_line": line,
            **_labels(method, node),
        }


def _without_none(fields: dict, keep: tuple = ()) -> dict:
    return {k: v for k, v in fields.items() if v is not None or k in keep}


def _new_entry(fields: dict, library: str) -> dict:
    """An entry in create-skill's key order, from the fields a record gives."""
    order = ("export_name", "export_type", "source_library", "params", "return_type", "source_file",
             "source_line", "confidence", "extraction_method", "ast_node_type", "signature_source")
    merged = {**fields, "source_library": fields.get("source_library") or library}
    out = {k: merged[k] for k in order if k in merged and (merged[k] is not None or k == "ast_node_type")}
    return out


def _rewrite(entry: dict, fields: dict) -> dict:
    """The entry with `fields` set in place; keys the update does not set keep their values."""
    out = dict(entry)
    for key, value in fields.items():
        if value is None and key not in ("ast_node_type",):
            continue
        out[key] = value
    return out


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


class _Map:
    """The provenance map being rewritten, with what changed."""

    def __init__(self, provenance: dict | None, skill_name: str):
        self.doc = json.loads(json.dumps(provenance)) if provenance is not None else {
            "provenance_version": "2.0", "skill_name": skill_name, "skill_type": "single", "entries": []}
        if not isinstance(self.doc.get("entries"), list):
            raise ValueError("provenance `entries` must be an array")
        libraries = [e.get("source_library") for e in self.doc["entries"]
                     if isinstance(e, dict) and isinstance(e.get("source_library"), str) and e["source_library"]]
        self.library = libraries[0] if libraries else skill_name
        self.added: list[str] = []
        self.updated: list[str] = []
        self.removed: list[str] = []
        self.touched_files: set[str] = set()

    def find(self, name: str, path: str | None, line: int | None = None) -> int | None:
        """The index of the entry with this name (and file, and line when several share both)."""
        hits = [i for i, e in enumerate(self.doc["entries"]) if isinstance(e, dict) and _name_of(e) == name
                and (path is None or _file_of(e) == path)]
        if len(hits) > 1 and line is not None:
            hits = [i for i in hits if _line_of(self.doc["entries"][i].get("source_line")) == line]
        return hits[0] if len(hits) == 1 else None

    def indexes_of(self, path: str) -> list[int]:
        return [i for i, e in enumerate(self.doc["entries"]) if isinstance(e, dict) and _file_of(e) == path]

    def add(self, entry: dict) -> None:
        self.doc["entries"].append(entry)
        self.added.append(entry["export_name"])
        if entry.get("source_file"):
            self.touched_files.add(_norm_path(entry["source_file"]))

    def update(self, index: int, fields: dict) -> None:
        before = self.doc["entries"][index]
        after = _rewrite(before, fields)
        if after != before:
            self.doc["entries"][index] = after
            self.updated.append(_name_of(after))
            for path in (_file_of(before), _file_of(after)):
                if path:
                    self.touched_files.add(path)

    def remove(self, indexes: list[int]) -> None:
        for index in sorted(set(indexes), reverse=True):
            entry = self.doc["entries"].pop(index)
            self.removed.append(_name_of(entry))
            if _file_of(entry):
                self.touched_files.add(_file_of(entry))


def _apply_normal(pmap: _Map, manifest: dict | None, categories: dict | None, fresh: _Fresh,
                  warnings: list[str]) -> tuple[int, int]:
    """Normal mode: the manifest's file and export changes. Returns (files, exports) for the update block."""
    per_file = [f for f in _get_list(manifest or {}, "per_file") if isinstance(f, dict)]

    def refresh(index: int | None, name: str, path: str, *, add: bool) -> None:
        record = fresh.record(name, path)
        if record is None:
            warnings.append(f"provenance: {name} in {path}: no extraction record, entry "
                            f"{'kept as it was' if index is not None else 'not added'}")
            return
        if index is None:
            if add:
                pmap.add(_new_entry(record, pmap.library))
            return
        pmap.update(index, _without_none(record, keep=("ast_node_type",)))

    for item in per_file:
        status, path = item.get("status"), _norm_path(item.get("file_path"))
        if not path:
            continue
        if status == "DELETED":
            pmap.remove(pmap.indexes_of(path))
            continue
        if status == "MOVED":
            old = _norm_path(item.get("old_path"))
            old_entries = {_name_of(pmap.doc["entries"][i]): pmap.doc["entries"][i]
                           for i in (pmap.indexes_of(old) if old else [])}
            pmap.remove(pmap.indexes_of(old) if old else [])
            for name, key_path in fresh.keys_of(path):
                record = fresh.record(name, key_path)
                carried = old_entries.get(name)
                entry = _rewrite(carried, _without_none(record, keep=("ast_node_type",))) if carried \
                    else _new_entry(record, pmap.library)
                pmap.add(entry)
            continue
        if status == "ADDED":
            for name, key_path in fresh.keys_of(path):
                index = pmap.find(name, key_path)
                refresh(index, name, key_path, add=True)
            continue
        for change in item.get("exports_affected") or []:
            if not isinstance(change, dict) or not _name_of(change):
                continue
            name, kind = _name_of(change), change.get("change_type")
            index = pmap.find(name, path, _line_of(change.get("old_line")))
            if kind == "DELETED_EXPORT":
                if index is not None:
                    pmap.remove([index])
            elif kind == "MOVED_EXPORT":
                record = fresh.record(name, path)
                line = record["source_line"] if record and record.get("source_line") is not None \
                    else _line_of(change.get("new_line"))
                if index is not None and line is not None:
                    pmap.update(index, {"source_file": path, "source_line": line})
            elif kind in ("NEW_EXPORT", "MODIFIED_EXPORT"):
                refresh(index, name, path, add=True)
    for rename in _get_list(categories or {}, "category_c", "renamed_exports"):
        if not isinstance(rename, dict):
            continue
        old_name, new_name = rename.get("old_name"), rename.get("new_name")
        path = _norm_path(rename.get("file"))
        old_path = _norm_path(rename.get("old_file")) or path
        if not (isinstance(old_name, str) and isinstance(new_name, str) and path):
            continue
        index = pmap.find(old_name, old_path)
        record = fresh.record(new_name, path)
        if index is None:
            continue
        fields = {"export_name": new_name, "source_file": path}
        if record is not None:
            fields.update(_without_none(record, keep=("ast_node_type",)))
        pmap.update(index, fields)
    files = len(per_file)
    total = manifest.get("total_export_changes") if isinstance(manifest, dict) else None
    return files, total if isinstance(total, int) else 0


def _apply_docs_only(pmap: _Map, records: dict) -> tuple[int, int]:
    changed = [u for u in records.get("changed_urls") or [] if isinstance(u, str) and u]
    exports = [e for e in records.get("exports") or [] if isinstance(e, dict)]
    for url in changed:
        old = {_name_of(pmap.doc["entries"][i]): pmap.doc["entries"][i] for i in pmap.indexes_of(url)}
        pmap.remove(pmap.indexes_of(url))
        for record in exports:
            if record.get("url") != url or not _name_of(record):
                continue
            fields = {"export_name": _name_of(record), "export_type": record.get("export_type", record.get("type")),
                      "params": record.get("params", record.get("parameters")),
                      "return_type": record.get("return_type"), "source_file": url,
                      "confidence": "T3", "signature_source": "T3"}
            carried = old.get(_name_of(record))
            entry = _rewrite(carried, _without_none(fields)) if carried else _new_entry(
                _without_none(fields), pmap.library)
            pmap.add(entry)
    return len(changed), len(exports)


def _drift_note(drift: tuple | None) -> str:
    return f"drift override: HEAD {drift[0]} is not pinned {drift[1]}" if drift else ""


def _apply_gap_driven(pmap: _Map, records: dict, merge_records: dict | None, drift: tuple | None,
                      warnings: list[str]) -> tuple[int, int] | list[dict]:
    """Gap-driven mode: one write per verification record. A list return is the refusal."""
    verification = [r for r in records.get("verification") or [] if isinstance(r, dict) and _name_of(r)]
    reextracted = _Fresh(records.get("files") or [], None, None)
    merged = {}
    for record in _exports_of(merge_records, "--merge-records file") if merge_records is not None else []:
        if _name_of(record):
            merged.setdefault(_name_of(record), record)

    def in_map(r: dict) -> bool:
        return bool(r.get("in_map")) or bool(r.get("map_entry"))

    blocking = [{"export_name": _name_of(r), "severity": r.get("severity")} for r in verification
                if r.get("verification") == "unknown" and not in_map(r)
                and r.get("gap_category") in ("NEW_EXPORT", "MODIFIED_EXPORT")
                and str(r.get("severity") or "").strip().lower() not in NON_BLOCKING]
    if blocking:
        return blocking
    note = _drift_note(drift)
    pinned_keys: set[tuple] = set()
    for r in verification:
        name, outcome, category = _name_of(r), r.get("verification"), r.get("gap_category")
        entry_file, entry_line = _location(r.get("map_entry"))
        index = pmap.find(name, entry_file, entry_line) if r.get("map_entry") else None
        lines = r.get("pinned_definition_lines")
        r5 = f"; definition lines per the test report: {lines}" if category == "MOVED_EXPORT" else ""
        if outcome == "rescoped":
            if index is not None:
                pmap.remove([index])
        elif outcome == "verified" and index is not None:
            if drift and category == "MOVED_EXPORT":
                warnings.append(f"provenance: {name}: verified at HEAD only ({note}{r5})")
        elif outcome == "moved" and index is not None:
            path, line = _location(r.get("new_location"))
            if path and line is not None:
                pmap.update(index, {"source_file": path, "source_line": line})
        elif outcome == "re-extracted":
            path, line = _location(r.get("new_location"))
            record = reextracted.record(name, path) if path else None
            if record is None:
                warnings.append(f"provenance: {name}: re-extracted, but no record of it in the run's files")
                continue
            existing = pmap.find(name, path)
            if existing is None:
                pmap.add(_new_entry(record, pmap.library))
            else:
                pmap.update(existing, _without_none(record, keep=("ast_node_type",)))
        elif outcome in ("verified", "moved") and not in_map(r) and category in ("NEW_EXPORT", "MODIFIED_EXPORT"):
            if r.get("reachability") == "internal-unreachable":
                continue
            where = r.get("source_citation") if outcome == "verified" else r.get("new_location")
            path, line = _location(where)
            if not path or line is None or (name, path) in pinned_keys or pmap.find(name, path) is not None:
                continue
            pinned_keys.add((name, path))
            extra = merged.get(name, {})
            pmap.add(_new_entry(_without_none({
                "export_name": name,
                "export_type": extra.get("export_type") or r.get("export_type"),
                "params": extra.get("params"), "return_type": extra.get("return_type"),
                "source_file": path, "source_line": line, **_labels("source-read", None)},
                keep=("ast_node_type",)), pmap.library))
        elif outcome == "unknown" and not in_map(r) and category in ("NEW_EXPORT", "MODIFIED_EXPORT"):
            extra = merged.get(name, {})
            pmap.add(_new_entry(_without_none({
                "export_name": name, "export_type": extra.get("export_type") or r.get("export_type"),
                "params": extra.get("params"), "return_type": extra.get("return_type"),
                **_labels("source-read", None)}, keep=("ast_node_type",)), pmap.library))
        else:
            if r.get("unknown_reason") == "drift-override":
                warnings.append(f"provenance: {name}: unknown ({note}; no line taken from HEAD{r5})")
            elif drift:
                warnings.append(f"provenance: {name}: {outcome} ({note}{r5})")
            else:
                warnings.append(f"provenance: {name}: {outcome}{r5}")
    return len(pmap.touched_files), len(verification)


def _apply_files(pmap: _Map, compare: dict | None, new_files: dict | None, promoted: list | None,
                 source_root: Path | None) -> dict:
    """The file_entries[] changes of Category D and the promoted documents."""
    rows = pmap.doc.get("file_entries")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise ValueError("provenance `file_entries` must be an array")
    done = {"added": [], "updated": [], "removed": []}
    by_source = {_norm_path(r.get("source_file")): i for i, r in enumerate(rows) if isinstance(r, dict)}
    gone = set()
    for row in _get_list(compare or {}, "comparisons"):
        if not isinstance(row, dict):
            continue
        path, kind = _norm_path(row.get("source_file")), row.get("classification")
        index = by_source.get(path)
        if index is None:
            continue
        if kind == "MODIFIED_FILE" and isinstance(row.get("current_hash"), str):
            if rows[index].get("content_hash") != row["current_hash"]:
                rows[index] = {**rows[index], "content_hash": row["current_hash"]}
                done["updated"].append(path)
        elif kind == "DELETED_FILE":
            gone.add(index)
            done["removed"].append(path)
    rows = [r for i, r in enumerate(rows) if i not in gone]
    held = {_norm_path(r.get("source_file")) for r in rows if isinstance(r, dict)}
    for item in _get_list(new_files or {}, "new_files"):
        if not isinstance(item, dict):
            continue
        path, kind = _norm_path(item.get("source_file")), item.get("kind")
        if not path or path in held or kind not in ("script", "asset"):
            continue
        if source_root is None:
            raise ValueError("--new-files needs --source-root, to hash each new file")
        try:
            digest = _sha256_of(source_root / path)
        except OSError as exc:
            raise ValueError(f"cannot hash new file {path} under {source_root}: {exc}") from exc
        rows.append({"file_name": f"{kind}s/{Path(path).name}", "file_type": kind, "source_file": path,
                     "confidence": "T1-low", "extraction_method": "file-copy", "content_hash": digest})
        held.add(path)
        done["added"].append(path)
    for doc in promoted or []:
        if not isinstance(doc, dict):
            continue
        path = _norm_path(doc.get("path"))
        if not path or path in held or not isinstance(doc.get("content_hash"), str):
            continue
        rows.append({"file_name": f"docs/authoritative/{path}", "file_type": "doc", "source_file": path,
                     "content_hash": doc["content_hash"], "confidence": "T1-low",
                     "extraction_method": "promoted-authoritative"})
        held.add(path)
        done["added"].append(path)
    if rows or "file_entries" in pmap.doc:
        pmap.doc["file_entries"] = rows
    return done


def apply_update(*, update_type: str, provenance: dict | None, skill_name: str, manifest: dict | None = None,
                 categories: dict | None = None, extraction: dict | None = None, details: dict | None = None,
                 records: dict | None = None, merge_records: dict | None = None, compare: dict | None = None,
                 new_files: dict | None = None, promoted: list | None = None, source_root: Path | None = None,
                 generation_date: str, test_report_run_id: str | None, confidence_tier: str,
                 manual_sections_preserved: int, source_commit: str | None = None,
                 source_ref: str | None = None, drift: tuple | None = None) -> tuple[dict, dict]:
    """(new map, summary) of one update (see "Apply" in the module docstring).

    A refusal returns ({}, summary) with status "refused" and no map.
    Raises ValueError for inputs it cannot read.
    """
    if update_type not in UPDATE_TYPES:
        raise ValueError(f"--update-type must be one of {', '.join(UPDATE_TYPES)}, got {update_type!r}")
    if provenance is None and update_type != "full":
        raise ValueError("--provenance-map is required unless --update-type is full (a degraded run)")
    records = records if isinstance(records, dict) else {}
    pmap = _Map(provenance, skill_name)
    warnings: list[str] = []
    mode = records.get("mode")
    if update_type == "gap-driven":
        outcome = _apply_gap_driven(pmap, records, merge_records, drift, warnings)
        if isinstance(outcome, list):
            return {}, {"status": "refused", "blocking_unresolved": outcome}
        files, exports = outcome
    elif mode == "docs-only":
        files, exports = _apply_docs_only(pmap, records)
    else:
        fresh = _Fresh(records.get("files") or [], extraction, details)
        if update_type == "full":
            for name, path in fresh.all_keys():
                index = pmap.find(name, path)
                record = fresh.record(name, path)
                if index is None:
                    pmap.add(_new_entry(record, pmap.library))
                else:
                    pmap.update(index, _without_none(record, keep=("ast_node_type",)))
            files = len({path for _name, path in fresh.all_keys()})
            exports = len(fresh.all_keys())
        else:
            files, exports = _apply_normal(pmap, manifest, categories, fresh, warnings)
    file_changes = _apply_files(pmap, compare, new_files, promoted, source_root)
    doc = pmap.doc
    for key, value in (("source_commit", source_commit), ("source_ref", source_ref)):
        if value is not None:
            doc[key] = value or None
    block = {
        "last_update": generation_date,
        "update_type": update_type,
        "test_report_run_id": test_report_run_id or None,
        "files_changed": files,
        "exports_affected": exports,
        "confidence_tier": confidence_tier,
        "manual_sections_preserved": manual_sections_preserved,
    }
    for key in UPDATE_BLOCK_KEYS:
        doc[key] = block[key]
    summary = {
        "status": "written",
        "entries": {"added": pmap.added, "updated": pmap.updated, "removed": pmap.removed},
        "file_entries": file_changes,
        "warnings": warnings,
    }
    return doc, summary


def _write_json_atomic(path: Path, value) -> None:
    """Write `value` as indented JSON through a temporary file beside `path` and one rename."""
    tmp = path.with_name(f".{path.name}.skf-{os.getpid()}-tmp")
    try:
        tmp.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# Records (update-skill re-extract.md §4, gap-driven.md §4a)
# --------------------------------------------------------------------------


# The fields a worker's patch may set: the ones no tool records, and the two
# a patch sets only where the seed has none.
PATCH_FIELDS = ("signature", "members", "docstring", "qmd_evidence")
PATCH_IF_NULL = ("params", "return_type")
_INVENTORY = None


def _typed_param(param, language: object) -> str | None:
    """One parameter as the provenance map writes it: skf-extraction-inventory.py's typed_param, loaded once from
    this folder, so create-skill and update-skill write one form."""
    global _INVENTORY
    if _INVENTORY is None:
        path = Path(__file__).resolve().parent / "skf-extraction-inventory.py"
        spec = importlib.util.spec_from_file_location("skf_extraction_inventory", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _INVENTORY = module
    return _INVENTORY.typed_param(param, language if isinstance(language, str) else None)


def _typed_params(value, language: object) -> list | None:
    if not isinstance(value, list):
        return None
    return [s for s in (_typed_param(p, language) for p in value) if s is not None]


def _seed(record: dict, path: str, read_by_eye: bool) -> dict:
    """The re-extraction record of one export from the runner's (or, read by eye, step 2's) record."""
    line = _line_of(record.get("source_line"))
    out = {
        "name": _name_of(record),
        "type": record.get("export_type", record.get("type")),
        "signature": record.get("signature"),
        "location": f"{path}:{line}" if line is not None else None,
        "params": _typed_params(record.get("params", record.get("parameters")), record.get("language")),
        "return_type": record.get("return_type"),
    }
    labels = _labels("source-read" if read_by_eye else record.get("extraction_method"), record.get("ast_node_type"))
    out.update({key: labels[key] for key in ("confidence", "extraction_method", "ast_node_type")})
    out["ast_recipe"] = None if read_by_eye else record.get("ast_recipe")
    return out


def _patch_blocks(folder: Path) -> list[dict]:
    """Every per-file block of the patch files in `folder` (a file holds one block or a list of them), in file
    name order. Raises ValueError."""
    if not folder.is_dir():
        raise ValueError(f"--patches {folder} is not a folder")
    blocks = []
    for path in sorted(folder.glob("*.json"), key=lambda p: p.name):
        doc = _load_json_file(path, "patch file")
        for block in doc if isinstance(doc, list) else [doc]:
            if not isinstance(block, dict) or not _norm_path(block.get("file_path")) \
                    or not isinstance(block.get("exports"), list):
                raise ValueError(f"patch file {path} holds a block with no file_path or exports list")
            blocks.append(block)
    return blocks


def build_records(extraction: dict | None, details: dict | None, files: list | None,
                  patches: list[dict]) -> tuple[dict, dict]:
    """(reextract-records.json, summary): each export's record seeded from the runner's and step 2's records, with
    the workers' patches merged in (see "Records" in the module docstring)."""
    runner, extra = {}, {}
    for source, doc, what in ((runner, extraction, "--extraction file"), (extra, details, "--export-details file")):
        for record in _exports_of(doc, what):
            key = (_name_of(record), _file_of(record))
            if all(key):
                source.setdefault(key, record)
    seeded: dict[tuple, dict] = {}
    languages: dict[tuple, object] = {}
    warnings = []

    def fill_if_null(key: tuple, record: dict) -> None:
        """Set params and return_type from `record` where the seed of `key` has none."""
        for field in PATCH_IF_NULL:
            value = record.get(field)
            if field == "params" and value is None:
                value = record.get("parameters")
            if seeded[key][field] is None and value is not None:
                seeded[key][field] = _typed_params(value, languages.get(key)) if field == "params" else value

    for key, record in runner.items():
        seeded[key], languages[key] = _seed(record, key[1], read_by_eye=False), record.get("language")
        fill_if_null(key, extra.get(key, {}))
    for key, record in extra.items():
        if key in runner:
            continue
        if record.get("export_type", record.get("type")) is None:
            warnings.append(f"re-extract: {key[0]} in {key[1]}: an export-details record with no export_type the "
                            f"runner does not hold; not added")
            continue
        seeded[key], languages[key] = _seed(record, key[1], read_by_eye=True), record.get("language")
    for block in patches:
        path = _norm_path(block.get("file_path"))
        for patch in block.get("exports") or []:
            key = (_name_of(patch) if isinstance(patch, dict) else None, path)
            if key not in seeded:
                warnings.append(f"re-extract: a patch names {key[0] or 'no export'} in {path}, which neither the "
                                f"runner nor step 2 recorded; not added")
                continue
            for field in PATCH_FIELDS:
                if patch.get(field) is not None:
                    seeded[key][field] = patch[field]
            fill_if_null(key, patch)
    paths = list(dict.fromkeys([p for p in (_norm_path(f) for f in files or []) if p]
                               + sorted({key[1] for key in seeded})))
    blocks = [{"file_path": path, "exports": [seeded[key] for key in sorted(seeded) if key[1] == path]}
              for path in paths]
    exports = [record for block in blocks for record in block["exports"]]
    summary = {
        "files_extracted": len(blocks),
        "exports_extracted": len(exports),
        "confidence_breakdown": {
            "T1": sum(1 for r in exports if r["confidence"] == "T1"),
            "T1-low": sum(1 for r in exports if r["confidence"] == "T1-low"),
            "T2": sum(1 for r in exports if r.get("qmd_evidence") is not None),
        },
        "warnings": warnings,
    }
    return {"mode": "normal", "files": blocks}, summary


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _category_c(args: argparse.Namespace, own: dict | None) -> dict | None:
    """Category C from --category-c and --ccc-pairs, else the input's own
    (`own`, None when there is none). Raises ValueError."""
    if not args.category_c and not args.ccc_pairs:
        return own
    cat_c = dict(own or {})
    if args.category_c:
        doc = _load_helper_file(Path(args.category_c), "--category-c file", "category_c")
        if not isinstance(doc["category_c"], dict):
            raise ValueError(f"--category-c file {args.category_c} has no `category_c` object")
        cat_c = dict(doc["category_c"])
    if args.ccc_pairs:
        pairs = _load_json_file(Path(args.ccc_pairs), "--ccc-pairs file")
        if not isinstance(pairs, dict):
            raise ValueError(f"--ccc-pairs file {args.ccc_pairs} must hold a JSON object")
        for key in ("renamed_files", "renamed_exports"):
            cat_c[key] = list(_get_list(cat_c, key)) + [p for p in _get_list(pairs, key) if isinstance(p, dict)]
    return cat_c


def _payload(args: argparse.Namespace) -> dict:
    """The category JSON of a build or deletion-ratio call: the input with
    the helper files' slices assembled in. Raises ValueError."""
    payload = _load_input(Path(args.input) if args.input else None)
    cat_c = _category_c(args, payload.get("category_c") if isinstance(payload.get("category_c"), dict) else None)
    if cat_c is not None:
        payload = {**payload, "category_c": cat_c}
    category_a_doc = (
        _load_helper_file(Path(args.category_a), "--category-a file", "category_a") if args.category_a else None
    )
    diff = _load_helper_file(Path(args.category_b_diff), "--category-b-diff file", "removed") \
        if args.category_b_diff else None
    return assemble(payload, category_a_doc=category_a_doc, diff=diff)


def docs_only_manifest(doc_hashes: dict) -> dict:
    """A docs-only skill's change manifest from compare-hashes' output."""
    def urls(key: str) -> list[str]:
        return [e["url"] for e in _get_list(doc_hashes, key) if isinstance(e, dict) and isinstance(e.get("url"), str)]

    changed, failed = urls("changed"), urls("fetch_failed")
    return {"mode": "docs-only", "no_changes": not changed, "changed_urls": changed, "fetch_failed": failed,
            "counts": {"docs_changed": len(changed), "docs_fetch_failed": len(failed)}}


def _category_d(args: argparse.Namespace) -> dict | None:
    """Category D from --file-compare (typed by --provenance-map) and --new-files, else None. Raises ValueError."""
    if not args.file_compare and not args.new_files:
        if args.provenance_map:
            raise ValueError("--provenance-map goes with --file-compare")
        return None
    if args.file_compare and not args.provenance_map:
        raise ValueError("--file-compare needs --provenance-map, which types each row by its file_entries[] row")
    compare = _load_helper_file(Path(args.file_compare), "--file-compare file", "comparisons") \
        if args.file_compare else None
    new_files = _load_helper_file(Path(args.new_files), "--new-files file", "new_files") if args.new_files else None
    provenance = _load_json_file(Path(args.provenance_map), "--provenance-map file") if args.provenance_map else None
    if provenance is not None and not isinstance(provenance, dict):
        raise ValueError(f"--provenance-map file {args.provenance_map} must hold a JSON object")
    return category_d_from_files(compare, new_files, provenance)


def _cmd_build(args: argparse.Namespace) -> int:
    try:
        if args.doc_hashes:
            if (args.input or args.category_a or args.category_b_diff or args.category_c or args.ccc_pairs
                    or args.file_compare or args.new_files or args.provenance_map):
                raise ValueError("--doc-hashes takes no other input")
            doc_hashes = _load_helper_file(Path(args.doc_hashes), "--doc-hashes file", "changed")
            manifest = docs_only_manifest(doc_hashes)
        else:
            payload = _payload(args)
            cat_d = _category_d(args)
            if cat_d is not None:
                payload = {**payload, "category_d": cat_d}
            manifest = build_manifest(payload)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(manifest, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_deletion_ratio(args: argparse.Namespace) -> int:
    try:
        payload = _payload(args)
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


def _optional_json(value: str | None, what: str):
    return _load_json_file(Path(value), what) if value else None


def _emit(result: dict, output: str | None) -> None:
    if output:
        _write_json_atomic(Path(output), result)
        print(json.dumps({"status": "ok", "output": output}))
    else:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")


def _cmd_rename_candidates(args: argparse.Namespace) -> int:
    try:
        category_a_doc = _load_helper_file(Path(args.category_a), "--category-a file", "category_a")
        diff = _load_helper_file(Path(args.category_b_diff), "--category-b-diff file", "removed") \
            if args.category_b_diff else None
        provenance = _load_json_file(Path(args.provenance_map), "--provenance-map file")
        result = rename_candidates(
            category_a_doc, diff, provenance,
            _optional_json(args.extraction, "--extraction file"),
            _optional_json(args.export_details, "--export-details file"),
            args.tier,
            source_root=Path(args.source_root) if args.source_root else None,
            sizes_commit=args.sizes_commit or None,
        )
        _emit(result, args.output)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
        return 1
    return 0


def _apply_categories(args: argparse.Namespace) -> dict | None:
    """The category JSON apply reads: --input, with --category-c and --ccc-pairs in place of its category_c."""
    categories = _optional_json(args.input, "--input file")
    if categories is not None and not isinstance(categories, dict):
        raise ValueError("--input file must hold a JSON object")
    own = (categories or {}).get("category_c")
    cat_c = _category_c(args, own if isinstance(own, dict) else None)
    if cat_c is None:
        return categories
    return {**(categories or {}), "category_c": cat_c}


def _cmd_apply(args: argparse.Namespace) -> int:
    if bool(args.drift_head) != bool(args.drift_pinned):
        print("error: --drift-head and --drift-pinned go together", file=sys.stderr)
        return 1
    try:
        promoted = _optional_json(args.promoted_docs, "--promoted-docs file")
        if promoted is not None and not isinstance(promoted, list):
            raise ValueError("--promoted-docs file must hold a JSON array")
        doc, summary = apply_update(
            update_type=args.update_type,
            provenance=_optional_json(args.provenance_map, "--provenance-map file"),
            skill_name=args.skill_name,
            manifest=_optional_json(args.manifest, "--manifest file"),
            categories=_apply_categories(args),
            extraction=_optional_json(args.extraction, "--extraction file"),
            details=_optional_json(args.export_details, "--export-details file"),
            records=_optional_json(args.reextract_records, "--reextract-records file"),
            merge_records=_optional_json(args.merge_records, "--merge-records file"),
            compare=_optional_json(args.file_compare, "--file-compare file"),
            new_files=_optional_json(args.new_files, "--new-files file"),
            promoted=promoted,
            source_root=Path(args.source_root) if args.source_root else None,
            generation_date=args.generation_date,
            test_report_run_id=args.test_report_run_id,
            confidence_tier=args.confidence_tier,
            manual_sections_preserved=args.manual_sections_preserved,
            source_commit=args.source_commit,
            source_ref=args.source_ref,
            drift=(args.drift_head, args.drift_pinned) if args.drift_head else None,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if summary["status"] == "refused":
        print(json.dumps(summary))
        return EXIT_REFUSED
    try:
        _write_json_atomic(Path(args.output), doc)
    except OSError as exc:
        print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({**summary, "map": args.output}))
    return 0


def _cmd_records(args: argparse.Namespace) -> int:
    try:
        files = _optional_json(args.files_from, "--files-from file")
        if files is not None and not (isinstance(files, list) and all(isinstance(f, str) for f in files)):
            raise ValueError(f"--files-from file {args.files_from} must hold a JSON array of paths")
        records, summary = build_records(
            _optional_json(args.extraction, "--extraction file"),
            _optional_json(args.export_details, "--export-details file"),
            files,
            _patch_blocks(Path(args.patches)) if args.patches else [],
        )
        _write_json_atomic(Path(args.output), records)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "written", "output": args.output, **summary}))
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
    p_build.add_argument("--doc-hashes", metavar="FILE",
                         help="a docs-only skill: skf-detect-docs.py compare-hashes output, the only input")
    p_build.add_argument("--file-compare", metavar="FILE",
                         help="skf-hash-content.py compare output: Category D's modified and deleted files")
    p_build.add_argument("--new-files", metavar="FILE", help="skf-new-file-diff.py output: Category D's new files")
    p_build.add_argument("--provenance-map", metavar="FILE",
                         help="the map --file-compare compared: each row's file_type")
    p_build.set_defaults(func=_cmd_build)

    p_ratio = sub.add_parser(
        "deletion-ratio",
        help="compute §2.2 trigger; requires --provenance-map",
    )
    p_ratio.add_argument(
        "--provenance-map", required=True, help="path to provenance-map.json"
    )
    p_ratio.set_defaults(func=_cmd_deletion_ratio)

    p_rename = sub.add_parser(
        "rename-candidates",
        help="Category C by fixed rules: renamed files and renamed exports",
    )
    p_rename.add_argument("--category-a", required=True, metavar="FILE",
                          help="skf-classify-changed-files.py classify output (deleted and added files)")
    p_rename.add_argument("--category-b-diff", metavar="FILE",
                          help="skf-structural-diff.py output (removed and added exports)")
    p_rename.add_argument("--provenance-map", required=True, metavar="FILE",
                          help="the provenance map: the deleted files' exports")
    p_rename.add_argument("--extraction", metavar="FILE", help="the recipe runner's output: the added files' exports")
    p_rename.add_argument("--export-details", metavar="FILE",
                          help="the workers' export details: params, return types and exports read by eye")
    p_rename.add_argument("--tier", required=True, choices=TIERS, help="the forge tier, which picks the rules")
    p_rename.add_argument("--source-root", metavar="DIR", help="the source tree: the added files' sizes")
    p_rename.add_argument("--sizes-commit", metavar="COMMIT",
                          help="the commit the deleted files' sizes are read at (git cat-file -s)")
    p_rename.add_argument("-o", "--output", metavar="FILE", help="write the JSON here instead of stdout")
    p_rename.set_defaults(func=_cmd_rename_candidates)

    p_apply = sub.add_parser("apply", help="write the provenance map an update leaves")
    p_apply.add_argument("--update-type", required=True, choices=UPDATE_TYPES,
                         help="incremental (normal mode), gap-driven, or full (degraded mode)")
    p_apply.add_argument("--provenance-map", metavar="FILE", help="the map the update started from")
    p_apply.add_argument("--manifest", metavar="FILE", help="the change manifest (build's output)")
    p_apply.add_argument("--input", metavar="FILE", help="the category JSON: category_c's renamed exports")
    p_apply.add_argument("--extraction", metavar="FILE", help="the recipe runner's output")
    p_apply.add_argument("--export-details", metavar="FILE", help="the workers' export details")
    p_apply.add_argument("--reextract-records", metavar="FILE", help="step 3's records")
    p_apply.add_argument("--merge-records", metavar="FILE", help="merge's records of the exports no fresh record holds")
    p_apply.add_argument("--file-compare", metavar="FILE", help="skf-hash-content.py compare output")
    p_apply.add_argument("--new-files", metavar="FILE", help="skf-new-file-diff.py output")
    p_apply.add_argument("--promoted-docs", metavar="FILE", help="the documents step 2 promoted, with their hashes")
    p_apply.add_argument("--source-root", metavar="DIR", help="the source tree: the new files' hashes")
    p_apply.add_argument("--skill-name", required=True, help="the skill name: source_library of a new entry")
    p_apply.add_argument("--generation-date", required=True, help="last_update: the generation_date written")
    p_apply.add_argument("--test-report-run-id", default=None, help="the run id of the test report applied")
    p_apply.add_argument("--confidence-tier", required=True, help="the forge tier the update ran at")
    p_apply.add_argument("--manual-sections-preserved", required=True, type=int,
                         help="the [MANUAL] blocks the post-merge check found intact")
    p_apply.add_argument("--source-commit", default=None, help="the map's source_commit (empty: null)")
    p_apply.add_argument("--source-ref", default=None, help="the map's source_ref (empty: null)")
    p_apply.add_argument("--drift-head", default=None, help="under the drift override: HEAD's short SHA")
    p_apply.add_argument("--drift-pinned", default=None, help="under the drift override: the pinned short SHA")
    p_apply.add_argument("-o", "--output", required=True, metavar="FILE", help="where to write the new map")
    p_apply.set_defaults(func=_cmd_apply)

    p_records = sub.add_parser("records", help="write step 3's re-extraction records from the runner's and the "
                                               "workers' files")
    p_records.add_argument("--extraction", metavar="FILE", help="the recipe runner's output")
    p_records.add_argument("--export-details", metavar="FILE",
                           help="step 2's export details: params and return types, and the exports read by eye")
    p_records.add_argument("--files-from", metavar="FILE",
                           help="the files step 3 extracts (a JSON array), each a block even with no export")
    p_records.add_argument("--patches", metavar="DIR", help="the folder of the workers' per-file patches")
    p_records.add_argument("-o", "--output", required=True, metavar="FILE", help="where to write the records")
    p_records.set_defaults(func=_cmd_records)

    for p in (p_build, p_ratio):
        p.add_argument(
            "--input", default=None, help="path to JSON input (default: stdin)"
        )
        p.add_argument(
            "--category-a", metavar="FILE",
            help="skf-classify-changed-files.py classify output: the Category A slice and its moves",
        )
        p.add_argument(
            "--category-b-diff", metavar="FILE",
            help="skf-structural-diff.py output over the modified files: the Category B slice",
        )
    for p in (p_build, p_ratio, p_apply):
        p.add_argument("--category-c", metavar="FILE", help="rename-candidates output: the Category C slice")
        p.add_argument("--ccc-pairs", metavar="FILE",
                       help="the CCC check's pairs, {renamed_files, renamed_exports}, added to Category C")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
