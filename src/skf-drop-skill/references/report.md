---
nextStepFile: 'health-check.md'
# {dropRosterHelper}: the §1 remaining versions.
dropRosterHelper: 'scripts/drop-roster.py'
# {emitEnvelopeHelper}: the §2 result contract.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
# {resolveCustomizationHelper}: the §2 post-drop hook's `on_complete` value.
resolveCustomizationProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-customization.py'
  - '{project-root}/src/shared/scripts/skf-resolve-customization.py'
---

<!-- Config: communicate in {communication_language}. Render the report block in {document_output_language}. -->

# Step 3: Report Drop Results

## STEP GOAL:

Present a clear, final summary of what the drop workflow changed — manifest state, platform context files, deleted directories, disk freed, and remaining versions — so the user can verify the outcome and know whether any manual follow-up is required.

## Rules

- Focus only on reporting results stored in context by step 2 — do not re-execute any part of the drop
- Do not hide verification errors, failed context file rebuilds or folders a purge could not delete
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}`.
- The post-drop hook runs `{resolveCustomizationHelper}`, resolved from `{resolveCustomizationProbeOrder}` when it is not bound.

## MANDATORY SEQUENCE

### 1. Determine Remaining Versions

**If `is_skill_level == true` and `drop_mode == "purge"`:**

Set `remaining_versions_display = "(skill fully removed)"`.

**Otherwise** (one or more versions, or a whole-skill deprecate, which keeps every version in the manifest as `deprecated`):

Read the target skill's versions from the roster:

```bash
uv run {dropRosterHelper} skills "{skills_output_folder}" --forge-data-folder "{forge_data_folder}" --skill "{target_skill}"
```

List each `versions` row of its one `skills` entry whose `in_manifest` is true, in the roster's order (newest first, so `0.10.0` precedes `0.9.0`), with its `status`, and mark the row whose `active` is true with a trailing `*`; that list is `remaining_versions_display`.

When the call exits non-zero, or prints no JSON, set `remaining_versions_display = "(unknown: {the result's error, or its first stderr line})"`.

### 2. Render the Report

Show the report in one block: the operation (Deprecate or Purge), `{target_skill}` and `target_versions` (or "ALL"); when `keep_version` is bound, that `{keep_version}` is now the active version; whether the manifest was updated (`manifest_updated`); the context files rebuilt (`context_files_updated`, or "(none)") and each one in `context_files_failed`; for a purge, the folders deleted (`files_deleted`, or "(none: nothing on disk)"), `disk_freed`, each `delete_failures` path with its error and its fix `rm -rf {path}`, and `forge_left_in_place` as "Left in place (not SKF output)" when it is set; `remaining_versions_display`; for a deprecate, that the files stay on disk and that setting the version's `status` back to `"active"` or `"archived"` in `{skills_output_folder}/.export-manifest.json`, then running `[EX] Export Skill`, reverses the drop; and each `verification_errors` entry with its manual fix.

### Result Contract

The shared emitter writes the result contract (`shared/references/output-contract-schema.md`) and prints the envelope; this step stages their content. Write `{run_dir}/result-context.json`:

```json
{
  "status": "success",
  "skill": "{target_skill}",
  "drop_mode": "{drop_mode}",
  "versions_affected": {target_versions},
  "files_deleted": {files_deleted},
  "forge_left_in_place": {forge_left_in_place},
  "manifest_updated": {manifest_updated},
  "result_contract": {
    "skill": "skf-drop-skill",
    "status": "{record_status}",
    "outputs": [{"type": "skill", "path": "{each path in files_deleted}"}],
    "summary": {
      "target_skill": "{target_skill}",
      "drop_mode": "{drop_mode}",
      "versions_affected": {target_versions},
      "forge_left_in_place": {forge_left_in_place},
      "keep_version": {keep_version}
    }
  }
}
```

- `{target_versions}` is a JSON array (e.g. `["0.5.0"]`, or `["0.6.0", "0.5.0"]` after Older versions) or the string `"all"`; `{files_deleted}` a JSON array of absolute paths (`[]` in deprecate mode, and so is `outputs`); `{forge_left_in_place}` the path step 2 carried (a JSON array of paths after a purge check over several versions), or `null` when none and in deprecate mode; `{manifest_updated}` the boolean from step 2.
- `{keep_version}` is the version select.md §7 made active before the drop, as a JSON string, or `null` when none.
- `{record_status}` is `"partial"` when some (but not all) purge folders failed to delete (step 2's `purge_status`); then also put step 2's `delete_failures` in `summary.delete_failures`. Otherwise it is `"success"`. A full purge failure and a failed manifest write never reach this step: step 2 HALTs with `halt_reason: "delete-failed"` or `"manifest-write-failed"`.
- The payload carries no `warnings`: the emitter adds the ones step 2 recorded, so a run whose envelope reads `success` still names what needs a manual fix.

Then run, in every mode:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-drop-skill --run-dir "{run_dir}" --result-dir "{skills_output_folder}" < "{run_dir}/result-context.json"
```

Bind `{result_json_path}` ← the `result_path` of the `SKF_DROP_SKILL_RESULT_JSON:` line it prints on stdout (field rules in `references/invocation-contract.md`): null when the record could not be written, and the line's `warnings` then say why. When `{headless_mode}` is true, bind `{result_envelope_line}` ← the line and do not display it here: the shared health check displays it verbatim as the run's last line, so a `claude -p` caller reads the envelope as the final message. If the helper exits non-zero, correct `result-context.json` from the `message` of its stderr JSON and run it once more; if it fails again, leave `{result_envelope_line}` empty, display "The drop result record could not be written: {message}" and go on, since the drop itself is complete.

### Post-drop hook (optional)

When `{onCompleteCommand}` is not bound, bind it to the `workflow.on_complete` value this prints, or to the one in `{skill-root}/customize.toml` when the resolver cannot run:

```bash
uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow.on_complete
```

If `{onCompleteCommand}` is non-empty and `{result_json_path}` is not null, invoke it once the emitter has written the record:

```bash
{onCompleteCommand} --result-path="{result_json_path}"
```

Run it from `{project-root}`. When it exits non-zero, display "on_complete hook failed (exit {code}): {its first stderr line}" as a line of its own, and never fail the workflow on a hook error: the drop has already completed and may be irreversible. When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely.

Whether or not a hook ran, then delete the run folder, whose payload the emitter has read: `rm -rf "{run_dir}"`.

### 3. Chain to Health Check

Once the report is shown and the record emitted, load, read the full file, and execute `{nextStepFile}`: the health check is the terminal step, and in a headless run it prints the envelope as the last line, so stopping at the report loses it. Do not re-run an earlier step after it completes.

