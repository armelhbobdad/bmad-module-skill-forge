---
nextStepFile: 'semantic-diff.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
loadProvenanceScript: '{project-root}/src/shared/scripts/skf-load-provenance.py'
compareFileHashesScript: '{project-root}/src/shared/scripts/skf-compare-file-hashes.py'
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

### 1. Prepare Comparison Sets

Load both datasets:

**Baseline (from provenance map):**
- Export list with names, types, signatures, file paths, line numbers

**Current (from Step 02 extraction):**
- Export list with names, types, signatures, file paths, line numbers

**Canonicalize extractor methodology differences before matching.** The extractor used by `skf-create-skill` at baseline time and the re-extractor used by step 2 can differ in cosmetic detail (quote style, module qualification, re-export resolution). Without normalization, those cosmetic differences surface as false-positive "Changed" and "Removed" entries even when the source commit has not moved. Apply these transforms to both sets symmetrically:

- **Quote style on string defaults.** Normalize string-literal defaults in signatures to a single style — e.g., `kind: str = "Hnsw"` ↔ `kind: str = 'Hnsw'`. Pick one canonical form and apply to both sides.
- **Module qualification of stdlib helpers.** Strip module prefixes on well-known stdlib helpers when the unqualified form is importable at the call site: `dataclasses.field(...)` → `field(...)`, `typing.Optional[...]` → `Optional[...]`, `typing.List[...]` → `List[...]`. Do not collapse user-defined namespaces.
- **Public-API re-export resolution.** When `{source_root}/**/__init__.py` re-exports an internal symbol under a different public name (`from .internal import _Impl as Public`, or via `__all__`), resolve both sides to the public name before key-matching — otherwise a renamed re-export in the current scan shows up as "Removed `_Impl`" + "Added `Public`" instead of matching the baseline entry. The re-export map is already in workflow context as `{reexport_map}` (produced by `skf-load-provenance.py normalize` in step 1 §4). Apply it directly without re-walking `__init__.py` files.

Record the set of transforms actually applied in workflow context — step 6 surfaces them in the Provenance section so a reviewer can tell which differences the diff collapsed and which were real.

Normalize both sets for comparison:
- Match by canonicalized export name (primary key)
- Group by file for location-aware comparison

> **Longer-term fix.** The principled remedy is to persist `skf-create-skill`'s ast-grep ruleset to `{forge_version}/extraction-rules.yaml` at create time and have step 2 replay that exact ruleset. When the file is present, step 2 extraction becomes reproducible against the baseline and the canonicalization pass above becomes a no-op. Until then, normalization is the salvage remediation for provenance maps that predate extractor pinning.

### 2. Detect Added Exports

**Launch subprocess (Pattern 4 — parallel execution):** In Claude Code, use multiple parallel Agent tool calls. In CLI, use `xargs -P` or equivalent.

Find exports that exist in current scan but NOT in provenance map.

For each added export, record:
- Export name, type, signature
- File path and line number (from current scan)
- Confidence tier (T1 if AST-backed, T1-low if text-based)

**If subprocess unavailable:** Iterate current exports, check against provenance map set.

### 3. Detect Removed Exports

Find exports that exist in provenance map but NOT in current scan.

For each removed export, record:
- Export name, type, signature (from provenance map)
- Original file path and line number
- Confidence tier (T1 if AST-backed, T1-low if text-based)

**Special check:** If export name exists but in a different file, classify as MOVED (not removed).

### 4. Detect Changed Exports

Find exports that exist in BOTH sets but have differences.

Compare:
- **Signature changes:** Parameter count, parameter types, return type
- **Type changes:** Function became class, const became function, etc.
- **Location changes:** Same name/signature but different file or line number (MOVED)

For each changed export, record:
- Export name
- Original signature → Current signature
- Original location → Current location
- What changed (signature / type / location)
- Confidence tier

### 4b. Detect Script/Asset Drift

**Only execute if provenance-map.json contains `file_entries`.**

Run one deterministic comparison subprocess — it walks tracked file_entries[] AND the inverse direction (source-tree → candidate set in standard script/asset/doc directories) so the LLM does not orchestrate per-file hashing:

```bash
uv run {compareFileHashesScript} compare {provenanceMap} {sourceRoot}
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

Append the three lists into the Structural Drift section as "### Script/Asset Drift ({stats.added + stats.removed + stats.changed})".

### Stack-Specific Structural Diff

If `{is_stack_skill}` is true:

**For v2 provenance (per-export entries with `source_library`):**
- Group entries by `source_library`
- For each library, perform the standard structural diff (same as single-skill) against current source
- Report per-library diff results

**For code-mode stacks:** Re-extract from each source repo and compare per-library entries.

**For compose-mode stacks:** Compare current constituent skill exports against the entries recorded at compose time. Use the `source_library` field to match entries to constituents.

**For v1 legacy provenance:** Report library-level summary only (export counts, extraction methods). Note that per-export drift detection requires re-composition with v2 provenance.

**Integration drift:** For each integration in `integrations[]`, verify that co-import files still contain the detected patterns (code-mode) or that constituent skills still document the integration (compose-mode).

### 5. Compile Structural Drift Section

**Rollup for high-volume uniform findings.** When ≥ 10 findings in the same table share one root cause (deleted source file, renamed module, entire package tree removed), you MAY collapse them into one row per root cause. Rollup rows replace the per-symbol `Export`/`Signature` columns with `Count` and `Representative symbols` (up to 3 names, `…` if more). Rollup applies to **Added Exports**, **Removed Exports**, and **Script/Asset Drift** tables — **not** to Changed Exports, which are heterogeneous by construction (signature changes and cross-file changes are inspected per-finding). Record which groupings were collapsed in workflow context for reviewer traceability.

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

Update {outputFile} frontmatter:
- Append `'structural-diff'` to `stepsCompleted`

### 7. Present MENU OPTIONS

Display: "**Structural diff complete. {total} drift items found. Proceeding to semantic diff...**"

#### Menu Handling Logic:

- After structural diff section is appended and frontmatter updated, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed analysis step with no user choices
- Proceed directly to next step after completion

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the ## Structural Drift section has been appended to {outputFile} with all findings documented will you then load and read fully `{nextStepFile}` to execute and begin semantic diff analysis.

