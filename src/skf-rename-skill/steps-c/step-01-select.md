---
nextStepFile: './step-02-execute.md'
versionPathsKnowledge: 'knowledge/version-paths.md'
---

# Step 1: Select Rename Target

## STEP GOAL:

Identify the skill the user wants to rename, validate the new name against the agentskills.io spec (kebab-case, length, uniqueness), warn about source authority implications, enumerate every version that will be touched, and obtain explicit user confirmation before any filesystem operation is scheduled. Every selection decision is stored in context so step-02 can execute the rename transactionally.

## Rules

- Focus only on selection, validation, and confirmation — do not modify manifest, copy, or delete files
- Do not proceed without explicit user confirmation at the final gate
- Do not accept a new name that fails validation (kebab-case, length, uniqueness)
- Present the list of affected versions clearly so the user understands the scope

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Knowledge

Read `{versionPathsKnowledge}` completely and extract:

- Path templates: `{skill_package}`, `{skill_group}`, `{forge_version}`, `{forge_group}`
- Export manifest v2 schema (`schema_version`, `exports`, `active_version`, `versions` map, `status` field values)
- The Rename section under "Skill Management Operations" — the complete list of 9 locations that must be updated coherently

You will use these templates and rules to build directory paths, enumerate affected versions, and plan the transactional rename in step-02.

### 2. Read Export Manifest

Load `{skills_output_folder}/.export-manifest.json` if it exists.

**If the file is missing or empty:** Treat as an empty manifest — proceed to section 3 and rely entirely on the on-disk directory scan. Drafted or never-exported skills can still be renamed. Store `manifest_exists = false` for later use in step-02 (section 6 will not attempt to update a manifest that does not exist).

**If the file exists but contains no `exports` entries:** Same handling — proceed to section 3 with the directory scan. Store `manifest_exists = true` so step-02 still touches the (empty) manifest on write.

**If the file exists with entries:** Parse JSON and verify `schema_version` is `"2"`. If the manifest is v1 (no `schema_version` field), note this but continue — treat every entry as having a single active version derived from its current state. Store `manifest_exists = true`.

**Hard halt condition:** If the file exists but is malformed (not valid JSON), halt with: "**Export manifest is corrupt** at `{skills_output_folder}/.export-manifest.json` — fix or remove the file before renaming."

### 3. List Available Skills

Build and display a summary of every skill available for rename. Start with the manifest (if any), then augment with on-disk scan.

For each skill in the manifest's `exports` (if `manifest_exists` and entries exist):

1. Read `active_version` from the manifest entry
2. Count the number of versions in the skill's `versions` map
3. Display `{skill-name} ({n} versions, active: {active_version})`

Also scan `{skills_output_folder}/` for any top-level directories that are NOT present in the manifest's `exports` object. Record these as "(not in manifest)" — they represent draft or orphaned skills that the rename workflow can also handle. When the manifest is missing or empty, every on-disk skill appears in this category.

**If the combined list is empty** (no manifest entries AND no on-disk skill directories): halt with "**Rename Skill — nothing to rename.** No skills found in `{skills_output_folder}/`. Run `[CS] Create Skill` first."

Display the combined list:

```
**Rename Skill — select target**

Available skills:
1. cognee (3 versions, active: 0.6.0)
2. express (1 version, active: 4.18.0)
3. legacy-helper (not in manifest)
```

### 4. Ask Which Skill

"**Which skill would you like to rename?**
Enter the skill name or its number from the list above."

Wait for user input. Accept either the numeric index or the skill name (exact match). **GATE [default: use args]** — If `{headless_mode}` and old skill name was provided as argument: select that skill and auto-proceed. If not provided, HALT: "headless mode requires old_name argument."

**If the user's input does not match any listed skill:** Re-display the list and ask again.

Store the selection as `old_name`.

### 5. Ask for New Name

"**What is the new name for this skill?**
The new name must be kebab-case: lowercase alphanumeric with hyphens, 1-64 characters, matching the regex `^[a-z][a-z0-9-]*[a-z0-9]$` (single-character names may be a single lowercase letter or digit)."

Wait for user input. Trim whitespace. **GATE [default: use args]** — If `{headless_mode}` and new_name was provided as argument: use it and auto-proceed through validation. If not provided, HALT: "headless mode requires new_name argument."

Apply the following validations in order:

1. **Kebab-case format:** Must match `^[a-z][a-z0-9-]*[a-z0-9]$` (or `^[a-z0-9]$` for the single-character case). If it fails:
   "**Invalid name format.** The new name must be lowercase alphanumeric with hyphens, starting with a letter and ending with a letter or digit. Try again."
   Re-ask.

2. **Length:** Must be 1-64 characters per the agentskills.io spec. If it fails:
   "**Invalid name length.** The new name must be 1-64 characters. Try again."
   Re-ask.

3. **Same as old name:** If the new name equals `old_name`:
   "**The new name is identical to the current name.** Nothing to rename. Try again or abort the workflow."
   Re-ask.

4. **Collision check:** The new name MUST NOT collide with any existing skill:
   - It must not appear as a key in `exports` in the manifest
   - It must not exist as a top-level directory in `{skills_output_folder}/`
   - It must not exist as a top-level directory in `{forge_data_folder}/`

   If any collision is detected:
   "**Name collision.** `{new-name}` already exists at: {list the colliding locations}. Pick a different name."
   Re-ask.

Only after all four validations pass, store the input as `new_name`.

### 6. Source Authority Check

Resolve `{skill_package}` for the active version using the manifest:
`{skills_output_folder}/{old_name}/{active_version}/{old_name}/metadata.json`

Read the `source_authority` field (if present).

**If `source_authority == "official"`:**

Display the warning:

```
⚠️  **source_authority: "official"**
This skill has `source_authority: "official"`. Renaming locally will diverge from any
published skill at agentskills.io under this name. Consumers fetching from the
registry will still get the original name. Rename is a LOCAL operation only — it
does not rename anything at the registry.
```

Ask: "**Continue anyway?** [Y/N]"

Wait for response.
- **If `N`** or anything other than `Y` → "**Cancelled.** No changes were made." HALT the workflow.
- **If `Y`** → proceed.

**If `source_authority` is absent, or any value other than `"official"`:** skip the warning and proceed.

### 7. Enumerate Affected Versions

List all versions for `old_name`:

1. Read every key under `exports.{old_name}.versions` in the manifest
2. Also list every directory under `{skills_output_folder}/{old_name}/` that looks like a version (any entry that is not `active`)
3. Union the two sets — this handles both manifest-tracked and orphaned on-disk versions
4. Sort descending where possible (newest first)

Store the sorted list as `affected_versions` and count it as `affected_versions_count`.

Also resolve the four outer paths using the templates from `{versionPathsKnowledge}`:

- `old_skill_group` = `{skills_output_folder}/{old_name}/`
- `new_skill_group` = `{skills_output_folder}/{new_name}/`
- `old_forge_group` = `{forge_data_folder}/{old_name}/`
- `new_forge_group` = `{forge_data_folder}/{new_name}/`

### 8. Confirmation Gate

Display the full operation summary:

```
**About to rename:**

  From: {old_name}
  To:   {new_name}
  Versions affected: {affected_versions_count} ({comma-separated affected_versions})

  Directories that will be copied then removed:
    {old_skill_group}  →  {new_skill_group}
    {old_forge_group}  →  {new_forge_group}

  Inside each version, the inner `{old_name}/` directory will be renamed to `{new_name}/`,
  and the following files will be updated:
    - SKILL.md (frontmatter `name` field)
    - metadata.json (`name` field)
    - context-snippet.md (display name and root paths)
    - provenance-map.json (`skill_name` field, under {old_forge_group})

  Manifest `exports.{old_name}` will be re-keyed to `exports.{new_name}`.
  Platform context files (CLAUDE.md, .cursorrules, AGENTS.md) will be rebuilt so
  the managed section references `{new_name}` instead of `{old_name}`.

Operation is **transactional** — the new name will be fully materialized and verified
before the old name is removed. If any step fails before the final delete, the new
directories are removed and the old skill remains intact.

Proceed? [Y/N]
```

**GATE [default: Y]** — If `{headless_mode}`: auto-proceed with [Y], log: "headless: auto-confirmed rename {old_name} → {new_name}"

Wait for explicit user response.

- **If `Y`** → proceed to section 9
- **If `N`** → "**Cancelled.** No changes were made." HALT the workflow
- **Any other input** → re-display the confirmation and ask again

### 9. Store Decisions in Context

Store the following decisions in workflow context for step-02:

- `old_name` — the current skill name
- `new_name` — the validated new name
- `affected_versions` — list of version strings for every version that must be updated
- `affected_versions_count` — integer count of the above
- `old_skill_group` — absolute path `{skills_output_folder}/{old_name}/`
- `new_skill_group` — absolute path `{skills_output_folder}/{new_name}/`
- `old_forge_group` — absolute path `{forge_data_folder}/{old_name}/`
- `new_forge_group` — absolute path `{forge_data_folder}/{new_name}/`
- `source_authority_override` — boolean (true if the user acknowledged the `"official"` warning, false/absent otherwise)

### 10. Load Next Step

Load, read the full file, and then execute `{nextStepFile}`.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user has confirmed with `Y` at the confirmation gate AND all selection decisions have been stored in context, will you then load and read fully `{nextStepFile}` to execute the rename.

