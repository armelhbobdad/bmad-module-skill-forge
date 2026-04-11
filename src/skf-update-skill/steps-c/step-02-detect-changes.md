---
nextStepFile: './step-03-re-extract.md'
noChangeReportFile: './step-07-report.md'
---

# Step 2: Detect Changes

## STEP GOAL:

Compare current source code state against the provenance map to produce a complete change manifest identifying every changed, added, deleted, moved, and renamed file and export since last extraction.

## Rules

- Focus only on detecting and classifying changes — do not extract or merge
- Use subprocess Pattern 4 (parallel) when available; if unavailable, compare sequentially

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

4. Build the change manifest from translated gaps — no file-level timestamp comparison needed since source hasn't changed. **For each manifest entry, if the corresponding test report finding includes a source citation (`file:line` — e.g., a Gap Report row that cites `packages/utils/src/builder-utils.ts:33`), preserve it on the entry as `source_citation: {file, line}`.** Step-03 §0 uses this field to perform a live spot-check against source rather than flagging the export as `unknown`. If the test report lacks a citation for a finding, omit the field — step-03 will record the entry as `unknown` with no spot-check attempted.
5. Set `gap_count` from the total number of translated entries
6. **Skip to section 5** (Display Change Summary) with the gap-derived manifest

"**Gap-driven update mode.** Translating {gap_count} test report findings into change manifest — source drift detection skipped."

**If normal mode:** Continue with source drift detection below.

### 1. Scan Current Source State

Read the source directory at `{source_root}` and build a current file inventory:
- For each source file: record path, file size, last modified timestamp
- Focus on file types relevant to the skill (from provenance map file patterns)
- Exclude non-source files (node_modules, build artifacts, etc.)

### 1b. Discovered Authoritative Files Protocol (Mirror)

**Purpose:** mirror `skf-create-skill` §2a into update-skill. `skf-create-skill` §2a catches authoritative AI documentation files (`llms.txt`, `AGENTS.md`, `.cursorrules`, etc.) during **creation**. But a project may add these files *after* the skill was created — for example, an upstream project adopts an `llms.txt` convention six months into development. Without this mirror, update-skill would either miss the new file entirely (if it doesn't match the provenance map's file patterns) or classify it as a generic ADDED file in §2 Category A with no authoritative-file treatment. The mirror surfaces the discovery with the same P/S/U prompt create-skill uses, honoring any prior amendments.

**Skip this section entirely if:**

- `update_mode == "gap-driven"` (source hasn't drifted — we're verifying test report findings, not discovering new files), OR
- `metadata.json.source_type == "docs-only"` (no source tree to scan)

**Procedure (identical heuristics to create-skill §2a):**

1. **Walk the source tree.** Match file basenames against the heuristic list case-insensitively:
   - `llms.txt`, `llms-full.txt`
   - `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `COPILOT.md`
   - `.cursorrules`, `.windsurfrules`, `.clinerules`

2. **Cross-reference with provenance map.** For each match:
   - **Already in provenance map** (`entries[].source_file` or `file_entries[].source_file` contains this path): the file is already tracked. §2 will detect any drift in the normal flow. No action in §1b.
   - **Not in provenance map:** continue to amendment check.

3. **Check brief amendments.** Load `brief.scope.amendments[]` from `{forge_data_folder}/{skill_name}/skill-brief.yaml`. For each candidate not in the provenance map:
   - **`action: "promoted"` for this path exists:** the brief says this file should be in scope, but it's missing from the provenance map. This means the file was promoted by a prior run but its `file_entries[]` row is missing (e.g. provenance-map was regenerated from source without re-reading amendments). Add the path to `promoted_docs_new[]` (see step 6 below) with its content hash so §4 merge writes a new `file_entries[]` row. No user prompt — the decision was already made. Display: `"Honoring prior amendment: promoted {path} scheduled for file_entries write."`
   - **`action: "skipped"` for this path exists:** user previously declined promotion. Honor the skip silently. No prompt, no action.
   - **No amendment for this path:** continue to user prompt.

4. **Prompt.** For each unresolved candidate, present the same prompt as create-skill §2a:

   ```
   **New authoritative file discovered since skill creation**

   Path: {relative_path_from_source_root}
   Size: {line_count} lines, {bytes} bytes
   Matched heuristic: {basename}
   Provenance age: {days since skill creation}

   First 20 lines:
   {inline preview}

   This file was not present (or not in scope) when the skill was created. How should update-skill handle it?

   [P] Promote — extract in this update run AND amend brief for future runs
   [S] Skip    — leave out of scope AND record skip in amendments (no re-prompt)
   [U] Update  — halt this run and return to skf-brief-skill to refine scope
   ```

5. **Headless mode (`{headless_mode}` is true):** auto-select `[S] Skip` for every candidate — record `action: "skipped"`, `reason: "headless: no user to prompt"`, `workflow: "skf-update-skill"`. A non-interactive update run must never silently add files to scope.

6. **Apply decision:**

   - **[P] Promote:**
     1. Append `candidate.path` to `brief.scope.include` as a literal glob.
     2. Append a `brief.scope.amendments[]` entry: `action: "promoted"`, `path: candidate.path`, `reason: {user-provided or auto: "discovered post-creation — matched heuristic {basename}"}`, `heuristic: {basename}`, `date: {today ISO}`, `workflow: "skf-update-skill"`.
     3. **Write the amended brief back to disk immediately** at `{forge_data_folder}/{skill_name}/skill-brief.yaml`. Preserve all other fields.
     4. **Compute SHA-256 content hash** of `candidate.path` and add an entry to the in-context `promoted_docs_new[]` list: `{path, heuristic, size_bytes, line_count, content_hash}`. This list is consumed by §4 merge Priority 7 to write new `file_entries[]` rows — promoted docs do NOT go through §3 code re-extraction, which would produce ghost entries on non-code files.
     5. Display: `"Promoted {path} — brief amended, scheduled as new file_entries row for file_type doc."`

   - **[S] Skip:**
     1. Do NOT modify `scope.include`.
     2. Append a `brief.scope.amendments[]` entry: `action: "skipped"`, `path: candidate.path`, `reason: {user-provided or auto: "user declined promotion at update-skill §1b"}`, `heuristic: {basename}`, `date: {today ISO}`, `workflow: "skf-update-skill"`.
     3. **Write the amended brief back to disk** so neither update-skill nor create-skill will re-prompt in future runs.
     4. Display: `"Skipped {path} — decision recorded in amendments."`

   - **[U] Update:**
     1. Halt the workflow immediately.
     2. Display: `"Halting update-skill. Re-run skf-brief-skill to refine scope for {skill_name}, then re-run skf-update-skill."`
     3. Exit with status `halted-for-brief-refinement`. Change manifest is discarded — no partial writes.

7. **Summary.** After all candidates are resolved (or none were found):

   - `"Authoritative files mirror: {N} candidates, {P} promoted, {S} skipped, {A} pre-decided from amendments, {T} already tracked in provenance."`
   - If N = 0: `"Authoritative files mirror: no candidates."`

**Record for evidence report:** the update-skill evidence report appends `authoritative_files_mirror: {candidates: N, promoted: P, skipped: S, pre_decided: A, already_tracked: T, decisions: [{path, action, heuristic, reason}]}`.

**Interaction with §2 change detection:** promoted docs live in `promoted_docs_new[]`, NOT in the change manifest. But §2 Category A ("files in source but not in provenance map → ADDED") would still find the promoted doc files on disk and classify them as ADDED if nothing prevents it. The coordination mechanism is an explicit pre-filter exclusion set built in §2.0 (below) that every Category A subprocess worker receives as an input before it starts scanning. See §2.0 for the exact contract. The exclusion set is the only mechanism guaranteeing that parallel subprocesses cannot double-count `promoted_docs_new[]` paths — prose-level "skip any path" instructions cannot cross subprocess boundaries.

### 2. Compare Against Provenance Map

**If normal mode (provenance map available):**

#### 2.0 — Build Pre-filter Exclusion Set

Before launching parallel subprocesses, build a `change_detection_excludes` set in context that Category A subprocess workers must honor. Parallel subprocesses cannot see each other's in-memory state, so any coordination between §1b's decisions and §2's scan results must be pre-materialized into an explicit input the subprocesses receive.

The exclusion set includes:

- Every path in `promoted_docs_new[]` (populated by §1b). These files are tracked as `file_entries[]` via step-04 Priority 7, not through Category A code extraction. Without this exclusion, Category A would classify them as ADDED (because they're in source but not yet in the provenance map) and §3 re-extract would send them to AST extraction, producing ghost entries.
- Every source path in `file_entries[].source_file` where `file_type == "doc"` in the existing provenance map. These are already-tracked authoritative docs; any drift in them is handled by Category D (script/asset file changes), not Category A.

Record the set size: "**Change-detection excludes:** {count} paths ({promoted_docs_new count} new promotions + {existing doc file_entries count} already tracked)."

#### 2.1 — Launch Category Subprocesses

Launch subprocesses in parallel that compare source state against provenance map across these categories, returning change findings per category. **Every subprocess receives `change_detection_excludes` as an explicit input** and applies it to its file-path iteration loop.

**Category A — File-level changes:**
- Files in provenance map but missing from source → DELETED
- Files in source but not in provenance map AND not in `change_detection_excludes` → ADDED
- Files in `change_detection_excludes`: skip entirely (routed to file_entries via §1b → step-04 Priority 7, never through Category A)
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

