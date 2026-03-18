---
name: 'step-03-re-extract'
description: 'Tier-aware AST extraction on changed files only, producing fresh exports with confidence tiers'

nextStepFile: './step-04-merge.md'
extractionPatternsData: '../../create-skill/data/extraction-patterns.md'
remoteSourceResolutionData: '../data/remote-source-resolution.md'
---

# Step 3: Re-Extract Changed Exports

## STEP GOAL:

Perform tier-aware extraction on only the changed files identified in step 02, producing fresh export data with confidence tier labels (T1/T1-low/T2) that will be merged into the existing skill in step 04.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a precision code analyst operating in Surgeon mode
- ✅ Zero-hallucination principle: every extracted instruction must include AST file:line citation
- ✅ Confidence tier labels are MANDATORY on all extracted content
- ✅ You bring AST-backed structural analysis; the source code provides ground truth

### Step-Specific Rules:

- 🎯 Focus ONLY on extracting changed exports — do not merge or modify existing skill
- 🚫 FORBIDDEN to extract unchanged files — only files in the change manifest
- 🚫 FORBIDDEN to modify SKILL.md — extraction produces intermediate data for step 04
- 💬 DO NOT BE LAZY — For EACH changed file, launch a subprocess for deep AST analysis (Pattern 2)
- ⚙️ If subprocess unavailable, perform extraction sequentially in main thread

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Produce structured extraction results per changed file
- 📖 Label every extraction with confidence tier
- 🚫 FORBIDDEN to hallucinate exports — only extract what exists in source

## CONTEXT BOUNDARIES:

- Available: change manifest from step 02, forge tier from step 01, source files
- Focus: extraction only — no merge, no write
- Limits: only changed files from manifest
- Dependencies: step 02 must have produced change manifest

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

**MCP source access check (before ephemeral clone):** If MCP source-reading tools are available (zread, deepwiki, gh API, or similar) and `source_repo` is set in metadata.json, use MCP tools to fetch only the changed files from the change manifest. This avoids ephemeral clone overhead entirely. MCP provides full source file content equivalent to a local read. If the fetched content is written to a temp file and analyzed with ast-grep, label confidence as T1. If AST is unavailable (the common case for MCP-fetched content), use pattern-based extraction and label confidence as T1-low.

**If MCP unavailable:** Load and follow `{remoteSourceResolutionData}` for ephemeral clone setup, version reconciliation, and AST tool unavailability handling.

**Quick tier (text pattern matching):**
- Extract function/class/type names via regex patterns
- Extract export statements via text matching
- Confidence: T1-low (pattern-matched, not AST-verified)

**Forge tier (AST structural extraction):**

⚠️ **CRITICAL:** Load and follow the **AST Extraction Protocol** from `{extractionPatternsData}`. Use the decision tree based on the number of changed files: prefer MCP `find_code()` for small sets, `find_code_by_rule()` with scoped YAML rules for medium sets, and CLI `--json=stream` with line-by-line streaming for large sets. Never use `ast-grep --json` (without `=stream`) — it loads the entire result set into memory and will fail on large codebases.

- Extract: function signatures, type definitions, class members, exported constants
- Extract: parameter types, return types, JSDoc/docstring comments
- Confidence: T1 (AST-verified structural truth)

**Deep tier (AST + QMD semantic enrichment):**
- Perform all Forge tier extractions (T1)
- Additionally: launch a subprocess that queries qmd_bridge for temporal context on changed exports, returning T2 evidence per export
- QMD provides: usage patterns, historical context, related documentation
- Confidence: T1 for structural, T2 for semantic enrichment

### 2. Extract Changed Files

DO NOT BE LAZY — For EACH file in the change manifest with status MODIFIED, ADDED, or RENAMED, launch a subprocess that:

1. Loads the source file
2. Performs tier-appropriate extraction (Quick/Forge/Deep)
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

**Re-export tracing (Forge/Deep only):** After extracting changed files, check if any public exports from the package entry point (`__init__.py`, `index.ts`, `lib.rs`) are unresolved — particularly when a changed file is part of a module re-export chain. Follow the **Re-Export Tracing** protocol in `{extractionPatternsData}` to trace unresolved symbols to their actual definition files.

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Every changed file from manifest extracted with tier-appropriate method
- All exports labeled with confidence tier (T1/T1-low/T2)
- AST file:line citations on every extracted export
- QMD enrichment performed for Deep tier (skipped with notice for Quick/Forge)
- Extraction results compiled with per-file detail
- Summary displayed before auto-proceeding
- No unchanged files extracted

### ❌ SYSTEM FAILURE:

- Extracting unchanged files (wasting resources)
- Missing confidence tier labels on any export
- Hallucinating exports not present in source code
- Skipping QMD enrichment at Deep tier
- Modifying SKILL.md or any existing artifacts during extraction

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
