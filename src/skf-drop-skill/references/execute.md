---
nextStepFile: 'report.md'
# {updateActiveSymlinkHelper}: the §4 `active` repoint.
updateActiveSymlinkProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-active-symlink.py'
  - '{project-root}/src/shared/scripts/skf-update-active-symlink.py'
# {skillInventoryHelper}: the §4 guarded delete and `resolve`.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# {dropRosterHelper}: the §5 context-file check.
dropRosterHelper: 'scripts/drop-roster.py'
# {dirSizesHelper}: the §4 `disk_freed` label.
dirSizesHelper: 'scripts/dir-sizes.py'
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

## MANDATORY SEQUENCE

### 1. Halt Envelope

Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode it also prints its envelope through the shared emitter before it stops (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On-Activation §4): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "exit_code": <code>}` plus the envelope fields the site names (and `"path"` when the halt names one), then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-drop-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. The emitter gives every field the site leaves out its default (`null`, `[]` or `false`) and checks `exit_code` against `halt_reason`. If it exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message, emits nothing and then deletes the run folder (`rm -rf "{run_dir}"`), which nothing reads after it.

### 2. Update Export Manifest

**If `target_in_manifest == false`** (draft skill discovered only by on-disk scan): Skip this section entirely. There is no manifest entry to deprecate or delete. Set `manifest_updated = false` and proceed directly to section 3.

**If `target_in_manifest == true`:**

Write through the `{manifestOpsHelper}` On-Activation §4 resolved: atomic manifest mutation always goes through the helper.

**If `is_skill_level == false` (version-level drop):**

For each version in `target_versions`, invoke:

```bash
python3 {manifestOpsHelper} {skills_output_folder} deprecate {target_skill} {version}
```

The helper sets `exports.{target_skill}.versions.{version}.status = "deprecated"` and writes the manifest atomically. It does NOT change `active_version` on the skill entry — if the dropped version was the active one (only reachable when it was the sole non-deprecated version per the step 1 guard), the field still points at it, but every consumer excludes deprecated versions from exports.

**If `is_skill_level == true` (skill-level drop):**

- **Deprecate (`drop_mode == "deprecate"`):** mark every version deprecated and keep the entry, so the soft drop stays reversible. With no version, the helper sets the `status` of every version under `exports.{target_skill}.versions` to `"deprecated"` and leaves `active_version` as it is:

  ```bash
  python3 {manifestOpsHelper} {skills_output_folder} deprecate {target_skill}
  ```

- **Purge:** the helper deletes the `exports.{target_skill}` key entirely; other entries are untouched:

  ```bash
  python3 {manifestOpsHelper} {skills_output_folder} remove {target_skill}
  ```

When the helper exits 0 (`status: "ok"`), set context flag `manifest_updated = true`.

**On error (the helper exits non-zero):** HALT (exit code 4, `halt_reason: "manifest-write-failed"`, phase `execute:manifest-write`, path `{skills_output_folder}/.export-manifest.json`) in every mode, before section 3: "**Manifest update failed:** {the helper's `error`, `status: not_found` when the entry is no longer there, or its stderr when stdout holds no JSON}. Nothing was changed: no file was deleted, no context file was rebuilt, and the manifest is in its pre-drop state. Re-run the drop once the cause is fixed." The §1 halt envelope carries the resolved `skill`, `drop_mode` and `versions_affected`, with `manifest_updated: false`. The run ends here: step 3 never runs, so no success report is shown and no result file is written.

### 3. Rebuild Context Files

Rebuild the managed section of each context file step 1 resolved (`target_context_files`, from `resolve-targets` in select.md §9b) the way export-skill writes it, through the `{rebuildManagedSectionsHelper}` On-Activation §4 resolved.

A target's file is `{context_path}`, its `{context_file}` in `{project-root}`, and `{target_paths}` is the `{context_path}` of every target, each quoted, space-separated, in the order of `target_context_files`. For each entry in `target_context_files`:

1. **Check the file.**

   ```bash
   python3 {rebuildManagedSectionsHelper} "{context_path}" check
   ```

   Its `case` decides. `create` (no file) or `append` (no managed section): skip this file, since there is no section to rebuild (export-skill adds one on its next run). `malformed` or `unreadable`: bind `{context_error}` ← `error` and take item 4. The drop does not halt on one context file: section 2 already updated the manifest, which is the canonical state, and the next `[EX] Export Skill` run rebuilds the file once it is repaired. `regenerate`: continue.

2. **Build the section body.**

   ```bash
   python3 {rebuildManagedSectionsHelper} assemble "{context_path}" \
     --skills-folder "{skills_output_folder}" --skill-root "{skill_root}" \
     --dropped {target_skill} --orphan-sources {target_paths} \
     [--skill-root-override "{snippet_skill_root_override}"]
   ```

   Add `--skill-root-override` only when `snippet_skill_root_override` is set in `config.yaml`. The helper builds the body export-skill would write for the manifest section 2 left, with the rows of skills the manifest does not know (orphan rows) kept verbatim; `--dropped {target_skill}` keeps the dropped skill's old rows from staying as orphan rows. It writes the body to `{context_path}.skf-content` and prints its result as JSON: show each `warnings[]` line and each `skipped_*` entry as a warning, except a `skipped_deprecated` entry for `{target_skill}`, which the drop itself deprecated. On a non-zero exit, bind `{context_error}` ← `error` and take item 4.

3. **Replace the section.** Feed the staged body to the helper by stdin redirection. Never pass the body inline as `--content "…"` or through `echo`: snippets carry backticks, `$` and quotes, which the shell expands, and the helper checks the text it received, so it would report success on corrupted bytes.

   ```bash
   python3 {rebuildManagedSectionsHelper} "{context_path}" replace < "{context_path}.skf-content"
   ```

   Delete `{context_path}.skf-content` once the helper returns, whatever its exit code. It refuses a body that holds a marker of its own, and then leaves the file unchanged. It exits 0 only when the `status` of its JSON is `"ok"`. On a non-zero exit, bind `{context_error}` ← `error`, or the helper's stderr when stdout holds no JSON.

4. **On per-file failure:** record `{context_error}` against that context file, record the warning `context_rebuild_failed: {context_file}: {context_error}`, and continue to the next entry. Do not halt: other context files should still be rebuilt.

**After the loop,** record `context_files_updated` as the list of files that were successfully rewritten, and `context_files_failed` as the list of any that failed.

Report: "**Rebuilt managed sections in:** {list of updated files}. {if any failed: 'Failed: {list}'}"

### 4. Delete Files (Purge Mode Only)

**If `drop_mode != "purge"`**, skip this section entirely. Set `files_deleted = []`, `disk_freed = "N/A (soft drop)"`, `delete_failures = []`, and `purge_status = "success"`, then jump to section 5.

**If `drop_mode == "purge"`:**

1. **Delete through the guarded delete.** Resolve `{skillInventoryHelper}` from `{skillInventoryProbeOrder}` (first existing path wins) and run it once over every path in `affected_directories`, with the skills folder and the forge folder as the only folders it may delete inside:

   ```bash
   uv run {skillInventoryHelper} guarded-delete --root "{skills_output_folder}" --root "{forge_data_folder}" {each path in affected_directories, quoted, space-separated}
   ```

   The helper removes any trailing `/`, and SKF never deletes through a link. Bind `files_deleted` ← `files_deleted`, `delete_failures` ← `delete_failures` (each `{path, error}`), `{bytes_freed}` ← `bytes_freed` and `{purge_status}` ← `purge_status`. An empty `affected_directories` (a manifest entry whose folders are already gone) deletes nothing and returns `success`.

   When no candidate exists, delete nothing by hand: take the `failed` outcome below, with "the inventory helper that checks each delete is missing; re-install SKF" as the error of every path. On a non-zero exit, or no JSON on stdout, take the `failed` outcome too, with the helper's `error` (its stderr when stdout holds no JSON) as the error of every path.

2. **Version-level purge, single version:** if the `active` symlink pointed to the just-deleted version, update or remove it. The version folder is already gone, so a symlink problem never claims `delete-failed`: record the manual repair in `verification_errors`, record the warning `active_link_dangling: {skills_output_folder}/{target_skill}/active: {the manual repair}`, and continue. Read the versions the drop left through the inventory helper's `resolve`, never from the manifest by hand:
     ```bash
     uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {target_skill} --forge-data-folder "{forge_data_folder}"
     ```
     When it exits non-zero, record the manual repair (point `active` at the newest version the manifest does not list as deprecated, or remove it when none is left) as above and continue.
     - **Other non-deprecated versions remain** (`resolve.counts.non_deprecated` is above `0`): `{new_active_version}` ← `resolve.active_version`, the version the manifest lists as active, unless it is null or its `resolve.versions` entry has `status` `"deprecated"`; then `resolve.newest_non_deprecated`. Repoint `active` to it atomically through the shared helper rather than a hand-rolled `ln`: resolve `{updateActiveSymlinkHelper}` from `{updateActiveSymlinkProbeOrder}` (first existing path wins), then:
       ```bash
       python3 {updateActiveSymlinkHelper} update \
         --skill-group {skills_output_folder}/{target_skill} \
         --version {new_active_version}
       ```
       Record a `mismatch`/`missing-target` exit (code 2), or a missing helper (no probe candidate), as above with the manual fix `ln -sfn {new_active_version} {skills_output_folder}/{target_skill}/active`, and continue.
     - **No non-deprecated versions remain** (`resolve.counts.non_deprecated` is `0`, reachable only when dropping the sole surviving version, permitted in step 1 because no other non-deprecated versions existed): remove the now-dangling `active` symlink with a single atomic unlink of the link itself: `rm {skills_output_folder}/{target_skill}/active` (unlink removes only the symlink, never its target). When it fails, record it as above with the manual fix `rm {skills_output_folder}/{target_skill}/active`.

3. Format the size of the deleted folders through the sizing helper; do not add or round in-prompt:

   ```bash
   uv run {dirSizesHelper} humanize {bytes_freed}
   ```

   Store `result.total_human` as `disk_freed` (e.g. `"4.2 MB"`; `"0 B"` when nothing was deleted).

**Classify the deletion outcome from `{purge_status}`:**

- **`failed`**: at least one path was attempted and none was deleted, so the purge accomplished none of its destructive intent and must NOT report success. HALT (exit code 4, `halt_reason: "delete-failed"`, phase `execute:delete`): "**Purge failed:** none of the target folders could be deleted: {list each `delete_failures` path with its error}. The manifest and context files were already updated in sections 2–3; the on-disk files remain and can be removed by hand (`rm -rf {path}`)." The §1 halt envelope carries the resolved `skill`, `drop_mode` and `versions_affected`, `files_deleted: []`, and `manifest_updated` from section 2. Do not proceed to section 5.
- **`partial`**: `delete_failures` is non-empty but at least one path was deleted. Keep record-and-continue: `purge_status = "partial"` lets step 3's on-disk result record reflect it (the `output-contract-schema.md` `status` enum supports `"partial"`). Record the warning `delete_failed: {path}: {error}` for each `delete_failures` entry, then proceed to section 5.
- **`success`**: nothing failed (a path already gone is not a failure). Proceed to section 5.

### 5. Verify Final State

Run these verification checks:

1. **Manifest check** (skip it when `target_in_manifest == false`: section 2 changed no entry). Read the entry through `{manifestOpsHelper}`:

   ```bash
   python3 {manifestOpsHelper} {skills_output_folder} get {target_skill}
   ```

   Version-level drop: `entry.versions.{version}.status` is `"deprecated"` for each version in `target_versions`. Skill-level deprecate: every version in `entry.versions` has `status` `"deprecated"`. Skill-level purge: `status` is `"not_found"`. A failure's manual fix: correct the `{target_skill}` entry of `{skills_output_folder}/.export-manifest.json` by hand.

2. **Context files check** (skip it when `context_files_updated` is empty): list the rows the rebuilt files still hold for the dropped skill, by name and version only:

   ```bash
   uv run {dropRosterHelper} rows --skill {target_skill} [--version {version}] {each file in context_files_updated, quoted}
   ```

   Pass `--version` for a version-level drop. Each `rows` entry fails the check, as does each `unchecked` entry (a file whose rows could not be read); the manual fix for both is to re-run `[EX] Export Skill`, which rebuilds the file. When the call exits non-zero, the check fails for every file in `context_files_updated`, with the helper's `error` (its stderr when stdout holds no JSON).

If any verification fails, record it in `verification_errors` with its manual fix, record the warning `verification_failed: {what failed}: {its manual fix}`, and do not halt: proceed to step 3 so the report shows what succeeded and what needs manual attention.

### 6. Store Results in Context

Step 3 reads what this step bound where it ran: `files_deleted`, `disk_freed`, `delete_failures`, `purge_status`, `manifest_updated`, `context_files_updated`, `context_files_failed` and `verification_errors`, with `forge_left_in_place` carried from step 1.

### 7. Load Next Step

The report in `{nextStepFile}` renders from the results stored in §6, so chain to it only after every execution stage above has been attempted and its outcome stored. Load, read the full file, and then execute it.

