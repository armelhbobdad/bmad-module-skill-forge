---
nextStepFile: './step-05-validate.md'
manualSectionRulesFile: 'references/manual-section-rules.md'
mergeConflictRulesFile: 'references/merge-conflict-rules.md'
---

# Step 4: Merge

## STEP GOAL:

Merge freshly extracted export data into the existing SKILL.md content while preserving all [MANUAL] sections. Detect and resolve conflicts where regenerated content overlaps developer-authored content. For stack skills, merge across all output files.

## Rules

- Focus only on merging extractions into existing skill content
- Never delete or modify [MANUAL] section content
- Write merged SKILL.md (and stack reference files) directly to disk at section 6b — Claude Code's Edit/Write tools commit on call, so there is no held-in-memory "edit plan" primitive; subsequent steps validate and verify against the on-disk files
- If [MANUAL] conflicts detected: halt and present to user. If clean merge: auto-proceed

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Merge Rules

Load {manualSectionRulesFile} for [MANUAL] detection and preservation patterns.
Load {mergeConflictRulesFile} for change category merge strategies and priority order.

### 2. Extract [MANUAL] Blocks

From the [MANUAL] inventory captured in step 01:
- Extract every `<!-- [MANUAL:section-name] -->` ... `<!-- [/MANUAL:section-name] -->` block
- Map each block to its parent section heading
- Store blocks in a preservation map keyed by section-name

### 3. Apply Merge by Priority Order

Follow the merge priority order from {mergeConflictRulesFile}:

**Priority 1 — Process DELETED exports:**
- Remove generated content for deleted exports
- Check if deleted export has attached [MANUAL] blocks
- If [MANUAL] attached: flag as ORPHAN conflict (do not remove)
- If no [MANUAL]: remove generated content cleanly

**Priority 2 — Process MOVED exports:**
- Update file:line citations in generated content
- Update provenance map file references
- [MANUAL] blocks unaffected (content unchanged)

**Priority 3 — Process RENAMED exports:**
- Replace old identifier with new identifier in generated content
- Check if [MANUAL] blocks reference old identifier name
- If referenced: flag as STALE_REFERENCE conflict

**Priority 4 — Process MODIFIED exports:**
- Replace generated content for the export with fresh extraction
- Preserve [MANUAL] blocks adjacent to the export
- Check for position conflicts (new content shifts [MANUAL] block)
- If position conflict: flag as POSITION conflict

**Priority 5 — Process NEW exports:**
- Append new export content to appropriate section
- Place before any [MANUAL] blocks at section boundary
- No conflicts expected (new content, no existing [MANUAL])

**Priority 6 — Process script/asset file changes (from Category D in change manifest):**

Category D operates on every `file_entries[]` row regardless of `file_type`. Handle each entry by its type:

- **`file_type: "script"` or `file_type: "asset"`:**
  - MODIFIED_FILE: queue file for re-copy from source, update `file_entries` content_hash
  - DELETED_FILE: queue file for removal from `scripts/` or `assets/`, remove from `file_entries`
  - NEW_FILE: queue file for copy from source, add to `file_entries`
  - Files in `scripts/[MANUAL]/` or `assets/[MANUAL]/` are never modified (user-authored)
  - Update Section 7b manifest table to reflect changes
  - Update `metadata.json` `scripts[]`/`assets[]` arrays and `stats.scripts_count`/`stats.assets_count`

- **`file_type: "doc"`** (authoritative docs promoted by §2a/§1b):
  - MODIFIED_FILE: update `file_entries` content_hash only. **Do NOT copy the file** — doc-type entries are source-tracked but not bundled. Record the drift in the update report.
  - DELETED_FILE: remove from `file_entries`. **Do NOT remove any file from the skill package** (there was nothing copied). Record the removal in the update report — a deleted authoritative doc is a meaningful upstream signal.
  - NEW_FILE: this path is not used for doc type — new doc entries come from Priority 7 below, not from Category D. If Category D reports NEW_FILE with `file_type: "doc"`, log a warning and route to Priority 7.

**Priority 7 — Process new authoritative docs (from `promoted_docs_new[]` populated by §1b):**

For each entry in the in-context `promoted_docs_new[]` list:

- Add a new row to `file_entries[]` in the merged provenance map with:
  - `file_name`: `"docs/authoritative/{source_path}"` (synthetic namespace — see skill-sections.md for convention)
  - `file_type`: `"doc"`
  - `source_file`: the path from `promoted_docs_new[].path`
  - `content_hash`: the hash pre-computed by §1b
  - `confidence`: `"T1-low"`
  - `extraction_method`: `"promoted-authoritative"`
- Do NOT copy the file into the skill package (doc type is source-tracked, not bundled).
- Record in the update report: `"Added authoritative doc: {path} (heuristic: {basename})"`.

**If `promoted_docs_new[]` is empty:** skip Priority 7 silently. No report entry.

### 4. Check for Conflicts

Scan all merge operations for flagged conflicts:

**If ZERO conflicts:**
- Report clean merge
- Auto-proceed to step 05

**If conflicts detected:**

Present each conflict to user:

"**[MANUAL] Conflict Resolution Required:**

**Conflict {N} of {total}:** {conflict_type}

{Detailed description of the conflict with before/after context}

**Options:**
- **[K]eep** — Preserve [MANUAL] content as-is, adjust generated content around it
- **[R]emove** — Remove the [MANUAL] block (content will be lost)
- **[E]dit** — Show me both versions, I'll provide the resolution

Select: [K] Keep / [R] Remove / [E] Edit"

Process each conflict with user's decision.

### 5. Stack Skill Merge (Conditional)

**ONLY if skill_type == "stack":**

Apply the same merge process to each stack output file:
- `references/{library}.md` — merge per-library changes, preserve [MANUAL] blocks
- `references/integrations/{pair}.md` — merge per-integration-pair
- `metadata.json` — regenerate completely (no [MANUAL] support)
- `context-snippet.md` — regenerate completely (no [MANUAL] support)

Report stack file merge status for each file.

**If skill_type != "stack":** Skip with notice: "Individual skill — single file merge."

### 6. Compile Merge Results

Build merge result summary:

```
Merge Results:
  exports_updated: [count]
  exports_added: [count]
  exports_removed: [count]
  exports_moved: [count]
  exports_renamed: [count]

  manual_sections_preserved: [count]
  manual_conflicts_resolved: [count]
  manual_orphans_kept: [count]
  manual_orphans_removed: [count]

  stack_files_merged: [count] (if stack skill)
```

### 6b. Write Merged Files to Disk

Write the merged content produced by sections 3–5 directly to disk now. Later steps read from these files for validation and verification. The write must happen exactly once, here.

**Write SKILL.md:**
- Use the `Edit` or `Write` tool to write merged SKILL.md content to `{skill_package}/SKILL.md`
- Preserve UTF-8 encoding
- If the source version detected during step-03 differs from the previous metadata version, create the new `{skill_package}` directory (`{skill_group}/{new_version}/`) first and write there — the previous version's directory is preserved on disk. Update `{skill_package}` in context to point at the new path.

**Write stack reference files (if `skill_type == "stack"`):**
- For each affected file from section 5, use `Edit` or `Write` to write:
  - `references/{library}.md` with merged per-library content
  - `references/integrations/{pair}.md` with merged per-integration content
- Preserve [MANUAL] blocks exactly as captured in section 2.

**Do NOT write here:**
- `metadata.json`, `provenance-map.json`, `evidence-report.md` — derived from merge + validation output, written by step-06 sections 2–4
- `context-snippet.md` — regenerated from the on-disk SKILL.md + metadata.json by step-06 section 5

**Halt-on-tool-failure:** If any `Edit`/`Write` call errors (permission denied, disk full, path invalid, etc.), halt and report the failure — do not proceed to step-05 validation. The skill package may be in a partial state and will need manual recovery before re-running update-skill.

### 7. Display Merge Summary

"**Merge Complete:**

| Metric | Count |
|--------|-------|
| Exports updated | {count} |
| Exports added | {count} |
| Exports removed | {count} |
| [MANUAL] sections preserved | {count} |
| Conflicts resolved | {count} |"

### 8. Present MENU OPTIONS

**If conflicts were resolved (user interaction occurred):**

Display: "**Merge complete with conflict resolution. Select:** [C] Continue to Validation"

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other: help user respond, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after conflict resolution
- **GATE [default: C if clean merge]** — If `{headless_mode}` and merge is clean (no [MANUAL] conflicts): auto-proceed with [C] Continue, log: "headless: clean merge, auto-continue". If conflicts exist, HALT even in headless mode — conflicts require human judgment.
- ONLY proceed when user selects 'C'

**If clean merge (no conflicts):**

Display: "**Clean merge — proceeding to validation...**"

#### Clean Merge Menu Handling Logic:

- Immediately load, read entire file, then execute {nextStepFile}

#### Clean Merge EXECUTION RULES:

- This is an auto-proceed path when no conflicts exist

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all merge operations are complete and any [MANUAL] conflicts have been resolved by the user will you load {nextStepFile} to begin validation.

