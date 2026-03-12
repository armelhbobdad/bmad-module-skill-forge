---
name: 'step-07-report'
description: 'Display comprehensive change summary with diff visualization and workflow chaining recommendations'
---

# Step 7: Report

## STEP GOAL:

Present a comprehensive change summary showing what was updated, [MANUAL] sections preserved, confidence tier breakdown, and recommend next workflow actions in the SKF chain.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 📋 YOU ARE A FACILITATOR, not a content generator
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a precision code analyst operating in Surgeon mode
- ✅ Report factually — no embellishment, no speculation
- ✅ Every reported metric must trace to actual operations performed
- ✅ Recommendations based on validation results and workflow chaining contracts

### Step-Specific Rules:

- 🎯 Focus ONLY on reporting — all operations are complete
- 🚫 FORBIDDEN to modify any files — report is read-only display
- 💬 Present clear, actionable summary with next step recommendations

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 No file writes — display only
- 📖 This is the final step — workflow completes here

## CONTEXT BOUNDARIES:

- Available: all results from steps 01-06 (baseline, change manifest, extraction results, merge results, validation results, write verification)
- Focus: summary and recommendations
- Limits: display only — no modifications
- Dependencies: all previous steps must be complete (or no-change shortcut from step 02)

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

→ **Workflow complete.** End here.

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
| `{skills_output_folder}/{skill_name}/SKILL.md` | Updated |
| `{skills_output_folder}/{skill_name}/metadata.json` | Updated |
| `{forge_data_folder}/{skill_name}/provenance-map.json` | Updated |
| `{forge_data_folder}/{skill_name}/evidence-report.md` | Appended |
| {stack reference files if applicable} | Updated |"

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

### 6. Workflow Complete

"---

**Update-skill workflow complete for `{skill_name}`.**"

→ **No next step.** Workflow ends here.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Comprehensive summary displayed with all metrics from the update operation
- Change categories broken down clearly
- Confidence tier breakdown reported
- [MANUAL] preservation status confirmed
- Validation findings presented if any
- Files written listed with paths
- Workflow chaining recommendations provided
- No-change shortcut handled correctly

### ❌ SYSTEM FAILURE:

- Reporting metrics not backed by actual operations
- Not reporting [MANUAL] preservation status
- Not providing workflow chaining recommendations
- Modifying any files during reporting
- Not handling the no-change shortcut from step 02

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
