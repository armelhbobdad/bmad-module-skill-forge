---
nextStepFile: './step-05-token-report.md'
managedSectionData: 'assets/managed-section-format.md'
---

# Step 4: Update Context

## STEP GOAL:

To update the managed `<!-- SKF:BEGIN/END -->` section in the platform-appropriate context file (CLAUDE.md/AGENTS.md/.cursorrules) using the four-case logic defined by ADR-J (Create, Append, Regenerate, Malformed Markers halt), rebuilding the complete skill index from all exported skills.

## Rules

- Focus only on the managed section update in the target context file
- Do not modify any content outside `<!-- SKF:BEGIN -->` and `<!-- SKF:END -->` markers
- Do not write without user confirmation — this modifies shared project files
- If `passive_context: false` was detected in step-01, skip this step entirely
- **Multi-skill mode:** this step executes ONCE for the whole batch, not once per skill. §4b already builds the exported skill set from the manifest (plus current export targets), so a multi-skill run naturally appears as a single rebuild. The only batch adjustment is in §9b: update the manifest entry for every skill in `skill_batch` (not just one), and include all of them when computing `ides_written`. See step-01 §1c.

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Check Passive Context Setting

**If `passive_context: false` was detected in step-01:**

"**Passive context disabled in preferences.yaml. Skipping context update.**"

Auto-proceed immediately to {nextStepFile}.

**If `passive_context: true` (default):** Continue to step 2.

### 2. Load Managed Section Format

Load {managedSectionData} and read the complete format template and four-case logic.

### 3. Determine Target File(s)

Using the `target_context_files` list resolved in step-01, determine all target files. Each entry has `{context_file, skill_root}` — the context file to write and the IDE's skill directory for root path resolution.

For each entry in `target_context_files`, resolve target file path: `{context_file}`

**If multiple context files:** Sections 4-9a execute as a loop — one full pass per target context file. Each iteration uses the same skill index but rewrites root paths per context file's `skill_root` (section 4d) and writes to the target context file. Section 9b executes once after all iterations complete.

**Processing order:** Process context files in the order listed in `target_context_files`.

#### 3b. Detect Orphaned Platform Files (Stale Managed Sections)

A context file becomes orphaned when its IDE is removed from `config.yaml` after a prior export. The file still contains an SKF managed section pointing to stale skill versions, but no future export will rewrite it.

Build `orphaned_context_files` — the set of context files that exist on disk with an `<!-- SKF:BEGIN -->` marker but whose context file is NOT in the current `target_context_files` list:

1. For each known context file in `{CLAUDE.md, .cursorrules, AGENTS.md}`:
   - If the context file is in `target_context_files`, skip (it will be rewritten in the main loop)
   - Otherwise, check whether the file exists at `{context_file}`
   - If the file exists, read it and check for the `<!-- SKF:BEGIN -->` marker
   - If the marker is present, add the file path to `orphaned_context_files` along with the context file name

2. If `orphaned_context_files` is non-empty, emit a warning:

   "**Orphaned context files detected.** The following files contain SKF managed sections but no configured IDEs target them:
   {list: context file → file path}

   The managed sections in these files are stale. Options:
   - **(a) clear** — remove the SKF managed section from each orphaned file (surgical marker replacement, leaves user content intact)
   - **(b) keep** — leave them untouched (they will remain stale until you re-add an IDE that targets this file or delete the file)
   - **(c) rewrite** — also rewrite the orphaned files with the current skill index (use this if the IDE was removed by mistake)"

3. Wait for user choice. In non-interactive mode (dry-run or unattended), default to **(b) keep** and print the warning only.

4. If the user chose **(a) clear**: for each orphaned file, replace everything between `<!-- SKF:BEGIN` and `<!-- SKF:END -->` (inclusive) with an empty string, preserving surrounding content byte-exactly. Record the cleared files in `orphans_cleared`.

5. If the user chose **(c) rewrite**: add each orphaned context file to a separate `rewrite_context_files` list (kept distinct from `target_context_files` so the user's intent to only export to configured IDEs is preserved in the manifest). Use `.agents/skills/` as the default skill root for rewritten orphans. Sections 4–9a will loop over `target_context_files + rewrite_context_files` for this run only. Record the rewritten files in `orphans_rewritten`.

6. If the user chose **(b) keep**: record nothing and proceed.

This cleanup only runs during interactive export. Drop-skill and rename-skill operate on the manifest's declared context files and are not responsible for orphan detection.

### 4. Rebuild Complete Skill Index

#### 4a. Read Export Manifest (v2 — version-aware)

Read `{skills_output_folder}/.export-manifest.json` — see `knowledge/version-paths.md` for the full v2 schema:

**If the file exists:** Parse JSON. Check for `schema_version` field:

**v2 manifest** (`schema_version: "2"`):
```json
{
  "schema_version": "2",
  "exports": {
    "skill-name": {
      "active_version": "0.6.0",
      "versions": {
        "0.1.0": {
          "ides": ["claude-code"],
          "last_exported": "2026-01-15",
          "status": "deprecated"
        },
        "0.5.0": {
          "ides": ["claude-code"],
          "last_exported": "2026-03-15",
          "status": "archived"
        },
        "0.6.0": {
          "ides": ["claude-code", "github-copilot"],
          "last_exported": "2026-04-04",
          "status": "active"
        }
      }
    }
  }
}
```

**Status values:**
- `"active"` — currently exported; snippet appears in managed sections
- `"archived"` — previously exported, not active; files retained for rollback
- `"deprecated"` — dropped via drop-skill workflow; excluded from all exports (files may or may not exist on disk)
- `"draft"` — created but never exported

**Legacy `platforms` → `ides` rename:** Pre-rename v2 manifests used a `platforms` array at the version level. If a version entry contains `platforms` instead of (or in addition to) `ides`, treat `platforms` as `ides` and rewrite it to `ides` on the next manifest write. This is a silent in-place upgrade — no user prompt, no v3 bump.

**v1 manifest** (no `schema_version` field — migrate in-place to v2):
1. For each entry in `exports`, read its `last_exported` (v1 had no per-version IDE list)
2. Resolve the skill's current version from `{resolved_skill_package}/metadata.json`
3. Wrap in v2 structure: set `active_version` to the resolved version, create a single entry in `versions` with `status: "active"`, `ides: []` (unknown — will be filled on next successful export), and `last_exported`
4. Set `schema_version: "2"` at root
5. Hold the migrated structure in context (it will be written in section 9b)

**If the file does not exist** (first export or migration): Treat as empty — only the current export target will appear in the rebuilt index.

#### 4b. Build Exported Skill Set (version-aware)

Determine the set of skills to include in the rebuilt index:

1. Start with all skill names listed in the manifest's `exports` object (if manifest exists)
2. For each skill, record its `active_version` from the manifest (v2 schema)
3. **Integrity guard — `active_version` must resolve to a versions entry:** Check that `versions[active_version]` exists as a key. If `active_version` is set but there is no matching entry under `versions`, the manifest is inconsistent (possible corruption or a botched v1→v2 migration). Skip this skill and log a loud warning: "**Manifest integrity warning:** `{skill-name}.active_version = v{active_version}` has no matching entry under `versions`. Skipping. Re-run `[EX] Export Skill` on `{skill-name}` to repair the manifest entry."
4. **Exclude deprecated skills:** If the `active_version` entry in `versions.{active_version}` has `status: "deprecated"`, skip this skill entirely — it has been dropped via drop-skill workflow and must not appear in the managed section. Log: "Skipping {skill-name} — active version v{active_version} is deprecated"
5. Add the current export target skill name (ensures it is always included even before manifest is written) — use the version from `{resolved_skill_package}/metadata.json` as its `active_version`
6. This is the **exported skill set** — each entry has a skill name and its resolved `active_version`

#### 4c. Resolve and Filter Snippets (manifest-driven — replaces glob scan)

Instead of globbing `{skills_output_folder}/*/context-snippet.md`, resolve snippets from the exported skill set built in 4b:

**For each skill in the exported skill set:**
1. Resolve `{skill_package}` using the skill's `active_version`: `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
2. Read `{skill_package}/context-snippet.md`
3. **If snippet exists:** Add to skill index
4. **If snippet does not exist at the versioned path:** Check for `active` symlink at `{skills_output_folder}/{skill-name}/active/{skill-name}/context-snippet.md`. If still not found, skip with warning: "Snippet missing for {skill-name} v{active_version} — skipping from managed section"

**Skills NOT in the exported skill set are never scanned** — they have not been through export-skill and must not appear in the managed section (ADR-K).

**If no snippets pass the filter:** Generate managed section with zero skills — header only, no skill entries.

#### 4d. Rewrite Root Paths for Target Context File

The context-snippet.md files on disk contain root paths for the IDE they were originally exported to. When assembling the managed section for the current target context file, rewrite root paths if they differ from the target's `skill_root`.

**Generic root path rewrite algorithm** (no hardcoded prefix list):

For each snippet being included in the managed section:

1. Read the `root:` value from the snippet's first line — it has the form `root: {prefix}{skill-name}/`
2. Extract the current prefix by stripping the trailing `{skill-name}/` from the root value
3. **Resolve the effective target prefix:** If `snippet_skill_root_override` is set in config.yaml, use the override value as the effective target prefix for this rebuild — by the override contract every skill in the repo lives under that single shared on-disk directory, so the managed section must reference the override for *every* snippet (not just the ones that already match it). Otherwise, use the current target's `skill_root` as the effective target prefix.
4. Compare the extracted prefix against the effective target prefix
5. If they differ, replace the prefix with the effective target prefix, preserving the skill name. When the override is set, this rewrites stale per-IDE prefixes carried by sibling snippets that were exported before the override was adopted, so the rebuilt managed section uniformly references the real on-disk location instead of mixing override and per-IDE paths.
6. Example: if snippet has `root: .claude/skills/my-lib/` but target skill_root is `.windsurf/skills/`, rewrite to `root: .windsurf/skills/my-lib/`
7. Example: if `snippet_skill_root_override: skills/` is set, the effective target prefix is `skills/` regardless of the IDE mapping. A snippet with `root: skills/my-lib/` passes through unchanged; a sibling snippet with `root: .claude/skills/my-other/` (carried over from a pre-override export) is rewritten to `root: skills/my-other/`.

This algorithm handles any IDE's skill root path — including future IDEs — without enumerating known prefixes. The legacy `skills/` prefix (no leading dot) may appear in draft snippets generated by create-skill/quick-skill before export.

**Sort skills alphabetically by name.**

Count totals:
- Total skills (single type)
- Total stack skills

### 5. Generate Managed Section

Assemble the complete managed section:

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

### 6. Detect Case and Prepare Changes

**Check target file at `{target-file}`:**

**Case 1: Create (file does not exist)**
- Action: Create new file with managed section only
- Diff: Show entire managed section as new content

**Case 2: Append (file exists, no `<!-- SKF:BEGIN` marker found)**
- Action: Read existing content, append managed section at end
- Diff: Show managed section being appended after existing content
- Preserved: ALL existing content untouched

**Case 3: Regenerate (file contains `<!-- SKF:BEGIN` and `<!-- SKF:END -->`)**
- Action: Replace everything between markers (inclusive) with new managed section
- Diff: Show old managed section vs new managed section
- Preserved: ALL content before `<!-- SKF:BEGIN` and after `<!-- SKF:END -->`

**Case 4: Malformed markers (file contains `<!-- SKF:BEGIN` but no `<!-- SKF:END -->`)**
- Action: HALT with warning: "Malformed SKF markers detected in `{target-file}` — `<!-- SKF:BEGIN` found but `<!-- SKF:END -->` is missing. Please restore the end marker manually before running export."
- Do NOT attempt to write or append — the file is in an inconsistent state

### 7. Present Change Preview

"**Context update prepared.{if multi-platform: ' (platform {i}/{total}: {platform})'}**

**Target:** `{target-file}`
**Case:** {1: Create / 2: Append / 3: Regenerate}
**Skills in index:** {n} skills, {m} stack

**Changes:**

{Show diff preview:}
- For Case 1: Show full file content to be created
- For Case 2: Show `...existing content preserved...\n\n{managed section}`
- For Case 3: Show old section vs new section with surrounding context preserved

**Content outside markers:** {preserved / n/a (new file)}

**Ready to write changes?**"

### 8. Present MENU OPTIONS

**If dry-run mode:**

"**[DRY RUN] No files will be written. Preview above shows what would change.**

**Proceeding to token report...**"

Auto-proceed to {nextStepFile}.

**If NOT dry-run:**

Display: "**Select:** [C] Continue — write changes to {target-file}"

**Multi-target behavior:** When processing multiple context files, present all previews together before asking for a single confirmation. After confirmation, write all target files sequentially, verifying each one.

"**Targets:** {list all context-file → target-file pairs}
**Ready to write changes to all targets?**"

Display: "**Select:** [C] Continue — write changes to all targets"

#### Menu Handling Logic:

- IF C: Write the changes to all target files (or single target), verify each write succeeded, then load, read entire file, then execute {nextStepFile}
- IF Any other: help user respond, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-approve context file update"
- ONLY proceed to next step when user selects 'C'
- In dry-run mode, auto-proceed without writing

### 9. Write and Verify (Non-Dry-Run Only)

After user confirms with 'C':

1. Write the file using the appropriate case logic
2. Re-read the written file
3. Verify `<!-- SKF:BEGIN` and `<!-- SKF:END -->` markers are present
4. Verify content outside markers is unchanged (for Cases 2 and 3)
5. Report: "**{target-file} updated successfully.** Verified: markers present, external content preserved."

**If verification fails:**
"**WARNING: Write verification failed.** {describe issue}. File may need manual review."

### 9b. Update Export Manifest (Non-Dry-Run Only)

**This section executes ONCE after all context-file iterations complete** (outside the per-context-file loop defined in section 3). Only IDEs whose target context files were successfully written and verified in section 9 are recorded.

**`ides` field definition:** `ides` is the list of IDE identifiers from `config.yaml.ides` (e.g. `claude-code`, `cursor`, `github-copilot`) whose context files were successfully written and verified in section 9. It is NOT the context file name (`CLAUDE.md`) and NOT the skill root path (`.claude/skills/`). Each IDE → context file → skill root mapping is defined in `skf-export-skill/assets/managed-section-format.md`.

1. Read `{skills_output_folder}/.export-manifest.json` (or start with `{"schema_version": "2", "exports": {}}` if it does not exist)
2. Ensure `schema_version` is `"2"` (if v1 was migrated in section 4a, the migrated structure is already in context). If any version entry still has a legacy `platforms` key, rename it to `ides` in place (see §4a).
3. Compute `ides_written` — the set of IDE identifiers from `config.yaml.ides` whose mapped context file was successfully written in section 9 (deduplicated, sorted). When `--context-file` was passed explicitly, `ides_written` contains only the IDEs that map to that single context file.
4. For each skill in `skill_batch` (multi-skill mode) — or the single current skill (single-skill mode) — add or update its entry in v2 format:
   ```json
   "{skill-name}": {
     "active_version": "{version}",
     "versions": {
       "{version}": {
         "ides": ["{ides_written}"],
         "last_exported": "{current-date}",
         "status": "active"
       }
     }
   }
   ```
   - `{version}` is the version from each skill's `{resolved_skill_package}/metadata.json`
   - If the skill already has a manifest entry:
     - Set `active_version` to the current version
     - If the version already exists in `versions`, union its existing `ides` with `ides_written` (deduplicate, keep sorted), refresh `last_exported`, and set `status: "active"`
     - If this is a new version, add it to `versions` with `status: "active"` and set any previously-active version's status to `"archived"`
     - Preserve all other version entries in `versions` (do not delete archived versions)
5. Write the updated manifest once to `{skills_output_folder}/.export-manifest.json` after all skills in the batch have been applied

**Dry-run mode:** Do NOT update the manifest. Display: "**[DRY RUN] Export manifest would be updated for {skill-name-list} — ides: {ides_written}.**" (list every skill in `skill_batch`)

**Error handling:** If manifest write fails, warn but do not fail the workflow — the managed section was already written successfully.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user confirms changes by selecting 'C' (or auto-proceed in dry-run) and the write is verified will you load and read fully `{nextStepFile}` to execute the token report.

