---
nextStepFile: './step-03-report.md'
versionPathsKnowledge: 'knowledge/version-paths.md'
managedSectionLogic: 'skf-export-skill/assets/managed-section-format.md'
---

# Step 2: Execute Drop

## STEP GOAL:

Execute the drop decisions recorded in step-01: update the export manifest, rebuild platform context files so dropped versions disappear from managed sections, and (in purge mode) delete the affected directories from disk. Record everything that was changed for the final report in step-03.

## Rules

- Focus only on manifest update, context rebuild, and (in purge mode) file deletion
- Do not re-prompt the user — decisions were made in step-01
- Do not delete files in deprecate mode; do not widen deletion scope beyond `affected_directories`
- Report each stage's outcome as it completes

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Re-read Version-Paths Knowledge

Read `{versionPathsKnowledge}` again and confirm the templates and management operations. This ensures the execution step uses the same rules as the selection step even when run in isolation.

Also read `{managedSectionLogic}` for the format template, the four-case logic, and the skill index rebuild rules that will be reused in section 3.

### 2. Update Export Manifest

**If `target_in_manifest == false`** (draft skill discovered only by on-disk scan): Skip this section entirely. There is no manifest entry to deprecate or delete. Set `manifest_updated = false` and proceed directly to section 3. Step-01 forced `drop_mode = "purge"` and `is_skill_level = true` in this case, so the subsequent sections will hard-delete the on-disk directories without any manifest interaction.

**If `target_in_manifest == true`:**

Load `{skills_output_folder}/.export-manifest.json`.

**If `is_skill_level == false` (version-level drop):**

For each version in `target_versions`:

1. Navigate to `exports.{target_skill}.versions.{version}`
2. Set `status = "deprecated"`
3. Leave `ides`, `last_exported`, and all other fields unchanged

Do NOT change `active_version` on the skill entry in this pass — if the dropped version was the active one (only reachable when it was the sole non-deprecated version per the step-01 guard), the active_version field will still point at it, but every consumer excludes deprecated versions from exports.

**If `is_skill_level == true` (skill-level drop):**

1. Delete the `exports.{target_skill}` key entirely from the manifest
2. Leave all other skill entries untouched

**Write the updated manifest back to `{skills_output_folder}/.export-manifest.json`.**

Set context flag `manifest_updated = true`.

**On error (read/parse/write failure):**

- Do not proceed to section 3
- Report: "**Manifest update failed:** {error}. No files were deleted and platform context files were not rebuilt. The manifest is in its pre-drop state — rerun the workflow once the underlying issue is resolved."
- Store `manifest_updated = false` and jump to section 6

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

3. **Build the exported skill set (version-aware, deprecated-excluded)** using the same logic as export-skill step-04 section 4b:
   - Read the manifest's `exports` object (already updated in section 2)
   - For each skill, resolve its `active_version`
   - If `versions.{active_version}.status == "deprecated"`, skip that skill entirely
   - The result is the set of `{skill-name, active_version}` pairs that should appear in the managed section

4. **Resolve and filter snippets** using export-skill step-04 section 4c logic:
   - For each `{skill-name, active_version}` in the set, read `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/context-snippet.md`
   - If the file is missing, fall back to the `active` symlink path, then skip with a warning if still not found
   - Collect successful snippets into the skill index

5. **Rewrite root paths for the current context file** using the generic rewrite algorithm from export-skill step-04 section 4d:

   For each snippet, parse the `root:` line (`root: {prefix}{skill-name}/`), strip the trailing `{skill-name}/` to extract the current prefix, and replace it with the **effective target prefix** if different. The effective target prefix is `snippet_skill_root_override` when that key is set in config.yaml — applied uniformly to every snippet so the managed section references the real on-disk location and never mixes override and per-IDE paths — otherwise the current entry's `skill_root`. See `skf-export-skill/steps-c/step-04-update-context.md` §4d for full semantics.

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

8. **Surgical replacement — Case 3 (Regenerate) only:**
   - Locate the `<!-- SKF:BEGIN` line — preserve everything before it
   - Locate the `<!-- SKF:END -->` line — preserve everything after it
   - Replace everything between the markers (inclusive) with the new managed section
   - Write the file back

9. **Verify:**
   - Re-read the written file
   - Confirm both markers are present
   - Confirm `{target_skill}` (at the dropped version, or at all versions if skill-level) no longer appears between the markers
   - Confirm content outside the markers is byte-identical to what was preserved

10. **On per-file failure:** record the error against that context file and continue to the next entry. Do not halt — other context files should still be rebuilt.

**After the loop,** record `context_files_updated` as the list of files that were successfully rewritten, and `context_files_failed` as the list of any that failed.

Report: "**Rebuilt managed sections in:** {list of updated files}. {if any failed: 'Failed: {list}'}"

### 4. Delete Files (Purge Mode Only)

**If `drop_mode != "purge"`**, skip this section entirely. Set `files_deleted = []` and `disk_freed = "N/A (soft drop)"`, then jump to section 5.

**If `drop_mode == "purge"`:**

1. Initialize `files_deleted = []` and `bytes_freed = 0`.

2. For each directory path in `affected_directories`:
   a. Verify the path is inside either `{skills_output_folder}` or `{forge_data_folder}` (defense in depth against accidental deletion of unrelated paths)
   b. If the directory does not exist, record it as "(already absent)" and continue
   c. Compute the directory size in bytes before deletion (recursive sum)
   d. Delete the directory recursively
   e. Verify deletion succeeded (the path no longer exists)
   f. Append the path to `files_deleted` and add its byte size to `bytes_freed`

3. **Version-level purge, single version:**
   - `{skills_output_folder}/{target_skill}/{version}/` is deleted, but `{skills_output_folder}/{target_skill}/` remains (it still contains other versions or the `active` symlink)
   - If the `active` symlink pointed to the just-deleted version, update or remove it:
     - If other versions remain in the manifest for `{target_skill}`, repoint `active` to the manifest's current `active_version` (skipping deprecated)
     - If no non-deprecated versions remain, remove the `active` symlink (reachable only when dropping the sole surviving version, which in step-01 was permitted because no other non-deprecated versions existed)

4. **Skill-level purge:**
   - `{skills_output_folder}/{target_skill}/` and `{forge_data_folder}/{target_skill}/` are deleted in full — the `active` symlink disappears with the parent directory

5. Convert `bytes_freed` to a human-readable string for the final report (e.g. `"4.2 MB"`). Store as `disk_freed`.

**On deletion error:**

- Record which path failed and the error message
- Continue attempting the remaining paths — partial purge is still better than no purge
- Report all failures at the end of this section

### 5. Verify Final State

Run these verification checks:

1. **Manifest check:** Re-read `{skills_output_folder}/.export-manifest.json` and confirm:
   - Version-level drop: `exports.{target_skill}.versions.{version}.status == "deprecated"`
   - Skill-level drop: `exports.{target_skill}` is absent

2. **Context files check:** For each file in `context_files_updated`, spot-check that the dropped skill/version is no longer referenced between the markers.

3. **Purge check (purge mode only):** For each path in `files_deleted`, confirm it no longer exists on disk.

If any verification fails, record the specific failure in `verification_errors` but do not halt — proceed to step-03 so the report can surface what succeeded and what needs manual attention.

### 6. Store Results in Context

Store the following for step-03:

- `files_deleted` — list of directory paths actually deleted (purge mode) or `[]` (soft drop)
- `disk_freed` — human-readable size (purge mode) or `"N/A (soft drop)"`
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
| File deletion (purge) | "Manifest and context files are consistent. Remaining directories listed in the report can be deleted manually: `rm -rf {path}`." |
| Verification | "Execution completed but post-write checks found drift. See the report for specific paths requiring manual review." |

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all execution stages have been attempted (manifest update, context rebuild, file deletion in purge mode, verification) and results have been stored in context, will you then load and read fully `{nextStepFile}` to generate the final report.

