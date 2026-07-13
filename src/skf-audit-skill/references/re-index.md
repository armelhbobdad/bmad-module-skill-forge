---
nextStepFile: 'structural-diff.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Re-Index Source

## STEP GOAL:

Re-scan the source code using the current forge tier tools to build a fresh extraction snapshot. This snapshot will be compared against the original provenance map in Step 03 to detect structural drift.

## Rules

- Focus only on extracting current source state — do not compare yet (that's Step 03)
- Extract every file in the bounded scan list — a file skipped here makes step 3 flag its exports as false "removed" drift
- Use subprocess Pattern 2 (per-file deep analysis) when available for AST extraction; if unavailable, extract in main thread file by file

## MANDATORY SEQUENCE

### 1. Determine Extraction Strategy

Based on forge tier detected in Step 01:

**Quick tier (no AST tools):**
- Read source files via gh_bridge or direct file I/O
- Extract export names by text pattern matching (function/class/type declarations)
- Confidence label: T1-low

**Forge tier (ast-grep available):**
- Use ast_bridge to perform AST extraction per source file
- Extract: export name, type (function/class/type/const), full signature, file path, line number
- Confidence label: T1

**Forge+ tier (ast-grep + ccc available):**
- Identical extraction to Forge tier: use ast_bridge for AST extraction per source file
- Confidence label: T1
- CCC rename detection available (see section 4b)

**Deep tier (ast-grep + QMD available):**
- Forge extraction (above) PLUS
- Query qmd_bridge for temporal context: when exports were added, modification history, usage frequency
- Confidence labels: T1 for structural, T2 for temporal context

**Tool resolution:** `gh_bridge` → `gh api` commands or direct file I/O if local. `ast_bridge` → ast-grep MCP tools (`find_code`, `find_code_by_rule`) or `ast-grep` CLI. `qmd_bridge` → QMD MCP tools (`search`, `vector_search`) or `qmd` CLI. See `knowledge/tool-resolution.md`.

### 2. Build Bounded Scan List

Audit-skill detects drift on files that were in scope during create-skill. The authoritative record of "what was in scope" is the provenance map loaded in step 1. Scan only those files — **audit-skill does NOT discover new files**. New-file detection is the responsibility of `skf-update-skill`, which maintains its own change manifest. To audit a project that has grown new files since creation, run update-skill first, then audit-skill.

**Why bounded:** without this constraint, files that were deliberately excluded by the original brief's scope patterns (test fixtures, vendored code, generated artifacts, demo code, unrelated modules) get scanned on every audit and their exports are flagged by step 3 structural diff as "added" — false-positive drift that obscures real structural changes.

**If a provenance map was loaded in step 1** (normal mode):

1. The **bounded scan list** is `{bounded_scan_files}` — the union of `entries[].source_file` and `file_entries[].source_file`, deduplicated, sorted, and forward-slash normalized by init.md §4's `skf-load-provenance.py normalize` call. Consume it directly; do **not** re-walk the provenance map to rebuild it. The union/dedup/sort has one correct answer per map and is already scripted — re-deriving it in-prompt risks diverging from step 3, which diffs against the same normalized projection.
2. Verify each path under `{source_root}`. Files that existed at creation time but are now missing are **not** errors at this stage — keep them in the list so step 3 can classify them as DELETED. Handling missing files is step 3's job, not step 2's.
3. Record `bounded_scan: true` and `bounded_scan_source: "provenance-map"` in context for the evidence report.
4. Report:

   "**Bounded scan:** {count} files from provenance map ({provenance_date})."

**If degraded mode** (no provenance map was loaded — user confirmed `[D]egraded mode` at step 1 §4):

1. Fall back to a source-tree scan: list all source files under `{source_root}` matching the project's primary language extensions (derive from `metadata.json.language` — e.g., `*.ts` / `*.tsx` for typescript, `*.py` for python, `*.rs` for rust, `*.go` for go).
2. Apply generic exclusions: `**/tests/**`, `**/test/**`, `**/__tests__/**`, `*.test.*`, `*.spec.*`, `node_modules/**`, `dist/**`, `build/**`, `target/**`, `__pycache__/**`, `.venv/**`, `vendor/**`.
3. Record `bounded_scan: false` and `bounded_scan_source: "source-tree-fallback"` in context.
4. Report:

   "**Degraded mode scan:** {count} files from source tree (no provenance map — results may include files out of the original brief scope)."

**Count files to process** and proceed to section 3 with the resolved scan list.

### 3. Extract Current Exports

**For each file in the bounded scan list from §2, launch a subprocess that:**
1. Loads the source file
2. Extracts all public exports using tier-appropriate method
3. Records: export name, type, signature, file path, line number, confidence tier
4. Returns structured findings to parent

**If a file from the bounded scan list is missing on disk:** record `{file, exports: [], status: "missing"}` and continue — step 3 structural diff will classify exports previously at this path as DELETED.

**If subprocess unavailable:** Perform extraction in main thread, processing each file sequentially.

**Build extraction snapshot and persist it to `{forge_version}/extraction-snapshot.json`** — step 3 (`structural-diff.md`) reads this file directly, so it must be written to disk, not merely held in context:
```
{
  "extraction_date": "{timestamp}",
  "confidence_tier": "{tier}",
  "source_root": "{source_path}",
  "files_scanned": {count},
  "bounded_scan": true|false,
  "bounded_scan_source": "provenance-map|source-tree-fallback",
  "exports": [
    {
      "name": "{export_name}",
      "type": "function|class|type|const|interface",
      "signature": "{full signature}",
      "file": "{relative_path}",
      "line": {line_number},
      "confidence": "T1|T1-low|T2"
    }
  ]
}
```

Record the written path as `{extractionSnapshot}` in workflow context — step 3 passes it to the deterministic structural-diff helper.

### 4. Deep Tier Enhancement (Deep Only)

**If forge tier is Deep:**

Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`.

Find the collection entry matching the current skill: look for an entry where `skill_name` matches the current skill being audited AND `type` is `"extraction"`.

Three collection states must be handled distinctly — semantic-diff.md §2 branches the same way:

**If a matching extraction collection is found and populated** (pre-query probe via `qmd ls {collection_name}` or equivalent returns one or more files):
Query qmd_bridge against the `{skill_name}-extraction` collection for temporal context on each extracted export:
- When was this export first added?
- Has it been modified recently?
- What is its usage frequency across the codebase?
- How does the current extraction compare to the previously compiled skill content?

Append temporal metadata to each export in the snapshot.

**If a matching extraction collection is found but empty** (pre-query probe reports `Files: 0 (updated never)` or an empty listing):
Log: "QMD collection `{collection_name}` is registered but empty. Run `qmd update` to (re-)index `{collection.path}`, then re-audit. Temporal enrichment skipped for this run."
Continue without T2 enrichment — the unpopulated collection is a setup gap, not an extraction failure. Step-04 will fall through to its direct-content fallback for semantic diff.

**If no matching collection found in registry:**
Log: "No QMD extraction collection found for {skill_name}. Temporal enrichment skipped. Re-run [CS] Create Skill to generate the collection."
Continue without T2 enrichment — this is not an error.

**If forge tier is Quick, Forge, or Forge+:**
Skip this section. Temporal context requires Deep tier.

### 4b. CCC Rename Detection (Forge+ and Deep with ccc)

**If `tools.ccc` is true in forge-tier.yaml:**

For each export in the skill baseline that was NOT found at its recorded file path during re-extraction (potential "deleted" export):

1. Run `ccc_bridge.search("{export_name}", source_root, top_k=5)` — **Tool resolution:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `ccc search "{export_name}" --path {source_root} --top 5` (CLI) — to find candidate current locations
2. If CCC returns files containing the export name:
   - Run ast-grep verification on each candidate file
   - If verified at a new location: reclassify from "deleted" to "moved" with the new file:line reference
   - This reduces false-positive structural drift findings where exports were relocated, not removed
3. If CCC returns no results or verification fails: keep the "deleted" classification

CCC failures: skip rename detection silently, proceed with standard structural diff.

**If `tools.ccc` is false:** Skip this section silently.

### 5. Validate Extraction Completeness

"**Extraction complete.**

| Metric | Value |
|--------|-------|
| Scan mode | {bounded (provenance-map) / degraded (source-tree)} |
| Files scanned | {count} |
| Exports found | {total_exports} |
| Functions | {function_count} |
| Classes | {class_count} |
| Types/Interfaces | {type_count} |
| Constants | {const_count} |
| Confidence | {T1/T1-low/T2} |

**Proceeding to structural comparison...**"

### 6. Update Report and Auto-Proceed

Update {outputFile} frontmatter — append `'re-index'` to `stepsCompleted`. Once the extraction snapshot is complete with all source files processed, load, read fully, and execute `{nextStepFile}` (structural diff).

