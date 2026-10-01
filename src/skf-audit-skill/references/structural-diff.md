---
nextStepFile: 'semantic-diff.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
# This run's stage data folder, beside its drift report: step 5 classifies the
# JSON saved here. The `.skf-` name keeps the version folder SKF's own.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
# §1b: the recipe runner, and the snapshot helper that adds its finds.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
extractionSnapshotProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extraction-snapshot.py'
  - '{project-root}/src/shared/scripts/skf-extraction-snapshot.py'
# Every HALT after step 1 §5b's [C] closes the private tree with it.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
compareFileHashesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-compare-file-hashes.py'
  - '{project-root}/src/shared/scripts/skf-compare-file-hashes.py'
structuralDiffProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-structural-diff.py'
  - '{project-root}/src/shared/scripts/skf-structural-diff.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Structural Diff

## STEP GOAL:

Compare the provenance map create-skill wrote with step 2's re-index snapshot: added, removed, moved and changed exports with file:line citations and confidence labels, then script and asset drift.

## Rules

- Focus only on structural comparison — added/removed/changed exports
- Do not classify severity (Step 05) or suggest remediation (Step 06)
- Save each helper's JSON in `{auditDataFolder}`: step 5 classifies those files, not the tables this step renders

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. When `{source_tree}` is set (step 1 §5b's [C]), first run `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` and go on whatever it prints. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Run the Deterministic Export Diff

One helper call compares the two export lists. Never diff them by hand: a hand diff of hundreds of exports drops or mis-matches entries, which this skill's zero-hallucination contract forbids.

**Resolve `{structuralDiffHelper}`** from `{structuralDiffProbeOrder}`; first existing path wins (SKILL.md On Activation checked that one exists).

Compare the baseline provenance map (`{provenanceMap}`, step 1 §1) with the extraction snapshot (`{extractionSnapshot}`, step 2 §3), and save the diff in `{auditDataFolder}` (create the folder first: `mkdir -p "{auditDataFolder}"`):

```bash
uv run {structuralDiffHelper} "{provenanceMap}" "{extractionSnapshot}" -o "{auditDataFolder}/structural-diff.json"
```

For a stack skill with v2 provenance, add `--group-by source_library` (see Stack-Specific Structural Diff).

With `-o` the helper saves the diff to the file and prints one line, `{"status": "ok", "output": ..., "summary": {...}}`. Exit `0` (no export added, removed, changed or moved) and exit `1` (differences found) both saved it. Exit `2` saved nothing; act on its `error`:

- It names `{extractionSnapshot}` (unreadable, not JSON, or, with `--group-by`, no export with a `source_library`): step 2 wrote that file, so fix it as re-index §3 describes and run the command again.
- It starts `Cannot write output`: HALT with **exit 4**, `halt_reason: "write-failed"`, phase `structural-diff:diff`, `"path": "{auditDataFolder}/structural-diff.json"`.
- Otherwise it names `{provenanceMap}`, which step 1 §4 read: HALT with **exit 3**, `halt_reason: "provenance-invalid"`, phase `structural-diff:diff`, `"path": "{provenanceMap}"`, showing the `error`.

The helper canonicalizes both sides before it matches each export by its name and its file (the quote style of string defaults, stdlib module prefixes, and a renamed public re-export resolved through the re-export map it derives from the provenance map), so a cosmetic extractor difference never reads as drift. It records each transform it applied in `applied_transforms`, and takes `--reexport-map {file}` only to override the derived map.

Read the saved diff from the file:

```
{
  "summary": {"added": N, "removed": N, "changed": N, "moved": N, "unchanged": N, "label_changes": N, "ambiguous_names": N, "signature_unverified": N},
  "added":   [ <entry>, ... ],   // in current snapshot, NOT in provenance map
  "removed": [ <entry>, ... ],   // in provenance map, NOT in current snapshot
  "changed": [ {"name", "field", "baseline_value", "current_value", "file", "line", "confidence"}, ... ],   // field: type | signature | params | return_type | line
  "moved":   [ {"name", "previous_file", "current_file", "previous_line", "line", "confidence"}, ... ],
  "ambiguous_names": [ {"name", "removed": [{"file", "line"}], "added": [{"file", "line"}]}, ... ],
  "label_changes": [ {"name", "file", "baseline": {"confidence", "extraction_method"}, "current": {"confidence", "extraction_method"}}, ... ],   // informational, not drift
  "signature_unverified": [ {"name", "file", "baseline", "current"}, ... ],
  "unchanged_count": N,
  "applied_transforms": [ {"transform": "quote-style|stdlib-prefix|reexport-resolution", "count": N}, ... ]
}
```

An `<entry>` in `added[]` or `removed[]` holds `name`, `type`, `signature`, `params`, `return_type`, `file`, `line`, `confidence` and `extraction_method`. With `--group-by`, every listed item also carries its `source_library`, and `groups[]` gives each library's `summary`.

§6 records `applied_transforms` in the drift report's frontmatter for step 6's Provenance table.

### 1b. Find Relocated Exports (Forge+ and Deep with ccc)

**Run only when** the tier is Forge+ or Deep, `tools.ccc` is true in forge-tier.yaml, and the saved diff's `summary.removed` is above 0. Otherwise skip this section silently.

An export moved to a file outside the bounded scan list is missing from the snapshot, so the diff reports it as removed, which step 5 grades CRITICAL. Look for each `removed[]` entry of `{auditDataFolder}/structural-diff.json` elsewhere in the source:

1. Search for its name: `cd {source_root} && ccc search --limit 5 "{name}"` (CLI), the `/ccc` skill (Claude Code) or the ccc MCP server (Cursor). `ccc search` reads the index of the current working directory (`knowledge/ccc-bridge.md` gives its flags). When `{source_tree}` is set, `{source_root}` is step 1 §5b's private tree, which has no ccc index: list the files of the tree that hold the name as a word instead, with `git -C "{source_root}" grep -l -w -F -e "{name}"`, and take them as the candidates.
2. Drop each candidate file on `{bounded_scan_files}`: step 2 extracted those files, so the diff already saw their exports.
3. Write the remaining candidates of every name, relative to `{source_root}` with forward slashes, as one JSON list in `{auditDataFolder}/relocation-candidates.json`. Resolve `{extractPublicApiHelper}` and `{extractionSnapshotHelper}` from their probe orders, then, from `{project-root}`, run the recipes over the candidates and add what they find to the snapshot:

   ```bash
   rm -f "{auditDataFolder}/relocations.json"
   uv run {extractPublicApiHelper} --mode full --source-root "{source_root}" --files-from "{auditDataFolder}/relocation-candidates.json" --head-cap 0 -o "{auditDataFolder}/relocations.json"
   uv run {extractionSnapshotHelper} relocate "{extractionSnapshot}" --diff "{auditDataFolder}/structural-diff.json" --extraction "{auditDataFolder}/relocations.json"
   ```

   `relocate` adds each export the runner found under a removed name in a file outside the bounded scan list (with the removed entry's `source_library` for a stack), recounts the snapshot and prints `added`: never edit the snapshot by hand.

When `added` is above 0, run §1's command again with the same arguments and the same `-o`, acting on its exit code as §1 does. The helper pairs each relocation with its removed entry as a move (or, when the name occurs more than once, lists it under `ambiguous_names[]`). A removed export the runner finds nowhere else stays removed. When ccc cannot search (no index for `{source_root}`, or the command fails), the runner writes no JSON, or `relocate` prints an `error`, skip the rest of this section and note `ccc relocation check skipped: {reason}` on the **Method:** line (§5).

### 2. Read Added / Removed / Moved from the Diff

These sets come straight from the saved diff, never from set arithmetic of your own:

- **Added** (`added[]`): exports in the current snapshot but not the provenance map.
- **Removed** (`removed[]`): exports in the provenance map but not the current snapshot.
- **Moved** (`moved[]`): matched exports whose file path changed (`previous_file` → `current_file`). A move is **not** a removal.
- **Ambiguous names** (`ambiguous_names[]`): a name left on both sides that occurs more than once on a side (a `GET` handler in several route files, for example), so the helper paired none of its entries. They stay in `removed[]` and `added[]`, and the item lists the `{file, line}` of each. §5 shows them in their own table, and step 5 judges whether a removed and an added entry of one name are one export that moved.

Each entry's confidence tier is the `confidence` the extractor recorded: T1 for an ast-grep match, T1-low for an export read by eye.

### 3. Read Changed Exports from the Diff

`changed[]` lists per-field differences for exports present in BOTH sets: the `field` that changed, its `baseline_value` → `current_value`, and the export's current `file`, `line` and `confidence`. Group items by export name and file when compiling the report, and pair with the export's `moved[]` entry (if any) to describe location changes. The Confidence column of Changed Exports (§5) is the item's `confidence`.

`summary.signature_unverified` counts the matched exports whose signature the helper could not compare: one side holds it as `params` and `return_type`, the other as `signature` text, so a change there cannot be seen. They are not drift, and §5 states the count, so an empty Changed Exports table does not read as checked signatures.

### 3b. Read Provenance Label Differences from the Diff

`label_changes[]` lists exports present in BOTH sets whose `confidence` or `extraction_method` differs between the provenance map and the snapshot, with each side's labels. A label names the tool that extracted the export, not what the source says, so a label difference is not drift: it never appears in Changed Exports, is not counted in Total Drift Items, and step 5 does not classify it. §5 renders it as an informational table. Take the count from `summary.label_changes`, no recount (for a stack it sums the libraries, and each row carries its `source_library`).

### 4b. Detect Script/Asset Drift

**Only execute if provenance-map.json contains `file_entries`.**

**Resolve `{compareFileHashesHelper}`** from `{compareFileHashesProbeOrder}`; first existing path wins. Run one comparison: it hashes the tracked `file_entries[]` and, the other way round, the files of the standard script, asset and doc folders of the source tree:

```bash
uv run {compareFileHashesHelper} compare "{provenanceMap}" "{source_root}" > "{auditDataFolder}/file-drift.json"
```

The saved JSON, which step 5 builds its Script/Asset findings from:

```
{
  "added":   ["<rel-path>", ...],   // present on disk in tracked dirs, NOT in file_entries
  "removed": ["<rel-path>", ...],   // in file_entries, missing on disk
  "changed": [{"path": "...", "stored_hash": "sha256:...", "current_hash": "sha256:..."}],
  "stats":   {"added": N, "removed": N, "changed": N, "unchanged": N}
}
```

Append the three lists into the Structural Drift section under a `### Script/Asset Drift (added {stats.added}, removed {stats.removed}, changed {stats.changed})` heading, each count straight from `stats`.

**When no candidate resolves, or the command exits non-zero** (delete the file then), skip the check with a `### Script/Asset Drift: skipped ({the reason})` note: it is supplementary to the export diff, so it never halts the audit.

### Stack-Specific Structural Diff

If `{is_stack_skill}` is true:

**A code-mode stack (v2 provenance, per-export entries with `source_library`):** step 2 re-indexed it from the project root step 1 §5 bound.
- §1 runs with `--group-by source_library`: the helper diffs each library on its own and tags every listed item with its `source_library`
- Report per-library diff results, taking each library's counts from `groups[]` (the top-level `summary` sums them)

A compose-mode stack never reaches this step: step 1 sends it to step 1c (`constituent-freshness.md`), which checks its constituents' freshness instead.

### 5. Compile Structural Drift Section

**Rollup for high-volume uniform findings.** When ≥ 10 findings in the same table share one root cause (deleted source file, renamed module, entire package tree removed), you may collapse them into one row per root cause. Rollup rows replace the per-symbol `Export`/`Signature` columns with `Count` and `Representative symbols` (up to 3 names, `…` if more). Rollup applies to the **Added Exports**, **Removed Exports** and **Script/Asset Drift** tables, never to Changed Exports, whose rows differ by construction. A rollup only changes how the table reads: step 5 classifies the saved diff, one finding per export, so a rollup changes no count and no grade.

**Rollup row form (Added / Removed Exports):**

| Root Cause | Count | Representative symbols | Location | Confidence |
|------------|-------|------------------------|----------|------------|
| {deleted/renamed path or similar} | {N} | `{sym1}`, `{sym2}`, `{sym3}`, … | {root-cause path} | {T1/T1-low} |

**Rollup for the Provenance label differences table.** When ≥ 10 rows share one baseline label and one current label (case-insensitively), you may collapse them into one row whose Export cell reads {count} exports (rep: `{sym1}`, `{sym2}`, `{sym3}`, …).

Append to {outputFile}, with the Script/Asset Drift subsection (§4b) after the Summary:

```markdown
## Structural Drift

**Comparison:** Provenance map ({provenance_date}) vs Current scan ({scan_date})
**Method:** {Quick: text-diff / Forge, Forge+ or Deep: AST structural}. Labels follow the tool that ran: T1 for an ast-grep match, T1-low for an export read by eye{; AST fallback files: {ast_fallback_files}, when any}{; ccc relocation check skipped: {reason}, when §1b skipped it}

### Added Exports ({count})

| Export | Type | Signature | Location | Confidence |
|--------|------|-----------|----------|------------|
| {name} | {type} | {signature} | {file}:{line} | {T1/T1-low} |

### Removed Exports ({count})

| Export | Type | Original Signature | Original Location | Confidence |
|--------|------|-------------------|-------------------|------------|
| {name} | {type} | {signature} | {file}:{line} | {T1/T1-low} |

### Moved Exports ({count})

| Export | From | To | Confidence |
|--------|------|----|------------|
| {name} | {previous_file}:{previous_line} | {current_file}:{line} | {T1/T1-low} |

### Changed Exports ({count})

| Export | Change Type | Before | After | Location | Confidence |
|--------|------------|--------|-------|----------|------------|
| {name} | {signature/type/location} | {old} | {new} | {file}:{line} | {T1/T1-low} |

### Ambiguous Names ({count})

| Export | Removed At | Added At |
|--------|------------|----------|
| {name} | {file}:{line}, one per removed entry | {file}:{line}, one per added entry |

### Summary

| Category | Count |
|----------|-------|
| Added | {added_count} |
| Removed | {removed_count} |
| Moved | {moved_count} |
| Changed | {changed_count} |
| **Total Drift Items** | {total} |

**Signatures not compared:** {signature_unverified_count} matched exports hold their signature in different fields on the two sides (§3), so a change there cannot be seen.

### Provenance label differences (not drift) ({label_changes_count})

These rows are informational: a label names the tool that extracted the export, so they are excluded from Total Drift Items and are not findings.

| Export | Baseline label | Current label |
|--------|----------------|---------------|
| {name} | {baseline.confidence} / {baseline.extraction_method} | {current.confidence} / {current.extraction_method} |
```

Take every count from the saved diff's `summary` (`{total}` is added, removed, moved and changed together). Include the **Ambiguous Names** subsection only when `ambiguous_names[]` is non-empty, and the **Signatures not compared** line only when `summary.signature_unverified` is above 0. Include the **Provenance label differences (not drift)** subsection only when `label_changes[]` is non-empty; take `{label_changes_count}` from `summary.label_changes` (summed across libraries for a stack, §3b). Write `(none)` for a label the helper emits as null. For a stack, write each Export cell as `{library}: {name}`.

### 6. Update Report and Auto-Proceed

Update {outputFile} frontmatter: append `'structural-diff'` to `stepsCompleted` and set `applied_transforms` to the saved diff's `applied_transforms` (an empty list when none fired). Once the ## Structural Drift section has been appended, load, read fully, and execute `{nextStepFile}` (semantic diff).

