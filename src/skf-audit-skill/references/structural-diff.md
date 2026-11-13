---
nextStepFile: 'semantic-diff.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
extractionSnapshotProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extraction-snapshot.py'
  - '{project-root}/src/shared/scripts/skf-extraction-snapshot.py'
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
compareFileHashesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-compare-file-hashes.py'
  - '{project-root}/src/shared/scripts/skf-compare-file-hashes.py'
structuralDiffProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-structural-diff.py'
  - '{project-root}/src/shared/scripts/skf-structural-diff.py'
renderDriftTablesScript: 'scripts/render-drift-tables.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Structural Diff

## STEP GOAL:

Compare the provenance map create-skill wrote with step 2's re-index snapshot: added, removed, moved and changed exports with file:line citations and confidence labels, then script and asset drift.

## Rules

- Focus only on structural comparison — added/removed/changed exports
- Do not classify severity (Step 05) or suggest remediation (Step 06)
- Save each helper's JSON in `{auditDataFolder}`: step 5 classifies those files, not the tables this step renders, and §5 renders the tables from them
- `{is_stack_skill}` is the `is_stack_skill` value step 1 §6 wrote into {outputFile}'s frontmatter: read it there, not from memory, so a compacted session still diffs a stack library by library
- `{legacy_stack_provenance}` is the `legacy_stack_provenance` value step 1 §6 wrote into {outputFile}'s frontmatter: read it there, not from memory, so a compacted session still diffs a v1 stack's exports as one list

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. When `{source_tree}` is set (the [C] of `upstream-checkout.md`), first run `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}`, with `{sourceTreeHelper}` resolved from `{sourceTreeProbeOrder}` when it is not bound, and go on whatever it prints. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, then run:

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

For a stack skill with v2 provenance, add `--group-by source_library` (see Stack-Specific Structural Diff): `{is_stack_skill}` true and `{legacy_stack_provenance}` false.

With `-o` the helper saves the diff to the file and prints one line, `{"status": "ok", "output": ..., "summary": {...}}`. Exit `0` (no export added, removed, changed or moved) and exit `1` (differences found) both saved it. Exit `2` saved nothing; act on its `error`:

- It names `{extractionSnapshot}` (unreadable, not JSON, or, with `--group-by`, no export with a `source_library`): step 2 wrote that file, so fix it as re-index §3 describes and run the command again.
- It starts `Cannot write output`: HALT with **exit 4**, `halt_reason: "write-failed"`, phase `structural-diff:diff`, `"path": "{auditDataFolder}/structural-diff.json"`.
- Otherwise it names `{provenanceMap}`, which step 1 §4 read: HALT with **exit 3**, `halt_reason: "provenance-invalid"`, phase `structural-diff:diff`, `"path": "{provenanceMap}"`, showing the `error`.

The saved diff holds every set §5 renders. This step reads three of its fields itself: §1b reads `summary.removed` and the `name` of each `removed[]` entry (an export in the provenance map but not in the snapshot), and §6 records `applied_transforms` (each transform the helper applied, with its count) in the drift report's frontmatter for step 6's Provenance table.

### 1b. Find Relocated Exports (Forge+ and Deep with ccc)

**Run only when** the tier is Forge+ or Deep, `tools.ccc` is true in forge-tier.yaml, and the saved diff's `summary.removed` is above 0. Otherwise skip this section silently.

An export moved to a file outside the bounded scan list is missing from the snapshot, so the diff reports it as removed, which step 5 grades CRITICAL. Look for each `removed[]` entry of `{auditDataFolder}/structural-diff.json` elsewhere in the source. Resolve `{extractPublicApiHelper}` and `{extractionSnapshotHelper}` from their probe orders, then, from `{project-root}`, list the files that hold a removed name, less the scan list step 2 wrote:

```bash
uv run {extractionSnapshotHelper} relocation-candidates --diff "{auditDataFolder}/structural-diff.json" --source-root "{source_root}" --scan-list "{auditDataFolder}/scan-files.json" -o "{auditDataFolder}/relocation-candidates.json"
```

Add `--ccc` unless `{source_tree}` is set: the helper then searches each name with `ccc search` over the index of `{source_root}`. When `{source_tree}` is set, `{source_root}` is the private tree the [C] of `upstream-checkout.md` read, which has no ccc index, so the helper lists the files that hold a name as a word with one `git grep` there. It writes the candidates relative to `{source_root}` and prints `candidates`, their count: 0 skips the rest of this section. An `error` that starts `cannot run ccc` while the `/ccc` skill (Claude Code) or the ccc MCP server (Cursor) can search: search each removed name with it and write the files it returns, relative to `{source_root}` with forward slashes, as one JSON list in `{auditDataFolder}/relocation-candidates.json` (`relocate` adds nothing from a scan-list file). Then run the recipes over the candidates and add what they find to the snapshot:

```bash
rm -f "{auditDataFolder}/relocations.json"
uv run {extractPublicApiHelper} --mode full --source-root "{source_root}" --files-from "{auditDataFolder}/relocation-candidates.json" --head-cap 0 -o "{auditDataFolder}/relocations.json"
uv run {extractionSnapshotHelper} relocate "{extractionSnapshot}" --diff "{auditDataFolder}/structural-diff.json" --extraction "{auditDataFolder}/relocations.json"
```

`relocate` adds each export the runner found under a removed name in a file outside the bounded scan list (with the removed entry's `source_library` for a stack), recounts the snapshot and prints `added`: never edit the snapshot by hand.

When `added` is above 0, run §1's command again with the same arguments and the same `-o`, acting on its exit code as §1 does. The helper pairs each relocation with its removed entry as a move (or, when the name occurs more than once, lists it under `ambiguous_names[]`). A removed export the runner finds nowhere else stays removed. When ccc cannot search (no index for `{source_root}`, or the command fails), `relocation-candidates` prints any other `error`, the runner writes no JSON, or `relocate` prints an `error`, skip the rest of this section and note `ccc relocation check skipped: {reason}` on the **Method:** line (§5).

### 4b. Detect Script/Asset Drift

**Only execute if provenance-map.json contains `file_entries`.**

**Resolve `{compareFileHashesHelper}`** from `{compareFileHashesProbeOrder}`; first existing path wins. Run one comparison of the tracked `file_entries[]` and the untracked scripts, assets and `docs/authoritative/` files the brief's scope takes; pass `--brief` only when `{forge_data_folder}/{skill_name}/skill-brief.yaml` exists:

```bash
uv run {compareFileHashesHelper} compare "{provenanceMap}" "{source_root}" \
    [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] > "{auditDataFolder}/file-drift.json"
```

The saved JSON, which step 5 builds its Script/Asset findings from:

```
{
  "added":   ["<rel-path>", ...],   // a script or an asset to the detector, or a docs/authoritative/ file, on disk, in the brief's scope, NOT in file_entries
  "added_not_checked": null,        // or why no new file was looked for: "no skill brief", the brief's error, or a helper it cannot load
  "removed": ["<rel-path>", ...],   // in file_entries, missing on disk
  "changed": [{"path": "...", "stored_hash": "sha256:...", "current_hash": "sha256:..."}],
  "stats":   {"added": N, "removed": N, "changed": N, "unchanged": N}
}
```

**When `added_not_checked` is not null** (`no skill brief` without `--brief`, the error of a brief the helper could not read, or `cannot load ... re-install SKF` when a helper beside it could not be loaded), no new file was looked for, so `added` is empty, while the tracked files were still compared: §5's renderer prints the reason under the Script/Asset Drift table. Record it for the envelope too: write `new_files_not_checked: {added_not_checked}` to `{run_dir}/warning.txt` with a file write (the reason can hold quotes), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`.

**When no candidate resolves, or the command exits non-zero** (delete the file then), skip the check with a `### Script/Asset Drift: skipped ({the reason})` note: it is supplementary to the export diff, so it never halts the audit.

### Stack-Specific Structural Diff

If `{is_stack_skill}` is true:

**A code-mode stack (v2 provenance, per-export entries with `source_library`):** step 2 re-indexed it from the project root step 1 §5 bound.
- §1 runs with `--group-by source_library`: the helper diffs each library on its own and tags every listed item with its `source_library`
- §5's renderer adds a By Library table, each library's counts from `groups[]` (the top-level `summary` sums them)

A compose-mode stack never reaches this step: step 1 sends it to step 1c (`constituent-freshness.md`), which checks its constituents' freshness instead.

### 5. Compile Structural Drift Section

Render the section's tables from the saved files, never by hand: a hand copy of hundreds of rows drops or mis-matches them as a hand diff would. `{renderDriftTablesScript}` resolves relative to the skill root; from `{project-root}`, run:

```bash
uv run {renderDriftTablesScript} structural "{auditDataFolder}/structural-diff.json" --file-drift "{auditDataFolder}/file-drift.json"
```

It prints the section's tables (`--help` lists them). Among them, a **Provenance label differences (not drift)** table comes only when `label_changes[]` is non-empty and an **Off the public surface:** note under the Summary only when `summary.not_public` is above 0, neither counted in Total Drift Items. A rollup changes no count: the headings and the summary come from the JSON.

Append to {outputFile}:

```markdown
## Structural Drift

**Comparison:** Provenance map ({provenance_date}) vs Current scan ({scan_date})
**Method:** {Quick: text-diff / Forge, Forge+ or Deep: AST structural}. Labels follow the tool that ran: T1 for an ast-grep match, T1-low for an export read by eye{; AST fallback files: {ast_fallback_files}, when any}{; ccc relocation check skipped: {reason}, when §1b skipped it}

{what the command printed, unchanged}
```

When §4b skipped its check and the printed tables hold no Script/Asset Drift heading, add its `### Script/Asset Drift: skipped ({the reason})` note after them. When the command exits non-zero, its JSON `error`, else its first stderr line, says what it could not read: write `Structural drift tables not rendered: {error}` in place of its output and go on, since step 5 classifies the saved diff, not these tables.

### 6. Update Report and Auto-Proceed

Update {outputFile} frontmatter: append `'structural-diff'` to `stepsCompleted` and set `applied_transforms` to the saved diff's `applied_transforms` (an empty list when none fired). Once the ## Structural Drift section has been appended, load, read fully, and execute `{nextStepFile}` (semantic diff).

