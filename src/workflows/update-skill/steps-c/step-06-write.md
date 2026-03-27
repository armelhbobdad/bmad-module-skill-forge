---
name: 'step-06-write'
description: 'Write updated SKILL.md, provenance-map.json, evidence-report.md, and stack reference files'

nextStepFile: './step-07-report.md'
---

# Step 6: Write Updated Files

## STEP GOAL:

Write all updated skill artifacts to disk: the merged SKILL.md, updated provenance-map.json with new timestamps and mappings, updated evidence-report.md with the update operation trail, and for stack skills, all affected reference files.

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
- ✅ File writes must be atomic — complete all writes or none
- ✅ Every write must be verified after completion
- ✅ Provenance metadata must accurately reflect the update operation

### Step-Specific Rules:

- 🎯 Focus ONLY on writing files — all merge and validation is complete
- 🚫 FORBIDDEN to modify merged content during write — write exactly what was produced
- 🚫 FORBIDDEN to skip provenance map update — this is critical for future audits
- 💬 Verify each file after writing to confirm integrity

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Write all files in the correct locations
- 📖 Update provenance map with current timestamps
- 🚫 FORBIDDEN to proceed if any write fails

## CONTEXT BOUNDARIES:

- Available: merged content from step 04, validation results from step 05, extraction results from step 03, change manifest from step 02
- Focus: file I/O operations — write and verify
- Limits: write only to skill output and forge data directories
- Dependencies: steps 02-05 must all be complete

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Write Updated SKILL.md

Write the merged SKILL.md content to `{skills_output_folder}/{skill_name}/SKILL.md`:
- Overwrite the existing file with merged content
- Preserve file encoding (UTF-8)
- Verify write by reading back and confirming [MANUAL] section count matches expected

### 2. Write Updated metadata.json

Update `{skills_output_folder}/{skill_name}/metadata.json`:
- Update `version`: if a source version was detected during re-extraction and differs from the current metadata version, use the source version; otherwise increment patch version
- Update `generation_date` timestamp to current ISO-8601 date
- Update `exports` array to reflect current export list
- Update `stats` from re-extraction results:
  - `exports_documented`: count of exports with documentation in the merged skill
  - `exports_public_api`: count of exports from public entry points (`__init__.py`, `index.ts`, `lib.rs`, or equivalent)
  - `exports_internal`: count of all other non-underscore-prefixed exports
  - `exports_total`: `exports_public_api` + `exports_internal`
  - `public_api_coverage`: `exports_documented / exports_public_api` (`null` if `exports_public_api` is 0)
  - `total_coverage`: `exports_documented / exports_total` (`null` if `exports_total` is 0)
- Update `confidence_distribution` from re-extraction results:
  - `confidence_distribution.t1`, `confidence_distribution.t1_low`, `confidence_distribution.t2`, `confidence_distribution.t3`: update counts from re-extraction results
  - `scripts_count`, `assets_count`: update from re-extraction results if scripts/assets changed
- For stack skills: update `library_count`, `integration_count` if changed

### 3. Write Updated provenance-map.json

Write to `{forge_data_folder}/{skill_name}/provenance-map.json`:

**For each export in the updated skill:**
- Update `export_name` if renamed
- Update `params[]` array if parameters changed (add, remove, or modify individual entries)
- Update `return_type` if changed
- Update `source_file` if moved
- Update `source_line` from fresh extraction
- Update `confidence` from extraction results
- Update `extraction_method` and `ast_node_type` if re-extracted with different tools

**For deleted exports:**
- Remove entry from provenance map

**For new exports:**
- Add new entry with full structured fields: `export_name`, `export_type`, `params[]`, `return_type`, `source_file`, `source_line`, `confidence`, `extraction_method`, `ast_node_type`

**For script/asset file changes (if `file_entries` exists):**
- MODIFIED_FILE: copy updated file to `scripts/` or `assets/`, update `content_hash` in `file_entries`
- DELETED_FILE: remove file from `scripts/` or `assets/`, remove entry from `file_entries`
- NEW_FILE: copy file to `scripts/` or `assets/`, add entry to `file_entries` with `file_name`, `file_type`, `source_file`, `confidence: "T1-low"`, `extraction_method: "file-copy"`, `content_hash`

**Add update operation metadata:**
```json
{
  "last_update": "{current_date}",
  "update_type": "{incremental if normal mode | full if degraded_mode}",
  "files_changed": {count},
  "exports_affected": {count},
  "confidence_tier": "{tier}",
  "manual_sections_preserved": {count}
}
```

### 4. Write Updated evidence-report.md

Append update operation section to `{forge_data_folder}/{skill_name}/evidence-report.md` (create the file with a standard header if it does not yet exist):

```markdown
## Update Operation — {current_date}

**Trigger:** {manual / audit-skill chain}
**Forge Tier:** {tier}
**Mode:** {normal / degraded}

### Changes Detected
- Files modified: {count}
- Files added: {count}
- Files deleted: {count}
- Exports affected: {total}

### Merge Results
- Exports updated: {count}
- Exports added: {count}
- Exports removed: {count}
- [MANUAL] sections preserved: {count}
- Conflicts resolved: {count}

### Validation Summary
- Spec compliance: {PASS/WARN/FAIL}
- [MANUAL] integrity: {PASS/WARN/FAIL}
- Confidence tiers: {PASS/WARN/FAIL}
- Provenance: {PASS/WARN/FAIL}
```

### 5. Write Stack Skill Reference Files (Conditional)

**ONLY if skill_type == "stack":**

For each affected reference file from the merge:
- Write updated `references/{library}.md` files
- Write updated `references/integrations/{pair}.md` files
- Regenerate `context-snippet.md` with updated export summaries
- Verify [MANUAL] sections preserved in each reference file

**If skill_type != "stack":** Skip reference file updates. However, if exports changed (added, removed, or renamed), warn: "⚠️ `context-snippet.md` was NOT updated — exports have changed. Run **[EX] Export Skill** to regenerate the context snippet and update CLAUDE.md/AGENTS.md."

### 6. Verify All Writes

For each file written:
- Read back the file
- Confirm content matches expected output
- Confirm [MANUAL] sections are intact (count comparison)
- Report verification status

"**Write Verification:**

| File | Status |
|------|--------|
| SKILL.md | {VERIFIED/FAILED} |
| metadata.json | {VERIFIED/FAILED} |
| provenance-map.json | {VERIFIED/FAILED} |
| evidence-report.md | {VERIFIED/FAILED} |
| {stack reference files...} | {VERIFIED/FAILED} |

**All files written and verified.**"

### 7. Run Post-Write Validation (Deferred from Step 05)

External tool checks deferred from step-05 now run against the written files:

**If skill-check available:**
- Run: `npx skill-check check {skills_output_folder}/{skill_name} --fix --format json --no-security-scan`
- **Context sync after --fix:** If `fixed[]` is non-empty (i.e., `--fix` modified files on disk), re-read the modified SKILL.md to update the in-context copy. This prevents silent divergence between the in-context SKILL.md and the on-disk version that step-07-report will reference.
- If `body.max_lines` reported, prefer selective split — extract only the largest Tier 2 section(s) to `references/`, keeping Tier 1 inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). Fall back to `npx skill-check split-body {skills_output_folder}/{skill_name} --write` if not feasible. Verify anchors resolve after split.
- Run: `npx skill-check diff` if original version was preserved
- Run: `npx skill-check check {skills_output_folder}/{skill_name} --format json` for security scan

Record findings in the evidence report (section 4). These are advisory — do not block on warnings.

**If skill-check unavailable:** Skip with note — structural checks from step-05 are sufficient.

### 8. Present MENU OPTIONS

Display: "**Proceeding to report...**"

#### Menu Handling Logic:

- After all writes verified and post-write validation complete, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to report after verification

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all files have been written and verified will you load {nextStepFile} to display the change report.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- SKILL.md written with all merged content and [MANUAL] sections intact
- metadata.json updated with new version, timestamp, export counts
- provenance-map.json updated with current file:line references and timestamps
- evidence-report.md appended with update operation record
- Stack reference files updated if applicable
- All writes verified by read-back confirmation

### ❌ SYSTEM FAILURE:

- Any [MANUAL] section content different after write (integrity violation)
- Skipping provenance map update
- Not verifying writes after completion
- Writing partial content (incomplete merge result)
- Not updating metadata version
- Leaving stale provenance entries for deleted exports

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
