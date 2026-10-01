---
nextStepFile: 'semantic-diff.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
# This run's stage data folder, beside its drift report: step 5 classifies the
# JSON saved here. The `.skf-` name keeps the version folder SKF's own for
# drop-skill and rename-skill, which read any other new name there as a file
# SKF did not write.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
# §1b verifies a relocated export with the recipes step 2 runs.
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
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

Compare the original provenance map extractions from create-skill against the current re-index snapshot from Step 02 to detect structural drift. Identify added, removed, moved and changed exports with file:line citations and confidence tier labels, then script and asset drift.

## Rules

- Focus only on structural comparison — added/removed/changed exports
- Do not classify severity (Step 05) or suggest remediation (Step 06)
- Use subprocess Pattern 4 (parallel) when available; if unavailable, compare sequentially
- Save each helper's JSON in `{auditDataFolder}`: step 5 classifies those files, not the tables this step renders

## MANDATORY SEQUENCE

### 1. Run the Deterministic Export Diff

The export comparison — canonicalization, set arithmetic (added/removed/moved), and field-level change detection — is fully deterministic and runs in one subprocess. Do **not** diff the two export lists by hand: an LLM comparing dozens or hundreds of exports can silently drop or mis-match entries, which violates this skill's zero-hallucination contract.

**Resolve `{structuralDiffHelper}`** from `{structuralDiffProbeOrder}`; first existing path wins. HALT if no candidate exists.

Run one comparison over the baseline provenance map (`{provenanceMap}`, bound in step 1 §1) and the current extraction snapshot (`{extractionSnapshot}`, written to disk by step 2 §3), and save it in `{auditDataFolder}` (create the folder first: `mkdir -p "{auditDataFolder}"`):

```bash
uv run {structuralDiffHelper} "{provenanceMap}" "{extractionSnapshot}" -o "{auditDataFolder}/structural-diff.json"
```

For a stack skill with v2 provenance, add `--group-by source_library` (see Stack-Specific Structural Diff).

With `-o` the helper saves the diff to the file and prints one line, `{"status": "ok", "output": ..., "summary": {...}}`. Exit `0` (no export added, removed, changed or moved) and exit `1` (differences found) both saved it. Exit `2` saved nothing; act on its `error`:

- It names `{extractionSnapshot}` (unreadable, not JSON, or, with `--group-by`, no export with a `source_library`): step 2 wrote that file, so fix it as re-index §3 describes and run the command again.
- It starts `Cannot write output`: HALT with **exit 4**, `halt_reason: "write-failed"`. When `{headless_mode}`, emit the error envelope on **stderr** (shape per SKILL.md → Result Contract).
- Otherwise it names `{provenanceMap}`, which step 1 §4 read: HALT as step 1 §4 does for a map it cannot read, showing the `error`.

The helper reads both shapes directly — the provenance map's `entries[]` (with `export_name`/`export_type`/`source_file`/`source_line`) and the snapshot's `exports[]` — and aliases the field names, so no manual projection is needed.

**Canonicalization is applied inside the helper, symmetrically to both sides**, before it matches each export by its name and its file together, so cosmetic extractor differences do not surface as false-positive "Changed"/"Removed"/"Added" entries:

- **Quote style on string defaults**: `kind: str = "Hnsw"` ↔ `kind: str = 'Hnsw'`.
- **Stdlib module qualification**: `typing.Optional[...]` → `Optional[...]`, `dataclasses.field(...)` → `field(...)` (user-defined namespaces are never collapsed).
- **Public-API re-export resolution**: a renamed public re-export (`_Impl` → `Public`) matches the baseline entry instead of splitting into "Removed `_Impl`" + "Added `Public`". The re-export map is **auto-derived from the provenance map** (identical to the `reexport_map` that `skf-load-provenance.py normalize` returns in step 1 §4). Pass `--reexport-map {file}` only to override with a custom map.

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

An `<entry>` in `added[]` or `removed[]` is the helper's normalized record, whichever input shape it came from: `name`, `type`, `signature`, `params`, `return_type`, `file`, `line`, `confidence` and `extraction_method`. With `--group-by`, every listed item also carries its `source_library`, and `groups[]` gives each library's `summary`.

§6 records `applied_transforms` in the drift report's frontmatter for step 6's Provenance section, so a reviewer can tell which cosmetic differences the diff collapsed, and §5 renders `label_changes[]` as an informational table (§3b).

**If `uv` / the helper cannot execute** (e.g. claude.ai web): fall back to comparing the two lists by hand. Identify each export by its name and its file together, the file compared with forward slashes and no leading `./` (apply the three transforms above to both sides first). Read off added (current-only), removed (baseline-only) and changed (matched, differing type, signature, params, return_type or line). Pair a leftover removed and added entry as moved only when its name occurs once on each side, and list any other name left on both sides as ambiguous. Compare a field only when it is present on both sides, and skip the line of a moved export. Compare the labels (`confidence`, `extraction_method`) separately: trim, and a blank label counts as absent; compare case-insensitively and only when both sides have a value, with `ast_bridge` counting as `ast-grep` and `source_reading` as `source-read`. A matched export whose labels differ goes to the label differences list (§3b), never to changed, and counts as unchanged when nothing else differs.

### 1b. Find Relocated Exports (Forge+ and Deep with ccc)

**Run only when** the tier is Forge+ or Deep, `tools.ccc` is true in forge-tier.yaml, and the saved diff's `summary.removed` is above 0. Otherwise skip this section silently.

An export moved to a file outside the bounded scan list is missing from the snapshot, so the diff reports it as removed, which step 5 grades CRITICAL. Look for each `removed[]` entry of `{auditDataFolder}/structural-diff.json` elsewhere in the source:

1. Search for its name: `cd {source_root} && ccc search --limit 5 "{name}"` (CLI), the `/ccc` skill (Claude Code) or the ccc MCP server (Cursor). `ccc search` reads the index in the current working directory and has no project-selector flag (`--path` is a file-path glob filter *within* the index, and the result cap is `--limit`, not `--top`): see `knowledge/ccc-bridge.md`.
2. Drop each candidate file on `{bounded_scan_files}`: step 2 extracted those files, so the diff already saw their exports.
3. Verify each remaining candidate with ast-grep: run the AST Extraction Protocol's recipes for its language (in `{extractionPatternsData}`) over that one file, and keep a match whose `$NAME` is the removed name.
4. Append each verified match to `{extractionSnapshot}`'s `exports[]` as step 2 records an export: `name`, `type`, `signature`, `file` (relative to `{source_root}`, with forward slashes), `line` (`$NAME`'s line), `confidence: "T1"`, `extraction_method: "ast-grep"`, `ast_node_type` (the kind the matching recipe declares) and, for a stack, the removed entry's `source_library`.

When any export was appended, write the snapshot back and run §1's command again with the same arguments and the same `-o`, acting on its exit code as §1 does. The helper pairs each relocation with its removed entry as a move (or, when the name occurs more than once, lists it under `ambiguous_names[]`), so `moved[]` comes from the script and never from an edit of the report. A removed export whose search finds nothing ast-grep verifies stays removed. When ccc cannot search (no index for `{source_root}`, or the command fails), skip the rest of this section and note `ccc relocation check skipped: {reason}` on the **Method:** line (§5).

### 2. Read Added / Removed / Moved from the Diff

These sets come straight from the saved diff, with no further set arithmetic:

- **Added** (`added[]`): exports in the current snapshot but not the provenance map.
- **Removed** (`removed[]`): exports in the provenance map but not the current snapshot.
- **Moved** (`moved[]`): matched exports whose file path changed (`previous_file` → `current_file`). A move is **not** a removal.
- **Ambiguous names** (`ambiguous_names[]`): a name left on both sides that occurs more than once on a side (a `GET` handler in several route files, for example), so the helper paired none of its entries. Its entries stay in `removed[]` and `added[]`, and the item lists the removed and the added `{file, line}` of each. §5 shows them in their own table, and step 5 judges whether a removed and an added entry of one name are one export that moved.

Confidence tier for each entry is the `confidence` field the extractor recorded, which names the tool that produced the export at any tier: T1 for an export an ast-grep rule matched (`extraction_method: ast-grep`), T1-low for an export read by eye (`extraction_method: source-read`).

### 3. Read Changed Exports from the Diff

`changed[]` lists per-field differences for exports present in BOTH sets. Each item names the export, the `field` that changed (type, signature, params, return_type or line), its `baseline_value` → `current_value`, and the export's current `file`, `line` and `confidence`. Group items by export name and file when compiling the report, and pair with the export's `moved[]` entry (if any) to describe location changes. The Confidence column of Changed Exports (§5) is the item's `confidence`.

`summary.signature_unverified` counts the matched exports whose signature the helper could not compare: one side holds it as `params` and `return_type`, the other as `signature` text, so a change there cannot be seen. They are not drift, and §5 states the count, so an empty Changed Exports table does not read as checked signatures.

### 3b. Read Provenance Label Differences from the Diff

`label_changes[]` lists exports present in BOTH sets whose `confidence` or `extraction_method` differs between the provenance map and the snapshot, with each side's `{confidence, extraction_method}`. A label names the tool that extracted the export, not what the source says: an export read by eye when the skill was created (T1-low, `source-read`) and matched by ast-grep now (T1, `ast-grep`) is the same export, and so is an entry create-skill or update-skill relabeled to match the tool that read it. A label difference is therefore not drift: it never appears in Changed Exports, is not counted in Total Drift Items, and step 5 does not classify it. Take the count from `summary.label_changes`, no recount: for a stack diffed with `--group-by source_library`, the summary already sums the libraries, and each row carries its `source_library`.

### 4b. Detect Script/Asset Drift

**Only execute if provenance-map.json contains `file_entries`.**

**Resolve `{compareFileHashesHelper}`** from `{compareFileHashesProbeOrder}`; first existing path wins. HALT if no candidate exists.

Run one deterministic comparison subprocess — it walks tracked file_entries[] AND the inverse direction (source-tree → candidate set in standard script/asset/doc directories) so the LLM does not orchestrate per-file hashing:

```bash
uv run {compareFileHashesHelper} compare "{provenanceMap}" "{source_root}" > "{auditDataFolder}/file-drift.json"
```

The saved JSON (step 5 builds its Script/Asset findings from this file; if the command exits non-zero, delete the file and write the skipped note below):

```
{
  "added":   ["<rel-path>", ...],   // present on disk in tracked dirs, NOT in file_entries
  "removed": ["<rel-path>", ...],   // in file_entries, missing on disk
  "changed": [{"path": "...", "stored_hash": "sha256:...", "current_hash": "sha256:..."}],
  "stats":   {"added": N, "removed": N, "changed": N, "unchanged": N}
}
```

Hash-prefix normalization (writer-vs-reader compatibility — `skf-create-skill` writes `content_hash` with a `"sha256:"` prefix, a bare-hex hash from `hashlib` would otherwise never match) is handled inside the script. Downstream consumers read `added`/`removed`/`changed` directly with no further normalization.

Append the three lists into the Structural Drift section under a `### Script/Asset Drift (added {stats.added}, removed {stats.removed}, changed {stats.changed})` heading — take each count straight from `stats`, no recount.

**If `uv`/the helper cannot execute** (e.g. claude.ai web): skip the script/asset drift check with a `### Script/Asset Drift — skipped (hashing helper unavailable)` note rather than blocking the audit. This check is supplementary to the export diff, which has its own by-hand fallback in §1.

### Stack-Specific Structural Diff

If `{is_stack_skill}` is true:

**For v2 provenance (per-export entries with `source_library`):**
- §1 runs with `--group-by source_library`: the helper diffs each library on its own and tags every listed item with its `source_library`, which step 2 records on each snapshot export
- Report per-library diff results, taking each library's counts from `groups[]` (the top-level `summary` sums them)

**For code-mode stacks:** Re-extract from each source repo and compare per-library entries.

**For v1 legacy provenance:** Report library-level summary only (export counts, extraction methods). Note that per-export drift detection requires re-composition with v2 provenance.

**Integration drift:** For each integration in `integrations[]`, verify that co-import files still contain the detected patterns.

A compose-mode stack never reaches this step: step 1 sends it to step 1c (`constituent-freshness.md`), which checks its constituents' freshness instead.

### 5. Compile Structural Drift Section

**Rollup for high-volume uniform findings.** When ≥ 10 findings in the same table share one root cause (deleted source file, renamed module, entire package tree removed), you may collapse them into one row per root cause. Rollup rows replace the per-symbol `Export`/`Signature` columns with `Count` and `Representative symbols` (up to 3 names, `…` if more). Rollup applies to the **Added Exports**, **Removed Exports** and **Script/Asset Drift** tables, **not** to Changed Exports, which are heterogeneous by construction (signature changes and cross-file changes are inspected per-finding). A rollup only changes how the table reads: step 5 classifies the saved diff, one finding per export, so a rollup changes no count and no grade.

**Rollup row form (Added / Removed Exports):**

| Root Cause | Count | Representative symbols | Location | Confidence |
|------------|-------|------------------------|----------|------------|
| {deleted/renamed path or similar} | {N} | `{sym1}`, `{sym2}`, `{sym3}`, … | {root-cause path} | {T1/T1-low} |

**Rollup for the Provenance label differences table.** When ≥ 10 rows share one baseline label and one current label (grouped case-insensitively, as the helper compares them), you may collapse them into one row whose Export cell reads {count} exports (rep: `{sym1}`, `{sym2}`, `{sym3}`, …).

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

