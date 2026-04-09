---
nextStepFile: 'shared/health-check.md'
---

# Step 8: Report

## STEP GOAL:

To display the final compilation summary — skill name, version, source, export count, confidence distribution, tier used, file list, and any warnings — and suggest next steps for the user.

## Rules

- Focus only on reporting compilation results — do not modify any files
- Deliver structured report with confidence breakdown
- Chains to shared health check via `{nextStepFile}` after completion

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
- `{skill_package}/SKILL.md` — Active skill with trigger-based usage
- `{skill_package}/context-snippet.md` — Passive context snippet (used by export-skill)
- `{skill_package}/metadata.json` — Machine-readable birth certificate
- `{skill_package}/references/` — Progressive disclosure ({ref_count} files)
- `{forge_version}/provenance-map.json` — Source map with AST bindings
- `{forge_version}/evidence-report.md` — Build audit trail
- `{forge_version}/extraction-rules.yaml` — Reproducible extraction schema
- `{skill_group}/active` -> `{version}` — Symlink to current version"

### 3. Display Warnings (If Any)

If there were warnings from extraction, validation, or enrichment, display them:

"**Warnings:**
- {warning_1}
- {warning_2}
- ..."

If no warnings, omit this section entirely.

**Next steps:** After reviewing the report, recommend the next workflow:
- **TS** (test skill) — verify completeness before export
- **EX** (export) — publish to your IDE's context system
- If issues were flagged, suggest **reviewing the SKILL.md** and re-running compilation

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

### Result Contract

**If not batch mode (or all batch briefs complete):**

Write `{skill_package}/create-skill-result.json` per `shared/references/output-contract-schema.md`. Include `SKILL.md`, `context-snippet.md`, and `metadata.json` paths in `outputs` and confidence distribution in `summary`.

### 6. Workflow Health Check

**If not batch mode (or all batch briefs complete):**

Load and execute `{nextStepFile}` for workflow self-improvement check.

**If batch mode with remaining briefs:** Skip health check — loop back to step-01 for the next brief. Health check runs after the final brief in the batch.

## CRITICAL STEP COMPLETION NOTE

This step chains to the shared health check (unless batch mode loops back to step-01). After the health check completes, the create-skill workflow is fully done.

For batch mode: loop back to step-01 for remaining briefs via sidecar checkpoint. Health check runs only after the last brief.

