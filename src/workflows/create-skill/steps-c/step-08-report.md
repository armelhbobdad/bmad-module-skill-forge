---
name: 'step-08-report'
description: 'Display compilation summary with confidence tiers, suggest next steps'
---

# Step 8: Report

## STEP GOAL:

To display the final compilation summary — skill name, version, source, export count, confidence distribution, tier used, file list, and any warnings — and suggest next steps for the user.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine delivering the final report
- ✅ This is the completion step — celebrate the forged skill
- ✅ Positive capability framing — describe what was achieved

### Step-Specific Rules:

- 🎯 Focus ONLY on reporting compilation results
- 🚫 FORBIDDEN to modify any files — reporting only
- 🚫 FORBIDDEN to re-run extraction or compilation
- 💬 Deliver structured report with confidence breakdown

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 No file operations — display only
- 📖 This is the final step — no next step to load
- 🚫 Do not modify any output files

## CONTEXT BOUNDARIES:

- Available: All data from previous steps — brief, extraction, enrichment, compilation, validation, artifacts
- Focus: Summarizing and reporting
- Limits: Do NOT modify files or re-run any previous step
- Dependencies: All artifacts must have been generated in step-07

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Display Forge Completion Banner

"**Skill forged: {name} v{version} — {export_count} functions, {primary_confidence} confidence.**"

Where `{primary_confidence}` is the predominant confidence tier (T1 if Forge/Deep, T1-low if Quick).

### 2. Display Compilation Summary

"**Compilation Summary**

| Field | Value |
|-------|-------|
| **Skill** | {name} v{version} |
| **Source** | {source_repo} @ {branch} ({commit_short}) |
| **Language** | {language} |
| **Forge Tier** | {tier} — {tier_description} |
| **Files Scanned** | {file_count} |
| **Exports Documented** | {documented_count} public API ({public_api_coverage}%) / {total_count} total ({total_coverage}%) |

**Confidence Distribution:**
| Tier | Count | Description |
|------|-------|-------------|
| T1 (AST) | {t1_count} | Structurally verified via ast-grep |
| T1-low (Source) | {t1_low_count} | Inferred from source reading |
| T2 (QMD) | {t2_count} | QMD-enriched semantic context |
| T3 (External) | {t3_count} | Sourced from external documentation URLs |

**Output Files:**
- `{skills_output_folder}/{name}/SKILL.md` — Active skill with trigger-based usage
- `{skills_output_folder}/{name}/context-snippet.md` — Passive context for CLAUDE.md
- `{skills_output_folder}/{name}/metadata.json` — Machine-readable birth certificate
- `{skills_output_folder}/{name}/references/` — Progressive disclosure ({ref_count} files)
- `{forge_data_folder}/{name}/provenance-map.json` — Source map with AST bindings
- `{forge_data_folder}/{name}/evidence-report.md` — Build audit trail
- `{forge_data_folder}/{name}/extraction-rules.yaml` — Reproducible extraction schema"

### 3. Display Warnings (If Any)

If there were warnings from extraction, validation, or enrichment, display them:

"**Warnings:**
- {warning_1}
- {warning_2}
- ..."

If no warnings, omit this section entirely.

### 4. Suggest Next Steps

"**Recommended next steps:**
- **[TS] Test Skill** — verify completeness and accuracy before export
- **[EX] Export Skill** — publish to your skill library or agentskills.io
- **[US] Update Skill** — edit specific sections or add manual content

To use this skill immediately, add the context snippet to your CLAUDE.md:
```
{context_snippet_content}
```"

### 5. Batch Mode Status (If Applicable)

**If running in --batch mode:**

"**Batch progress:** {completed_count} of {total_count} skills compiled.

{If more remaining:} Proceeding to next brief: {next_skill_name}..."

Update the batch checkpoint in `{sidecar_path}/batch-state.yaml` with:

```yaml
batch_active: true
brief_list: [{full list of brief paths}]
current_index: {index of next brief to process, 0-based}
completed: [{list of completed skill names}]
last_updated: {ISO timestamp}
```

Then loop back to step-01 for the next brief. Step-01 detects an active batch via `batch-state.yaml` and loads the brief at `current_index`.

**If all batch briefs complete:**

Set `batch_active: false` in `{sidecar_path}/batch-state.yaml` to prevent stale state. Display: "Batch complete. {completed_count} skills compiled."

**If not batch mode:**

End workflow. No further steps.

### 6. Workflow Complete

This is the final step. No `{nextStepFile}` to load.

Display: "Forge session complete. Return to Ferris menu for further actions."

## CRITICAL STEP COMPLETION NOTE

This is the FINAL STEP of the create-skill workflow. After displaying the compilation report and next steps, the workflow is complete. No further steps are loaded.

For batch mode: loop back to step-01 for remaining briefs via sidecar checkpoint.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Forge completion banner displayed with skill name, version, export count
- Full compilation summary with confidence distribution
- All output file paths listed
- Warnings displayed (if any)
- Next steps suggested (test-skill, export-skill, update-skill)
- Context snippet provided for immediate use
- Batch progress updated (if applicable)
- Workflow ended gracefully

### ❌ SYSTEM FAILURE:

- Not displaying the forge completion banner
- Missing confidence distribution in summary
- Modifying any files during the report step
- Not listing all output file paths
- Not suggesting next steps
- Not ending the workflow (attempting to load nonexistent next step)

**Master Rule:** This step reports and celebrates. It does not modify, re-extract, or re-compile. The skill is forged.
