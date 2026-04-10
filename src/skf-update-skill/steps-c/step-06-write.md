---
nextStepFile: './step-07-report.md'
---

# Step 6: Write Updated Files

## STEP GOAL:

Verify the merged SKILL.md and stack reference files that step-04 section 6b wrote to disk, then write the derived artifacts (metadata.json, provenance-map.json, evidence-report.md, context-snippet.md, and the active symlink).

## Rules

- Focus only on verifying merged files and writing derived artifacts — merge content was already written in step-04
- Do not modify merged SKILL.md content — any mismatch detected during verification triggers HALT, not repair
- Do not skip provenance map update — critical for future audits
- HALT immediately on verification failure before writing any derived artifact — a partial-write skill package is worse than an unchanged one

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Verify SKILL.md Write

SKILL.md was written in step-04 section 6b. Verify the write landed intact before proceeding to any derived-artifact writes.

- Read `{skill_package}/SKILL.md` from disk
- Count `<!-- [MANUAL:*] -->` opening markers and compare against the [MANUAL] inventory captured in step-01
- Verify the resolved `{skill_package}` path matches the version directory step-04 wrote to (if the version changed, step-04 updated `{skill_package}` in context to point at the new path)
- If [MANUAL] count matches and path resolves: proceed to section 2
- **If [MANUAL] count does not match: HALT immediately.** Do not write `metadata.json`, `provenance-map.json`, or any other artifact — further writes would compound the inconsistency. Alert the user:

  "**[MANUAL] section count mismatch after write.** Expected {N} from step-01 inventory, found {M} on disk at `{skill_package}/SKILL.md`. The skill package is in an inconsistent state. Manual recovery required — restore the previous version from `{skill_group}/{previous_version}/` or fix the file in place, then re-run update-skill."

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

**If `no_reextraction == true` (gap-driven mode from step-03 section 0):**
No fresh extraction data exists for `verified` exports — their provenance entries stay byte-identical. Only apply targeted updates:
- For `moved` exports: update `source_line` (and `source_file` if different) to the new location recorded by the spot-check
- For `unknown` exports (not found in provenance map but present in gap manifest): add new entries with fields populated from step-04 merge output; `source_file`/`source_line` may be `null` if the export was undocumented and no fresh extraction was performed — leave these fields unset rather than writing stale values
- Do NOT overwrite `confidence`, `extraction_method`, `ast_node_type`, `params[]`, or `return_type` for `verified` exports
- Skip the "For each export in the updated skill" bullets below — they apply only to normal re-extraction mode

**For each export in the updated skill (normal mode only):**
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

### 5. Verify Stack Skill Reference File Writes (Conditional) and Regenerate context-snippet.md

**ONLY if skill_type == "stack":**

Stack reference files were written in step-04 section 6b. Verify each affected reference file that the merge produced:

- Read each `references/{library}.md` back from disk
- Read each `references/integrations/{pair}.md` back from disk
- Verify per-file [MANUAL] section counts match the per-file inventory captured in step-01
- **If any verification fails: HALT** using the same recovery protocol as section 1 — do not regenerate `context-snippet.md` or write any further derived artifact

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

### 6. Verify Derived Artifact Writes

SKILL.md was verified in section 1 and stack reference files in section 5 (both written by step-04 section 6b). This section verifies the artifacts this step wrote: `metadata.json`, `provenance-map.json`, `evidence-report.md`, and `context-snippet.md`.

For each derived artifact:
- Read back the file
- Confirm content matches expected output
- Report verification status

"**Write Verification:**

| File | Status |
|------|--------|
| SKILL.md | {VERIFIED in section 1} |
| metadata.json | {VERIFIED/FAILED} |
| provenance-map.json | {VERIFIED/FAILED} |
| evidence-report.md | {VERIFIED/FAILED} |
| context-snippet.md | {VERIFIED/FAILED} |
| {stack reference files...} | {VERIFIED in section 5} |

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

