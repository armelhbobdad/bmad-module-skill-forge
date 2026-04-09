---
nextStepFile: './step-04-merge.md'
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
extractionPatternsTracingData: 'skf-create-skill/references/extraction-patterns-tracing.md'
remoteSourceResolutionData: 'references/remote-source-resolution.md'
tierDegradationRulesData: 'skf-create-skill/references/tier-degradation-rules.md'
---

# Step 3: Re-Extract Changed Exports

## STEP GOAL:

Perform tier-aware extraction on only the changed files identified in step 02, producing fresh export data with confidence tier labels (T1/T1-low/T2) that will be merged into the existing skill in step 04.

## Rules

- Focus only on extracting changed exports — do not merge or modify existing skill
- Only extract files in the change manifest — do not touch unchanged files
- For each changed file, launch a subprocess for deep AST analysis (Pattern 2); if unavailable, extract sequentially

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Check for Docs-Only Mode

**If `source_type: "docs-only"` in the original brief or metadata:**

"**Docs-only skill detected.** This skill was generated from external documentation, not source code. Re-extraction will re-fetch the original `doc_urls` to check for updated content."

- Re-fetch each URL from `doc_urls` (from the brief or metadata) using whatever web fetching capability is available
- Extract updated API information with T3 `[EXT:{url}]` citations
- Build the updated extraction inventory from fetched content
- Skip all source code extraction below — proceed directly to the merge step (section 5 or equivalent)

**If `source_type: "source"` (default):** Continue with source extraction below.

### 1b. Determine Extraction Strategy by Tier

**Remote Source Resolution (Forge/Deep only):**

**MCP source access (ordered fallback):** When `source_repo` is set in metadata.json, try each MCP tool in order to fetch only the changed files from the change manifest. This avoids clone overhead entirely. Tools are ordered by data freshness — gh API returns live GitHub content and is preferred for update-skill where current file versions are required. zread and deepwiki depend on manual indexing and may return stale data if indexes haven't been refreshed since the changes being extracted.

1. **gh API** — `gh api repos/{owner}/{repo}/contents/{path}` for raw file content
   - If accessible: fetch file content (base64-decoded), always current
   - If rate-limited, 404, or inaccessible: log tool and reason, continue to next tool
2. **zread** — `get_repo_structure` + `read_file` for targeted file access
   - If repo found: fetch changed files, proceed with extraction
   - If "repo not found" or error: log tool and reason, continue to next tool
   - Caveat: indexed data — may be stale if index wasn't refreshed after the target changes
3. **deepwiki** — `ask_question` for targeted export/signature queries
   - If repo indexed and returns usable source data: extract from response
   - If no results or repo not indexed: log tool and reason, continue to next tool
   - Caveat: returns synthesized content, not raw source — extraction quality varies; index may be stale

**Confidence labeling:** MCP-fetched content written to a temp file and analyzed with ast-grep → T1. MCP-fetched content analyzed with pattern matching (AST unavailable) → T1-low.

**If all MCP tools fail for this repo:** Fall back to workspace or ephemeral clone — load and follow `{remoteSourceResolutionData}` for clone setup, version reconciliation, and AST tool unavailability handling.

**If all approaches fail (MCP + ephemeral clone):** Degrade to provenance-map-only analysis (State 2, T1 confidence from compilation-time data). Warn user: "Source access failed for {source_repo}. Analysis limited to provenance-map baseline."

**Quick tier (text pattern matching):**
- Extract function/class/type names via regex patterns
- Extract export statements via text matching
- Confidence: T1-low (pattern-matched, not AST-verified)

**Forge tier (AST structural extraction):**

⚠️ **CRITICAL:** Load and follow the **AST Extraction Protocol** from `{extractionPatternsData}`. Use the decision tree based on the number of changed files: prefer MCP `find_code()` for small sets, `find_code_by_rule()` with scoped YAML rules for medium sets, and CLI `--json=stream` with line-by-line streaming for large sets. Never use `ast-grep --json` (without `=stream`) — it loads the entire result set into memory and will fail on large codebases.

- Extract: function signatures, type definitions, class members, exported constants
- Extract: parameter types, return types, JSDoc/docstring comments
- Confidence: T1 (AST-verified structural truth)

**Tier degradation handling (Forge/Forge+/Deep):** If ast-grep is unavailable or fails on individual files, follow `{tierDegradationRulesData}` for fallback strategy and user notification requirements. Silent degradation is forbidden — the user must always know when AST extraction was skipped.

**Deep tier (AST + QMD semantic enrichment):**
- Perform all Forge tier extractions (T1)
- Additionally: launch a subprocess that queries qmd_bridge for temporal context on changed exports, returning T2 evidence per export
- QMD provides: usage patterns, historical context, related documentation
- Confidence: T1 for structural, T2 for semantic enrichment

**Tool resolution:** `ast_bridge` → ast-grep MCP tools (`find_code`, `find_code_by_rule`) or `ast-grep` CLI. `qmd_bridge` → QMD MCP tools (`mcp__plugin_qmd-plugin_qmd__search`, `vector_search`) or `qmd` CLI. See `knowledge/tool-resolution.md`.

### 2. Extract Changed Files

DO NOT BE LAZY — For EACH file in the change manifest with status MODIFIED, ADDED, or RENAMED, launch a subprocess that:

1. Loads the source file
2. Performs tier-appropriate extraction (Quick/Forge/Forge+/Deep)
3. For each export found:
   - Record: export name, type (function/class/type/constant), signature
   - Record: file path, start line, end line
   - Record: parameters with types (if function/method)
   - Record: return type (if function/method)
   - Record: JSDoc/docstring summary (if present)
   - Label: confidence tier (T1/T1-low/T2)
4. Returns structured extraction findings to parent

**For DELETED files:** No extraction needed — deletions handled in merge step.

**For MOVED files:** Re-extract at new location to update file:line references.

**Re-export tracing (Forge/Deep only):** After extracting changed files, check if any public exports from the package entry point (`__init__.py`, `index.ts`, `lib.rs`) are unresolved — particularly when a changed file is part of a module re-export chain. Follow the **Re-Export Tracing** protocol in `{extractionPatternsTracingData}` to trace unresolved symbols to their actual definition files.

### 2b. CCC Semantic Ranking (Forge+ and Deep with ccc)

**IF `tools.ccc` is true in forge-tier.yaml:**

Before aggregating extraction results, use CCC to assess semantic significance of changes:

1. Run `ccc_bridge.search("{skill_name}", source_root, top_k=15)` — **Tool resolution:** `/ccc` skill search (Claude Code), ccc MCP (Cursor), `ccc search` (CLI) — to get the skill's most semantically central files
2. Cross-reference the change manifest files with CCC results
3. Files appearing in BOTH the change manifest AND CCC's top results are **semantically significant changes** — flag them for priority in the merge step
4. Store `{ccc_significant_changes: [{file, score}]}` in context

This helps the merge step (section 4) prioritize which changes are most likely to affect the skill's core content vs. peripheral modifications.

CCC failures: skip ranking silently, all changes treated equally.

**Note on remote sources:** If `source_root` is a workspace clone, the CCC index may already exist from a prior forge and can be reused via `ccc search --refresh`. If the source is an ephemeral fallback clone, the clone path is not indexed by CCC — the search will return empty results and semantic ranking will be skipped. Deferred CCC indexing is implemented in create-skill step-03 but not in update-skill. All changes are treated equally for ephemeral remote sources.

**IF `tools.ccc` is false:** Skip this section silently.

### 3. Deep Tier QMD Enrichment (Conditional)

**ONLY if forge_tier == Deep:**

Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`.

Find the collection entry matching the current skill: look for an entry where `skill_name` matches the skill being updated AND `type` is `"extraction"`.

**If a matching extraction collection is found:**
Launch a subprocess that loads qmd_bridge and for each changed export:
1. Queries the `{skill_name}-extraction` collection for semantic context related to the export
2. Searches for usage patterns, documentation references, temporal history
3. Returns T2 evidence per export (usage frequency, context snippets, related concepts)

**If no matching collection found in registry:**
Log: "No QMD extraction collection found for {skill_name}. T2 enrichment skipped. Re-run [CS] Create Skill to generate the collection."
Continue without T2 enrichment — extraction still produces T1 results.

**If forge_tier != Deep:** Skip this section with notice: "QMD enrichment skipped (tier: {forge_tier})"

### 4. Compile Extraction Results

Aggregate all subprocess results into structured extraction data:

```
Extraction Results:
  files_extracted: [count]
  exports_extracted: [count]
  confidence_breakdown:
    T1: [count]
    T1-low: [count]
    T2: [count]

  Per-file extractions:
    {file_path}:
      exports:
        - name: {export_name}
          type: function|class|type|constant
          signature: {full signature}
          location: {file}:{start_line}-{end_line}
          confidence: T1|T1-low|T2
          parameters: [{name, type}]
          return_type: {type}
          docstring: {summary}
          qmd_evidence: {if Deep tier}
```

### 5. Display Extraction Summary and Auto-Proceed

"**Re-Extraction Complete:**

| Metric | Count |
|--------|-------|
| Files extracted | {count} |
| Exports extracted | {count} |
| T1 (AST-verified) | {count} |
| T1-low (pattern-matched) | {count} |
| T2 (QMD-enriched) | {count} |

**Proceeding to merge with existing skill...**"

### 6. Present MENU OPTIONS

Display: "**Proceeding to merge...**"

- After extraction results are compiled, immediately load, read entire file, then execute {nextStepFile}
- This is an auto-proceed step with no user choices

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all changed files have been extracted and results compiled will you load {nextStepFile} to begin the merge operation.

