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

Display the following block, filling in values from context:

```
**Rename complete.**

From: {old_name}
To:   {new_name}

Versions renamed: {the number of renamed_versions} ({comma-separated renamed_versions})

References updated:
  - SKILL.md frontmatter       (×{the files_rewritten entries of kind skill-frontmatter})
  - metadata.json              (×{the files_rewritten entries of kind metadata-json})
  - context-snippet.md         (×{the files_rewritten entries of kind context-snippet})
  {if forge_move or same_folder:}- provenance-map.json        (×{the files_rewritten entries of kind provenance-json})

Manifest updated: {if manifest_rekeyed: "exports.{new_name} (re-keyed from exports.{old_name})" else: "(no manifest entry existed for {old_name})"}
Context files rebuilt: {list from context_files_updated, or "(none)"}
{if forge_left_in_place:}Left in place (not SKF output): {forge_left_in_place} — SKF did not generate it, so it keeps its name.
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

{if run_warnings is non-empty:}
Warnings:
  {list each entry of run_warnings}

{if headless_decisions is non-empty:}
Headless auto-decisions:
  {for each entry: "{gate}: took {taken_action} (default {default_action}) — {reason}"}

Result file: {result_path, or "(not written)"}

---

**Next steps:**
  - Run `@Ferris EX` if you want to re-verify the managed sections in platform context files
  - If you had QMD collections or external tooling registered under `{old_name}`, re-run `@Ferris SF` (or your registration command) to re-index under `{new_name}`
  - If this skill was published to agentskills.io under `{old_name}`, the registry version is unchanged — this rename is a LOCAL operation only
```

When `{headless_mode}` is true, display `{result_line}` verbatim on its own line after the block, when §1 printed one: it is the run's envelope, on **stdout**.

### 3. Post-Completion Hook (optional)

If `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`) and `{result_path}` is not null, invoke it with the per-run result file §1 wrote:

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
rm -f "{run_dir}/result-context.json" "{run_dir}/decision.json" "{run_dir}/headless-decisions.jsonl" "{run_dir}/warnings.jsonl" && rmdir "{run_dir}"
```

When that fails, tell the user in one line that `{run_dir}` stays and can be deleted, then continue. When §1's emitter printed no line, keep `{run_dir}` instead and tell the user in one line that it holds the run's decisions, its warnings and the payload the emitter refused.

### 5. Chain to Health Check

The report reads as final, but the workflow ends at step 4: load, read the full file, and then execute `{nextStepFile}`.

