---
nextStepFile: 'shared/health-check.md'
---

# Step 7: Report

## STEP GOAL:

Present a comprehensive change summary showing what was updated, [MANUAL] sections preserved, confidence tier breakdown, and recommend next workflow actions in the SKF chain.

## Rules

- Focus only on reporting — all operations are complete; do not modify any files
- Present clear, actionable summary with next step recommendations
- Chains to shared health check via `{nextStepFile}` after completion

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Handle No-Change Shortcut

**If routed here from step 02 with no changes detected:**

"**Update Skill Report: {skill_name}**

**Status:** No changes detected

Source code matches provenance map exactly. The skill `{skill_name}` is current — no update was needed.

**Provenance age:** {days} days since last extraction
**Forge tier:** {tier}

**Recommendation:** No action required. Run audit-skill periodically to monitor for drift."

→ Load and execute `{nextStepFile}` for workflow self-improvement check.

### 2. Present Change Summary

"**Update Skill Report: {skill_name}**

---

### Operation Summary

| Metric | Value |
|--------|-------|
| **Skill** | {skill_name} ({single/stack}) |
| **Forge Tier** | {tier} |
| **Mode** | {normal/degraded} |
| **Duration** | {step count} steps |

### Changes Applied

| Category | Count |
|----------|-------|
| Files modified | {count} |
| Files added | {count} |
| Files deleted | {count} |
| Files moved/renamed | {count} |
| **Total exports affected** | {count} |

### Export Changes

| Change Type | Count |
|-------------|-------|
| Updated (signature/type change) | {count} |
| Added (new exports) | {count} |
| Removed (deleted exports) | {count} |
| Moved (file relocated) | {count} |
| Renamed (identifier changed) | {count} |

### Confidence Tier Breakdown

| Tier | Count | Description |
|------|-------|-------------|
| T1 | {count} | AST-verified structural extraction |
| T1-low | {count} | Pattern-matched (Quick tier or degraded) |
| T2 | {count} | QMD-enriched semantic context |

### [MANUAL] Section Preservation

| Metric | Count |
|--------|-------|
| Sections preserved | {count} |
| Conflicts resolved | {count} |
| Orphans kept | {count} |
| Orphans removed | {count} |
| **Integrity** | {VERIFIED / count issues} |"

### 3. Present Validation Findings (If Any)

**If validation findings exist from step 05:**

"### Validation Findings

| Check | Status | Issues |
|-------|--------|--------|
| Spec compliance | {PASS/WARN/FAIL} | {count} |
| [MANUAL] integrity | {PASS/WARN/FAIL} | {count} |
| Confidence tiers | {PASS/WARN/FAIL} | {count} |
| Provenance | {PASS/WARN/FAIL} | {count} |

{List specific findings if WARN or FAIL}"

**If all validations passed:** "### Validation: All checks passed."

### 4. Show Files Updated

"### Files Written

| File | Status |
|------|--------|
| `{resolved_skill_package}/SKILL.md` | Updated |
| `{resolved_skill_package}/metadata.json` | Updated |
| `{forge_version}/provenance-map.json` | Updated |
| `{forge_version}/evidence-report.md` | Appended |
| {stack reference files if applicable} | Updated |

Where `{resolved_skill_package}` = `{skills_output_folder}/{skill_name}/{version}/{skill_name}/` and `{forge_version}` = `{forge_data_folder}/{skill_name}/{version}/` — see `knowledge/version-paths.md`."

### 5. Workflow Chaining Recommendations

"### Next Steps

Based on the update results:"

**If all validations passed:**
"- **audit-skill** — Run to verify the update resolved known drift
- **export-skill** — Package the updated skill for distribution
- **test-skill** — Run test suite against the updated skill"

**If validation warnings/failures exist:**
"- **audit-skill** — Run to identify remaining issues
- Review validation findings above before exporting"

**If triggered by audit-skill chain:**
"- **audit-skill** — Re-run to verify CRITICAL/HIGH drift resolved
- **export-skill** — Package once audit confirms clean state"

### 5b. Result Contract

Write `{forge_version}/update-skill-result.json` per `shared/references/output-contract-schema.md`. Include all modified file paths in `outputs`; include `exports_affected`, `files_modified`, and `validation_status` (passed/warnings/failures) in `summary`.

### 6. Workflow Complete

"---

**Update-skill workflow complete for `{skill_name}`.**"

### 7. Workflow Health Check

Load and execute `{nextStepFile}` for workflow self-improvement check.

