---
name: 'step-04-merge'
description: 'Merge new extractions into existing skill content, preserving all [MANUAL] sections with conflict resolution'

nextStepFile: './step-05-validate.md'
manualSectionRulesFile: '../data/manual-section-rules.md'
mergeConflictRulesFile: '../data/merge-conflict-rules.md'
---

# Step 4: Merge

## STEP GOAL:

Merge freshly extracted export data into the existing SKILL.md content while preserving all [MANUAL] sections. Detect and resolve conflicts where regenerated content overlaps developer-authored content. For stack skills, merge across all output files.

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
- ✅ [MANUAL] section preservation is the HIGHEST PRIORITY — zero content loss
- ✅ Every merge decision must be traceable and reversible
- ✅ When in doubt about [MANUAL] conflicts, HALT and ask the user

### Step-Specific Rules:

- 🎯 Focus ONLY on merging extractions into existing skill content
- 🚫 FORBIDDEN to delete or modify [MANUAL] section content
- 🚫 FORBIDDEN to write files — merge produces an edit plan for step 06 to execute
- 💬 If [MANUAL] conflicts detected: HALT and present to user for resolution
- 💬 If clean merge: auto-proceed without user interaction

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Load merge rules from data files for conflict resolution
- 📖 Track every merge operation for evidence report
- 🚫 FORBIDDEN to auto-resolve [MANUAL] conflicts — user must decide

## CONTEXT BOUNDARIES:

- Available: extraction results from step 03, existing SKILL.md content, [MANUAL] inventory from step 01, change manifest from step 02
- Focus: content merge and [MANUAL] preservation
- Limits: merge planning only — no file writes (step 06 executes the edit plan)
- Dependencies: step 03 must have produced extraction results

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
- MODIFIED_FILE: queue file for re-copy from source, update `file_entries` content_hash
- DELETED_FILE: queue file for removal from `scripts/` or `assets/`, remove from `file_entries`
- NEW_FILE: queue file for copy from source, add to `file_entries`
- Files in `scripts/[MANUAL]/` or `assets/[MANUAL]/` are never modified (user-authored)
- Update Section 7b manifest table to reflect changes
- Update `metadata.json` `scripts[]`/`assets[]` arrays and `stats.scripts_count`/`stats.assets_count`

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
- ONLY proceed when user selects 'C'

**If clean merge (no conflicts):**

Display: "**Clean merge — proceeding to validation...**"

#### Clean Merge Menu Handling Logic:

- Immediately load, read entire file, then execute {nextStepFile}

#### Clean Merge EXECUTION RULES:

- This is an auto-proceed path when no conflicts exist

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all merge operations are complete and any [MANUAL] conflicts have been resolved by the user will you load {nextStepFile} to begin validation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All [MANUAL] sections preserved with zero content loss
- Merge applied in correct priority order (delete → move → rename → modify → add)
- Every conflict presented to user for resolution (no auto-resolution of [MANUAL] conflicts)
- Stack skill files merged if applicable
- Merge results compiled with full accounting
- Clean merges auto-proceed; conflict merges require user [C]

### ❌ SYSTEM FAILURE:

- ANY [MANUAL] content lost or modified without user consent
- Auto-resolving [MANUAL] conflicts without user input
- Writing files during merge planning (edits are executed in step 06)
- Applying merge out of priority order
- Not detecting orphaned [MANUAL] blocks on deleted exports
- Not handling stack skill multi-file merge

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
