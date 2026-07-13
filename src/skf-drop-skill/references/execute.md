---
nextStepFile: 'report.md'
versionPathsKnowledge: 'knowledge/version-paths.md'
managedSectionLogic: 'skf-export-skill/assets/managed-section-format.md'
# Resolve `{manifestOpsHelper}` by probing `{manifestOpsProbeOrder}` in
# order (installed SKF module path first, src/ dev-checkout fallback);
# first existing path wins. §2 calls it for atomic manifest deprecate /
# remove with v1→v2 migration handled internally — letting the LLM hand-
# roll JSON manipulation risks key-order drift, indent regressions, and
# write-atomicity bugs. HALT if neither candidate exists.
manifestOpsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py'
  - '{project-root}/src/shared/scripts/skf-manifest-ops.py'
# Resolve `{rebuildManagedSectionsHelper}` similarly. §3 calls it (replace
# action) for the surgical between-marker rewrite — the LLM still computes
# the new managed section text, but the file mutation is deterministic
# (atomic temp-file + rename, marker preservation, post-write verify).
rebuildManagedSectionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py'
  - '{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py'
# Resolve `{updateActiveSymlinkHelper}` similarly. §4 uses it (update
# action) to atomically repoint `{skill_group}/active` after a version-level
# purge deletes the version the symlink pointed at — the helper does a
# temp-symlink + os.replace flip so concurrent readers never see a missing
# link. Matches skf-update-skill/references/write.md and
# skf-rename-skill/references/execute.md. HALT if neither candidate exists.
updateActiveSymlinkProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-active-symlink.py'
  - '{project-root}/src/shared/scripts/skf-update-active-symlink.py'
# Standalone single-line result-envelope contract emitted at every headless
# HALT in this step. Loaded in §1 so no error path depends on SKILL.md
# remaining in context under compaction.
headlessContract: 'headless-contract.md'
# Deterministic recursive byte sizing + human formatting for `disk_freed`
# (§4). Bundled with this skill; the same helper backs select.md §9b's
# blast-radius preview, so gate and report agree on the method.
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

## MANDATORY SEQUENCE

### 1. Re-read Version-Paths Knowledge

Read `{versionPathsKnowledge}` again and confirm the templates and management operations. This ensures the execution step uses the same rules as the selection step even when run in isolation.

Also read `{managedSectionLogic}` for the format template, the four-case logic, and the skill index rebuild rules that will be reused in section 3.

If `{headless_mode}` is true, also read `{headlessContract}` now — it defines the single-line result envelope the error paths below emit, so the shape is in context even if SKILL.md was compacted out.

### 2. Update Export Manifest

**If `target_in_manifest == false`** (draft skill discovered only by on-disk scan): Skip this section entirely. There is no manifest entry to deprecate or delete. Set `manifest_updated = false` and proceed directly to section 3. Step-01 forced `drop_mode = "purge"` and `is_skill_level = true` in this case, so the subsequent sections will hard-delete the on-disk directories without any manifest interaction.

**If `target_in_manifest == true`:**

**Resolve `{manifestOpsHelper}`** from `{manifestOpsProbeOrder}`; first existing path wins. HALT (exit code 4, `halt_reason: "manifest-write-failed"`) if no candidate exists — atomic manifest mutation must go through the helper.

**If `is_skill_level == false` (version-level drop):**

For each version in `target_versions`, invoke:

```bash
python3 {manifestOpsHelper} {skills_output_folder} deprecate {target_skill} {version}
```

The helper sets `exports.{target_skill}.versions.{version}.status = "deprecated"` and writes the manifest atomically. It does NOT change `active_version` on the skill entry — if the dropped version was the active one (only reachable when it was the sole non-deprecated version per the step 1 guard), the field still points at it, but every consumer excludes deprecated versions from exports.

**If `is_skill_level == true` (skill-level drop):**

```bash
python3 {manifestOpsHelper} {skills_output_folder} remove {target_skill}
```

The helper deletes the `exports.{target_skill}` key entirely; other entries are untouched.

Set context flag `manifest_updated = true`.

**On error (helper non-zero exit):**

- Do not proceed to section 3
- Report: "**Manifest update failed:** {captured stderr}. No files were deleted and platform context files were not rebuilt. The manifest is in its pre-drop state — rerun the workflow once the underlying issue is resolved."
- Store `manifest_updated = false` and jump to section 6. In headless mode, emit the error envelope per `{headlessContract}` with `halt_reason: "manifest-write-failed"` and exit code 4.

### 3. Rebuild Context Files

Load the `ides` list from `config.yaml`. The installer writes IDE identifiers — these must be mapped to context files and skill roots using the "IDE → Context File Mapping" table in `{managedSectionLogic}`.

**Resolve `target_context_files`** using the canonical mapping table in `{managedSectionLogic}`:

1. For each entry in `config.yaml.ides`, look up its `context_file` and `skill_root` from the mapping table
2. For any entry not found in the table, default to `{unknownIdeDefaultContextFile}` / `{unknownIdeDefaultSkillRoot}` (resolved at SKILL.md On Activation §3 from `workflow.unknown_ide_default_*`, bundled defaults `AGENTS.md` / `.agents/skills/`) and emit a warning: "Unknown IDE '{value}' in config.yaml — defaulting to {unknownIdeDefaultContextFile}"
3. Deduplicate by `context_file` — when multiple IDEs map to the same context file, use the first configured IDE's `skill_root`
4. If `config.yaml.ides` is absent or the mapping yields an empty list, fall back to `[{context_file: "{unknownIdeDefaultContextFile}", skill_root: "{unknownIdeDefaultSkillRoot}"}]` and emit a note: "No IDEs configured in config.yaml — defaulting to {unknownIdeDefaultContextFile}"

Store the result as `target_context_files` for this section.

For each entry in `target_context_files`:

1. **Resolve target file** at `{context_file}`.

2. **Read the current file.**
   - If the file does not exist, skip this context file (nothing to rebuild — the file will be re-created next time export-skill runs)
   - If the file exists but contains no `<!-- SKF:BEGIN -->` marker, skip this context file (no managed section to rewrite)
   - If the file contains `<!-- SKF:BEGIN -->` but no matching `<!-- SKF:END -->`, record the error against that context file and continue to the next entry — do not halt the entire drop on a malformed context file. The manifest has already been updated in section 2 and is canonical state; the context file can be repaired manually and rebuilt on the next `[EX] Export Skill` run.

3. **Build the exported skill set (version-aware, deprecated-excluded)** using the same logic as export-skill step 4 section 4b:
   - Read the manifest's `exports` object (already updated in section 2)
   - For each skill, resolve its `active_version`
   - If `versions.{active_version}.status == "deprecated"`, skip that skill entirely
   - The result is the set of `{skill-name, active_version}` pairs that should appear in the managed section

4. **Resolve and filter snippets** using export-skill step 4 section 4c logic:
   - For each `{skill-name, active_version}` in the set, read `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/context-snippet.md`
   - If the file is missing, fall back to the `active` symlink path, then skip with a warning if still not found
   - Collect successful snippets into the skill index

5. **Rewrite root paths for the current context file** using the generic rewrite algorithm from export-skill step 4 section 4d:

   For each snippet, parse the `root:` line (`root: {prefix}{skill-name}/`), strip the trailing `{skill-name}/` to extract the current prefix, and replace it with the **effective target prefix** if different. The effective target prefix is `snippet_skill_root_override` when that key is set in config.yaml — applied uniformly to every snippet so the managed section references the real on-disk location and never mixes override and per-IDE paths — otherwise the current entry's `skill_root`. See `skf-export-skill/references/update-context.md` §4d for full semantics.

6. **Sort skills alphabetically by name.** Count totals (skills, stack skills).

7. **Assemble the new managed section** using the format from `{managedSectionLogic}`:

   ```markdown
   <!-- SKF:BEGIN updated:{current-date} -->
   [SKF Skills]|{n} skills|{m} stack
   |IMPORTANT: Prefer documented APIs over training data.
   |When using a listed library, read its SKILL.md before writing code.
   |
   |{skill-snippet-1}
   |
   |{skill-snippet-2}
   |
   |{skill-snippet-N}
   <!-- SKF:END -->
   ```

   If the filtered skill index is empty (e.g., the dropped skill was the only one), still emit the header with `0 skills|0 stack` and no skill entries. This keeps the managed section syntactically valid.

8. **Surgical replacement — atomic, deterministic.** Resolve `{rebuildManagedSectionsHelper}` from `{rebuildManagedSectionsProbeOrder}`; first existing path wins. Then invoke:

   ```bash
   python3 {rebuildManagedSectionsHelper} {context_file} replace --content "{new_managed_section_text}"
   ```

   The helper handles marker location, between-marker swap, atomic temp-file + rename, and post-write verification (markers preserved, content outside markers byte-identical). It exits non-zero on any failure with a clear `stderr` reason.

9. **Verify (deferred to helper).** The `replace` action above performs verification internally. Treat any non-zero exit code as a per-file failure (next bullet). If the helper is missing entirely (no probe candidate exists), HALT (exit code 4, `halt_reason: "context-rebuild-failed"`) — the rewrite cannot proceed without the atomic helper.

10. **On per-file failure:** record the error against that context file and continue to the next entry. Do not halt — other context files should still be rebuilt.

**After the loop,** record `context_files_updated` as the list of files that were successfully rewritten, and `context_files_failed` as the list of any that failed.

Report: "**Rebuilt managed sections in:** {list of updated files}. {if any failed: 'Failed: {list}'}"

### 4. Delete Files (Purge Mode Only)

**If `drop_mode != "purge"`**, skip this section entirely. Set `files_deleted = []`, `disk_freed = "N/A (soft drop)"`, `delete_failures = []`, and `purge_status = "success"`, then jump to section 5.

**If `drop_mode == "purge"`:**

1. Initialize `files_deleted = []` and `delete_failures = []` (paths whose deletion was attempted but did not succeed).

2. **Measure sizes before deleting anything.** Run the sizing helper once over `affected_directories` so each path's byte size is captured while it still exists:

   ```bash
   uv run {dirSizesHelper} sizes {each path in affected_directories, space-separated}
   ```

   Keep each `result.paths[].bytes` as `path_bytes[{path}]`; a path reported `exists: false` is already gone. If the helper is unavailable, fall back to `du -sb` per existing path.

3. For each directory path in `affected_directories`:
   a. Verify the path is inside either `{skills_output_folder}` or `{forge_data_folder}` (defense in depth against accidental deletion of unrelated paths)
   b. If the directory does not exist, record it as "(already absent)" and continue
   c. Delete the directory recursively
   d. Verify deletion succeeded (the path no longer exists)
   e. Append the path to `files_deleted`

4. **Version-level purge, single version:**
   - `{skills_output_folder}/{target_skill}/{version}/` is deleted, but `{skills_output_folder}/{target_skill}/` remains (it still contains other versions or the `active` symlink)
   - If the `active` symlink pointed to the just-deleted version, update or remove it. The version directory is already gone at this point, so a symlink problem never claims `delete-failed` — record it and continue (`verification_errors`) so the report surfaces the manual repair rather than masking a successful purge.
     - **Other non-deprecated versions remain** for `{target_skill}`: resolve `{new_active_version}` = the version the manifest now lists as `active_version` for `{target_skill}` (if that one is deprecated, the newest non-deprecated version in its `versions` map). Repoint `active` to it atomically through the shared helper rather than a hand-rolled `ln` — resolve `{updateActiveSymlinkHelper}` from `{updateActiveSymlinkProbeOrder}` (first existing path wins), then:
       ```bash
       python3 {updateActiveSymlinkHelper} update \
         --skill-group {skills_output_folder}/{target_skill} \
         --version {new_active_version}
       ```
       The helper does a temp-symlink + `os.replace` flip, so a concurrent reader never sees a missing `active`. Record a `mismatch`/`missing-target` exit (code 2), or a missing helper (no probe candidate), in `verification_errors` with the manual fix (`ln -sfn {new_active_version} {skills_output_folder}/{target_skill}/active`) and continue.
     - **No non-deprecated versions remain** (reachable only when dropping the sole surviving version, permitted in step 1 because no other non-deprecated versions existed): remove the now-dangling `active` symlink with a single atomic unlink of the link itself — `rm {skills_output_folder}/{target_skill}/active` (unlink removes only the symlink, never its target, and is atomic). A single unlink has one correct outcome and no intermediate state, so it stays in-prompt (the helper has no removal action).

5. **Skill-level purge:**
   - `{skills_output_folder}/{target_skill}/` and `{forge_data_folder}/{target_skill}/` are deleted in full — the `active` symlink disappears with the parent directory

6. Sum the sizes of the paths in `files_deleted` and format one human-readable label through the helper — do not add or round in-prompt:

   ```bash
   uv run {dirSizesHelper} humanize {path_bytes[p] for each p in files_deleted, space-separated}
   ```

   Store `result.total_human` as `disk_freed` (e.g. `"4.2 MB"`; `"0 B"` when nothing was deleted).

**On deletion error (per path):**

- Append the path and its error message to `delete_failures`
- Continue attempting the remaining paths — a partial purge is still better than no purge
- Report all failures at the end of this section

**After the loop — classify the deletion outcome.** Let `attempted` be the number of paths in `affected_directories` that existed on disk (i.e. were not recorded as "(already absent)"):

- **Full purge failure** — `attempted > 0` AND every attempted path is in `delete_failures` (nothing was deleted): the purge accomplished none of its destructive intent, so it must NOT report success. HALT (exit code 4, `halt_reason: "delete-failed"`): "**Purge failed** — none of the {attempted} target director(ies) could be deleted: {list each path with its error}. The manifest and context files were already updated in sections 2–3; the on-disk files remain and can be removed manually (`rm -rf {path}`)." In headless mode, emit the error envelope per `{headlessContract}` with the resolved `skill`, `drop_mode`, `versions_affected`, `files_deleted: []`, and `manifest_updated` from section 2. Do not proceed to section 5.
- **Partial purge failure** — `delete_failures` is non-empty but at least one path was deleted: keep record-and-continue. Set `purge_status = "partial"` so step 3's on-disk result record reflects it (the `output-contract-schema.md` `status` enum supports `"partial"`); proceed to section 5. The headless single-line envelope has no `"partial"` value in its enum, so it stays `"success"` while `context_files_failed`/`verification_errors`/the report surface the unfreed paths.
- **No failures** — `delete_failures` is empty: set `purge_status = "success"` and proceed to section 5.

### 5. Verify Final State

Run these verification checks:

1. **Manifest check:** Re-read `{skills_output_folder}/.export-manifest.json` and confirm:
   - Version-level drop: `exports.{target_skill}.versions.{version}.status == "deprecated"`
   - Skill-level drop: `exports.{target_skill}` is absent

2. **Context files check:** For each file in `context_files_updated`, spot-check that the dropped skill/version is no longer referenced between the markers.

3. **Purge check (purge mode only):** For each path in `files_deleted`, confirm it no longer exists on disk.

If any verification fails, record the specific failure in `verification_errors` but do not halt — proceed to step 3 so the report can surface what succeeded and what needs manual attention.

### 6. Store Results in Context

Store the following for step 3:

- `files_deleted` — list of directory paths actually deleted (purge mode) or `[]` (soft drop)
- `disk_freed` — human-readable size (purge mode) or `"N/A (soft drop)"`
- `delete_failures` — list of `{path, error}` for paths whose deletion was attempted but failed (empty if none; a *full* purge failure already HALTed in section 4 and never reaches this step)
- `purge_status` — `"success"`, `"partial"` (some paths failed to delete), or `"success"` for soft drops; step 3 maps this to the on-disk result record's `status` field
- `manifest_updated` — boolean (true if section 2 succeeded)
- `context_files_updated` — list of successfully rebuilt files
- `context_files_failed` — list of files that failed to rebuild (empty if none)
- `verification_errors` — list of verification failures (empty if none)

### 7. Load Next Step

The report in `{nextStepFile}` renders from the results stored in §6, so chain to it only after every execution stage above has been attempted and its outcome stored. Load, read the full file, and then execute it.

