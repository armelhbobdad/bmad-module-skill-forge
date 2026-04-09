---
nextStepFile: 'shared/health-check.md'
---

# Step 3: Report Drop Results

## STEP GOAL:

Present a clear, final summary of what the drop workflow changed — manifest state, platform context files, deleted directories, disk freed, and remaining versions — so the user can verify the outcome and know whether any manual follow-up is required.

## Rules

- Focus only on reporting results stored in context by step-02 — do not re-execute any part of the drop
- Do not hide verification errors or failed context file rebuilds
- Chains to shared health check via `{nextStepFile}` after completion

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly.

### 1. Determine Remaining Versions

**If `is_skill_level == true`:**

Set `remaining_versions_display = "(skill fully removed)"`.

**If `is_skill_level == false`:**

Read `{skills_output_folder}/.export-manifest.json` and look up `exports.{target_skill}.versions`. Build a human-readable list of every remaining version with its status, with the active one marked:

```
  - 0.1.0 (deprecated)
  - 0.5.0 (archived)
  - 0.6.0 (active) *
```

### 2. Render the Report

Display the following block, filling in values from context:

```
**Drop operation complete.**

Operation:     {Deprecate | Purge}
Skill:         {target_skill}
Version(s):    {comma-separated target_versions or "ALL"}

Changes:
- Manifest updated:      {yes | no}
- Context files rebuilt: {list from context_files_updated, or "(none)"}
{if context_files_failed is non-empty:}
- Context files FAILED: {list from context_files_failed}
{if drop_mode == "purge":}
- Files deleted:         {list from files_deleted, or "(none — nothing on disk)"}
- Disk space freed:      {disk_freed}

Remaining versions for {target_skill}:
{remaining_versions_display}

{if drop_mode == "deprecate":}
**Note:** Files remain on disk. This operation is reversible by manually editing
`{skills_output_folder}/.export-manifest.json` and changing the version's `status`
field back to `"active"` or `"archived"`, then re-running `[EX] Export Skill` to
restore the managed section entry.

{if verification_errors is non-empty:}
**Verification warnings:**
{list each verification error}
These require manual review — see the error-handling guidance in step-02.
```

### Result Contract

Write `{skills_output_folder}/drop-skill-result.json` per `shared/references/output-contract-schema.md`. Include all purged file paths in `outputs`; include `target_skill`, `drop_mode`, and `versions_affected` in `summary`.

### 3. Workflow Health Check

Load and execute `{nextStepFile}` for workflow self-improvement check.

## CRITICAL STEP COMPLETION NOTE

This step chains to the shared health check. After the health check completes, the drop-skill workflow is fully done. Do not re-run any earlier step automatically — if the user wants another drop, they should re-invoke the workflow from the top.

