---
nextStepFile: 'health-check.md'
# SKILL.md On-Activation §4 binds `{manifestOpsHelper}`, which §1 reads the
# skill's remaining versions through (`get` for the versions and their status,
# `affected-versions` for the numeric semver-descending order), and
# `{emitEnvelopeHelper}` with `{run_dir}`: the emitter stamps the time and the
# result file names, so this step types neither.
---

<!-- Config: communicate in {communication_language}. Render the report block in {document_output_language}. -->

# Step 3: Report Drop Results

## STEP GOAL:

Present a clear, final summary of what the drop workflow changed — manifest state, platform context files, deleted directories, disk freed, and remaining versions — so the user can verify the outcome and know whether any manual follow-up is required.

## Rules

- Focus only on reporting results stored in context by step 2 — do not re-execute any part of the drop
- Do not hide verification errors or failed context file rebuilds
- Reached only after step 2 wrote the manifest (or had none to write, for a draft skill): a failed manifest write HALTs in step 2, so this step never reports a drop that did not happen
- Chains to the local health-check step via `{nextStepFile}` after completion (see §3)

## MANDATORY SEQUENCE

### 1. Determine Remaining Versions

**If `is_skill_level == true` and `drop_mode == "purge"`:**

Set `remaining_versions_display = "(skill fully removed)"`.

**Otherwise** (one version, or a whole-skill deprecate, which keeps every version in the manifest as `deprecated`):

Read the target skill's remaining versions through the `{manifestOpsHelper}` On-Activation §4 resolved, rather than re-parsing the manifest by hand:

```bash
python3 {manifestOpsHelper} {skills_output_folder} get {target_skill}
python3 {manifestOpsHelper} {skills_output_folder} affected-versions {target_skill}
```

`get` returns `result.entry` (its `active_version` and its `versions` map with each version's `status`); `affected-versions` returns `result.affected_versions` sorted numerically-descending (so `0.10.0` precedes `0.9.0`). Build the display in that order, annotating each version with its `status` and marking `active_version` with a trailing `*`:

```
  - 0.6.0 (active) *
  - 0.5.0 (archived)
  - 0.1.0 (deprecated)
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
{if forge_left_in_place:}- Left in place (not SKF output): {forge_left_in_place}

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
      "headless_provenance": {"headless": {headless_mode}, "mode_source": "{mode_source}", "confirm": "{confirm_source}"}
    }
  }
}
```

- `{target_versions}` is a JSON array (e.g. `["0.5.0"]`) or the string `"all"`; `{files_deleted}` a JSON array of absolute paths (`[]` in deprecate mode, and so is `outputs`); `{forge_left_in_place}` the path step 2 carried, or `null` when none and in deprecate mode; `{manifest_updated}` the boolean from step 2.
- `{record_status}` is `"partial"` when some (but not all) purge folders failed to delete (step 2's `purge_status`); then also put step 2's `delete_failures` in `summary.delete_failures`. Otherwise it is `"success"`. A full purge failure and a failed manifest write never reach this step: step 2 HALTs with `halt_reason: "delete-failed"` or `"manifest-write-failed"`.
- `headless_provenance` persists the §8/§10 decision trail from step 1, so an unattended run's auto-decisions survive in the durable record and a consumer can tell an operator-confirmed drop from a headless auto-confirmed one: `{headless_mode}` is the resolved boolean, `{mode_source}` the step-1 §8 value (`"--mode argument"` / `"interactive-prompt"` / `"draft-skill-forced-purge"`), and `{confirm_source}` the step-1 §10 value (`"headless-auto"` / `"user-explicit"`).

Then run, in every mode:

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-drop-skill --run-dir "{run_dir}" --result-dir "{skills_output_folder}" < "{run_dir}/result-context.json"
```

The emitter stamps the UTC time, the run id, the run's warnings and the auto-decisions select.md recorded (`headless_decisions`) into the record, writes it as `{skills_output_folder}/drop-skill-result-{YYYYMMDD-HHmmss}.json`, copies it to `{skills_output_folder}/drop-skill-result-latest.json` (the stable path pipelines read), and prints the `SKF_DROP_SKILL_RESULT_JSON:` line on stdout (field rules in `references/invocation-contract.md`). Bind `{result_json_path}` ← that line's `result_path`: null when the record could not be written, and the line's `warnings` then say why. When `{headless_mode}` is true, display the line verbatim before chaining to step 4. If the helper exits non-zero, correct `result-context.json` from the `message` of its stderr JSON and run it once more; if it fails again, display "The drop result record could not be written: {message}" and go on, since the drop itself is complete.

### Post-drop hook (optional)

If `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`) and `{result_json_path}` is not null, invoke it once the emitter has written the record:

```bash
{onCompleteCommand} --result-path={result_json_path}
```

When it exits non-zero, display "on_complete hook failed (exit {code}): {its first stderr line}" as a line of its own (after the envelope line when `{headless_mode}` is true), and never fail the workflow on a hook error: the drop has already completed and may be irreversible. When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely.

Whether or not a hook ran, then delete the run folder, whose payload the emitter has read: `rm -rf "{run_dir}"`.

### 3. Chain to Health Check

ONLY WHEN the report has been rendered and the result contract saved will you then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the report reads as final, and do not re-run any earlier step after it completes (a fresh drop means re-invoking the workflow from the top).

