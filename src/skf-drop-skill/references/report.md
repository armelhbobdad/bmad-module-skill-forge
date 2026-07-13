---
nextStepFile: 'health-check.md'
---

<!-- Config: communicate in {communication_language}. Render the report block in {document_output_language}. -->

# Step 3: Report Drop Results

## STEP GOAL:

Present a clear, final summary of what the drop workflow changed — manifest state, platform context files, deleted directories, disk freed, and remaining versions — so the user can verify the outcome and know whether any manual follow-up is required.

## Rules

- Focus only on reporting results stored in context by step 2 — do not re-execute any part of the drop
- Do not hide verification errors or failed context file rebuilds
- Chains to the local health-check step via `{nextStepFile}` after completion (see §3)

## MANDATORY SEQUENCE

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
These require manual review — see the error-handling guidance in step 2.
```

### Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{skills_output_folder}/drop-skill-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{skills_output_folder}/drop-skill-result-latest.json` (stable path for pipeline consumers — copy, not symlink). Include all purged file paths in `outputs`; include `target_skill`, `drop_mode`, and `versions_affected` in `summary`.

Set the record's `status` from step 2's `purge_status`: `"partial"` when some (but not all) purge-mode directories failed to delete — surface the failing paths from `delete_failures` in `summary.delete_failures` — otherwise `"success"`. A *full* purge failure never reaches this step: step 2 §4 HALTs with `halt_reason: "delete-failed"` and the error-envelope path below handles it.

When `{headless_mode}` is true, also emit the single-line envelope on **stdout** before chaining to step 4 (the full shape and field rules are in `references/headless-contract.md`):

```
SKF_DROP_SKILL_RESULT_JSON: {"status":"success","skill":"{target_skill}","drop_mode":"{drop_mode}","versions_affected":{target_versions},"files_deleted":{files_deleted},"manifest_updated":{manifest_updated},"exit_code":0,"halt_reason":null}
```

Substitute `{target_versions}` as a JSON array (e.g. `["0.5.0"]`) or the literal string `"all"`; substitute `{files_deleted}` as a JSON array of absolute paths (`[]` in soft-drop mode); `manifest_updated` is the boolean from step 2's context.

### Post-drop hook (optional)

If `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`), invoke it once the result contract above is finalized:

```bash
{onCompleteCommand} --result-path={result_json_path}
```

where `{result_json_path}` is the per-run record written above (`{skills_output_folder}/drop-skill-result-{YYYYMMDD-HHmmss}.json`). Log success or failure to `workflow_warnings[]` — never fail the workflow on a hook error; the drop has already completed and may be irreversible. When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely.

### 3. Chain to Health Check

ONLY WHEN the report has been rendered and the result contract saved will you then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the report reads as final.

## CRITICAL STEP COMPLETION NOTE

After the health-check step (`{nextStepFile}`) completes, do not automatically re-run any earlier step — a fresh drop means the user re-invokes the workflow from the top.

