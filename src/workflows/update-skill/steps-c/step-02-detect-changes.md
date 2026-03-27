---
name: 'step-02-detect-changes'
description: 'Diff source file timestamps and hashes against provenance map to identify all changes since last extraction'

nextStepFile: './step-03-re-extract.md'
noChangeReportFile: './step-07-report.md'
---

# Step 2: Detect Changes

## STEP GOAL:

Compare current source code state against the provenance map to produce a complete change manifest identifying every changed, added, deleted, moved, and renamed file and export since last extraction.

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
- ✅ Zero-hallucination principle: every change must be verified against actual source state
- ✅ Clinical, terse communication — report changes factually with file:line references
- ✅ You bring provenance-driven analysis; the source code provides ground truth

### Step-Specific Rules:

- 🎯 Focus ONLY on detecting and classifying changes — do not extract or merge
- 🚫 FORBIDDEN to modify any files — read-only change detection
- 🚫 FORBIDDEN to re-extract content — that is step 03
- 💬 Use subprocess Pattern 4 (parallel): In Claude Code, use multiple parallel Agent tool calls or `run_in_background: true`. In Cursor, use parallel requests (IDE-dependent). In CLI, use `xargs -P` or background processes. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md)
- ⚙️ If subprocess unavailable, perform comparison sequentially in main thread

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Build change manifest with categorized findings
- 📖 Track change counts by category for summary
- 🚫 FORBIDDEN to proceed if source path is inaccessible

## CONTEXT BOUNDARIES:

- Available: loaded baseline from step 01 (SKILL.md, metadata.json, provenance-map.json, forge-tier, source_root)
- Focus: change detection only — no extraction, no merge
- Limits: read-only operations on source code
- Dependencies: step 01 must have loaded all artifacts successfully

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 0. Check for Test Report Input (Gap-Driven Mode)

**If `update_mode == "gap-driven"` (set in step-01 via `--from-test-report`):**

Load the test report at `{test_report_path}` and extract findings:

1. Read the **Gap Report** section — each gap entry has severity, category, and description
2. Read the **Coverage Analysis** section — each per-export row has documented/missing/mismatch status
3. Translate findings into change manifest format:

| Gap Severity | Gap Type | Change Category |
|-------------|----------|-----------------|
| Critical | Missing export documentation | NEW_EXPORT (undocumented public API) |
| High | Signature mismatch | MODIFIED_EXPORT (signature needs update) |
| Medium | Missing type/interface docs | NEW_EXPORT (undocumented type) |
| Medium | Stale documentation | MODIFIED_EXPORT (docs reference removed export) |
| Low | Missing metadata/examples | metadata update |

4. Build the change manifest from translated gaps — no file-level timestamp comparison needed since source hasn't changed
5. Set `gap_count` from the total number of translated entries
6. **Skip to section 5** (Display Change Summary) with the gap-derived manifest

"**Gap-driven update mode.** Translating {gap_count} test report findings into change manifest — source drift detection skipped."

**If normal mode:** Continue with source drift detection below.

### 1. Scan Current Source State

Read the source directory at `{source_root}` and build a current file inventory:
- For each source file: record path, file size, last modified timestamp
- Focus on file types relevant to the skill (from provenance map file patterns)
- Exclude non-source files (node_modules, build artifacts, etc.)

### 2. Compare Against Provenance Map

**If normal mode (provenance map available):**

Launch subprocesses in parallel that compare source state against provenance map across these categories, returning change findings per category:

**Category A — File-level changes:**
- Files in provenance map but missing from source → DELETED
- Files in source but not in provenance map → ADDED
- Files in both but with different timestamps/sizes → MODIFIED
- Files with same content at different paths → MOVED

**Category B — Export-level changes (for MODIFIED files only):**
- For each modified file, compare export list against provenance map exports
- Exports in provenance but not in source → DELETED_EXPORT
- Exports in source but not in provenance → NEW_EXPORT
- Exports with changed signatures/types → MODIFIED_EXPORT
- Exports at different line numbers but same content → MOVED_EXPORT

**Category C — Rename detection:**
- Cross-reference deleted files/exports with added files/exports
- If content similarity > 80%: classify as RENAMED instead of deleted+added. **Similarity mechanism by tier:** Quick: compare file size ratio (within 20%) and export name overlap (>70% of exports match by name). Forge and above: use ast-grep to compare export signatures between the deleted and added files. Forge+/Deep: use CCC semantic similarity when available

**Category D — Script/asset file changes:**
- Compare `file_entries` from provenance-map.json against current source files
- For each file_entry: compute current SHA-256 content hash, compare against stored hash
- Files with changed hashes → MODIFIED_FILE
- Files in provenance but missing from source → DELETED_FILE
- Files in source matching detection patterns (scripts/, bin/, assets/, templates/) but not in provenance → NEW_FILE
- Files in `scripts/[MANUAL]/` or `assets/[MANUAL]/` → SKIP (user-authored, preserved)

Aggregate all subprocess results into a unified change manifest.

**If degraded mode (no provenance map):**
- All source files are treated as MODIFIED
- All exports will be fully re-extracted in step 03
- Skip export-level comparison

### 3. Build Change Manifest

Compile the change manifest with structured entries:

```
Change Manifest:
  files_changed: [count]
  files_added: [count]
  files_deleted: [count]
  files_moved: [count]

  exports_modified: [count]
  exports_new: [count]
  exports_deleted: [count]
  exports_renamed: [count]
  exports_moved: [count]

  scripts_modified, scripts_added, scripts_deleted: {counts}
  assets_modified, assets_added, assets_deleted: {counts}

  Per-file detail:
    {file_path}:
      status: MODIFIED|ADDED|DELETED|MOVED
      exports_affected: [{export_name, change_type, old_line, new_line}]
```

### 4. Check for No-Change Shortcut

**If zero changes detected across all categories:**

"**No changes detected.** Source code matches provenance map exactly.

The skill `{skill_name}` is current — no update needed.

**Skipping to report step...**"

→ Skip steps 03-06, immediately load {noChangeReportFile} with "no changes" status.

### 5. Display Change Summary and Auto-Proceed

"**Change Detection Complete:**

| Category | Count |
|----------|-------|
| Files modified | {count} |
| Files added | {count} |
| Files deleted | {count} |
| Files moved/renamed | {count} |
| Exports affected | {total_export_changes} |

**Proceeding to re-extraction of {affected_file_count if normal mode, or gap_count if gap-driven mode} changes...**"

### 6. Present MENU OPTIONS

Display: "**Proceeding to re-extraction...**"

#### Menu Handling Logic:

- After change manifest is built, immediately load, read entire file, then execute {nextStepFile}
- **EXCEPTION:** If no changes detected (section 4), load {noChangeReportFile} instead

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after change detection completes

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the change manifest is fully built will you load {nextStepFile} to begin re-extraction. If no changes detected, skip to {noChangeReportFile}.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Every file in provenance map compared against current source state
- Changes categorized correctly (modified, added, deleted, moved, renamed)
- Export-level changes detected for modified files
- Change manifest built with per-file detail
- No-change shortcut correctly routes to report step
- Summary displayed before auto-proceeding

### ❌ SYSTEM FAILURE:

- Not comparing all files in provenance map
- Missing category of changes (e.g., not detecting deletions)
- Modifying any files during detection
- Not detecting rename patterns (treating as delete+add)
- Proceeding with empty change manifest when changes exist

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
