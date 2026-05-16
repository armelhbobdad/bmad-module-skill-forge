---
nextStepFile: 'health-check.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 8: Report

## STEP GOAL:

To display the final compilation summary — skill name, version, source, export count, confidence distribution, tier used, file list, and any warnings — and suggest next steps for the user.

## Rules

- Focus only on reporting compilation results — do not modify any files
- Deliver structured report with confidence breakdown
- Chains to the local health-check step via `{nextStepFile}` after completion (non-batch mode, or after the final batch brief) — the user-facing report is NOT the terminal step

## MANDATORY SEQUENCE

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

**Before writing:** validate the same two invariants that step 1 re-checks on resume — `0 <= current_index < len(brief_list)` AND `os.path.exists(brief_list[current_index])`. If either fails (e.g., the next brief file was deleted mid-batch, or arithmetic pushed the index off the end), set `batch_active: false` and write `batch_halt_reason: "invalid checkpoint at write time — index or file missing"` instead of the active record. The next run will re-discover rather than resume a broken index.

Then load and execute `references/load-brief.md` for the next brief. Step-01 detects an active batch via `batch-state.yaml` and loads the brief at `current_index` only after re-validating the same invariants (belt and braces — the checkpoint may have been edited between runs).

**If all batch briefs complete:**

Set `batch_active: false` in `{sidecar_path}/batch-state.yaml` to prevent stale state. Display: "Batch complete. {completed_count} skills compiled."

**If not batch mode:**

End workflow. No further steps.

### Result Contract

**If not batch mode (or all batch briefs complete):**

**Resolve the schema reference:** before writing, verify that `{project-root}/src/shared/references/output-contract-schema.md` exists and is readable. Try in order: `{project-root}/src/shared/references/output-contract-schema.md`, then `{project-root}/_bmad/skf/shared/references/output-contract-schema.md` (installed-forge path).

- **If resolved:** write the result contract per the schema — the per-run record at `{forge_version}/create-skill-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{forge_version}/create-skill-result-latest.json` (stable path for pipeline consumers — copy, not symlink). Include `SKILL.md`, `context-snippet.md`, and `metadata.json` paths in `outputs` and confidence distribution in `summary`. Use `python3 {atomicWriteHelper} write --target {forge_version}/create-skill-result-{YYYYMMDD-HHmmss}.json` (stdin-piped JSON) for the per-run record, then the same helper for the `-latest.json` copy.

- **If neither candidate path resolves:** skip the result-contract write entirely. Append a warning to `evidence-report.md`: "Result contract skipped — `shared/references/output-contract-schema.md` could not be resolved at either candidate path." Then set `validation_status: 'schema-unavailable'` in `metadata.json` (and re-write metadata.json via `skf-atomic-write.py write`). Pipeline consumers will observe the missing `-latest.json` and the metadata flag.

### 6. Chain to Health Check

**If not batch mode (or all batch briefs complete):**

ONLY WHEN the compilation report, warnings (if any), recommended next steps, and result contract have been handled will you then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the report reads as final.

**If batch mode with remaining briefs:** Skip the health-check chain — load and execute `references/load-brief.md` for the next brief instead. The health check runs only after the final brief in the batch.

## CRITICAL STEP COMPLETION NOTE

This step chains to the local health-check step (`{nextStepFile}`), which in turn delegates to `shared/health-check.md` (unless batch mode loops back to step 1). After the health check completes, the create-skill workflow is fully done.

For batch mode: load and execute `references/load-brief.md` for remaining briefs via sidecar checkpoint. Health check runs only after the last brief.

