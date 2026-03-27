---
name: 'step-02-re-index'
description: 'Re-scan source code with current tier tools to build fresh extraction snapshot'

nextStepFile: './step-03-structural-diff.md'
outputFile: '{forge_data_folder}/{skill_name}/drift-report-{timestamp}.md'
---

# Step 2: Re-Index Source

## STEP GOAL:

Re-scan the source code using the current forge tier tools to build a fresh extraction snapshot. This snapshot will be compared against the original provenance map in Step 03 to detect structural drift.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor operating in Ferris Audit mode
- ✅ Every extraction must be precise — file paths, line numbers, signatures
- ✅ You enforce zero-hallucination: only extract what actually exists in source

### Step-Specific Rules:

- 🎯 Focus only on extracting current source state — do NOT compare yet
- 🚫 FORBIDDEN to perform any diff or comparison — that happens in Step 03
- 🚫 FORBIDDEN to skip files or take shortcuts in extraction
- 💬 Use subprocess Pattern 2 (per-file deep analysis) when available for AST extraction
- ⚙️ If subprocess unavailable, perform extraction in main thread file by file

## EXECUTION PROTOCOLS:

- 🎯 Extract all public exports from source using tier-appropriate tools
- 💾 Store current extraction as internal state for Step 03
- 📖 Update {outputFile} frontmatter stepsCompleted when complete
- 🚫 Do not append analysis sections to drift report — only update frontmatter

## CONTEXT BOUNDARIES:

- Available: Source path, forge tier, tool availability (from Step 01)
- Focus: Building a complete current-state extraction snapshot
- Limits: Extract only — no comparison, no judgment, no severity
- Dependencies: Step 01 must have loaded skill baseline and validated source path

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

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

**Tool resolution:** `gh_bridge` → `gh api` commands or direct file I/O if local. `ast_bridge` → ast-grep MCP tools (`find_code`, `find_code_by_rule`) or `ast-grep` CLI. `qmd_bridge` → QMD MCP tools (`search`, `vector_search`) or `qmd` CLI. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md).

### 2. Scan Source Files

Identify all source files in the source directory that contain public exports.

"**Scanning source files...**"

- List all relevant source files (exclude test files, config files, build artifacts)
- Count files to process
- Report: "Found {count} source files to extract."

### 3. Extract Current Exports

**DO NOT BE LAZY — For EACH source file, launch a subprocess that:**
1. Loads the source file
2. Extracts all public exports using tier-appropriate method
3. Records: export name, type, signature, file path, line number, confidence tier
4. Returns structured findings to parent

**If subprocess unavailable:** Perform extraction in main thread, processing each file sequentially.

**Build extraction snapshot:**
```
{
  "extraction_date": "{timestamp}",
  "confidence_tier": "{tier}",
  "source_root": "{source_path}",
  "files_scanned": {count},
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

### 4. Deep Tier Enhancement (Deep Only)

**IF forge tier is Deep:**

Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`.

Find the collection entry matching the current skill: look for an entry where `skill_name` matches the current skill being audited AND `type` is `"extraction"`.

**If a matching extraction collection is found:**
Query qmd_bridge against the `{skill_name}-extraction` collection for temporal context on each extracted export:
- When was this export first added?
- Has it been modified recently?
- What is its usage frequency across the codebase?
- How does the current extraction compare to the previously compiled skill content?

Append temporal metadata to each export in the snapshot.

**If no matching collection found in registry:**
Log: "No QMD extraction collection found for {skill_name}. Temporal enrichment skipped. Re-run [CS] Create Skill to generate the collection."
Continue without T2 enrichment — this is not an error.

**IF forge tier is Quick, Forge, or Forge+:**
Skip this section. Temporal context requires Deep tier.

### 4b. CCC Rename Detection (Forge+ and Deep with ccc)

**IF `tools.ccc` is true in forge-tier.yaml:**

For each export in the skill baseline that was NOT found at its recorded file path during re-extraction (potential "deleted" export):

1. Run `ccc_bridge.search("{export_name}", source_root, top_k=5)` — **Tool resolution:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `ccc search "{export_name}" --path {source_root} --top 5` (CLI) — to find candidate current locations
2. If CCC returns files containing the export name:
   - Run ast-grep verification on each candidate file
   - If verified at a new location: reclassify from "deleted" to "moved" with the new file:line reference
   - This reduces false-positive structural drift findings where exports were relocated, not removed
3. If CCC returns no results or verification fails: keep the "deleted" classification

CCC failures: skip rename detection silently, proceed with standard structural diff.

**IF `tools.ccc` is false:** Skip this section silently.

### 5. Validate Extraction Completeness

"**Extraction complete.**

| Metric | Value |
|--------|-------|
| Files scanned | {count} |
| Exports found | {total_exports} |
| Functions | {function_count} |
| Classes | {class_count} |
| Types/Interfaces | {type_count} |
| Constants | {const_count} |
| Confidence | {T1/T1-low/T2} |

**Proceeding to structural comparison...**"

### 6. Update Report and Auto-Proceed

Update {outputFile} frontmatter:
- Append `'step-02-re-index'` to `stepsCompleted`

### 7. Present MENU OPTIONS

Display: "**Proceeding to structural diff...**"

#### Menu Handling Logic:

- After extraction is complete and frontmatter updated, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed analysis step with no user choices
- Proceed directly to next step after extraction

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the extraction snapshot is complete with all source files processed will you then load and read fully `{nextStepFile}` to execute and begin structural comparison.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All source files scanned (none skipped)
- All public exports extracted with file:line references
- Confidence tier labels applied to every extraction
- Tier-appropriate tools used (AST for Forge+, text for Quick)
- Deep tier temporal context added if applicable
- Extraction snapshot complete and validated
- Frontmatter stepsCompleted updated

### ❌ SYSTEM FAILURE:

- Skipping source files or being lazy with extraction
- Not recording file:line references for each export
- Performing comparison in this step (comparison is Step 03)
- Missing confidence tier labels
- Hardcoded paths instead of frontmatter variables
- Not using subprocess Pattern 2 when available

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
