---
nextStepFile: 'structural-diff.md'
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
tierDegradationRulesData: 'skf-create-skill/references/tier-degradation-rules.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Re-Index Source

## STEP GOAL:

Re-scan the source code using the current forge tier tools to build a fresh extraction snapshot. This snapshot will be compared against the original provenance map in Step 03 to detect structural drift.

## Rules

- Focus only on extracting current source state — do not compare yet (that's Step 03)
- Extract every file in the bounded scan list — a file skipped here makes step 3 flag its exports as false "removed" drift
- Use subprocess Pattern 2 (per-file deep analysis) when available to build each file's exports (§3); if unavailable, build them in main thread file by file

## MANDATORY SEQUENCE

### 1. Determine Extraction Strategy

Label every export by the tool that produced it, never by the tier: an export an ast-grep rule matched is T1 with `extraction_method: ast-grep` and, as `ast_node_type`, the `kind` the matching pattern or recipe declares in `{extractionPatternsData}` (ast-grep's output does not report it); an export read by eye is T1-low with `extraction_method: source-read` and `ast_node_type: null`.

Based on forge tier detected in Step 01:

**Quick tier (no AST tools):**
- Read source files via gh_bridge or direct file I/O
- Extract export names by text pattern matching (function/class/type declarations)
- Label every export T1-low (read by eye, not matched by ast-grep) with `extraction_method: source-read` and `ast_node_type: null`

**Forge tier (ast-grep available):**
- Follow the **AST Extraction Protocol** in `{extractionPatternsData}` with the bounded scan list from §2 as the files in scope: the list's file count is the decision tree's input. Run every recipe for the language once over the whole list, not once per file, and keep only the matches whose file, relative to `{source_root}` and with forward slashes, is on the list. §3's per-file workers take their file's matches from these runs
- A run that returns as many matches as its cap (`max_results`, or the CLI template's `| head -N`) may have dropped some, and step 3 would report each dropped export as removed: rerun that recipe with a higher cap, or through the CLI streaming template on smaller batches of the list's files (passed as its `{path}`), until no run fills its cap
- Extract: export name, type (function/class/type/const), full signature, file path, line number. The name is the match's `$NAME`, and the line is `$NAME`'s line (`metaVariables.single.NAME.range.start.line + 1`), as create-skill records it, not the match's first line (a decorator or an `export` line can come first)
- Read by eye the forms the recipes leave out (Known Limitation #11 in `{extractionPatternsData}`) when a file uses them. `find_code` is only the fallback of Known Limitation #4, for a recipe that errors or finds nothing where the file holds exports
- Label each export by the tool that produced it: an export an ast-grep rule matched is T1 (AST-verified structural truth) with `extraction_method: ast-grep` and the `kind` the matching pattern or recipe declares as `ast_node_type`; an export read by eye (ast-grep could not parse its file, the rules missed it, or the file was read instead of matched) is T1-low with `extraction_method: source-read` and `ast_node_type: null`

**Tier degradation handling (Forge/Forge+/Deep):** If ast-grep is unavailable or fails on individual files, follow `{tierDegradationRulesData}` (AST Tool Unavailable, Per-File AST Failure) for the fallback and the user notification. A file ast-grep cannot parse falls back to reading that file only: its exports are T1-low with `extraction_method: source-read` and `ast_node_type: null`, and exports ast-grep matched in other files stay T1. Silent degradation is forbidden: the run names each file read after an ast-grep failure, and why (§3, §5). When ast-grep is unavailable for the whole run, every export is T1-low and `ast_fallback_files` records `all files (ast-grep unavailable)`.

**Forge+ tier (ast-grep + ccc available):**
- Identical extraction to Forge tier (the AST Extraction Protocol, above)
- Label each export by tool, as at Forge tier
- CCC rename detection available (see section 4)

**Deep tier (ast-grep + QMD available):**
- Identical extraction to Forge tier, labeled by tool as at Forge tier
- No QMD query at this step: step 4 (semantic diff) queries QMD itself

**Tool resolution:** `gh_bridge` → `gh api` commands or direct file I/O if local. `ast_bridge` → the ast-grep MCP tool `find_code_by_rule` with a recipe and `output_format="json"`, or the protocol's CLI streaming template (`ast-grep scan -r {recipe_file} --json=stream`); `find_code` only as the fallback of Known Limitation #4. See `knowledge/tool-resolution.md`.

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

At Forge, Forge+ and Deep, run the recipes over the bounded scan list first (§1).

**For each file in the bounded scan list from §2, launch a subprocess that:**
1. Loads the source file
2. Extracts all public exports using tier-appropriate method
3. Records: export name, type, signature, file path, line number, and the labels of the tool that produced it (`confidence`, `extraction_method`, `ast_node_type`, per §1)
4. Returns structured findings to parent

**If ast-grep cannot parse a file** (Forge, Forge+ or Deep): read that file only, label its exports T1-low with `extraction_method: source-read` and `ast_node_type: null`, and warn: "**AST fallback:** ast-grep could not parse {file} ({reason}); its exports were read from source and labeled T1-low." Record the file in `ast_fallback_files` in workflow context: the §5 summary, the Structural Drift **Method:** line (step 3 §5) and the report's Provenance table (step 6 §3) read it.

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
      "confidence": "T1|T1-low",
      "extraction_method": "ast-grep|source-read",
      "ast_node_type": "{the kind the matching ast-grep pattern or recipe declares, or null}"
    }
  ]
}
```

`confidence_tier` holds the forge tier the re-index ran at, not a label. `confidence`, `extraction_method` and `ast_node_type` label the structural extraction by the tool that produced it (§1).

Record the written path as `{extractionSnapshot}` in workflow context — step 3 passes it to the deterministic structural-diff helper.

### 4. CCC Rename Detection (Forge+ and Deep with ccc)

**If `tools.ccc` is true in forge-tier.yaml:**

For each export in the skill baseline that was NOT found at its recorded file path during re-extraction (potential "deleted" export):

1. Run `ccc_bridge.search("{export_name}", source_root, top_k=5)` — **Tool resolution:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `cd {source_root} && ccc search --limit 5 "{export_name}"` (CLI) — to find candidate current locations. `ccc search` reads the index in the current working directory and has no project-selector flag (`--path` is a file-path glob filter *within* the index, and the result cap is `--limit`, not `--top`) — see `knowledge/ccc-bridge.md`.
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
| Labels | {t1_count} T1 (`ast-grep`), {t1_low_count} T1-low (`source-read`) |
| AST fallback files | {count and names from `ast_fallback_files`, or none; n/a at Quick} |

**Proceeding to structural comparison...**"

### 6. Update Report and Auto-Proceed

Update {outputFile} frontmatter — append `'re-index'` to `stepsCompleted`. Once the extraction snapshot is complete with all source files processed, load, read fully, and execute `{nextStepFile}` (structural diff).

