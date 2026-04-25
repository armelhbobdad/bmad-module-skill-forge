---
nextStepFile: './step-03-report.md'
versionPathsKnowledge: 'knowledge/version-paths.md'
managedSectionLogic: 'skf-export-skill/assets/managed-section-format.md'
---

# Step 2: Execute Rename (Transactional)

## STEP GOAL:

Execute the rename decisions recorded in step-01 as a transaction. Copy the old `{skill_group}` and `{forge_group}` to the new name, rename inner directories, rewrite every in-file reference, verify no trace of the old name remains inside the new location, update the export manifest, rebuild platform context files, and only then delete the old directories. Any failure before the final delete rolls back by removing the new directories — the old skill remains intact.

## Rules

- Execute sections strictly in order — each section depends on the previous one
- Do not re-prompt the user — decisions were made in step-01
- Do not delete anything from old directories before section 8
- Do not proceed past a verification failure in section 5
- Report each section's outcome as it completes

## MANDATORY SEQUENCE

**CRITICAL:** This is transactional. After section 1 (copy), the old skill is untouched. If any section between 2 and 7 fails, delete `{new_skill_group}` and `{new_forge_group}`, report the failure, and halt — the old skill remains intact. Only section 8 (delete old) makes the operation irreversible. Do not skip, reorder, or improvise.

### 0. Re-read Version-Paths Knowledge

Read `{versionPathsKnowledge}` again and confirm the templates (`{skill_package}`, `{skill_group}`, `{forge_version}`, `{forge_group}`) and the Rename section. Also read `{managedSectionLogic}` for the managed-section format template and the skill index rebuild rules that will be reused in section 7.

### 1. Copy skill_group and forge_group

**Precondition:** Both `{new_skill_group}` and `{new_forge_group}` must NOT exist (step-01 validated this in the collision check, but verify again before copying).

1. If `{new_skill_group}` or `{new_forge_group}` exists on disk, halt with: "**Collision detected at execution time.** `{new_skill_group}` or `{new_forge_group}` now exists on disk — it did not exist during step-01 selection. Aborting before any files are touched."

2. Copy `{old_skill_group}` to `{new_skill_group}` recursively:
   - Preserve file permissions, timestamps, and symlinks
   - Equivalent to `cp -a {old_skill_group} {new_skill_group}` (preserves symlinks) or `cp -r` followed by explicit symlink re-creation in section 4
   - If the copy fails: halt with "**Copy failed:** `{old_skill_group}` → `{new_skill_group}`: {error}. No files were modified. Old skill is intact."

3. Copy `{old_forge_group}` to `{new_forge_group}` the same way:
   - If the copy fails: **rollback** by deleting `{new_skill_group}` (just created in step 2), then halt with "**Copy failed:** `{old_forge_group}` → `{new_forge_group}`: {error}. Rolled back new skill_group. Old skill is intact."

**Rollback procedure for this section:** `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}` (whichever exist). Old skill is untouched.

Report: "**Copied** `{old_skill_group}` → `{new_skill_group}` and `{old_forge_group}` → `{new_forge_group}`."

### 2. Rename Inner Version Directories

For each version `v` in `affected_versions`:

1. Resolve the old inner directory: `{new_skill_group}/{v}/{old_name}/`
2. Resolve the new inner directory: `{new_skill_group}/{v}/{new_name}/`
3. Rename the directory (move within the same parent): `mv {new_skill_group}/{v}/{old_name} {new_skill_group}/{v}/{new_name}`
4. If the old inner directory does not exist (orphaned version with no skill package), skip with a warning recorded in `section2_warnings`

**Rollback on any rename failure:**

- `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}`
- Halt with: "**Inner directory rename failed** at `{v}/{old_name}`: {error}. Rolled back both new directories. Old skill is intact."

Report: "**Renamed {count} inner directories** to `{new_name}/`."

### 3. Update File Contents Inside the New Location

For each version `v` in `affected_versions`, operate on the files inside `{new_skill_group}/{v}/{new_name}/` (the freshly renamed inner directory) and `{new_forge_group}/{v}/`:

**3a. SKILL.md frontmatter:**

- Path: `{new_skill_group}/{v}/{new_name}/SKILL.md`
- In the YAML frontmatter (between the leading `---` markers), replace the `name:` field value from `{old_name}` to `{new_name}`
- Only replace within the frontmatter block — do not substitute matches inside the body text
- If the file is missing, record it in `section3_warnings` and continue

**3b. metadata.json:**

- Path: `{new_skill_group}/{v}/{new_name}/metadata.json`
- Parse the JSON, set `name` = `{new_name}`, write back preserving formatting
- If the file is missing, record it in `section3_warnings` and continue

**3c. context-snippet.md:**

- Path: `{new_skill_group}/{v}/{new_name}/context-snippet.md`
- Replace the display name header `[{old_name} v...]` → `[{new_name} v...]` (preserving the version suffix)
- Rewrite every `root:` path that references the old name to use the new name. Parse the `root:` line as `root: {prefix}{old_name}/`, preserve the prefix as-is, and replace `{old_name}` with `{new_name}`. This generically handles any IDE's skill root path (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/`) as well as the draft `skills/` prefix and legacy forms — no enumeration of known prefixes needed.
  - Example: `root: .windsurf/skills/{old_name}/` → `root: .windsurf/skills/{new_name}/`
  - Example: `root: skills/{old_name}/` → `root: skills/{new_name}/`
  - Legacy pre-fix form `root: skills/{old_name}/active/{old_name}/` → `root: skills/{new_name}/` (normalize to flat form during rename)
- If the file is missing, record it in `section3_warnings` and continue

**3d. provenance-map.json:**

- Path: `{new_forge_group}/{v}/provenance-map.json`
- Parse JSON, set `skill_name` = `{new_name}`, write back preserving formatting
- If the file is missing (some versions may not have a provenance map), record it in `section3_warnings` and continue

**Rollback on any update failure (not just a missing file):**

- `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}`
- Halt with: "**File update failed** at `{path}`: {error}. Rolled back both new directories. Old skill is intact."

Report: "**Updated file contents** across {affected_versions_count} version(s): SKILL.md, metadata.json, context-snippet.md, provenance-map.json."

### 4. Fix the `active` Symlink in the New Location

Recreate or repair the `active` symlink in `{new_skill_group}`:

1. Inspect `{old_skill_group}/active` to determine the target version (the value the symlink points to — typically just the version string, not an absolute path)
2. Check `{new_skill_group}/active`:
   - If the copy in section 1 preserved it correctly and it points to the same version string → leave it as-is
   - If it exists but points somewhere invalid (e.g., an absolute path back into the old location) → remove and recreate it
   - If it is missing (some copy tools do not preserve symlinks) → create it
3. The symlink target should be a relative path: the version string alone (e.g., `0.6.0`), so that `{new_skill_group}/active/{new_name}/` resolves correctly

**Rollback on failure:**

- `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}`
- Halt with: "**Failed to repair `active` symlink** in `{new_skill_group}`: {error}. Rolled back both new directories. Old skill is intact."

### 5. Verify — No Trace of `{old_name}` Inside the New Location

This is the commit-point check. If any match is found, the rename is not safe to commit.

For every version `v` in `affected_versions`, grep (literal substring, case-sensitive) for `{old_name}` in:

- `{new_skill_group}/{v}/{new_name}/SKILL.md`
- `{new_skill_group}/{v}/{new_name}/metadata.json`
- `{new_skill_group}/{v}/{new_name}/context-snippet.md`
- `{new_forge_group}/{v}/provenance-map.json`

Also check the directory listing itself:

- `{new_skill_group}/{v}/` should contain `{new_name}/` and MUST NOT contain `{old_name}/`

**Important nuance:** body text of SKILL.md may legitimately mention the old name (e.g., historical notes, changelog, cross-references). The grep is allowed to match within SKILL.md body text ONLY if the match is clearly informational (surrounding prose, not a structural reference). For the purposes of this step, treat any match in `metadata.json`, `context-snippet.md`, `provenance-map.json`, or the SKILL.md frontmatter block as a hard failure. Matches inside the SKILL.md body below the closing `---` are recorded as `verification_warnings` but do not block the rename.

**On hard failure (any structural reference to `{old_name}` remains):**

- `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}`
- Halt with: "**Verification failed.** `{old_name}` still appears in: {list of paths}. Rolled back both new directories. Old skill is intact."

Report: "**Verified** — no structural references to `{old_name}` remain inside the new location across {affected_versions_count} version(s). {if verification_warnings is non-empty: 'Informational body-text mentions retained in SKILL.md: {list}.'}"

### 6. Update Export Manifest

**If `manifest_exists = false` (step-01 recorded no manifest on disk):**

Skip this section entirely. Set `manifest_updated = false` and `manifest_backup = null`. There is no manifest to re-key — the skill was never exported. Section 7 will find no platform context files to rebuild either (no manifest means no prior export, so no `<!-- SKF:BEGIN -->` markers exist), and any platform file that happens to be present will be left alone by the section 2 marker check.

Report: "**Manifest update skipped** — no `.export-manifest.json` on disk. The rename is a pure on-disk operation."

**If `manifest_exists = true`:**

1. Load `{skills_output_folder}/.export-manifest.json`
2. **Hold a deep copy in memory** as `manifest_backup` — required for rollback in this section and section 7 on failure
3. If the manifest contains `exports.{old_name}`:
   - Set `exports.{new_name}` = deep copy of `exports.{old_name}` (preserving `active_version`, `versions` map, and all fields)
   - Delete `exports.{old_name}`
4. If the manifest does NOT contain `exports.{old_name}` (the skill was on disk but never exported), skip the re-key — the manifest has nothing to change for this skill
5. Write the updated manifest back to `{skills_output_folder}/.export-manifest.json`

**Rollback on write failure:**

- Restore the manifest from `manifest_backup` (write it back to disk)
- `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}`
- Halt with: "**Manifest update failed:** {error}. Restored manifest from backup and rolled back new directories. Old skill is intact."

Set context flag `manifest_updated = true`.

Report: "**Manifest updated** — re-keyed `exports.{old_name}` → `exports.{new_name}`."

### 7. Rebuild Context Files

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
   - If the file contains `<!-- SKF:BEGIN -->` but no matching `<!-- SKF:END -->`, record the error against that context file and continue to the next entry — do not halt the entire rename on a malformed context file

3. **Build the exported skill set (version-aware, deprecated-excluded)** using the same logic as export-skill step-04 section 4b and the snippet resolution logic from section 4c:
   - Read the manifest's `exports` object (already updated in section 6, so `{new_name}` is present and `{old_name}` is absent)
   - For each skill, resolve its `active_version`
   - If `versions.{active_version}.status == "deprecated"`, skip that skill entirely
   - For each remaining `{skill-name, active_version}` pair, read `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/context-snippet.md`
   - If missing, fall back to the `active` symlink path; if still missing, skip with a warning

4. **Rewrite root paths for the current context file** using the generic rewrite algorithm from export-skill step-04 section 4d:

   For each snippet, parse the `root:` line (`root: {prefix}{skill-name}/`), strip the trailing `{skill-name}/` to extract the current prefix, and replace it with the **effective target prefix** if different. The effective target prefix is `snippet_skill_root_override` when that key is set in config.yaml — applied uniformly to every snippet so the managed section references the real on-disk location and never mixes override and per-IDE paths — otherwise the current entry's `skill_root`. See `skf-export-skill/steps-c/step-04-update-context.md` §4d for full semantics.

5. **Sort skills alphabetically by name.** Count totals (skills, stack skills).

6. **Assemble the new managed section** using the format from `{managedSectionLogic}`:

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

7. **Surgical replacement — Regenerate case only:**
   - Locate the `<!-- SKF:BEGIN` line — preserve everything before it
   - Locate the `<!-- SKF:END -->` line — preserve everything after it
   - Replace everything between the markers (inclusive) with the new managed section
   - Write the file back

8. **Verify:**
   - Re-read the written file
   - Confirm both markers are present
   - Confirm `{old_name}` no longer appears between the markers
   - Confirm `{new_name}` appears between the markers (if this skill's active version is not deprecated)
   - Confirm content outside the markers is byte-identical to what was preserved

9. **On per-file failure:** record the error against that context file and continue to the next entry. Do not halt the rename on a recoverable per-context-file error — the manifest and filesystem are already consistent; context files can be re-rebuilt later via `[EX] Export Skill`.

**After the loop:**

- Record `context_files_updated` as the list of files that were successfully rewritten
- Record `context_files_failed` as the list of any that failed

Report: "**Rebuilt managed sections in:** {list of updated files}. {if any failed: 'Failed: {list} — re-run `[EX] Export Skill` to retry.'}"

**Note:** Section 7 failures do not trigger a rollback because the manifest and filesystem are the canonical state. Platform context files are derived artifacts that can be regenerated at any time.

### 8. Delete Old Directories (Point of No Return)

This is the only section after which rollback is impossible. By this point:

- `{new_skill_group}` is fully materialized with all inner directories renamed and files updated
- `{new_forge_group}` is fully materialized with `skill_name` updated in every provenance map
- No structural references to `{old_name}` remain inside either new directory (verified in section 5)
- The manifest has been re-keyed (section 6)
- Platform context files reference `{new_name}` (section 7, best-effort)

Execute the deletes:

1. Verify `{old_skill_group}` is inside `{skills_output_folder}` (defense in depth)
2. `rm -rf {old_skill_group}` — delete the old skill_group recursively
3. Verify deletion succeeded (the path no longer exists)
4. Verify `{old_forge_group}` is inside `{forge_data_folder}` (defense in depth)
5. `rm -rf {old_forge_group}` — delete the old forge_group recursively
6. Verify deletion succeeded

**On deletion error:**

- Record the error in `deletion_errors` against the specific path
- Continue attempting the other path — partial cleanup is still better than none
- Do NOT attempt any rollback — the new name is already committed and the old name's remnants can be removed manually

Report: "**Deleted old directories:** `{old_skill_group}` and `{old_forge_group}`. {if deletion_errors is non-empty: 'Errors: {list} — remove manually with `rm -rf {path}`.'}"

### 9. Store Results in Context

Store the following for step-03:

- `old_name` — the previous skill name
- `new_name` — the new skill name
- `affected_versions` — list of versions that were renamed
- `affected_versions_count` — integer count
- `files_updated_per_version` — structured summary (SKILL.md, metadata.json, context-snippet.md, provenance-map.json — each with ×count)
- `manifest_rekeyed` — boolean (true if section 6 succeeded)
- `context_files_updated` — list of successfully rebuilt files
- `context_files_failed` — list of files that failed to rebuild (empty if none)
- `section2_warnings` — list of orphaned version warnings (empty if none)
- `section3_warnings` — list of missing file warnings (empty if none)
- `verification_warnings` — list of informational SKILL.md body mentions of `{old_name}` retained (empty if none)
- `deletion_errors` — list of post-commit deletion errors (empty if none)

### 10. Load Next Step

Load, read the full file, and then execute `{nextStepFile}`.

## Error Handling Summary

| Section | Failure Mode | Reversible? | Recovery Action |
|---------|--------------|-------------|-----------------|
| 1 | Copy failure | Yes | Delete whichever new directory exists; old skill intact |
| 2 | Inner rename failure | Yes | `rm -rf` both new directories; old skill intact |
| 3 | File update failure | Yes | `rm -rf` both new directories; old skill intact |
| 4 | `active` symlink repair failure | Yes | `rm -rf` both new directories; old skill intact |
| 5 | Verification failure | Yes | `rm -rf` both new directories; old skill intact |
| 6 | Manifest write failure | Yes | Restore manifest from backup; `rm -rf` both new directories; old skill intact |
| 7 | Platform context rebuild failure | Per-file | Record errors, continue other platforms; do NOT rollback — manifest and disk are canonical |
| 8 | Delete failure | **No** | Record deletion errors; new name is already committed; user removes remnants manually |

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all execution sections have been attempted (copy, inner rename, file updates, symlink fix, verification, manifest re-key, context rebuild, old delete) and results have been stored in context, will you then load and read fully `{nextStepFile}` to generate the final report.

