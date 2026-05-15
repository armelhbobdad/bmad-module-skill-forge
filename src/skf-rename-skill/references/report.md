---
nextStepFile: 'health-check.md'
---

<!-- Config: communicate in {communication_language}. Render the report block in {document_output_language}. -->

# Step 3: Report Rename Results

## STEP GOAL:

Present a clear, final summary of what the rename workflow changed — old and new names, versions renamed, file-level update counts, manifest re-key, platform context rebuild, and any residual warnings or deletion errors — so the user can verify the outcome and know whether any manual follow-up is required.

## Rules

- Focus only on reporting results stored in context by step 2 — do not re-execute any part of the rename
- Do not hide verification warnings, context file rebuild failures, or deletion errors
- Present next-steps guidance so the user knows which downstream workflows to run
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing report is NOT the terminal step

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly.

### 1. Render the Report

Display the following block, filling in values from context:

```
**Rename complete.**

From: {old_name}
To:   {new_name}

Versions renamed: {affected_versions_count} ({comma-separated affected_versions})

References updated:
  - SKILL.md frontmatter       (×{affected_versions_count})
  - metadata.json              (×{affected_versions_count})
  - context-snippet.md         (×{affected_versions_count})
  - provenance-map.json        (×{affected_versions_count})

Manifest updated: {if manifest_rekeyed: "exports.{new_name} (re-keyed from exports.{old_name})" else: "(no manifest entry existed for {old_name})"}
Context files rebuilt: {list from context_files_updated, or "(none)"}
{if context_files_failed is non-empty:}
Context files FAILED: {list from context_files_failed}
  → Re-run `[EX] Export Skill` to retry the managed section rebuild for these files.

{if section2_warnings is non-empty:}
Warnings (inner directory rename):
  {list each warning from section2_warnings}

{if section3_warnings is non-empty:}
Warnings (missing files during content update):
  {list each warning from section3_warnings}

{if verification_warnings is non-empty:}
Informational: the old name still appears in SKILL.md body text (prose only, non-structural) in:
  {list each path from verification_warnings}
  → These are typically historical notes or changelog entries. Review and edit manually if you want them updated.

{if deletion_errors is non-empty:}
**Post-commit deletion errors:**
  {list each error}
  → The new name is fully committed. Remove the remnants manually with `rm -rf {path}`.

---

**Next steps:**
  - Run `@Ferris EX` if you want to re-verify the managed sections in platform context files
  - If you had QMD collections or external tooling registered under `{old_name}`, re-run `@Ferris SF` (or your registration command) to re-index under `{new_name}`
  - If this skill was published to agentskills.io under `{old_name}`, the registry version is unchanged — this rename is a LOCAL operation only
```

### Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{skills_output_folder}/{new_name}/rename-skill-result-{timestamp}.json` (reuse the activation-stored `{timestamp}`, resolution to seconds) and a copy at `{skills_output_folder}/{new_name}/rename-skill-result-latest.json` (stable path for pipeline consumers — copy, not symlink). Include all updated file paths (SKILL.md, metadata.json, context-snippet.md, provenance-map.json) in `outputs`; include `old_name`, `new_name`, and `versions_renamed` in `summary`.

When `{headless_mode}` is true, also emit the single-line envelope on **stdout** before chaining to step 4 (matches the SKILL.md "Result Contract (Headless)" shape):

```
SKF_RENAME_SKILL_RESULT_JSON: {"status":"success","old_name":"{old_name}","new_name":"{new_name}","versions_renamed":{affected_versions},"manifest_rekeyed":{manifest_rekeyed},"context_files_updated":{context_files_updated},"exit_code":0,"halt_reason":null}
```

Substitute `{affected_versions}` and `{context_files_updated}` as JSON arrays; `manifest_rekeyed` is the boolean from step 2's context.

### 2. Chain to Health Check

ONLY WHEN the rename report has been rendered and the result contract saved will you then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the report reads as final.

## CRITICAL STEP COMPLETION NOTE

This step chains to the local health-check step (`{nextStepFile}`), which in turn delegates to `shared/health-check.md`. After the health check completes, the rename-skill workflow is fully done. Do not re-run any earlier step automatically — if the user wants another rename, they should re-invoke the workflow from the top.

