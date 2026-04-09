---
nextStepFile: './step-07-report.md'
---

# Step 6: Write Updated Files

## STEP GOAL:

Write all updated skill artifacts to disk: the merged SKILL.md, updated provenance-map.json with new timestamps and mappings, updated evidence-report.md with the update operation trail, and for stack skills, all affected reference files.

## Rules

- Focus only on writing files — all merge and validation is complete
- Write exactly what was produced — do not modify merged content
- Do not skip provenance map update — critical for future audits

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Write Updated SKILL.md

Write the merged SKILL.md content to `{skill_package}/SKILL.md`:
- Overwrite the existing file with merged content
- Preserve file encoding (UTF-8)
- Verify write by reading back and confirming [MANUAL] section count matches expected

If the version changed (source version differs from the previous metadata version), write to the new `{skill_package}` (creating the version directory if needed). The previous version's directory is preserved on disk.

### 2. Write Updated metadata.json

Update `{skill_package}/metadata.json`:
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

Write to `{forge_version}/provenance-map.json`:

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

Append update operation section to `{forge_version}/evidence-report.md` (create the file with a standard header if it does not yet exist):

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

### 5. Write Stack Skill Reference Files (Conditional) and Regenerate context-snippet.md

**ONLY if skill_type == "stack":**

For each affected reference file from the merge:
- Write updated `references/{library}.md` files
- Write updated `references/integrations/{pair}.md` files
- Verify [MANUAL] sections preserved in each reference file

**For all skills (both single and stack) — regenerate `context-snippet.md`:**

Per `knowledge/version-paths.md` "Writing Workflows (CS, QS, SS, US)", update-skill is a writing workflow that MUST write all deliverables to `{skill_package}`. `context-snippet.md` is one of those deliverables and goes stale whenever exports, version, or gotchas change.

Regenerate the snippet using the format from the matching template file:

- For single skills: `skf-create-skill/assets/skill-sections.md` (pipe-delimited indexed format)
- For stack skills: `skf-create-stack-skill/assets/stack-skill-template.md`

Use the **flat draft form** for the `root:` path in the draft snippet: `root: skills/{skill-name}/`. The per-IDE skill root (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/` — see `skf-export-skill/assets/managed-section-format.md`) is applied later by `export-skill` step-03 when the skill is exported. Do not choose an IDE-specific prefix in update-skill — that is an export-time decision that depends on config.yaml.

Pull values for the regenerated snippet from the updated metadata.json (version, top exports), the merged SKILL.md (section anchors, inline summaries), and the evidence report (new gotchas). If gotchas cannot be derived from the updated evidence but the prior snippet has a `|gotchas:` line, carry forward the prior line with the `[CARRIED]` marker — see `skf-export-skill/steps-c/step-03-generate-snippet.md` for the carry-forward protocol (one-cycle limit).

Write the regenerated snippet to `{skill_package}/context-snippet.md`, preserving file permissions.

**If skill_type == "stack"**, also verify that the reference file updates from the first half of this section have been applied before writing the snippet so the stack snippet reflects the newest integration list.

### 5b. Update Active Symlink (If Version Changed)

If the version was incremented or changed in section 2 (metadata.json update):
- Create or update the `active` symlink at `{skill_group}/active` pointing to the new `{version}`
- If the symlink already exists, remove it first and recreate

```
{skill_group}/active -> {version}
```

If the version did not change, the existing symlink already points to the correct version -- no action needed.

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
- Run: `npx skill-check check {skill_package} --fix --format json --no-security-scan`
- **Context sync after --fix:** If `fixed[]` is non-empty (i.e., `--fix` modified files on disk), re-read the modified SKILL.md to update the in-context copy. This prevents silent divergence between the in-context SKILL.md and the on-disk version that step-07-report will reference.
- If `body.max_lines` reported, prefer selective split — extract only the largest Tier 2 section(s) to `references/`, keeping Tier 1 inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). Fall back to `npx skill-check split-body {skill_package} --write` if not feasible. Verify anchors resolve after split.
- Run: `npx skill-check diff` if original version was preserved
- Run: `npx skill-check check {skill_package} --format json` for security scan

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

