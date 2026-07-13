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
  "summary": {"added": N, "removed": N, "changed": N, "moved": N, "unchanged": N},
  "added":   [ <entry>, ... ],   // in current snapshot, NOT in provenance map
  "removed": [ <entry>, ... ],   // in provenance map, NOT in current snapshot
  "changed": [ {"name", "field", "baseline_value", "current_value"}, ... ],
  "moved":   [ {"name", "previous_file", "current_file"}, ... ],
  "unchanged_count": N,
  "applied_transforms": [ {"transform": "quote-style|stdlib-prefix|reexport-resolution", "count": N}, ... ]
}
```

Stash `applied_transforms` in workflow context — step 6 surfaces it in the Provenance section so a reviewer can tell which cosmetic differences the diff collapsed and which changes were real.

**If `uv` / the helper cannot execute** (e.g. claude.ai web): fall back to comparing the two lists by hand — match by canonicalized export name (apply the three transforms above to both sides), then read off added (current-only), removed (baseline-only), moved (same name, different `file`), and changed (matched name, differing type/signature/line). Compare a field only when it is present on both sides.

### 2. Read Added / Removed / Moved from the Diff

These sets come straight from the helper's JSON — no further set arithmetic:

- **Added** — `added[]`: exports in the current snapshot but not the provenance map. Each carries name, type, signature, file, line, confidence.
- **Removed** — `removed[]`: exports in the provenance map but not the current snapshot. Same fields (in provenance-map field names).
- **Moved** — `moved[]`: matched exports whose file path changed (`previous_file` → `current_file`). A move is **not** a removal.

Confidence tier for each entry is the `confidence` field the extractor recorded (T1 if AST-backed, T1-low if text-based).

### 3. Read Changed Exports from the Diff

`changed[]` lists per-field differences for exports present in BOTH sets. Each item names the export, the `field` that changed (type / signature / line / confidence), and its `baseline_value` → `current_value`. Group items by export name when compiling the report, and pair with the export's `moved[]` entry (if any) to describe location changes.

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

Append to {outputFile}:

```markdown
## Structural Drift

**Comparison:** Provenance map ({provenance_date}) vs Current scan ({scan_date})
**Method:** {Quick: text-diff / Forge: AST structural / Deep: AST structural}

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
```

### 6. Update Report and Auto-Proceed

Update {outputFile} frontmatter — append `'structural-diff'` to `stepsCompleted`. Once the ## Structural Drift section has been appended, load, read fully, and execute `{nextStepFile}` (semantic diff).

