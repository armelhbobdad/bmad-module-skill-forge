---
name: 'step-04-parallel-extract'
description: 'Extract per-library documentation in parallel using tier-dependent tools'

nextStepFile: './step-05-detect-integrations.md'
---

# Step 4: Parallel Library Extraction

## STEP GOAL:

For each confirmed dependency, extract key exports, usage patterns, and API surface documentation using tier-dependent tools in parallel.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a dependency analyst operating in Ferris Architect mode
- ✅ Zero hallucination — only extract what exists in actual source code
- ✅ Every export and pattern must cite actual file:line references

### Step-Specific Rules:

- 🎯 Extract per-library using Pattern 4 (parallel): In Claude Code, use multiple parallel Agent tool calls or `run_in_background: true`. In Cursor, use parallel requests (IDE-dependent). In CLI, use `xargs -P` or background processes. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md)
- 💬 Each subprocess returns structured extraction, not raw file contents
- 🚫 FORBIDDEN to analyze cross-library integrations — that is step 05
- ⚙️ If parallel subprocess unavailable, extract libraries sequentially in main thread

## EXECUTION PROTOCOLS:

- 🎯 Launch parallel extraction per confirmed library
- 💾 Store per_library_extractions with confidence tier labels
- 📖 Report extraction summary before auto-proceeding
- 🚫 FORBIDDEN to proceed if zero libraries successfully extracted

## CONTEXT BOUNDARIES:

- From step 03: confirmed_dependencies[] (user-approved scope)
- From step 01: forge_tier, available_tools
- This step produces: per_library_extractions[] per library
- Each extraction includes: exports, patterns, confidence tier

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 0. Check Compose Mode

**If `compose_mode` is true:**

"**Extraction data already available from individual skills. Skipping extraction phase.**"

For each confirmed skill, load `{skills_output_folder}/{skill_dir}/SKILL.md` (where `skill_dir` is the subdirectory name stored in step-02, which may differ from the `name` field in metadata.json) into context. Build a `per_library_extractions[]` entry for each skill with the following fields:
- `library`: skill name from metadata.json
- `exports`: exports list extracted from the SKILL.md exports section
- `usage_patterns`: usage patterns from the SKILL.md usage section
- `confidence`: the skill's existing confidence tier (T1, T1-low, T2) — inherited directly

Display an extraction summary:

"**Loaded {N} skill extractions from existing skills.**

| Skill | Exports | Confidence | Status |
|-------|---------|------------|--------|
| {name} | {count} | {tier} | Loaded |"

Auto-proceed to next step.

**If not compose_mode:** Continue with section 1 (existing flow).

### 1. Prepare Extraction Plan

**AST Tool Availability Check (Forge/Deep only):**

This workflow operates on local project files and installed library packages. Remote source resolution does not apply — libraries are analyzed as they exist within the project's dependency tree.

**If AST tool is unavailable at Forge/Deep tier:**

⚠️ **Warn the user explicitly:** "AST tools are unavailable — extraction will use source reading (T1-low). Run [SF] Setup Forge to detect and configure AST tools for T1 confidence."

Degrade to Quick tier extraction. Note the degradation reason in context for the evidence report.

**Per-file AST failure handling:**

If ast-grep fails on an individual file (parse error, unsupported syntax), fall back to source reading for that file only. Label the affected file's results T1-low; unaffected files retain T1. Log a warning noting which file degraded and why.

For each library in `confirmed_dependencies`, determine extraction strategy based on forge tier:

**Quick Tier:**
- Read source files that import the library
- Extract usage patterns from import statements and function calls
- Identify key exports used in this project
- Confidence: T1-low (source reading inference)

**Forge Tier (adds to Quick):**
- Use ast_bridge to analyze structural exports from library source
- Extract function signatures, type definitions, class hierarchies
- Map parameter types and return types
- Confidence: T1 (AST-verified structural extraction)

**Deep Tier (adds to Forge):**
- Perform all Forge tier extractions (T1)
- Additionally: query existing QMD temporal collections for each library
- Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`
- For each library in `confirmed_dependencies`, search for a registry entry where `skill_name` matches the library name AND `type` is `"temporal"`
- **If a matching temporal collection exists:**
  - Query `qmd_bridge.search("{library_name} deprecated OR removed OR breaking change")` for deprecation context
  - Query `qmd_bridge.search("{library_name} migration OR upgrade")` for migration patterns
  - Query `qmd_bridge.search("{library_name} version issue OR bug OR workaround")` for version-specific warnings
  - **Tool resolution for qmd_bridge:** Use QMD MCP tools — `mcp__plugin_qmd-plugin_qmd__search` (Claude Code), qmd MCP server (Cursor), `qmd search "{query}"` (CLI). See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md)
  - Classify each result as T2-past (historical) or T2-future (planned changes) per confidence-tiers.md
  - Append temporal findings to the library's extraction as T2 annotations with `[QMD:{collection}:{doc}]` citations
- **If no matching temporal collection found:**
  - Log: "No temporal collection for {library_name}. T2 enrichment skipped."
  - Continue with T1/T1-low extraction only
- Confidence: T1 for structural (AST), T2 for temporal annotations (QMD-enriched)

### 2. Launch Parallel Extraction

**Launch subprocesses in parallel** (max_parallel_generation: 3–5 concurrent Agent tool calls in Claude Code, IDE-dependent in Cursor, CPU core count in CLI) — one per confirmed library:

Each subprocess:
1. Reads all files importing the library (from step 03 file lists)
2. Extracts key exports used in this project (functions, classes, types, constants)
3. Identifies usage patterns (initialization, configuration, common call patterns)
4. Labels confidence tier based on extraction method
5. Returns structured extraction to parent:

```
{
  library: "name",
  version: "from_manifest",
  exports_found: ["fn1", "fn2", "Type1"],
  usage_patterns: ["pattern description with file:line"],
  confidence: "T1|T1-low|T2",
  files_analyzed: count,
  warnings: [],
  temporal: {
    deprecated_exports: ["export_name — reason [QMD:collection:doc]"],
    migration_notes: ["note [QMD:collection:doc]"],
    version_warnings: ["warning [QMD:collection:doc]"],
    t2_annotation_count: count
  }
}
```

**If parallel subprocess unavailable:** Process libraries sequentially in main thread. Report progress after each library.

### 3. Handle Extraction Failures

For each library extraction:

**Success:** Store extraction result.

**Partial failure:** Store partial result with warnings, continue with other libraries.

**Complete failure:** Log failure reason, exclude from stack skill, note in report.

"**Warning:** Extraction failed for {library}: {reason}. Excluding from stack skill."

**If ALL extractions fail:** HALT — cannot produce meaningful stack skill.

### 4. Display Extraction Summary

"**Library extraction complete.**

| Library | Exports | Patterns | Confidence | Status |
|---------|---------|----------|------------|--------|
| {name} | {count} | {count} | {tier} | ✓ |
| {name} | {count} | {count} | {tier} | ✓ |
| {name} | — | — | — | ⚠ partial |

**Results:** {success_count}/{total_count} libraries extracted
**Confidence distribution:** T1: {count}, T1-low: {count}, T2: {count}
{If Deep tier:} **T2 enrichment:** {enriched_count}/{total_count} libraries had temporal collections available
{If libraries without temporal > 0:} **Tip:** Run [CS] Create Skill at Deep tier for individual libraries to generate temporal collections, then re-run [SS] for full T2 enrichment.
{If warnings:} **Warnings:** {warning_count} issues noted

**Proceeding to integration detection...**"

### 5. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All confirmed libraries have extraction attempted
- Extractions cite actual file:line references
- Confidence tiers correctly assigned per extraction method
- Partial failures handled gracefully (skip library, continue)
- Extraction summary displayed with accurate counts
- Auto-proceeded to step 05

### ❌ SYSTEM FAILURE:

- Fabricating exports not found in source code
- Not assigning confidence tiers to extractions
- Halting on single library failure (should degrade gracefully)
- Analyzing cross-library integrations (step 05's job)
- Returning raw file contents instead of structured extractions

**Master Rule:** Extract per-library only. Every export must trace to actual code. Degrade gracefully on individual failures.
