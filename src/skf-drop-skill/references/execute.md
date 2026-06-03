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
- Store `manifest_updated = false` and jump to section 6. In headless mode, emit the error envelope per SKILL.md "Result Contract (Headless)" with `halt_reason: "manifest-write-failed"` and exit code 4.

### 3. Rebuild Context Files

Load the `ides` list from `config.yaml`. The installer writes IDE identifiers — these must be mapped to context files and skill roots using the "IDE → Context File Mapping" table in `{managedSectionLogic}`.

**Resolve `target_context_files`** using the canonical mapping table in `{managedSectionLogic}`:

1. For each entry in `config.yaml.ides`, look up its `context_file` and `skill_root` from the mapping table
2. For any entry not found in the table, default to AGENTS.md / `.agents/skills/` and emit a warning: "Unknown IDE '{value}' in config.yaml — defaulting to AGENTS.md"
3. Deduplicate by `context_file` — when multiple IDEs map to the same context file, use the first configured IDE's `skill_root`
4. If `config.yaml.ides` is absent or the mapping yields an empty list, fall back to `[{context_file: "AGENTS.md", skill_root: ".agents/skills/"}]` and emit a note: "No IDEs configured in config.yaml — defaulting to AGENTS.md"

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

1. Initialize `files_deleted = []` and `bytes_freed = 0`.

2. Also initialize `delete_failures = []` to track paths whose deletion was attempted but did not succeed.

3. For each directory path in `affected_directories`:
   a. Verify the path is inside either `{skills_output_folder}` or `{forge_data_folder}` (defense in depth against accidental deletion of unrelated paths)
   b. If the directory does not exist, record it as "(already absent)" and continue
   c. Compute the directory size in bytes before deletion (recursive sum)
   d. Delete the directory recursively
   e. Verify deletion succeeded (the path no longer exists)
   f. Append the path to `files_deleted` and add its byte size to `bytes_freed`

4. **Version-level purge, single version:**
   - `{skills_output_folder}/{target_skill}/{version}/` is deleted, but `{skills_output_folder}/{target_skill}/` remains (it still contains other versions or the `active` symlink)
   - If the `active` symlink pointed to the just-deleted version, update or remove it:
     - If other versions remain in the manifest for `{target_skill}`, repoint `active` to the manifest's current `active_version` (skipping deprecated)
     - If no non-deprecated versions remain, remove the `active` symlink (reachable only when dropping the sole surviving version, which in step 1 was permitted because no other non-deprecated versions existed)

5. **Skill-level purge:**
   - `{skills_output_folder}/{target_skill}/` and `{forge_data_folder}/{target_skill}/` are deleted in full — the `active` symlink disappears with the parent directory

6. Convert `bytes_freed` to a human-readable string for the final report (e.g. `"4.2 MB"`). Store as `disk_freed`.

**On deletion error (per path):**

- Append the path and its error message to `delete_failures`
- Continue attempting the remaining paths — a partial purge is still better than no purge
- Report all failures at the end of this section

**After the loop — classify the deletion outcome.** Let `attempted` be the number of paths in `affected_directories` that existed on disk (i.e. were not recorded as "(already absent)"):

- **Full purge failure** — `attempted > 0` AND every attempted path is in `delete_failures` (nothing was deleted): the purge accomplished none of its destructive intent, so it must NOT report success. HALT (exit code 4, `halt_reason: "delete-failed"`): "**Purge failed** — none of the {attempted} target director(ies) could be deleted: {list each path with its error}. The manifest and context files were already updated in sections 2–3; the on-disk files remain and can be removed manually (`rm -rf {path}`)." In headless mode, emit the error envelope per SKILL.md "Result Contract (Headless)" with the resolved `skill`, `drop_mode`, `versions_affected`, `files_deleted: []`, and `manifest_updated` from section 2. Do not proceed to section 5.
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

Load, read the full file, and then execute `{nextStepFile}`.

## Error Handling Summary

If any stage fails, record which stage failed and provide recovery guidance in the final report:

| Failed Stage | Recovery Guidance |
|--------------|-------------------|
| Manifest update | "Manifest is in pre-drop state. Re-run the workflow once the underlying I/O issue is resolved. No files were deleted." |
| Context file rebuild | "Manifest is already updated. Re-run `[EX] Export Skill` against any still-valid skill to regenerate the affected managed sections, or rerun the drop workflow." |
| File deletion (purge — partial) | "Manifest and context files are consistent. Remaining directories listed in the report can be deleted manually: `rm -rf {path}`." (status `partial`) |
| File deletion (purge — full) | "No target directory could be deleted. Manifest and context files are already updated; the on-disk files remain. HALT with `delete-failed` (exit 4) — re-run once the I/O issue is resolved, or remove the listed directories manually." |
| Verification | "Execution completed but post-write checks found drift. See the report for specific paths requiring manual review." |

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all execution stages have been attempted (manifest update, context rebuild, file deletion in purge mode, verification) and results have been stored in context, will you then load and read fully `{nextStepFile}` to generate the final report.

