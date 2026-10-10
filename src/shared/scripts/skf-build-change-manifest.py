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
        [--not-public-out <file>]
      The provenance map an update writes (see "Apply" below): the old
      map with this run's changes, written to -o through a temporary file
      and a rename, and the summary's not_public list to --not-public-out
      when given. Prints a summary with the warnings for a person.

  records [--extraction <file>] [--export-details <file>]
          [--files-from <file>] [--patches <dir>] -o <file>
      Step 3's re-extraction records (see "Records" below), written to -o
      through a temporary file and a rename. Prints {"status": "written",
      "output", "files_extracted", "exports_extracted",
      "confidence_breakdown": {"T1", "T1-low", "T2"}, "marked_not_public"
      (the exports marked public: false), "warnings"}.

  gap-records --manifest <file> --provenance-map <file> [--source-root <dir>]
              [--drift-status ok|skipped|overridden] [--judgments <file>]
              [--remediation-records <file>] [--evidence <file> --tier <tier>]
              (--plan [--files-out <file>] | -o <file>)
      A gap-driven repair's spot-checks, routing and verification records
      (see "Gap records" below): --plan prints what to answer and which
      files targeted re-extraction scans; without it, the records are
      written to -o through a temporary file and a rename.

  baseline-gaps --provenance-map <file> --extraction <file> --files <file>
                --source-root <dir> -o <file>
      Category B's baseline gaps (see "Baseline gaps" below): each map
      entry of the files --files lists that the runner did not report and
      its file still declares, written to -o through a temporary file and
      a rename. Prints {"status": "written", "output": <-o>, "gaps": N,
      "unchecked": N}.

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
                                            current_file, old_file:
                                            previous_file (only when it
                                            differs), old_line:
                                            previous_line, new_line: line},
                                            unless it is a modified export,
                                            which then takes old_file and
                                            old_line: previous_line
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
      "modified_exports": [{name, file, old_line, new_line, old_file?}, ...],
      "new_exports":      [{name, file, line}, ...],
      "deleted_exports":  [{name, file, old_line}, ...],
      "moved_exports":    [{name, file, old_line, new_line, old_file?}, ...]
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

  Each per_file item's exports_affected holds {name, change_type,
  old_line, new_line}, and old_file for an export that moved across files
  (a MOVED_EXPORT, or a MODIFIED_EXPORT that also changed).

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
              export's fields (file included) from its fresh record,
              MOVED_EXPORT moves the entry to the file and the fresh
              record's line, else new_line, DELETED_EXPORT removes it;
              a change with an old_file finds its entry in that file
    ADDED     every fresh record of the file becomes an entry
    DELETED   every entry of the file is removed
    MOVED     the old path's entries are replaced by the new path's
              fresh records, each keeping the keys of the entry of its
              name it replaces
  and each renamed export takes its new name and fresh fields. A
  MOVED_EXPORT whose fresh record is the runner's (ast-grep) also takes
  its confidence, extraction_method and ast_node_type (the entry's when
  the record's is null), and its signature_source when the record holds
  each of params and return_type the entry holds (else the entry's),
  never its export_type, params or return_type; one read by eye moves
  the line and file only.

  Public-api skills (incremental only): a NEW_EXPORT or MODIFIED_EXPORT
  the map does not hold, an ADDED file's record and a MOVED file's record
  whose name no old entry carries become entries only when on the public
  surface: the record's `public` mark (see "Records"), else, for a record
  --reextract-records does not mark, the same rule over --extraction (its
  scope.type). A name whose entry this run removes (a DELETED_EXPORT, a
  DELETED file's or a MOVED file's old path's entry) is added whatever
  its mark. Each one left out is listed in the summary's not_public,
  {name, file}, with one warning for them all; an entry the map holds is
  updated whatever its mark, and no entry is removed for it. A public-api
  --extraction the rule cannot read (no entry_point_diff, an incomplete
  run or one with errors, an unresolved entry point) adds every name, with
  one warning. A docs-only
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
    re-extracted            the entry from its `files` record (gap-driven.md §4a);
                            none when its reachability is internal-unreachable
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
  {"added", "updated", "removed"}, "not_public": [{name, file}],
  "file_entries": {"added", "updated", "removed"}, "warnings": [...]},
  or {"status": "refused",
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

  Public surface. When --extraction's scope.type is public-api (in any
  case) and it has an entry_point_diff, each export of a language family
  whose entry_points.by_language status is `barrel` is marked `public`:
  true when its name and file are a pair of the runner's entry_point_diff
  `public` (its name, or the name `local` gives it in that file) or
  `extraction_gaps`, when a `public` item of its name and family has no
  file, or when one with `via` namespace has its file in the export's
  folder (the names counts.exports_public_api counts); false otherwise.
  The rule is skf-extraction-inventory.py's public_surface, loaded from
  this folder, by which create-skill marks its extraction inventory too.
  In a normal update merge documents no export marked false that the map
  does not hold, and apply adds none; gap-records drops the mark, and a
  full (degraded) apply adds every record. Any other scope type, a family
  with no barrel, and a run with no entry_point_diff, an incomplete one,
  one with errors or one whose entry_points.unresolved is not empty mark
  nothing.

Gap records (update-skill gap-driven.md §3, §4 and §4a):

  Reads the change manifest skf-parse-gaps.py translate wrote. Its
  STRUCTURAL_FIX and metadata update entries are forwarded to merge as
  they are (`forwarded`); every other entry is export-bearing. A severity
  is blocking unless it is Medium, Low or Info (NON_BLOCKING), compared
  case-insensitively, so a missing one is blocking. In order:

  1. Drift gate (--drift-status overridden): each export-bearing entry
     but a MOVED_EXPORT needs the tree, with the first reason that fits:
     a DELETED_EXPORT "a public API recount from the tree (rule R1)", a
     provenance_completeness entry "a line from the tree (rule R3)", one
     whose map_match is not-found "a line and a signature from the tree",
     any other "a signature from the tree". Any such entry: {"status":
     "drift-blocked", "drift_blocked": [{gap_id, name, change_category,
     severity, reason}]}, and no spot-check runs.
  2. A DELETED_EXPORT without a `rescope` that holds its `amendment` and
     `exclude`: {"status": "blocked", "rescope_without_amendment": [names]}.
  3. Spot-checks, by skf-verify-provenance-completeness.py's definition-
     lines rules, loaded from this folder, under --source-root:
       DELETED_EXPORT         rescoped, no check
       MOVED_EXPORT           checked at its map entry when map_match is
                              found (unknown otherwise); under the
                              override a `moved` becomes unknown with
                              unknown_reason drift-override; its
                              pinned_definition_lines are the numbers of
                              its remediation's "definition line(s) (...)"
       NEW_EXPORT, MODIFIED_EXPORT
         map_match found      checked at the map entry (its export_type)
         ambiguous            unknown
         not-found            checked at its source_citation (no export
                              type) when it has one; when that pins no
                              line (unknown or missing), or with no
                              citation: targeted re-extraction (§4a) for a
                              provenance_completeness entry with a source
                              root, for a blocking one whatever its
                              resolved_paths, and for a missing-export or
                              missing-type one with resolved_paths; else
                              unknown
     A check gives `verified` (the line is a definition line, or a module
     or package entry whose file exists), `moved` (one definition line,
     not the recorded one: new_location), `missing` (no such file) or
     `unknown` (several definition lines, none the recorded one, or
     none). A file the rules cover no language of
     takes the answered `declaring_line`: the recorded line is verified,
     another is moved, null is unknown. With no verifier every check is
     unknown, with a `provenance: spot-checks not run` warning; a check
     the verifier fails on (a file it cannot read, or any error) is
     unknown, with a `provenance: spot-check failed for {name}: {error}`
     warning.
  --plan stops here: {"status": "planned", "reextract": {"entries":
  [{gap_id, name, severity, resolved_paths}], "files": [the union of
  their resolved_paths]}, "warnings"}, the files also written to
  --files-out as a JSON array.
  4. Targeted re-extraction (--remediation-records, `records`' output
     over those files): each routed entry with resolved_paths takes the
     first export of its name in the blocks of those files, in their
     order: `re-extracted`, new_location its record's location,
     resolution_source remediation-paths, and the record copied into
     `files` as `records` wrote it, less its `public` mark (a normal
     update's), with the answered `docstring` added.
     An entry with no match, or no path to scan, is unresolved, except a
     missing-export or missing-type one that is not blocking, which is
     unknown. Any unresolved entry: {"status": "unresolved",
     "unresolved": [{gap_id, name, severity, remediation_paths,
     rejected_paths, files_scanned, exports_found_in_scan}]}.
  5. The public-reachability gate: every NEW_EXPORT that is verified,
     moved or re-extracted takes the answered `reachability`, `public` or
     `internal-unreachable`. An internal one keeps its outcome in its
     verification record, its record is not in `files`, `counts` tallies
     it under `reclassified` instead of its outcome, and it is listed in
     `reclassified` (merge queues it as a metadata update; apply writes no
     entry for it).

  Any answer missing in step 3 or 5 (a `docstring` too, for each
  re-extracted entry): {"status": "needs-judgment", "needs_judgment":
  [{gap_id, name, needs: [...], file?, line?}]}. --judgments gives them,
  keyed by gap id (the answers file translate reads; its keys are left).
  Then it writes {"mode": "gap-driven", "files_extracted" (the blocks of
  --remediation-records, 0 when it scanned none), "exports_extracted" (the
  manifest's entries), "confidence_breakdown": {"T1", "T1-low",
  "unlabeled", "T2": 0} (each manifest entry by the extraction_method of
  its re-extracted record or, in the map, of its map entry; a pinned cited
  export the map lacks and the gate passed is T1-low), "verification":
  [one record per export-bearing entry: export_name, gap_category,
  severity, verification, in_map, map_entry, provenance_citation,
  source_citation, new_location, unknown_reason, pinned_definition_lines,
  resolution_source, reachability, export_type (always null: for a cited
  export the map lacks, apply takes it from merge.md's
  merge-records.json)], "files": [...]}, and prints {"status": "written",
  "output", "gap_count", "files_extracted", "exports_extracted",
  "confidence_breakdown", "counts" (per verification outcome, and
  `reclassified`), "reclassified", "forwarded", "targeted_reextraction",
  "warnings"}. When targeted re-extraction ran, `targeted_reextraction`
  is {resolved_count, files_scanned, exports_matched, tier}, also appended
  to --evidence as one JSON line keyed `targeted_reextraction`.

Baseline gaps (update-skill detect-changes Category B, step 1):

  The recipe runner never reports a module, an alias that renames, a
  dunder such as `__version__` or another underscore name, so the diff
  would read each such map entry as a deleted export. baseline-gaps lists,
  for step 2 to read by eye, each entry of a file --files lists (the
  modified files, Category A's modified-files.json) whose name and file
  no export of --extraction (the runner's JSON, or {"exports": []} when
  it could not run) holds, under its name or its re-export target, and
  whose file still declares it. The selection and the declaration rule
  are skf-verify-provenance-completeness.py's `baseline_gaps` (the rule
  audit-skill's extraction snapshot applies), loaded from this folder: a
  verifier that cannot be loaded is an error, never an empty list. A
  name the runner's own `entry_point_diff.extraction_gaps` lists at that
  file is left to that list. A map whose `entries` is missing or null
  has none to check. Writes {"gaps": [{name, file, line, entry: null,
  export_type?}], "unchecked": [{name, file, export_type}]}: a gap's line
  declares the name (line 1 of the module or package so named for a
  `module` or `package` entry), and `unchecked` holds each entry no rule
  can check, to read by eye: its file neither Python nor TS/JS, a file
  the lookup will not read (outside the source root, a test file or a
  minified bundle, a symlink on its path), or a dotted `module` or
  `package` name.

Exit codes:
  0  operation succeeded (for gap-records, whatever its `status`)
  1  user error (malformed JSON, bad path, malformed provenance file, a
     helper file that is not the output it names, a gap-records answer of
     the wrong type, targeted re-extraction to match with no
     --remediation-records, or, for baseline-gaps, a source root that is
     no folder or a verifier that cannot be loaded)
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
import re
import subprocess
import sys
import time
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
        if not isinstance(item, dict):
            continue
        key, old_file = (item.get("name"), item.get("current_file")), _norm_path(item.get("previous_file"))
        across = old_file not in (None, _norm_path(item.get("current_file")))  # apply finds the entry at old_file
        if key in modified:
            if across:  # moved across files and changed: a MODIFIED_EXPORT that names the file it left
                for entry in lists["modified_exports"]:
                    if (entry["name"], entry["file"]) == key:
                        entry.update(old_line=item.get("previous_line"), old_file=old_file)
            continue
        move = {"name": item.get("name"), "file": item.get("current_file")}
        if across:
            move["old_file"] = old_file
        lists["moved_exports"].append({**move, "old_line": item.get("previous_line"), "new_line": item.get("line")})
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
        change = {
            "name": entry.get("name"),
            "change_type": change_type,
            "old_line": entry.get("old_line"),
            "new_line": entry.get("new_line") or entry.get("line"),
        }
        if entry.get("old_file"):
            change["old_file"] = entry["old_file"]  # a move across files: a MOVED_EXPORT, or a MODIFIED_EXPORT
        exports_by_file.setdefault(path, []).append(change)

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


_INVENTORY = None


def _inventory():
    """skf-extraction-inventory.py, loaded once from this folder: its typed_param and its public-surface rule, so
    create-skill and update-skill write one parameter form and keep one public surface."""
    global _INVENTORY
    if _INVENTORY is None:
        path = Path(__file__).resolve().parent / "skf-extraction-inventory.py"
        spec = importlib.util.spec_from_file_location("skf_extraction_inventory", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _INVENTORY = module
    return _INVENTORY


def public_surface(extraction: object) -> tuple[object | None, str | None]:
    """skf-extraction-inventory.py's public_surface over the recipe runner's output (see "Records" in the module
    docstring): (the public surface, None) for a public-api run, (None, why) when its surface cannot be read, and
    (None, None) for any other scope type. An input that is no object (a gap-driven or docs-only run gives none)
    is (None, None) without loading the inventory helper."""
    if not isinstance(extraction, dict):
        return None, None
    return _inventory().public_surface(extraction)


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
REPLACE_WAIT_SECONDS = 5.0  # how long a Windows rename onto a file held open is retried
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
        self.surface, self.surface_problem = public_surface(extraction)
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

    def public(self, name: str, path: str) -> bool | None:
        """The `public` mark `records` gave the export, else the public-surface rule over --extraction; None when
        neither marks it."""
        mark = (self.worker.get((name, path)) or {}).get("public")
        if isinstance(mark, bool):
            return mark
        if self.surface is None:
            return None
        record = self.runner.get((name, path)) or self.details.get((name, path)) or {}
        return self.surface.public(name, path, record.get("language"))

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
                  warnings: list[str], not_public: list[dict]) -> tuple[int, int]:
    """Normal mode: the manifest's file and export changes. Returns (files, exports) for the update block; each
    name it leaves out as off a public-api skill's public surface goes to `not_public`."""
    per_file = [f for f in _get_list(manifest or {}, "per_file") if isinstance(f, dict)]
    # the names of the entries this run removes (a DELETED_EXPORT, a DELETED file's, a MOVED file's old path's):
    # one that comes back in another file is re-added whatever its mark, so no held export is lost
    removed: set[str] = set()
    for item in per_file:
        path = _norm_path(item.get("old_path") if item.get("status") == "MOVED" else item.get("file_path"))
        if item.get("status") in ("DELETED", "MOVED") and path:
            removed.update(_name_of(pmap.doc["entries"][i]) for i in pmap.indexes_of(path))
        removed.update(_name_of(c) for c in item.get("exports_affected") or []
                       if isinstance(c, dict) and c.get("change_type") == "DELETED_EXPORT")
    listed: set[tuple[str, str]] = set()

    def off_surface(name: str, path: str) -> bool:
        """True for a name the run would add that is off the public surface, which it lists."""
        if name in removed or fresh.public(name, path) is not False:
            return False
        if (name, path) not in listed:
            listed.add((name, path))
            not_public.append({"name": name, "file": path})
        return True

    def refresh(index: int | None, name: str, path: str, *, add: bool) -> None:
        record = fresh.record(name, path)
        if record is None:
            warnings.append(f"provenance: {name} in {path}: no extraction record, entry "
                            f"{'kept as it was' if index is not None else 'not added'}")
            return
        if index is None:
            if add and not off_surface(name, path):
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
                if carried is None and off_surface(name, key_path):
                    continue
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
            # a move across files (a MOVED_EXPORT, or a MODIFIED_EXPORT that also moved) names the file its entry is at
            index = pmap.find(name, _norm_path(change.get("old_file")) or path, _line_of(change.get("old_line")))
            if kind == "DELETED_EXPORT":
                if index is not None:
                    pmap.remove([index])
            elif kind == "MOVED_EXPORT":
                record = fresh.record(name, path)
                line = record["source_line"] if record and record.get("source_line") is not None \
                    else _line_of(change.get("new_line"))
                if index is not None and line is not None:
                    fields = {"source_file": path, "source_line": line}
                    if record is not None and record["extraction_method"] == "ast-grep":
                        # the runner matched it: its labels, never its export_type, params or return_type
                        fields.update(confidence=record["confidence"], extraction_method=record["extraction_method"])
                        if record["ast_node_type"] is not None:
                            fields["ast_node_type"] = record["ast_node_type"]
                        entry = pmap.doc["entries"][index]
                        # its signature_source only when the record holds each signature part the entry does
                        if all(record.get(part) is not None for part in ("params", "return_type")
                               if entry.get(part) is not None):
                            fields["signature_source"] = record["signature_source"]
                    pmap.update(index, fields)
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
            if r.get("reachability") == "internal-unreachable":
                continue  # not public API: merge queued it as a metadata update
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
    not_public: list[dict] = []
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
            files, exports = _apply_normal(pmap, manifest, categories, fresh, warnings, not_public)
            if fresh.surface_problem:
                warnings.append(f"provenance: the public surface of this public-api skill could not be applied "
                                f"({fresh.surface_problem}): every new export was added")
    if not_public:
        warnings.append(_not_public_warning(not_public))
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
        "not_public": not_public,
        "file_entries": file_changes,
        "warnings": warnings,
    }
    return doc, summary


NOT_PUBLIC_NAMED = 10  # the names the not_public warning spells out; the summary lists them all


def _not_public_warning(not_public: list[dict]) -> str:
    """The one warning for every name apply left out as off a public-api skill's public surface."""
    names = [item["name"] for item in not_public]
    shown = ", ".join(names[:NOT_PUBLIC_NAMED])
    more = f" and {len(names) - NOT_PUBLIC_NAMED} more" if len(names) > NOT_PUBLIC_NAMED else ""
    return (f"provenance: {len(names)} new export(s) off the public surface of this public-api skill not added "
            f"(the summary's not_public lists each with its file): {shown}{more}")


def _write_json_atomic(path: Path, value) -> None:
    """Write `value` as indented JSON through a temporary file beside `path` and one rename, retried on Windows,
    where a scanner may hold the target open for a moment."""
    tmp = path.with_name(f".{path.name}.skf-{os.getpid()}-tmp")
    try:
        tmp.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        deadline = time.monotonic() + REPLACE_WAIT_SECONDS
        while True:
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if os.name != "nt" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
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


def _typed_param(param, language: object) -> str | None:
    """One parameter as the provenance map writes it: skf-extraction-inventory.py's typed_param, so create-skill
    and update-skill write one form."""
    return _inventory().typed_param(param, language if isinstance(language, str) else None)


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
    surface, _problem = public_surface(extraction)  # apply warns when a public-api run gives no surface
    for key in seeded if surface is not None else ():
        mark = surface.public(key[0], key[1], languages.get(key))
        if mark is not None:
            seeded[key]["public"] = mark
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
        "marked_not_public": sum(1 for r in exports if r.get("public") is False),
        "warnings": warnings,
    }
    return {"mode": "normal", "files": blocks}, summary


# --------------------------------------------------------------------------
# Gap records (update-skill gap-driven.md §3, §4 and §4a)
# --------------------------------------------------------------------------


EXPORT_CATEGORIES = ("NEW_EXPORT", "MODIFIED_EXPORT", "MOVED_EXPORT", "DELETED_EXPORT")
DOCUMENT_CATEGORIES = ("missing-export", "missing-type")  # routed to §4a by category, never halting
DRIFT_STATUSES = ("ok", "skipped", "overridden")
# The drift gate's reasons, gap-driven.md §3: the first that fits.
DRIFT_RESCOPE = "a public API recount from the tree (rule R1)"
DRIFT_COMPLETENESS = "a line from the tree (rule R3)"
DRIFT_NOT_IN_MAP = "a line and a signature from the tree"
DRIFT_IN_MAP = "a signature from the tree"
REACHABILITY = ("public", "internal-unreachable")
VERIFIER_MISSING = "provenance: spot-checks not run: skf-verify-provenance-completeness.py is missing; re-install SKF"
OUTCOMES = ("verified", "moved", "missing", "re-extracted", "rescoped", "unknown")
_DEFINITION_LINES = re.compile(r"definition lines?\s*\(([\d,\s]+)\)", re.IGNORECASE)
_VERIFIER = None


def _verifier():
    """skf-verify-provenance-completeness.py, loaded once from this folder for its definition-lines rules, or None
    when it cannot be loaded."""
    global _VERIFIER
    if _VERIFIER is None:
        path = Path(__file__).resolve().parent / "skf-verify-provenance-completeness.py"
        try:
            spec = importlib.util.spec_from_file_location("skf_verify_provenance_completeness", path)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except (OSError, ImportError, SyntaxError):
            _VERIFIER = False
        else:
            _VERIFIER = module
    return _VERIFIER or None


def _blocking(severity: object) -> bool:
    return str(severity or "").strip().lower() not in NON_BLOCKING


def _gap_judgments(doc) -> dict:
    """The answers gap-records reads from a --judgments file, checked. Raises ValueError."""
    if not isinstance(doc, dict) or not all(isinstance(v, dict) for v in doc.values()):
        raise ValueError("--judgments must map each gap id to an object of answers")
    for gid, answers in doc.items():
        line = answers.get("declaring_line")
        if "declaring_line" in answers and line is not None and (isinstance(line, bool) or not isinstance(line, int)):
            raise ValueError(f"--judgments: {gid}'s `declaring_line` must be a line number or null")
        if "reachability" in answers and answers["reachability"] not in REACHABILITY:
            raise ValueError(f"--judgments: {gid}'s `reachability` must be one of {', '.join(REACHABILITY)}")
        if "docstring" in answers and not isinstance(answers["docstring"], (str, type(None))):
            raise ValueError(f"--judgments: {gid}'s `docstring` must be a string or null")
    return doc


def _drift_reason(entry: dict) -> str | None:
    """The drift gate's reason an export-bearing entry needs the tree, or None for one that passes."""
    category = entry.get("change_category")
    if category == "DELETED_EXPORT":
        return DRIFT_RESCOPE
    if category not in ("NEW_EXPORT", "MODIFIED_EXPORT"):
        return None
    if entry.get("provenance_completeness"):
        return DRIFT_COMPLETENESS
    status = (entry.get("map_match") or {}).get("status")
    return DRIFT_IN_MAP if status in ("found", "ambiguous") else DRIFT_NOT_IN_MAP


def _spot_check(root: Path | None, path: str | None, name: str, line: int | None, export_type: object,
                answers: dict) -> tuple[str, int | None, bool, str | None]:
    """(outcome, the line a `moved` export moves to, whether it waits on a `declaring_line` answer, why the
    check failed)."""
    verifier = _verifier()
    if verifier is None or root is None or not path or line is None:
        return "unknown", None, False, None
    try:
        report = verifier.definition_lines_report(path, name, root, line,
                                                  export_type if isinstance(export_type, str) else None)
    except Exception as exc:  # noqa: BLE001 - a file it cannot read, or any verifier failure: this entry only
        return "unknown", None, False, f"{type(exc).__name__}: {exc}"
    check = report.get("line_check")
    if check == "file-missing":
        return "missing", None, False, None
    if check == "skipped-export-type":
        return "verified", None, False, None
    if check == "skipped-language":
        if "declaring_line" not in answers:
            return "unknown", None, True, None
        declared = answers["declaring_line"]
        if declared is None:
            return "unknown", None, False, None
        return ("verified", None, False, None) if declared == line else ("moved", declared, False, None)
    if report.get("line_is_definition"):
        return "verified", None, False, None
    defs = report.get("definition_lines") or []
    if len(defs) == 1 and defs[0] != line:
        return "moved", defs[0], False, None
    return "unknown", None, False, None


def _pinned_lines(remediation: object) -> list[int] | None:
    """The definition lines a provenance-line gap's remediation lists, `... definition line (5, 7) ...`."""
    m = _DEFINITION_LINES.search(remediation) if isinstance(remediation, str) else None
    lines = [int(n) for n in re.findall(r"\d+", m.group(1))] if m else []
    return lines or None


def _where(path: object, line: object) -> str | None:
    file, number = _norm_path(path), _line_of(line)
    return f"{file}:{number}" if file and number is not None else None


class _GapEntry:
    """One export-bearing manifest entry as gap-records routes it."""

    def __init__(self, entry: dict, answers: dict):
        self.entry = entry
        self.answers = answers
        self.name = _name_of(entry) or ""
        self.category = entry.get("change_category")
        match = entry.get("map_match") if isinstance(entry.get("map_match"), dict) else {}
        self.match_status = match.get("status") or "not-found"
        found = match.get("entry") if self.match_status == "found" and isinstance(match.get("entry"), dict) else None
        self.map_entry = {"source_file": found.get("source_file"), "source_line": found.get("source_line")} \
            if found else None
        self.map_export_type = found.get("export_type") if found else None
        self.in_map = bool(match.get("candidates"))
        citation = entry.get("source_citation")
        self.citation = citation if isinstance(citation, dict) else None
        self.recorded: tuple[str | None, int | None] = (None, None)  # the file and line a check read
        self.outcome: str | None = None
        self.new_line: int | None = None
        self.unknown_reason: str | None = None
        self.reextract = False
        self.record: dict | None = None  # the §4a record it matched
        self.record_path: str | None = None
        self.waits = False  # on a declaring_line answer
        self.failure: str | None = None  # why its spot-check failed

    @property
    def blocking(self) -> bool:
        return _blocking(self.entry.get("severity"))

    @property
    def paths(self) -> list[str]:
        return [p for p in (_norm_path(p) for p in self.entry.get("resolved_paths") or []) if p]

    def check(self, root: Path | None, path: object, line: object, export_type: object) -> None:
        self.recorded = (_norm_path(path), _line_of(line))
        self.outcome, self.new_line, self.waits, self.failure = _spot_check(
            root, self.recorded[0], self.name, self.recorded[1], export_type, self.answers)

    def route(self, root: Path | None, drift: bool) -> None:
        """Spot-check the entry, or send it to targeted re-extraction (see "Gap records" in the module docstring)."""
        if self.category == "DELETED_EXPORT":
            self.outcome = "rescoped"
            if self.map_entry:
                self.recorded = (_norm_path(self.map_entry["source_file"]), _line_of(self.map_entry["source_line"]))
            return
        if self.category == "MOVED_EXPORT":
            if self.map_entry is None:
                self.outcome = "unknown"
                return
            self.check(root, self.map_entry["source_file"], self.map_entry["source_line"], self.map_export_type)
            if drift and self.outcome == "moved":
                self.outcome, self.new_line, self.unknown_reason = "unknown", None, "drift-override"
            return
        if self.match_status == "found":
            self.check(root, self.map_entry["source_file"], self.map_entry["source_line"], self.map_export_type)
            return
        if self.match_status == "ambiguous":
            self.outcome = "unknown"
            return
        if self.citation:
            self.check(root, self.citation.get("file"), self.citation.get("line"), None)
            if self.waits or self.outcome in ("verified", "moved"):
                return
        if self.entry.get("provenance_completeness") and root is not None:
            self.reextract = True
        elif self.blocking:
            self.reextract = True
        elif self.entry.get("category") in DOCUMENT_CATEGORIES and self.paths:
            self.reextract = True
        else:
            self.outcome = "unknown"

    def match(self, blocks: dict[str, list[dict]]) -> tuple[int, int]:
        """Take the first export of the entry's name in the blocks of its resolved files; (files scanned, exports
        found in them)."""
        exports = 0
        for path in self.paths:
            for record in blocks.get(path, []):
                exports += 1
                if self.record is None and _name_of(record) == self.name:
                    self.record, self.record_path = record, path
        if self.record is not None:
            self.outcome = "re-extracted"
        return len(self.paths), exports

    @property
    def located(self) -> bool:
        return self.outcome in ("verified", "moved", "re-extracted")

    @property
    def internal(self) -> bool:
        return self.category == "NEW_EXPORT" and self.answers.get("reachability") == "internal-unreachable"

    def needs(self) -> list[str]:
        """The answers the entry still waits on once routed."""
        want = []
        if self.category == "NEW_EXPORT" and self.located and "reachability" not in self.answers:
            want.append("reachability")
        if self.outcome == "re-extracted" and "docstring" not in self.answers:
            want.append("docstring")
        return want

    def new_location(self) -> str | None:
        if self.outcome == "moved":
            return _where(self.recorded[0], self.new_line)
        if self.outcome == "re-extracted":
            return (self.record or {}).get("location")
        return None

    def verification(self) -> dict:
        recorded = _where(*self.recorded)
        if self.outcome == "re-extracted":
            citation = self.new_location()
        elif self.outcome in ("verified", "moved", "missing", "rescoped") and recorded:
            citation = recorded
        else:
            citation = "unknown"
        return {
            "export_name": self.name,
            "gap_category": self.category,
            "severity": self.entry.get("severity"),
            "verification": self.outcome,
            "in_map": self.in_map,
            "map_entry": self.map_entry,
            "provenance_citation": citation,
            "source_citation": self.citation,
            "new_location": self.new_location(),
            "unknown_reason": self.unknown_reason,
            "pinned_definition_lines": _pinned_lines(self.entry.get("remediation"))
            if self.category == "MOVED_EXPORT" else None,
            "resolution_source": "remediation-paths" if self.outcome == "re-extracted" else None,
            "reachability": self.answers.get("reachability") if self.category == "NEW_EXPORT" and self.located
            else None,
            "export_type": None,
        }

    def label(self, provenance: list[dict]) -> str:
        """T1, T1-low or unlabeled: the confidence_breakdown bin of the entry."""
        if self.internal:
            return "unlabeled"
        method = None
        if self.outcome == "re-extracted":
            method = (self.record or {}).get("extraction_method")
        elif self.map_entry is not None:
            file, line = _norm_path(self.map_entry["source_file"]), _line_of(self.map_entry["source_line"])
            for entry in provenance:
                if (_name_of(entry) == self.name and _file_of(entry) == file
                        and _line_of(entry.get("source_line")) == line):
                    method = entry.get("extraction_method")
                    break
        elif self.located and self.category in ("NEW_EXPORT", "MODIFIED_EXPORT"):
            method = "source-read"  # a pinned cited export the map lacks: write.md §3 writes it source-read
        if method in ("ast-grep", "ast_bridge"):
            return "T1"
        if method in ("source-read", "source_reading"):
            return "T1-low"
        return "unlabeled"


def gap_records(manifest: dict, provenance: dict | None, *, source_root: Path | None, drift_status: str = "ok",
                judgments: dict | None = None, remediation: dict | None = None, plan: bool = False,
                tier: str | None = None) -> tuple[dict | None, dict]:
    """(reextract-records.json or None, the summary): see "Gap records" in the module docstring."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        raise ValueError("the change manifest has no `entries` array: is it translate's output?")
    entries = [e for e in manifest["entries"] if isinstance(e, dict)]
    judgments = judgments or {}
    root = source_root if source_root is not None and source_root.is_dir() else None
    forwarded = [{"gap_id": e.get("gap_id"), "change_category": e.get("change_category")}
                 for e in entries if e.get("change_category") not in EXPORT_CATEGORIES]
    routed = [_GapEntry(e, judgments.get(e.get("gap_id")) or {}) for e in entries
              if e.get("change_category") in EXPORT_CATEGORIES]
    drift = drift_status == "overridden"
    if drift:
        blocked = [{"gap_id": g.entry.get("gap_id"), "name": g.name, "change_category": g.category,
                    "severity": g.entry.get("severity"), "reason": _drift_reason(g.entry)}
                   for g in routed if _drift_reason(g.entry)]
        if blocked:
            return None, {"status": "drift-blocked", "drift_blocked": blocked}
    bare = [g.name for g in routed if g.category == "DELETED_EXPORT" and not (
        isinstance(g.entry.get("rescope"), dict) and g.entry["rescope"].get("amendment")
        and g.entry["rescope"].get("exclude"))]
    if bare:
        return None, {"status": "blocked", "rescope_without_amendment": bare}
    warnings = []
    if root is not None and _verifier() is None:
        warnings.append(VERIFIER_MISSING)
    for g in routed:
        g.route(root, drift)
    warnings += [f"provenance: spot-check failed for {g.name}: {g.failure}" for g in routed if g.failure]
    waiting = [{"gap_id": g.entry.get("gap_id"), "name": g.name, "needs": ["declaring_line"],
                "file": g.recorded[0], "line": g.recorded[1]} for g in routed if g.waits]
    if waiting:
        return None, {"status": "needs-judgment", "needs_judgment": waiting, "warnings": warnings}
    to_scan = [g for g in routed if g.reextract]
    files = list(dict.fromkeys(p for g in to_scan for p in g.paths))
    if plan:
        return None, {"status": "planned", "reextract": {
            "entries": [{"gap_id": g.entry.get("gap_id"), "name": g.name, "severity": g.entry.get("severity"),
                         "resolved_paths": g.paths} for g in to_scan], "files": files}, "warnings": warnings}
    blocks: dict[str, list[dict]] = {}
    scanned = 0
    if files:
        if remediation is None:
            raise ValueError("targeted re-extraction has files to match: pass --remediation-records, the output "
                             "of `records` over them")
        if not isinstance(remediation, dict) or not isinstance(remediation.get("files"), list):
            raise ValueError("--remediation-records has no `files` array: is it the output of `records`?")
        for block in remediation["files"]:
            if isinstance(block, dict) and _norm_path(block.get("file_path")):
                scanned += 1
                blocks.setdefault(_norm_path(block["file_path"]), []).extend(
                    r for r in block.get("exports") or [] if isinstance(r, dict))
    unresolved = []
    for g in to_scan:
        files_scanned, found = g.match(blocks)
        if g.record is not None:
            continue
        if not g.blocking and g.entry.get("category") in DOCUMENT_CATEGORIES:
            g.outcome = "unknown"
            continue
        unresolved.append({"gap_id": g.entry.get("gap_id"), "name": g.name, "severity": g.entry.get("severity"),
                           "remediation_paths": g.entry.get("remediation_paths") or [],
                           "rejected_paths": g.entry.get("rejected_paths") or [],
                           "files_scanned": files_scanned, "exports_found_in_scan": found})
    if unresolved:
        return None, {"status": "unresolved", "unresolved": unresolved, "warnings": warnings}
    needs = [{"gap_id": g.entry.get("gap_id"), "name": g.name, "needs": g.needs(),
              "file": _location(g.new_location())[0] if g.outcome != "verified" else g.recorded[0],
              "line": _location(g.new_location())[1] if g.outcome != "verified" else g.recorded[1]}
             for g in routed if g.needs()]
    if needs:
        return None, {"status": "needs-judgment", "needs_judgment": needs, "warnings": warnings}
    kept: dict[str, list[dict]] = {}
    for g in routed:
        if g.record is not None and not g.internal:
            record = dict(g.record)
            record.pop("public", None)  # a repair documents and maps every record: the mark is a normal update's
            if g.answers.get("docstring") is not None:
                record["docstring"] = g.answers["docstring"]
            if record not in kept.setdefault(g.record_path, []):
                kept[g.record_path].append(record)
    breakdown = {"T1": 0, "T1-low": 0, "unlabeled": 0, "T2": 0}
    provenance_entries = _entries_of(provenance)
    for g in routed:
        breakdown[g.label(provenance_entries)] += 1
    breakdown["unlabeled"] += len(forwarded)
    records = {
        "mode": "gap-driven",
        "files_extracted": scanned,
        "exports_extracted": len(entries),
        "confidence_breakdown": breakdown,
        "verification": [g.verification() for g in routed],
        "files": [{"file_path": path, "exports": exports} for path, exports in kept.items()],
    }
    matched = [g for g in to_scan if g.record is not None]
    targeted = {"resolved_count": len(matched), "files_scanned": scanned,
                "exports_matched": len({(g.record_path, _name_of(g.record)) for g in matched}),
                "tier": tier} if to_scan else None
    summary = {
        "status": "written",
        "gap_count": len(entries),
        "files_extracted": scanned,
        "exports_extracted": len(entries),
        "confidence_breakdown": breakdown,
        "counts": {**{outcome: sum(1 for g in routed if g.outcome == outcome and not g.internal)
                      for outcome in OUTCOMES}, "reclassified": sum(1 for g in routed if g.internal)},
        "reclassified": [g.name for g in routed if g.internal],
        "forwarded": forwarded,
        "targeted_reextraction": targeted,
        "warnings": warnings,
    }
    return records, summary


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
    for path, value in ((args.not_public_out, summary["not_public"]), (args.output, doc)):
        try:
            if path:
                _write_json_atomic(Path(path), value)
        except OSError as exc:
            print(f"error: cannot write {path}: {exc}", file=sys.stderr)
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


def _cmd_gap_records(args: argparse.Namespace) -> int:
    try:
        if args.plan and args.output:
            raise ValueError("--plan writes no records: drop -o")
        if not args.plan and not args.output:
            raise ValueError("-o is required without --plan")
        if args.files_out and not args.plan:
            raise ValueError("--files-out goes with --plan")
        if bool(args.evidence) != bool(args.tier):
            raise ValueError("--evidence and --tier go together")
        judgments = _gap_judgments(_load_json_file(Path(args.judgments), "--judgments file")) \
            if args.judgments else {}
        records, summary = gap_records(
            _load_json_file(Path(args.manifest), "--manifest file"),
            _load_json_file(Path(args.provenance_map), "--provenance-map file"),
            source_root=Path(args.source_root) if args.source_root else None,
            drift_status=args.drift_status,
            judgments=judgments,
            remediation=_optional_json(args.remediation_records, "--remediation-records file"),
            plan=args.plan,
            tier=args.tier,
        )
        if summary["status"] == "planned" and args.files_out:
            _write_json_atomic(Path(args.files_out), summary["reextract"]["files"])
        if records is not None:
            _write_json_atomic(Path(args.output), records)
            summary = {"status": summary["status"], "output": args.output,
                       **{k: v for k, v in summary.items() if k != "status"}}
            if args.evidence and summary["targeted_reextraction"] is not None:
                with open(args.evidence, "a", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps({"targeted_reextraction": summary["targeted_reextraction"]}) + "\n")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot write: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


# --------------------------------------------------------------------------
# Baseline gaps (update-skill detect-changes Category B)
# --------------------------------------------------------------------------


VERIFIER_FILE = "skf-verify-provenance-completeness.py"


def _baseline_verifier():
    """The verifier beside this script, for its `baseline_gaps`. Unlike `_verifier()`, which lets a gap-driven
    spot-check go on as unknown, one that cannot be loaded (or has no `baseline_gaps`) is a ValueError: with no
    verifier no gap is listed, and every name the runner leaves out would read as a deleted export."""
    path = Path(__file__).resolve().parent / VERIFIER_FILE
    where = f"cannot load {VERIFIER_FILE} beside {Path(__file__).name}"
    try:
        spec = importlib.util.spec_from_file_location("skf_verify_provenance_completeness_baseline", path)
        if spec is None or spec.loader is None or not path.is_file():
            raise ImportError(f"no file at {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:  # whatever the script raises, the call reports it
        raise ValueError(f"{where}: {exc}; re-install SKF") from exc
    if not callable(getattr(module, "baseline_gaps", None)):
        raise ValueError(f"{where}: it has no baseline_gaps; re-install SKF")
    return module


def baseline_gaps(provenance: dict, extraction: dict, files: list, source_root: Path, verifier) -> dict:
    """{"gaps", "unchecked"}: the map entries of `files` the runner's `extraction` lacks whose file still declares
    them (see "Baseline gaps" in the module docstring)."""
    if not isinstance(extraction, dict):
        raise ValueError("--extraction file has no `exports` array: is it the helper's output?")
    held = {(name, file) for e in _exports_of(extraction, "--extraction file")
            if (name := _name_of(e)) is not None and (file := _file_of(e)) is not None}
    diff = extraction.get("entry_point_diff")
    listed = {(item["name"], _norm_path(item["file"]))
              for item in (diff.get("extraction_gaps") or [] if isinstance(diff, dict) else [])
              if isinstance(item, dict) and isinstance(item.get("name"), str) and _norm_path(item.get("file"))}
    if provenance.get("entries") is not None and not isinstance(provenance["entries"], list):
        raise ValueError("provenance `entries` must be an array")  # missing or null: no entry (#684)
    wanted = {f for f in (_norm_path(p) for p in files) if f is not None}
    gaps, unchecked = verifier.baseline_gaps(provenance, source_root, held, wanted, listed)
    return {"gaps": gaps, "unchecked": unchecked}


def _cmd_baseline_gaps(args: argparse.Namespace) -> int:
    try:
        source_root = Path(args.source_root)
        if not source_root.is_dir():
            raise ValueError(f"--source-root {args.source_root} is not a folder")
        files = _load_json_file(Path(args.files), "--files file")
        if not (isinstance(files, list) and all(isinstance(f, str) for f in files)):
            raise ValueError(f"--files file {args.files} must hold a JSON array of paths")
        provenance = _load_json_file(Path(args.provenance_map), "--provenance-map file")
        if not isinstance(provenance, dict):
            raise ValueError(f"--provenance-map file {args.provenance_map} must hold a JSON object")
        extraction = _load_json_file(Path(args.extraction), "--extraction file")
        result = baseline_gaps(provenance, extraction, files, source_root, _baseline_verifier())
        _write_json_atomic(Path(args.output), result)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "written", "output": args.output, "gaps": len(result["gaps"]),
                      "unchecked": len(result["unchecked"])}))
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
    p_apply.add_argument("--not-public-out", metavar="FILE",
                         help="also write the summary's not_public list here (a JSON array)")
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

    p_gap = sub.add_parser("gap-records", help="spot-check, route and record a gap-driven repair's manifest entries")
    p_gap.add_argument("--manifest", required=True, metavar="FILE", help="skf-parse-gaps.py translate's manifest")
    p_gap.add_argument("--provenance-map", required=True, metavar="FILE", help="the map the repair starts from")
    p_gap.add_argument("--source-root", metavar="DIR", help="the source tree the spot-checks read")
    p_gap.add_argument("--drift-status", choices=DRIFT_STATUSES, default="ok",
                       help="the workspace drift check's status; overridden runs the drift gate")
    p_gap.add_argument("--judgments", metavar="FILE", help="the answers to its needs_judgment[], keyed by gap id")
    p_gap.add_argument("--remediation-records", metavar="FILE",
                       help="`records` output over the files targeted re-extraction scanned")
    p_gap.add_argument("--plan", action="store_true",
                       help="print the answers it needs and the files targeted re-extraction scans; write no records")
    p_gap.add_argument("--files-out", metavar="FILE", help="with --plan: write those files here, a JSON array")
    p_gap.add_argument("--evidence", metavar="FILE",
                       help="append the targeted_reextraction record to this JSON-lines file when it ran")
    p_gap.add_argument("--tier", help="with --evidence: the forge tier the record names")
    p_gap.add_argument("-o", "--output", metavar="FILE", help="where to write the records (without --plan)")
    p_gap.set_defaults(func=_cmd_gap_records)

    p_base = sub.add_parser("baseline-gaps", help="list the map entries the runner left out that their modified "
                                                  "file still declares, for Category B's step 2 to read")
    p_base.add_argument("--provenance-map", required=True, metavar="FILE", help="the map the update starts from")
    p_base.add_argument("--extraction", required=True, metavar="FILE",
                        help="the recipe runner's output ({\"exports\": []} when it could not run)")
    p_base.add_argument("--files", required=True, metavar="FILE",
                        help="the files whose entries are checked: Category A's modified-files.json")
    p_base.add_argument("--source-root", required=True, metavar="DIR", help="the source tree the files are read in")
    p_base.add_argument("-o", "--output", required=True, metavar="FILE", help="where to write the gaps")
    p_base.set_defaults(func=_cmd_baseline_gaps)

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
