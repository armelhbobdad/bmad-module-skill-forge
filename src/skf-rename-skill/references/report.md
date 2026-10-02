---
nextStepFile: 'health-check.md'
# `{emitEnvelopeHelper}` and `{runLockHelper}` stay bound from step 1 §1;
# resolve them again when a binding was lost: first existing path wins. §1
# writes the result files and the envelope through the first, and §4
# releases the run lock through the second.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runLockProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py'
  - '{project-root}/src/shared/scripts/skf-run-lock.py'
---

<!-- Config: communicate in {communication_language}. Render the report block in {document_output_language}. -->

# Step 3: Report Rename Results

## STEP GOAL:

End the rename with one terminal sequence: write the result files and the envelope through the shared emitter, present a clear, final summary of what the rename workflow changed (old and new names, versions renamed, the files rewritten, manifest re-key, platform context rebuild, and any residual warnings or deletion errors) so the user can verify the outcome and know whether any manual follow-up is required, fire the post-completion hook, release the run lock, and chain to the health check.

## Rules

- Report only the results step 2 recorded from its helpers: do not re-execute any part of the rename, and never state a count or a version list step 2 did not record
- Do not hide verification warnings, context file rebuild failures, or deletion errors
- Present next-steps guidance so the user knows which downstream workflows to run
- Run the sections in order: the rename is already committed, so nothing here halts or undoes it

## MANDATORY SEQUENCE

### 1. Write the Result Files and the Envelope

Read `{run_dir}/rename-rewrite.json`, the record step 2 §2's helper wrote (step 2 rolls back a run whose record it could not write), and bind from it `renamed_versions`, `files_rewritten`, `rewrite_counts` ← `counts`, `package_warnings` and `missing_files`.

Stage the rename's result in the run folder, every value from what step 2 recorded: write each string as JSON (escape `"`, `\` and control characters, and write every path with `/`). Then let the shared emitter write the result files. From `{project-root}`:

```bash
cat > "{run_dir}/result-context.json" <<'SKF_RESULT'
{"status": "success", "old_name": "{old_name}", "new_name": "{new_name}", "versions_renamed": <renamed_versions as a JSON array>, "manifest_rekeyed": <manifest_rekeyed>, "context_files_updated": <context_files_updated as a JSON array>, "halt_reason": null, "result_contract": {"skill": "skf-rename-skill", "status": "success", "outputs": <one {"type": "skill", "path": "<path>"} per path in files_rewritten>, "summary": {"old_name": "{old_name}", "new_name": "{new_name}", "versions_renamed": <renamed_versions>, "manifest_rekeyed": <manifest_rekeyed>, "context_files_updated": <context_files_updated>, "context_files_failed": <context_files_failed>, "forge_left_in_place": <forge_left_in_place, or null>}}}
SKF_RESULT
uv run {emitEnvelopeHelper} emit --workflow skf-rename-skill --run-dir "{run_dir}" --result-dir "{skills_output_folder}/{new_name}" < "{run_dir}/result-context.json"
```

The emitter checks the envelope against `shared/scripts/schemas/skf-rename-skill-result-envelope.v1.json`, adds the decisions and warnings the run recorded, and writes the result files in `{skills_output_folder}/{new_name}/` as `shared/references/output-contract-schema.md` describes. It prints the `SKF_RENAME_SKILL_RESULT_JSON:` line on stdout: bind `{result_line}` ← that line, and from its JSON `{result_path}` ← `result_path` (the per-run record, or null when it could not be written), `{headless_decisions}` ← `headless_decisions` and `{run_warnings}` ← `warnings` (empty when absent).

When the emitter exits non-zero and its `message` names the payload, fix `{run_dir}/result-context.json` once and run it again. If it still exits non-zero, or prints no line, the rename stays committed: show its stderr message as a warning, bind `{result_line}` and `{result_path}` to null and `{headless_decisions}` and `{run_warnings}` to empty lists, and go on. No result file was written, and §4 keeps the run folder.

### 2. Render the Report

Open with "**Rename complete.**", then show, each from what step 2 recorded:

- From `{old_name}` to `{new_name}`, and the versions renamed: the number and the list of `renamed_versions`.
- The references updated, each with its count from `rewrite_counts`: SKILL.md frontmatter, metadata.json, context-snippet.md and, when `{forge_move}` or `{same_folder}` is true, provenance-map.json.
- The manifest: `exports.{new_name}`, re-keyed from `exports.{old_name}`, when `manifest_rekeyed` is true, else that no manifest entry existed for `{old_name}`.
- The context files rebuilt (`context_files_updated`, or "(none)"). When `context_files_failed` is not empty, list it with: "Re-run `[EX] Export Skill` to retry the managed section rebuild for these files."
- When `{forge_left_in_place}` is set: "Left in place (not SKF output): {forge_left_in_place}. SKF did not generate it, so it keeps its name."
- Each entry of `package_warnings`, `missing_files` and `{run_warnings}`, as warnings, except a `{run_warnings}` entry that starts with `installed-copy-not-renamed:`, which the next steps name.
- When `verification_warnings` is not empty, the SKILL.md files whose body text still names the old name (prose only, non-structural), with: "These are typically historical notes or changelog entries. Review and edit them by hand if you want them updated."
- When `deletion_errors` is not empty, each one, with: "The new name is fully committed. Remove the remnants by hand with `rm -rf {path}`."
- Each entry of `{headless_decisions}`, as "{gate}: took {taken_action} (default {default_action}): {reason}".
- The result file: `{result_path}`, or "(not written)".

Close with the next steps:

- For each path in `installed_copies`: "`{path}` is the copy `npx skills add` installed under `{old_name}`, and the rebuilt rows point at the same folder under `{new_name}`. Remove it, run `npx skills add {new_skill_group}/{version}/{new_name}`, then reload the IDE." `{version}` is `target_version`, else the first of `renamed_versions` (newest first), and `{new_skill_group}` is absolute, as export requires.
- Run `@Ferris EX` if you want to re-verify the managed sections in platform context files.
- If you had QMD collections or external tooling registered under `{old_name}`, re-run `@Ferris SF` (or your registration command) to re-index under `{new_name}`.
- If this skill was published to agentskills.io under `{old_name}`, the registry version is unchanged: this rename is a LOCAL operation only.

When `{headless_mode}` is true, display `{result_line}` verbatim on its own line after the report, when §1 printed one: it is the run's envelope, on **stdout**.

### 3. Post-Completion Hook (optional)

If `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`) and `{result_path}` is not null, run it as a shell command from `{project-root}` with the per-run result file §1 wrote:

```bash
{onCompleteCommand} --result-path="{result_path}"
```

Log success/failure but never fail the workflow on a hook error: the rename is already committed. The hook runs after the result files are written so an audit-log emit, registry re-index, or notifier sees the completed rename. When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely; when `{result_path}` is null, skip it with one line saying no result file was written for it to read.

### 4. Release the Run Lock and the Run Folder

Release the lock step 1 §4b took, naming it by its full path. From `{project-root}`, run:

```bash
uv run {runLockHelper} release \
    --lock "{forge_data_folder}/.skf-rename-{old_name}.lock" \
    --owner "{lock_owner}"
```

Never stop on the result:

- `released` true, or `reason` `absent`: continue.
- `reason` `not-owner`: another rename took the lock over after this run's lock went stale, and the helper left that run's lock in place. Tell the user in one line "The run lock {forge_data_folder}/.skf-rename-{old_name}.lock now belongs to {held_by}: another rename of {old_name} took it over while this one ran.", then continue.
- The command fails or prints no JSON: tell the user in one line "The run lock {forge_data_folder}/.skf-rename-{old_name}.lock was not released ({the first stderr line}); delete it when no rename of {old_name} is running.", then continue.

Then, when §1's emitter printed its line, delete the run folder:

```bash
rm -f "{run_dir}/result-context.json" "{run_dir}/decision.json" "{run_dir}/headless-decisions.jsonl" "{run_dir}/warnings.jsonl" "{run_dir}/rename-rewrite.json" "{run_dir}/export-manifest.backup.json" && rmdir "{run_dir}"
```

When that fails, tell the user in one line that `{run_dir}` stays and can be deleted, then continue. When §1's emitter printed no line, keep `{run_dir}` instead and tell the user in one line that it holds the run's decisions, its warnings and the payload the emitter refused.

### 5. Chain to Health Check

The report reads as final, but the workflow ends at step 4: load, read the full file, and then execute `{nextStepFile}`.

