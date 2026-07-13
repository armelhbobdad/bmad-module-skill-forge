---
nextStepFile: 'execute.md'
versionPathsKnowledge: 'knowledge/version-paths.md'
# Read-side inventory helpers (reads, not atomicity-critical). §2 uses
# `{manifestOpsHelper} read` (manifest parse + v1→v2 migration + corrupt-JSON
# detection); §3 uses `{skillInventoryHelper}` (on-disk scan + exports∪on-disk
# diff for orphan detection) and `{manifestOpsHelper} affected-versions <skill>`
# (numeric semver-descending order, so 0.10.0 precedes 0.9.0 — LLM-unreliable).
# Probe each in order (installed SKF path first, src/ fallback); first hit wins.
# If neither candidate resolves, the section computes the result in-prompt.
manifestOpsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py'
  - '{project-root}/src/shared/scripts/skf-manifest-ops.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Standalone single-line result-envelope contract emitted at every headless
# HALT in this step. Loaded in §1 so no error path depends on SKILL.md
# remaining in context under compaction.
headlessContract: 'headless-contract.md'
# Deterministic recursive byte sizing + human formatting for the §9b
# blast-radius line. Bundled with this skill (no probe order needed);
# execute.md §4 reuses the same helper for the canonical `disk_freed`.
dirSizesHelper: 'scripts/dir-sizes.py'
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
- **Interactive cancel (every gate below):** at any prompt, `cancel` / `exit` / `[X]` / `q` / `:q` → display "Cancelled — no changes were made." and HALT (exit code 6, `halt_reason: "user-cancelled"`). Stated once here; the §10 commit gate adds its own tip + headless envelope on top of this.

## MANDATORY SEQUENCE

### 1. Load Knowledge

Read `{versionPathsKnowledge}` completely and extract:

- Path templates: `{skill_package}`, `{skill_group}`, `{forge_version}`, `{forge_group}`
- Export manifest v2 schema (`schema_version`, `exports`, `active_version`, `versions` map, `status` field values)
- Skill management operations (Drop section — soft vs hard, active version guard, skill-level drop)

You will use these templates and rules to build directory paths and enforce safety guards in the following sections.

If `{headless_mode}` is true, also read `{headlessContract}` now — it defines the single-line result envelope every HALT below emits, so the shape is in context even if SKILL.md was compacted out.

### 2. Read Export Manifest

**Resolve `{manifestOpsHelper}`** ← first existing path in `{manifestOpsProbeOrder}`. Parse the manifest through it rather than hand-rolling JSON — the helper migrates v1→v2, normalizes `platforms`→`ides`, and reports a parse error deterministically:

```bash
python3 {manifestOpsHelper} {skills_output_folder} read
```

Read the JSON result:

- **`status == "error"`** — the manifest file exists but is malformed (the helper returns `{"status":"error","error":"Manifest JSON parse error: ..."}`): halt with "**Export manifest is corrupt** at `{skills_output_folder}/.export-manifest.json` — fix or remove the file before dropping." HALT (exit code 3, `halt_reason: "manifest-corrupt"`). In headless mode, emit the error envelope per `{headlessContract}` with `skill: null`, `drop_mode: null`, `versions_affected: []`.
- **`status == "ok"`** — use `result.manifest` (already migrated to v2) as `manifest` for the rest of this step. Set `manifest_exists = true` when `manifest.exports` has at least one entry, else `false` (a missing manifest reads back as an empty `exports` object, so it correctly yields `false`).

When `manifest_exists = false`, section 3's on-disk scan is authoritative: draft skills (created by `[CS]`/`[QS]`/`[SS]` but never exported) can still be hard-dropped in purge mode, and section 8 restricts the options to purge only — soft-deprecate is meaningless without a manifest entry to record it against.

**If neither `{manifestOpsProbeOrder}` candidate resolves:** read the manifest file in-prompt — a missing/empty file is `manifest_exists = false`; a file with `exports` entries is `true` (no `schema_version` field means v1 — treat each entry as a single active version); invalid JSON takes the corrupt-manifest HALT above.

### 3. List Available Skills

Build and display a summary of every skill available to drop: every manifest-tracked skill, plus every on-disk skill not in the manifest (draft/orphaned, eligible for purge only).

**Manifest-tracked skills** come from the `manifest` resolved in section 2 — for each key in `manifest.exports`, its `active_version` and its `versions` map (with each version's `status`) are already parsed. Order each skill's versions newest-first through the helper rather than by eye:

```bash
python3 {manifestOpsHelper} {skills_output_folder} affected-versions {skill-name}
```

`result.affected_versions` is that skill's versions deduped and sorted in the helper's numeric-descending order (see the frontmatter note). Annotate each with its `status` from `manifest.exports.{skill-name}.versions.{version}.status` and mark `active_version` with a trailing `*`.

**On-disk (not-in-manifest) skills** come from the inventory helper. **Resolve `{skillInventoryHelper}`** ← first existing path in `{skillInventoryProbeOrder}`; it scans `{skills_output_folder}/` and computes the exports∪on-disk merge for you — do not re-scan the directory in the prompt:

```bash
python3 {skillInventoryHelper} {skills_output_folder}
```

Any `result.skills[].name` that is **not** a key in `manifest.exports` is a draft or orphaned skill — record it as "(not in manifest — purge only)". When the manifest is empty, every on-disk skill lands here. The inventory lists only skills with an on-disk directory, so a manifest entry whose files were already removed still appears above via `manifest.exports`.

**If the combined roster is empty** (no `manifest.exports` entries AND `result.skills[]` is empty): halt with "**Drop Skill — nothing to drop.** No skills found in `{skills_output_folder}/` and no entries in `.export-manifest.json`. Run `[CS] Create Skill` first." HALT (exit code 3, `halt_reason: "nothing-to-drop"`). In headless mode, emit the error envelope per `{headlessContract}` with `skill: null`, `drop_mode: null`, `versions_affected: []`.

Display the combined list (versions newest-first):

```
**Drop Skill — select target**

Available skills:
1. cognee
   - 0.6.0 (active) *
   - 0.5.0 (archived)
   - 0.1.0 (deprecated)
2. express
   - 4.18.0 (active) *
3. legacy-helper (not in manifest — purge only)
```

**If neither helper resolves** (Python/helper unavailable): fall back to the in-prompt computation — list each `manifest.exports` skill (versions with `status`, active marked `*`, ordered newest-first by comparing version components numerically), then scan `{skills_output_folder}/` for top-level directories absent from `manifest.exports` and record them as "(not in manifest — purge only)". If the combined list is empty, take the "nothing to drop" HALT above.

### 4. Ask Which Skill

"**Which skill would you like to drop?**
Enter the skill name or its number from the list above, or `cancel` / `exit` / `:q` to abort."

Wait for user input. Accept either the numeric index or the skill name (exact match). **GATE [default: use args]** — If `{headless_mode}` and skill name was provided as argument: select that skill and auto-proceed. If not provided, HALT (exit code 2, `halt_reason: "input-missing"`): "headless mode requires skill name argument." In headless mode, emit the error envelope per `{headlessContract}` with `skill: null`, `drop_mode: null`.

- **If the user's input does not match any listed skill:**
  - **Interactive:** Re-display the list and ask again.
  - **Headless (`{headless_mode}` is true):** the supplied `skill_name` argument resolves to no skill in the combined list — there is no further input to re-prompt for. HALT (exit code 2, `halt_reason: "input-invalid"`): "headless mode: skill argument `{supplied value}` does not match any listed skill." Emit the error envelope per `{headlessContract}` with `skill: null`, `drop_mode: null`, `versions_affected: []`.

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

**If [N] Specific version:**

"**Which version?** Enter the version string (e.g. `0.5.0`)."

Wait for user input. Validate that the version exists in the manifest's `versions` map for `target_skill`.

- **If it does not match (interactive):** repeat the prompt.
- **If it does not match (headless — `{headless_mode}` is true):** the supplied `version` argument is unparseable or absent from the `versions` map — there is no further input to re-prompt for. HALT (exit code 2, `halt_reason: "input-invalid"`): "headless mode: version argument `{supplied value}` does not exist in `{target_skill}`'s versions." Emit the error envelope per `{headlessContract}` with `skill: "{target_skill}"`, `drop_mode: null`, `versions_affected: []`.

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

      HALT (exit code 5, `halt_reason: "active-version-guard-refused"`). In headless mode, emit the error envelope per `{headlessContract}` with `skill: "{target_skill}"`, `drop_mode: null`, `versions_affected: ["{version}"]`. Do not proceed.

   c. If the count is `0` → the active version is the ONLY version; allow the drop to continue (it is functionally equivalent to a skill-level drop on a single-version skill)

### 8. Ask Mode

**If `target_in_manifest = false`:** Skip this prompt — soft-deprecate is meaningless without a manifest entry to mark. Force `drop_mode = "purge"` (record `mode_source = "draft-skill-forced-purge"`) and inform the user: "**Mode forced to purge** — `{target_skill}` has no manifest entry, so there is nothing to deprecate. The skill's on-disk directories will be deleted."

**If `target_in_manifest = true`:**

**If a `mode` argument was supplied at invocation:** an explicit `mode` arg is the per-run override and takes precedence over `{defaultMode}`. If it is `"deprecate"` or `"purge"`, set `drop_mode` from it and record the decision source `mode_source = "--mode argument"`. If a `mode` arg was supplied but is not one of `deprecate` / `purge`, HALT (exit code 2, `halt_reason: "input-invalid"`): "invalid `--mode` value `{supplied}` — expected `deprecate` or `purge`." In headless mode, emit the error envelope per `{headlessContract}` with `skill: "{target_skill}"`, `drop_mode: null`.

**Else if `{defaultMode}` is non-empty (`"deprecate"` or `"purge"`)**: skip the prompt, set `drop_mode = "{defaultMode}"`, and record the decision source `mode_source = "customize.toml.workflow.default_mode"` for the headless decision trail.

**Otherwise (interactive):** If `{headless_mode}` is true at this point (no `mode` arg and no `{defaultMode}`), there is no input to prompt for — HALT (exit code 2, `halt_reason: "input-missing"`): "headless mode requires `--mode deprecate|purge` or `default_mode` in customize.toml to set the drop mode." Emit the error envelope per `{headlessContract}` with `skill: "{target_skill}"`, `drop_mode: null`. Otherwise, prompt the user:

"**How should this be dropped?**

- **[D]** Deprecate (soft) — Mark the version as `deprecated` in the manifest. Files remain on disk. Export-skill will exclude it from all platform context files. Reversible by editing the manifest.
- **[P]** Purge (hard) — Deprecate AND delete files from disk (`{skill_package}` and `{forge_version}`, or full `{skill_group}` and `{forge_group}` for a skill-level drop). **Irreversible.**
- **[X]** Cancel and exit (or type `cancel` / `exit` / `:q`)"

Wait for user selection.

Set `drop_mode` to `"deprecate"` (on D) or `"purge"` (on P), and record `mode_source = "interactive-prompt"`.

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

Compute three scalars to put in front of the path list at §10, so the user sees the scale of an irreversible drop before scanning individual paths:

1. **`versions_count`** — the number of skill versions in scope:
   - Version-level drop: `len(target_versions)` (typically `1`)
   - Skill-level drop: count of non-deprecated versions in `exports.{target_skill}.versions` (the deprecated ones are already absent from the active managed sections)

2. **`bytes_total`** — the on-disk size of `affected_directories`. Delegate the recursive sum and the human label to the sizing helper rather than adding file sizes in-prompt:

   ```bash
   uv run {dirSizesHelper} sizes {each path in affected_directories, space-separated}
   ```

   Read `total_human` (e.g. `"4.2 MB"`) as `bytes_total` and `total_bytes` as `bytes_total_raw`; non-existent paths report `exists: false` and drop out of the total. If the helper is unavailable, fall back to `du -sb` per path — the display is best-effort. execute.md §4 re-runs the same helper on the paths it actually deletes for the canonical `disk_freed`, so the two share one method and differ only if files change between this gate and execution.

3. **`context_files_count`** — the number of distinct context files the §3 rebuild loop will rewrite:
   - Read `config.yaml.ides`
   - For each entry, look up its `context_file` via the canonical mapping table in `skf-export-skill/assets/managed-section-format.md` (use the `{unknownIdeDefaultContextFile}` fallback for unknown IDEs)
   - Deduplicate by `context_file`
   - Count the result. If `config.yaml.ides` is absent or empty, default to `1` (the single `{unknownIdeDefaultContextFile}` fallback)

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

**Resolve `--dry-run` first — it takes precedence over the headless auto-confirm.** `--dry-run` and `--headless` can be combined (dry-run is the automated-preview path), so a dry-run run must always short-circuit to the preview below and never mutate, even when `{headless_mode}` is true.

**If `--dry-run` was passed**: skip the Y/N prompt entirely — do not evaluate the headless auto-confirm gate. Display the `[DRY RUN]` line with the resolved selection, so the user can re-run interactively with the same values when ready to commit:

```
**[DRY RUN] No changes were made — preview above shows what would be dropped.**

Resolved selection:
  Skill:   {target_skill}
  Version: {target_versions[0] if is_skill_level == false else "all"}
  Mode:    {Deprecate (soft) | Purge (hard)}
```

Then emit the success envelope per `{headlessContract}` with `status: "dry-run"`, the resolved `skill`, `drop_mode`, and `versions_affected`, then HALT (exit code 0). The manifest, filesystem, and context files are untouched.

**Otherwise (not a dry-run) — GATE [default: Y]:** If `{headless_mode}`: auto-proceed with [Y], record `confirm_source = "headless-auto"`, log: "headless: auto-confirmed drop of {target_skill}"

Wait for explicit user response.

- **If `Y`** → record `confirm_source = "user-explicit"` and proceed to section 11
- **If `N`** (or `cancel` / `exit` / `[X]` / `:q`) → "**Cancelled.** No changes were made. (Tip: invoke with `--dry-run` next time to preview the operation without reaching the commit prompt.)" HALT (exit code 6, `halt_reason: "user-cancelled"`). In headless mode, emit the error envelope per `{headlessContract}` with the resolved `skill`, `drop_mode`, and `versions_affected`.
- **Any other input** → re-display the confirmation and ask again

### 11. Store Decisions in Context

Store the following decisions in workflow context for step 2:

- `target_skill` — the skill name
- `target_in_manifest` — boolean (true if the skill has a manifest entry, false if it was discovered only by on-disk scan)
- `target_versions` — list of version strings (`[<version>]`) or the literal string `"all"`
- `drop_mode` — `"deprecate"` or `"purge"` (always `"purge"` when `target_in_manifest = false`)
- `is_skill_level` — boolean (true if all versions; always true when `target_in_manifest = false`)
- `affected_directories` — list of absolute directory paths that step 2 will delete in purge mode (or retain in deprecate mode)
- `mode_source` — where `drop_mode` was decided, set inline at §8 (one of the four sources named there)
- `confirm_source` — how the §10 gate was cleared, set inline at §10 (`"headless-auto"` or `"user-explicit"`)

### 12. Load Next Step

`{nextStepFile}` performs the destructive mutation, so reach it only after the §10 gate returned `Y` and §11 stored the decisions — chaining any earlier would drop without the user's explicit consent (the sequence above enforces this ordering). Load, read the full file, and then execute it.

