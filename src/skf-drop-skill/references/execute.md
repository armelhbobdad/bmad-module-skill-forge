---
nextStepFile: 'report.md'
# {updateActiveSymlinkHelper}: the §2 keep and the §4 `active` repair.
updateActiveSymlinkProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-active-symlink.py'
  - '{project-root}/src/shared/scripts/skf-update-active-symlink.py'
# {skillInventoryHelper}: the §4 guarded delete.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# {dropRosterHelper}: the §5 final-state check.
dropRosterHelper: 'scripts/drop-roster.py'
# {dirSizesHelper}: the §4 `disk_freed` label.
dirSizesHelper: 'scripts/dir-sizes.py'
# {atomicWriteHelper}: the §4 manual fix when the `active` repair prints no JSON.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# {emitEnvelopeHelper}: the §2 and §4 halt envelopes and the warnings the Rules record.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
# {rebuildManagedSectionsHelper}: the §3 context-file rebuild.
rebuildManagedSectionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py'
  - '{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py'
# {manifestOpsHelper}: the §2 keep and manifest write.
manifestOpsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py'
  - '{project-root}/src/shared/scripts/skf-manifest-ops.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Execute Drop

## STEP GOAL:

Execute the drop decisions recorded in step 1: update the export manifest, rebuild platform context files so dropped versions disappear from managed sections, and (in purge mode) delete the affected directories from disk. Record everything that was changed for the final report in step 3.

## Rules

- Focus only on manifest update, context rebuild, and (in purge mode) file deletion
- Do not re-prompt the user — decisions were made in step 1
- Do not delete files in deprecate mode; do not widen deletion scope beyond `affected_directories`
- Report each stage's outcome as it completes
- Record each degraded outcome as a warning the moment it happens, with the text the section names, so the envelope and the result record carry it: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '<the warning>'`, a single quote in it written as a backtick. If the command fails, go on: only that entry is lost.
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}`, `{manifestOpsHelper}` in `{manifestOpsProbeOrder}` and `{rebuildManagedSectionsHelper}` in `{rebuildManagedSectionsProbeOrder}`.

## Halts

Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode it also prints its envelope through the shared emitter before it stops (`{run_dir}` comes from SKILL.md On-Activation §4): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "exit_code": <code>}` plus the envelope fields the site names (and `"path"` when the halt names one), then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-drop-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. The emitter gives every field the site leaves out its default (`null`, `[]` or `false`) and checks `exit_code` against `halt_reason`. If it exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message, emits nothing and then deletes the run folder (`rm -rf "{run_dir}"`), which nothing reads after it.

## MANDATORY SEQUENCE

### 2. Update Export Manifest

**If `target_in_manifest == false`** (draft skill discovered only by on-disk scan): Skip this section entirely. There is no manifest entry to deprecate or delete. Set `manifest_updated = false` and proceed directly to section 3.

**If `target_in_manifest == true`:**

Write through `{manifestOpsHelper}`: atomic manifest mutation always goes through the helper.

**If `is_skill_level == false` (version-level drop):**

When `keep_version` is bound (select.md §7), make it the active version first, so the drop never leaves the skill without one. Resolve `{updateActiveSymlinkHelper}` from `{updateActiveSymlinkProbeOrder}` (first existing path wins), point `active` at it, then record it as the active version, keeping its `last_exported` date:

```bash
uv run {updateActiveSymlinkHelper} update --skill-group "{skills_output_folder}/{target_skill}" --version {keep_version}
python3 {manifestOpsHelper} {skills_output_folder} set {target_skill} {keep_version} --keep-last-exported
```

When no candidate exists, or `update` exits non-zero or prints no JSON, HALT (exit code 4, `halt_reason: "write-failed"`, phase `execute:keep-active`) in every mode, before `set` runs, with the resolved `skill`, `drop_mode` and `versions_affected` in the halt envelope: "**SKF cannot make `{keep_version}` the active version:** {its `halt_message`, its first stderr line, or "the active-link helper is missing; re-install SKF"}. Nothing was changed. Re-run the drop once the cause is fixed." A `set` that exits non-zero takes the manifest-write HALT below.

Then deprecate every version in scope in one call:

```bash
python3 {manifestOpsHelper} {skills_output_folder} deprecate {target_skill} {each version in target_versions, space-separated}
```

The helper checks every version before it marks any, sets the `status` of each to `"deprecated"` and writes the manifest atomically, once. It leaves `active_version` as it is: after a keep it names `{keep_version}`; otherwise, when the dropped version was the active one (the step 1 guard lets that through only for the last non-deprecated version), it still names it, and every consumer leaves deprecated versions out of exports.

**If `is_skill_level == true` (skill-level drop):**

- **Deprecate (`drop_mode == "deprecate"`):** mark every version deprecated and keep the entry, so the soft drop stays reversible. With no version, the helper sets the `status` of every version under `exports.{target_skill}.versions` to `"deprecated"` and leaves `active_version` as it is:

  ```bash
  python3 {manifestOpsHelper} {skills_output_folder} deprecate {target_skill}
  ```

- **Purge:** the helper deletes the `exports.{target_skill}` key entirely:

  ```bash
  python3 {manifestOpsHelper} {skills_output_folder} remove {target_skill}
  ```

When the helper exits 0 (`status: "ok"`), set context flag `manifest_updated = true`.

**On error (the helper exits non-zero):** HALT (exit code 4, `halt_reason: "manifest-write-failed"`, phase `execute:manifest-write`, path `{skills_output_folder}/.export-manifest.json`) in every mode, before section 3: "**Manifest update failed:** {the helper's `error`, `status: not_found` when the entry is no longer there, or its stderr when stdout holds no JSON}. Nothing was changed: no file was deleted, no context file was rebuilt, and the manifest is in its pre-drop state. Re-run the drop once the cause is fixed." The halt envelope carries the resolved `skill`, `drop_mode` and `versions_affected`, with `manifest_updated: false`. When `keep_version` is bound, the part after the error reads instead: "`active` names `{keep_version}`; no file was deleted and no context file was rebuilt. Re-run the same drop to finish it." When `set` succeeded, the message adds "The manifest lists `{keep_version}` as active." after its first sentence, and the envelope carries `manifest_updated: true`.

### 3. Rebuild Context Files

Rebuild the managed section of each context file step 1 counted the way export-skill writes it, through `{rebuildManagedSectionsHelper}`. `rebuild` resolves `target_context_files` again from the same `{ides}` (the comma-joined `ides` list of `config.yaml`, as select.md §9b passed it), so it rebuilds the files §10 counted:

```bash
python3 {rebuildManagedSectionsHelper} rebuild --project-root "{project-root}" --ides "{ides}" --skills-folder "{skills_output_folder}" --dropped {target_skill} [--skill-root-override "{snippet_skill_root_override}"]
```

Add `--skill-root-override` only when `snippet_skill_root_override` is set in `config.yaml`. For each file the helper builds the body export-skill would write for the manifest section 2 left, with that file's own skill root and the rows of skills the manifest does not know (orphan rows) kept verbatim, and replaces the section; `--dropped {target_skill}` keeps the dropped skill's old rows from staying as orphan rows. A file with no section is skipped, since export-skill adds one on its next run. The drop does not halt on a context file: section 2 already updated the manifest, which is the canonical state, and the next `[EX] Export Skill` run rebuilds a file once it is repaired.

Bind `context_files_updated` ← `updated` and `context_files_failed` ← the `file` of each `failed` entry, show each `warnings[]` line, and record the warning `context_rebuild_failed: {context_file}: {error}` for each `failed` entry. When the helper exits non-zero, or prints no JSON, bind `context_files_updated` ← `[]` and `context_files_failed` ← the path under `{project-root}` of every `target_context_files` entry, and record `context_rebuild_failed: all context files: {its error, or its first stderr line}`.

Report: "**Rebuilt managed sections in:** {list of updated files}. {if any failed: 'Failed: {list}'}"

### 4. Delete Files (Purge Mode Only)

**If `drop_mode != "purge"`**, skip this section entirely. Set `files_deleted = []`, `disk_freed = "N/A (soft drop)"`, `delete_failures = []`, and `purge_status = "success"`, then jump to section 5.

**If `drop_mode == "purge"`:**

1. **Delete through the guarded delete.** Resolve `{skillInventoryHelper}` from `{skillInventoryProbeOrder}` (first existing path wins) and run it once over every path in `affected_directories`, with the skills folder and the forge folder as the only folders it may delete inside:

   ```bash
   uv run {skillInventoryHelper} guarded-delete --root "{skills_output_folder}" --root "{forge_data_folder}" {each path in affected_directories, quoted, space-separated}
   ```

   SKF never deletes through a link. Bind `files_deleted` ← `files_deleted`, `delete_failures` ← `delete_failures` (each `{path, error}`), `{bytes_freed}` ← `bytes_freed` and `{purge_status}` ← `purge_status`. An empty `affected_directories` (a manifest entry whose folders are already gone) deletes nothing and returns `success`.

   When no candidate exists, delete nothing by hand: take the `failed` outcome below, with "the inventory helper that checks each delete is missing; re-install SKF" as the error of every path. On a non-zero exit, or no JSON on stdout, take the `failed` outcome too, with the helper's `error` (its stderr when stdout holds no JSON) as the error of every path.

2. **Version-level purge: repair `active`** (a whole-skill purge skips this item). Run the call below once per `target_versions` entry, with `{version}` that entry. Each version folder is already gone, so a link problem never claims `delete-failed`. Resolve `{updateActiveSymlinkHelper}` from `{updateActiveSymlinkProbeOrder}` (first existing path wins) and run:

   ```bash
   uv run {updateActiveSymlinkHelper} repair-after-drop --skill-group "{skills_output_folder}/{target_skill}" --dropped {version}
   ```

   It changes `active` only when the link names `{version}`: it points it at the version the manifest lists as active, else at the newest one the manifest does not list as deprecated, else it removes the link. A non-null `manual_fix` is the manual repair: record it in `verification_errors`, record the warning `active_link_dangling: {skills_output_folder}/{target_skill}/active: {the manual repair}`, and continue. When no candidate exists, or the helper prints no JSON, record the same way the manual repair "if `active` still names `{version}`, run `uv run {atomicWriteHelper} flip-link --link "{skills_output_folder}/{target_skill}/active" --target <the version the manifest lists as active, else the newest one it does not list as deprecated>`, or remove the link when there is none", followed by its last stderr line in parentheses, or by `(exit <code>)` when it prints nothing on stderr. `{atomicWriteHelper}` is the first existing path in `{atomicWriteProbeOrder}`, or its first entry when neither exists.

3. Format the size of the deleted folders through the sizing helper; do not add or round in-prompt:

   ```bash
   uv run {dirSizesHelper} humanize {bytes_freed}
   ```

   Store `result.total_human` as `disk_freed` (e.g. `"4.2 MB"`; `"0 B"` when nothing was deleted). When the helper exits non-zero or prints no JSON, store `disk_freed` as `"unknown"`.

**Classify the deletion outcome from `{purge_status}`:**

- **`failed`**: at least one path was attempted and none was deleted, so the purge accomplished none of its destructive intent. HALT (exit code 4, `halt_reason: "delete-failed"`, phase `execute:delete`): "**Purge failed:** none of the target folders could be deleted: {list each `delete_failures` path with its error}. The manifest and context files were already updated in sections 2–3; the on-disk files remain and can be removed by hand (`rm -rf {path}`)." The halt envelope carries the resolved `skill`, `drop_mode` and `versions_affected`, `files_deleted: []`, and `manifest_updated` from section 2. Do not proceed to section 5.
- **`partial`**: `delete_failures` is non-empty but at least one path was deleted. Keep record-and-continue: `purge_status = "partial"` lets step 3's on-disk result record reflect it. Record the warning `delete_failed: {path}: {error}` for each `delete_failures` entry, then proceed to section 5.
- **`success`**: nothing failed (a path already gone is not a failure). Proceed to section 5.

### 5. Verify Final State

Check the state the drop left, the manifest entry and the rows the rebuilt context files still hold for the dropped skill, in one call:

```bash
uv run {dropRosterHelper} verify "{skills_output_folder}" --skill {target_skill} --mode {drop_mode} [--version {version}] {each file in context_files_updated, quoted}
```

Pass `--version` once per `target_versions` entry for a version-level drop. Each `failures` entry is one failed check: its `detail` is what failed and its `manual_fix` the fix. When the call exits non-zero, or prints no JSON, the check itself failed: what failed is the helper's `error` (its stderr when stdout holds no JSON), and the fix is to check the `{target_skill}` entry of `{skills_output_folder}/.export-manifest.json` by hand and re-run `[EX] Export Skill`.

If any verification fails, record it in `verification_errors` with its manual fix, record the warning `verification_failed: {what failed}: {its manual fix}`, and do not halt: proceed to step 3 so the report shows what succeeded and what needs manual attention.

### 7. Load Next Step

Step 3 reads what this step bound where it ran: `files_deleted`, `disk_freed`, `delete_failures`, `purge_status`, `manifest_updated`, `context_files_updated`, `context_files_failed` and `verification_errors`, with `forge_left_in_place` and `keep_version` carried from step 1. Once every stage above has been attempted and its outcome bound, load, read the full file, and then execute `{nextStepFile}`.

