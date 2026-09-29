---
nextStepFile: 'semantic-diff.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
loadProvenanceProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-load-provenance.py'
  - '{project-root}/src/shared/scripts/skf-load-provenance.py'
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

Compare the original provenance map extractions from create-skill against the current re-index snapshot from Step 02 to detect structural drift. Identify added, removed, and changed exports with file:line citations and confidence tier labels.

## Rules

- Focus only on structural comparison — added/removed/changed exports
- Do not classify severity (Step 05) or suggest remediation (Step 06)
- Use subprocess Pattern 4 (parallel) when available; if unavailable, compare sequentially

## MANDATORY SEQUENCE

### 1. Run the Deterministic Export Diff

The export comparison — canonicalization, set arithmetic (added/removed/moved), and field-level change detection — is fully deterministic and runs in one subprocess. Do **not** diff the two export lists by hand: an LLM comparing dozens or hundreds of exports can silently drop or mis-match entries, which violates this skill's zero-hallucination contract.

**Resolve `{structuralDiffHelper}`** from `{structuralDiffProbeOrder}`; first existing path wins. HALT if no candidate exists.

Run one comparison over the baseline provenance map (from step 1) and the current extraction snapshot (`{extractionSnapshot}`, written to disk by step 2 §3):

```bash
uv run {structuralDiffHelper} {provenanceMap} {extractionSnapshot}
```

The helper reads both shapes directly — the provenance map's `entries[]` (with `export_name`/`export_type`/`source_file`/`source_line`) and the snapshot's `exports[]` — and aliases the field names, so no manual projection is needed.

**Canonicalization is applied inside the helper, symmetrically to both sides**, before name-keyed matching — so cosmetic extractor differences do not surface as false-positive "Changed"/"Removed"/"Added" entries:

- **Quote style on string defaults** — `kind: str = "Hnsw"` ↔ `kind: str = 'Hnsw'`.
- **Stdlib module qualification** — `typing.Optional[...]` → `Optional[...]`, `dataclasses.field(...)` → `field(...)` (user-defined namespaces are never collapsed).
- **Public-API re-export resolution** — a renamed public re-export (`_Impl` → `Public`) matches the baseline entry instead of splitting into "Removed `_Impl`" + "Added `Public`". The re-export map is **auto-derived from the provenance map** (identical to the `{reexport_map}` projection `skf-load-provenance.py normalize` produced in step 1 §4). Pass `--reexport-map {file}` only to override with a custom map.

Parse the emitted JSON:

```
{
  "summary": {"added": N, "removed": N, "changed": N, "moved": N, "unchanged": N, "label_changes": N},
  "added":   [ <entry>, ... ],   // in current snapshot, NOT in provenance map
  "removed": [ <entry>, ... ],   // in provenance map, NOT in current snapshot
  "changed": [ {"name", "field", "baseline_value", "current_value"}, ... ],   // field: type | signature | line
  "moved":   [ {"name", "previous_file", "current_file"}, ... ],
  "label_changes": [ {"name", "baseline": {"confidence", "extraction_method"}, "current": {"confidence", "extraction_method"}}, ... ],   // informational, not drift
  "unchanged_count": N,
  "applied_transforms": [ {"transform": "quote-style|stdlib-prefix|reexport-resolution", "count": N}, ... ]
}
```

Stash `applied_transforms` in workflow context — step 6 surfaces it in the Provenance section so a reviewer can tell which cosmetic differences the diff collapsed and which changes were real.

Stash `label_changes` in workflow context too: §5 renders it as an informational table (§3b).

**If `uv` / the helper cannot execute** (e.g. claude.ai web): fall back to comparing the two lists by hand. Match by canonicalized export name (apply the three transforms above to both sides), then read off added (current-only), removed (baseline-only), moved (same name, different `file`), and changed (matched name, differing type/signature/line). Compare a field only when it is present on both sides. Compare the labels (`confidence`, `extraction_method`) separately: trim, and a blank label counts as absent; compare case-insensitively and only when both sides have a value, with `ast_bridge` counting as `ast-grep` and `source_reading` as `source-read`. A matched export whose labels differ goes to the label differences list (§3b), never to changed, and counts as unchanged when nothing else differs.

### 2. Read Added / Removed / Moved from the Diff

These sets come straight from the helper's JSON — no further set arithmetic:

- **Added** (`added[]`): exports in the current snapshot but not the provenance map.
- **Removed** (`removed[]`): exports in the provenance map but not the current snapshot.
- **Moved** (`moved[]`): matched exports whose file path changed (`previous_file` → `current_file`). A move is **not** a removal.

Added and removed entries are the helper's normalized records, whichever input shape they came from: each carries `name`, `type`, `signature`, `file`, `line`, `confidence` and `extraction_method`.

Confidence tier for each entry is the `confidence` field the extractor recorded, which names the tool that produced the export at any tier: T1 for an export an ast-grep rule matched (`extraction_method: ast-grep`), T1-low for an export read by eye (`extraction_method: source-read`).

### 3. Read Changed Exports from the Diff

`changed[]` lists per-field differences for exports present in BOTH sets. Each item names the export, the `field` that changed (type / signature / line), and its `baseline_value` → `current_value`. Group items by export name when compiling the report, and pair with the export's `moved[]` entry (if any) to describe location changes. `changed[]` items carry no label: the Confidence column of Changed Exports (§5) shows the current snapshot's `confidence` for that export, read from `{extractionSnapshot}`.

### 3b. Read Provenance Label Differences from the Diff

`label_changes[]` lists exports present in BOTH sets whose `confidence` or `extraction_method` differs between the provenance map and the snapshot, with each side's `{confidence, extraction_method}`. A label names the tool that extracted the export, not what the source says: an export read by eye when the skill was created (T1-low, `source-read`) and matched by ast-grep now (T1, `ast-grep`) is the same export, and so is an entry create-skill or update-skill relabeled to match the tool that read it. A label difference is therefore not drift: it never appears in Changed Exports, is not counted in Total Drift Items, and step 5 does not classify it. Take the count from `summary.label_changes`, no recount. For a stack diffed per library (Stack-Specific Structural Diff), sum `summary.label_changes` across the per-library runs and merge their `label_changes[]` rows, tagging each row with its library.

### 4b. Detect Script/Asset Drift

**Only execute if provenance-map.json contains `file_entries`.**

**Resolve `{compareFileHashesHelper}`** from `{compareFileHashesProbeOrder}`; first existing path wins. HALT if no candidate exists.

Run one deterministic comparison subprocess — it walks tracked file_entries[] AND the inverse direction (source-tree → candidate set in standard script/asset/doc directories) so the LLM does not orchestrate per-file hashing:

```bash
uv run {compareFileHashesHelper} compare {provenanceMap} {sourceRoot}
```

Parse the emitted JSON:

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
- Group entries by `source_library`
- For each library, run the same deterministic diff as the single-skill path (§1) — pass the per-library baseline slice and the matching current snapshot to `{structuralDiffHelper}`
- Report per-library diff results
- Sum each library's `summary.label_changes` and merge its `label_changes[]` rows, tagged with the library (§3b)

**For code-mode stacks:** Re-extract from each source repo and compare per-library entries.

**For compose-mode stacks:** Compare current constituent skill exports against the entries recorded at compose time. Use the `source_library` field to match entries to constituents.

**For v1 legacy provenance:** Report library-level summary only (export counts, extraction methods). Note that per-export drift detection requires re-composition with v2 provenance.

**Integration drift:** For each integration in `integrations[]`, verify that co-import files still contain the detected patterns (code-mode) or that constituent skills still document the integration (compose-mode).

### 5. Compile Structural Drift Section

**Rollup for high-volume uniform findings.** When ≥ 10 findings in the same table share one root cause (deleted source file, renamed module, entire package tree removed), you may collapse them into one row per root cause. Rollup rows replace the per-symbol `Export`/`Signature` columns with `Count` and `Representative symbols` (up to 3 names, `…` if more). Rollup applies to **Added Exports**, **Removed Exports**, and **Script/Asset Drift** tables — **not** to Changed Exports, which are heterogeneous by construction (signature changes and cross-file changes are inspected per-finding). Record which groupings were collapsed in workflow context for reviewer traceability.

**Rollup row form (Added / Removed Exports):**

| Root Cause | Count | Representative symbols | Location | Confidence |
|------------|-------|------------------------|----------|------------|
| {deleted/renamed path or similar} | {N} | `{sym1}`, `{sym2}`, `{sym3}`, … | {root-cause path} | {T1/T1-low} |

**Rollup for the Provenance label differences table.** When ≥ 10 rows share one baseline label and one current label (grouped case-insensitively, as the helper compares them), you may collapse them into one row whose Export cell reads {count} exports (rep: `{sym1}`, `{sym2}`, `{sym3}`, …).

Append to {outputFile}:

```markdown
## Structural Drift

**Comparison:** Provenance map ({provenance_date}) vs Current scan ({scan_date})
**Method:** {Quick: text-diff / Forge, Forge+ or Deep: AST structural}. Labels follow the tool that ran: T1 for an ast-grep match, T1-low for an export read by eye{; AST fallback files: {ast_fallback_files}, when any}

### Added Exports ({count})

| Export | Type | Signature | Location | Confidence |
|--------|------|-----------|----------|------------|
| {name} | {type} | {signature} | {file}:{line} | {T1/T1-low} |

### Removed Exports ({count})

| Export | Type | Original Signature | Original Location | Confidence |
|--------|------|-------------------|-------------------|------------|
| {name} | {type} | {signature} | {file}:{line} | {T1/T1-low} |

### Changed Exports ({count})

| Export | Change Type | Before | After | Location | Confidence |
|--------|------------|--------|-------|----------|------------|
| {name} | {signature/type/location} | {old} | {new} | {file}:{line} | {T1/T1-low} |

### Summary

| Category | Count |
|----------|-------|
| Added | {added_count} |
| Removed | {removed_count} |
| Changed | {changed_count} |
| **Total Drift Items** | {total} |

### Provenance label differences (not drift) ({label_changes_count})

These rows are informational: a label names the tool that extracted the export, so they are excluded from Total Drift Items and are not findings.

| Export | Baseline label | Current label |
|--------|----------------|---------------|
| {name} | {baseline.confidence} / {baseline.extraction_method} | {current.confidence} / {current.extraction_method} |
```

Include the **Provenance label differences (not drift)** subsection only when `label_changes[]` is non-empty; take `{label_changes_count}` from `summary.label_changes` (summed across libraries for a stack, §3b). Write `(none)` for a label the helper emits as null. For a stack, write each Export cell as `{library}: {name}`.

### 6. Update Report and Auto-Proceed

Update {outputFile} frontmatter — append `'structural-diff'` to `stepsCompleted`. Once the ## Structural Drift section has been appended, load, read fully, and execute `{nextStepFile}` (semantic diff).

