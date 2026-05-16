---
nextStepFile: 'execute.md'
versionPathsKnowledge: 'knowledge/version-paths.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Select Drop Target

## STEP GOAL:

Identify exactly what the user wants to drop — which skill, which version(s), and whether the drop is a soft deprecation (manifest-only) or a hard purge (files deleted). Enforce the active version guard, gather the list of affected directories, and obtain explicit user confirmation before any write or delete operation is scheduled.

## Rules

- Focus only on selection, validation, and confirmation — do not modify the manifest or delete files
- Do not proceed without explicit user confirmation at the final gate
- Do not drop an active version when other non-deprecated versions exist
- Present selections clearly so the user can verify scope, mode, and blast radius

## MANDATORY SEQUENCE

### 1. Load Knowledge

Read `{versionPathsKnowledge}` completely and extract:

- Path templates: `{skill_package}`, `{skill_group}`, `{forge_version}`, `{forge_group}`
- Export manifest v2 schema (`schema_version`, `exports`, `active_version`, `versions` map, `status` field values)
- Skill management operations (Drop section — soft vs hard, active version guard, skill-level drop)

You will use these templates and rules to build directory paths and enforce safety guards in the following sections.

### 2. Read Export Manifest

Load `{skills_output_folder}/.export-manifest.json` if it exists.

**If the file is missing, empty, or contains no `exports` entries:** Treat as an empty manifest — proceed to section 3 and rely on the on-disk directory scan. Draft skills (created by `[CS]`/`[QS]`/`[SS]` but never exported) can still be hard-dropped in purge mode. Store `manifest_exists = false` so section 8 (Ask Mode) can restrict the options to purge only. Soft-deprecate is meaningless without a manifest to record the deprecation against.

**If the file exists with entries:** Parse JSON and verify `schema_version` is `"2"`. If the manifest is v1 (no `schema_version` field), note this but continue — treat every entry as having a single active version derived from its current state. Store `manifest_exists = true`.

**Hard halt condition:** If the file exists but is malformed (not valid JSON), halt with: "**Export manifest is corrupt** at `{skills_output_folder}/.export-manifest.json` — fix or remove the file before dropping." HALT (exit code 3, `halt_reason: "manifest-corrupt"`). In headless mode, emit the error envelope per SKILL.md "Result Contract (Headless)" with `skill: null`, `drop_mode: null`, `versions_affected: []`.

### 3. List Available Skills

Build and display a summary of every skill available to drop. Start with the manifest (if any), then augment with an on-disk scan.

For each skill in the manifest's `exports` (only if `manifest_exists = true` and entries exist):

1. Read `active_version` from the manifest entry
2. List every entry in the skill's `versions` map with its `status` field
3. Mark the active version with a trailing `*`
4. Sort versions in descending order (newest first) where possible

Also scan `{skills_output_folder}/` for any top-level directories that are NOT present in the manifest's `exports` object. Record these as "(not in manifest)" — they represent draft or orphaned skills eligible for purge mode only. When the manifest is missing or empty, every on-disk skill appears in this category.

**If the combined list is empty** (no manifest entries AND no on-disk skill directories): halt with "**Drop Skill — nothing to drop.** No skills found in `{skills_output_folder}/` and no entries in `.export-manifest.json`. Run `[CS] Create Skill` first." HALT (exit code 3, `halt_reason: "nothing-to-drop"`). In headless mode, emit the error envelope with `skill: null`, `drop_mode: null`, `versions_affected: []`.

Display the combined list:

```
**Drop Skill — select target**

Available skills:
1. cognee
   - 0.1.0 (deprecated)
   - 0.5.0 (archived)
   - 0.6.0 (active) *
2. express
   - 4.18.0 (active) *
3. legacy-helper (not in manifest — purge only)
```

### 4. Ask Which Skill

"**Which skill would you like to drop?**
Enter the skill name or its number from the list above, or `cancel` / `exit` / `:q` to abort."

Wait for user input. Accept either the numeric index or the skill name (exact match). **GATE [default: use args]** — If `{headless_mode}` and skill name was provided as argument: select that skill and auto-proceed. If not provided, HALT (exit code 2, `halt_reason: "input-missing"`): "headless mode requires skill name argument." In headless mode, emit the error envelope with `skill: null`, `drop_mode: null`.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q`: Display "Cancelled — no changes were made." and HALT (exit code 6, `halt_reason: "user-cancelled"`).
- **If the user's input does not match any listed skill:** Re-display the list and ask again.

Store the selection as `target_skill`. Also store `target_in_manifest = true` if the selected skill has an entry in the manifest, `false` otherwise — subsequent sections use this flag to restrict the available drop options.

### 5. Display Version Details

**If `target_in_manifest = true`**, display every version with its full metadata from the manifest:

```
**{target_skill} — versions:**

| Version | Status     | Last Exported | Platforms              |
|---------|------------|---------------|------------------------|
| 0.1.0   | deprecated | 2026-01-15    | claude                 |
| 0.5.0   | archived   | 2026-03-15    | claude                 |
| 0.6.0   | active *   | 2026-04-04    | claude, copilot        |
```

**If `target_in_manifest = false`** (draft skill discovered only by on-disk scan), display the on-disk version directories instead and note the constraint:

```
**{target_skill} — on-disk versions (not in manifest):**

  {list version subdirectories found under {skills_output_folder}/{target_skill}/, or "(flat layout)" if no version nesting is present}

**Note:** This skill has no manifest entry, so soft-deprecate is not available. Only a skill-level hard purge can be performed — the drop will delete the entire on-disk skill group and forge group.
```

### 6. Ask Scope

**If `target_in_manifest = false`:** Skip this prompt — draft skills can only be dropped as a whole. Set `target_versions = "all"` and `is_skill_level = true`, then proceed to section 7.

**If `target_in_manifest = true`:**

"**Drop which version(s)?**

- **[N]** Specific version — soft deprecate or hard purge a single version
- **[A]** All versions — drops the entire skill (skill-level operation)
- **[X]** Cancel and exit (or type `cancel` / `exit` / `:q`)"

Wait for user selection.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q`: Display "Cancelled — no changes were made." and HALT (exit code 6, `halt_reason: "user-cancelled"`).

**If [N] Specific version:**

"**Which version?** Enter the version string (e.g. `0.5.0`)."

Wait for user input. Validate that the version exists in the manifest's `versions` map for `target_skill`. If not, repeat the prompt.

Set `target_versions = [<selected version>]` and `is_skill_level = false`.

**If [A] All versions:**

Set `target_versions = "all"` and `is_skill_level = true`.

### 7. Active Version Guard

**Does not apply when `target_in_manifest = false`:** A draft skill has no manifest-recorded active version, so the guard is a no-op. Proceed to section 8.

**Applies only when `target_in_manifest = true` AND `is_skill_level = false` (specific version selected):**

1. Read the selected version's `status` field from the manifest
2. If `status != "active"` → skip this guard, the version is safe to drop
3. If `status == "active"`:
   a. Count the number of OTHER versions in the `versions` map with `status != "deprecated"` (i.e., `active`, `archived`, or `draft`)
   b. If that count is `> 0` → REFUSE the drop:

      "**Cannot drop the active version `{version}`.**
      Other non-deprecated versions of `{target_skill}` still exist. To proceed, either:

      **(a)** Switch the active version to another version first by re-running `[EX] Export Skill` with a different version selected, then return here to drop `{version}`, OR

      **(b)** Use the `[A] All versions` option to drop every version of `{target_skill}` at once."

      HALT (exit code 5, `halt_reason: "active-version-guard-refused"`). In headless mode, emit the error envelope per SKILL.md "Result Contract (Headless)" with `skill: "{target_skill}"`, `drop_mode: null`, `versions_affected: ["{version}"]`. Do not proceed.

   c. If the count is `0` → the active version is the ONLY version; allow the drop to continue (it is functionally equivalent to a skill-level drop on a single-version skill)

### 8. Ask Mode

**If `target_in_manifest = false`:** Skip this prompt — soft-deprecate is meaningless without a manifest entry to mark. Force `drop_mode = "purge"` and inform the user: "**Mode forced to purge** — `{target_skill}` has no manifest entry, so there is nothing to deprecate. The skill's on-disk directories will be deleted."

**If `target_in_manifest = true`:**

**If `{defaultMode}` is non-empty (`"deprecate"` or `"purge"`)**: skip the prompt, set `drop_mode = "{defaultMode}"`, and log the override source for the headless decision trail (`"customize.toml.workflow.default_mode"`).

**Otherwise:**

"**How should this be dropped?**

- **[D]** Deprecate (soft) — Mark the version as `deprecated` in the manifest. Files remain on disk. Export-skill will exclude it from all platform context files. Reversible by editing the manifest.
- **[P]** Purge (hard) — Deprecate AND delete files from disk (`{skill_package}` and `{forge_version}`, or full `{skill_group}` and `{forge_group}` for a skill-level drop). **Irreversible.**
- **[X]** Cancel and exit (or type `cancel` / `exit` / `:q`)"

Wait for user selection.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q`: Display "Cancelled — no changes were made." and HALT (exit code 6, `halt_reason: "user-cancelled"`).

Set `drop_mode` to `"deprecate"` (on D) or `"purge"` (on P).

### 9. Compute Affected Directories

Using the templates from `{versionPathsKnowledge}`, resolve the list of directories that would be affected:

**If `is_skill_level = false` (version-level drop):**

- `{skill_package}` = `{skills_output_folder}/{target_skill}/{version}/{target_skill}/`
- The enclosing version directory = `{skills_output_folder}/{target_skill}/{version}/`
- `{forge_version}` = `{forge_data_folder}/{target_skill}/{version}/`

**If `is_skill_level = true` (skill-level drop):**

- `{skill_group}` = `{skills_output_folder}/{target_skill}/`
- `{forge_group}` = `{forge_data_folder}/{target_skill}/`

Store the list as `affected_directories`.

If `drop_mode == "deprecate"`, record the list but present it as "retained" in the confirmation output — no deletion will occur.

#### 9b. Compute Blast-Radius Metrics (for §10 summary)

Compute three scalars to put in front of the path list at §10. The user's "I didn't know it would touch THAT" footgun is real — 12 paths can hide 50MB of on-disk content and a sweep across every IDE's managed section. A one-line summary makes the scale legible before the gate.

1. **`versions_count`** — the number of skill versions in scope:
   - Version-level drop: `len(target_versions)` (typically `1`)
   - Skill-level drop: count of non-deprecated versions in `exports.{target_skill}.versions` (the deprecated ones are already absent from the active managed sections)

2. **`bytes_total`** — recursive sum of byte sizes for every path in `affected_directories` that exists on disk. For each path, walk it and sum file sizes (`du -sb {path}` or equivalent). Skip non-existent paths silently — the §10 display is best-effort. Convert to a human-readable string for display (e.g. `"4.2 MB"`, `"812 KB"`); store the raw integer alongside as `bytes_total_raw` if a downstream step wants exact arithmetic. Defense in depth with execute.md §4 — that section will recompute per-path sizes for the canonical `disk_freed` reporting; this pre-compute is purely for the gate display and may slightly disagree if files change between gate and execute (acceptable for an "approximate" label).

3. **`context_files_count`** — the number of distinct context files the §3 rebuild loop will rewrite:
   - Read `config.yaml.ides`
   - For each entry, look up its `context_file` via the canonical mapping table in `skf-export-skill/assets/managed-section-format.md` (use `AGENTS.md` fallback for unknown IDEs)
   - Deduplicate by `context_file`
   - Count the result. If `config.yaml.ides` is absent or empty, default to `1` (the AGENTS.md fallback)

Store as `blast_radius = {versions_count, bytes_total, bytes_total_raw, context_files_count}` for §10's summary line.

### 10. Confirmation Gate

Display the full operation summary with the blast-radius summary line ahead of the path list so the user sees the scale before scanning paths:

```
**About to drop:**

  Skill:   {target_skill}
  Version: {version or "ALL versions"}
  Mode:    {Deprecate (soft) | Purge (hard)}
  Scope:   {versions_count} version(s), ~{bytes_total} on disk, will rebuild {context_files_count} context file(s)
  Files:
    {for each path in affected_directories, list one per line}
    {or "(retained on disk — soft drop)" if drop_mode == "deprecate"}

{if drop_mode == "purge":}
  ⚠️  This operation cannot be undone. Files will be permanently deleted.
{else:}
  Files remain on disk. Reversible by manually editing the manifest.

Proceed? [Y/N]
```

The `Scope:` line is the §9b-computed `blast_radius` rendered as one line. In `deprecate` mode the `~{bytes_total} on disk` reads as "size that will remain on disk (soft drop — files retained)"; the user is still served by knowing it. In `purge` mode it reads as "approximate disk that will be freed". The wording stays the same — the surrounding `Mode:` field disambiguates intent.

**GATE [default: Y]** — If `{headless_mode}`: auto-proceed with [Y], log: "headless: auto-confirmed drop of {target_skill}"

Wait for explicit user response.

**If `--dry-run` was passed**: skip the Y/N prompt entirely. Display "**[DRY RUN] No changes were made — preview above shows what would be dropped.**" and emit the success envelope per SKILL.md "Result Contract (Headless)" with `status: "dry-run"`, the resolved `skill`, `drop_mode`, and `versions_affected`, then HALT (exit code 0). The manifest, filesystem, and context files are untouched.

- **If `Y`** → proceed to section 11
- **If `N`** (or `cancel` / `exit` / `[X]` / `:q`) → "**Cancelled.** No changes were made." HALT (exit code 6, `halt_reason: "user-cancelled"`). In headless mode, emit the error envelope per SKILL.md "Result Contract (Headless)" with the resolved `skill`, `drop_mode`, and `versions_affected`.
- **Any other input** → re-display the confirmation and ask again

### 11. Store Decisions in Context

Store the following decisions in workflow context for step 2:

- `target_skill` — the skill name
- `target_in_manifest` — boolean (true if the skill has a manifest entry, false if it was discovered only by on-disk scan)
- `target_versions` — list of version strings (`[<version>]`) or the literal string `"all"`
- `drop_mode` — `"deprecate"` or `"purge"` (always `"purge"` when `target_in_manifest = false`)
- `is_skill_level` — boolean (true if all versions; always true when `target_in_manifest = false`)
- `affected_directories` — list of absolute directory paths that step 2 will delete in purge mode (or retain in deprecate mode)

### 12. Load Next Step

Load, read the full file, and then execute `{nextStepFile}`.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user has confirmed with `Y` at the confirmation gate AND all selection decisions have been stored in context, will you then load and read fully `{nextStepFile}` to execute the drop.

