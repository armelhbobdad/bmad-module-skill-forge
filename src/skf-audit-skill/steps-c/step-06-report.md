---
outputFile: '{forge_version}/drift-report-{timestamp}.md'
nextStepFile: '../../shared/health-check.md'
---

# Step 6: Generate Report

## STEP GOAL:

Finalize the drift report by completing the Audit Summary with calculated metrics, generating actionable remediation suggestions for each drift finding, and adding provenance metadata. Present the final report to the user with a next-workflow recommendation.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor delivering the final audit report
- ✅ Remediation suggestions must be specific and actionable
- ✅ Every suggestion must reference the specific drift finding it addresses

### Step-Specific Rules:

- 🎯 Focus on completing the report — summary, remediation, provenance
- 🚫 FORBIDDEN to discover new drift items or reclassify severity
- 💬 Remediation suggestions must be practical: what to change, where, and why
- 📋 Chains to shared health check via `{nextStepFile}` — no further steps after that

## EXECUTION PROTOCOLS:

- 🎯 Complete all remaining sections in {outputFile}
- 💾 Update {outputFile} frontmatter to mark workflow complete
- 📖 Present final summary to user
- 🚫 Do not re-analyze — only synthesize and present

## CONTEXT BOUNDARIES:

- Available: Complete drift report with structural diff, semantic diff, severity classification
- Focus: Synthesis, remediation guidance, and presentation
- Limits: Do not add new findings or reclassify — only complete the report
- Dependencies: Steps 01-05 must be complete

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Complete Audit Summary

Update the ## Audit Summary section at the top of {outputFile} with final calculated values:

- Fill in severity count table from Step 05 classification summary
- Set overall drift score
- Add total findings count

### 2. Generate Remediation Suggestions

For EACH classified drift finding, generate a specific remediation suggestion:

**CRITICAL findings remediation:**
- Removed export → "Remove reference to `{export_name}` from SKILL.md section {section}. Export no longer exists at `{file}:{line}`."
- Changed signature → "Update `{export_name}` signature in SKILL.md from `{old_signature}` to `{new_signature}`. See `{file}:{line}`."
- Renamed export → "Replace `{old_name}` with `{new_name}` throughout SKILL.md. Renamed at `{file}:{line}`."

**HIGH findings remediation:**
- New public API (>3) → "Add documentation for {count} new exports to SKILL.md: {export_list}. Consider running update-skill workflow."
- Deprecated API → "Mark `{export_name}` as deprecated in SKILL.md. Current replacement: `{replacement}` at `{file}:{line}`."

**MEDIUM findings remediation:**
- Moved function → "Update file reference for `{export_name}` from `{old_file}` to `{new_file}:{line}`."
- New exports (1-3) → "Consider adding `{export_names}` to SKILL.md for completeness."
- Changed convention → "Review convention documentation in SKILL.md for currency."

**LOW findings remediation:**
- Style changes → "Optional: Update style references in SKILL.md to reflect current conventions."

Append to {outputFile}:

```markdown
## Remediation Suggestions

### Priority Actions (CRITICAL + HIGH)

| # | Severity | Finding | Remediation | Effort |
|---|----------|---------|-------------|--------|
| 1 | {severity} | {finding} | {specific action} | {low/medium/high} |

### Recommended Updates (MEDIUM)

| # | Finding | Remediation | Effort |
|---|---------|-------------|--------|
| 1 | {finding} | {specific action} | {low/medium} |

### Optional Improvements (LOW)

| # | Finding | Remediation |
|---|---------|-------------|
| 1 | {finding} | {specific action} |

### Workflow Recommendation

{IF any CRITICAL or HIGH findings:}
**Recommended:** Run `[US] Update Skill` workflow to apply priority remediations automatically.

{IF only MEDIUM or LOW findings:}
**Optional:** Minor drift detected. Manual updates sufficient, or run `[US] Update Skill` for automated remediation.

{IF CLEAN:}
**No action needed.** Skill is current with source code.
```

### 3. Add Provenance Section

Append to {outputFile}:

```markdown
## Provenance

| Field | Value |
|-------|-------|
| **Audit Date** | {current_date} |
| **Audited By** | Ferris (Audit mode) |
| **Forge Tier** | {tier} |
| **Tools Used** | {tool_list based on tier} |
| **Source Path** | {source_path} |
| **Skill Path** | {skill_path} |
| **Provenance Map** | {provenance_map_path} |
| **Provenance Age** | {days} days |
| **Mode** | {normal / degraded} |

**Confidence Legend:**
- **T1:** AST extraction — high reliability, structural truth
- **T1-low:** Text pattern matching — moderate reliability
- **T2:** QMD temporal context — evidence-backed semantic analysis
```

### 4. Update Report Frontmatter

Update {outputFile} frontmatter:
- Append `'step-06-report'` to `stepsCompleted`
- Set `drift_score` to final calculated score
- Set `nextWorkflow` to `'update-skill'` if CRITICAL or HIGH findings, otherwise leave empty

### 5. Present Final Report Summary

"**Audit Complete: {skill_name}**

---

**Overall Drift Score: {CLEAN / MINOR / SIGNIFICANT / CRITICAL}**

| Severity | Count |
|----------|-------|
| CRITICAL | {count} |
| HIGH | {count} |
| MEDIUM | {count} |
| LOW | {count} |
| **Total** | {total} |

**Report saved to:** `{outputFile}`

{IF CRITICAL/HIGH findings:}
**Action Required:** {count} priority items need remediation. Recommend running `[US] Update Skill` workflow.

{IF MEDIUM/LOW only:}
**Minor Drift:** Skill is functional but could benefit from updates. See report for details.

{IF CLEAN:}
**All Clear:** No drift detected. Skill accurately reflects current source code.

---

**Next Steps:**
{IF findings exist:}
1. **[US] Update Skill** — Automatically apply remediations from this drift report
2. **Review report** — Manual review at `{outputFile}`

{IF CLEAN:}
1. **No action needed** — Skill is current
2. **[EX] Export Skill** — Skill is ready for distribution

---

**Audit workflow complete.**"

### Workflow Health Check

Load and execute `{nextStepFile}` for workflow self-improvement check.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Audit Summary completed with accurate metrics
- Remediation suggestion for every CRITICAL and HIGH finding
- Each remediation is specific: what to change, where, and why
- Provenance section documents complete audit trail
- Overall drift score correctly reflects findings
- Frontmatter updated with completion status and nextWorkflow
- Final summary presented clearly to user
- Report saved to correct output path

### ❌ SYSTEM FAILURE:

- Missing remediation for any CRITICAL or HIGH finding
- Vague remediation suggestions (e.g., "update the skill" without specifics)
- Discovering new findings in this step
- Reclassifying severity
- Not presenting final summary to user
- Missing provenance section
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
