---
nextStepFile: 'execute.md'
versionPathsKnowledge: 'knowledge/version-paths.md'
# Read-side inventory helpers (reads, not atomicity-critical). §2 uses
# `{manifestOpsHelper} read` (manifest parse + v1→v2 migration + corrupt-JSON
# detection); §3 uses `{skillInventoryHelper}` (on-disk scan + exports∪on-disk
# diff for orphan detection, plus each folder's `ownership` and, with
# `--forge-data-folder`, each skill's forge-folder verdict (`forge_groups`),
# which §4 and §8b read so a purge never deletes a folder SKF did not
# generate) and
# `{manifestOpsHelper} affected-versions <skill>` (numeric semver-descending
# order, so 0.10.0 precedes 0.9.0 — LLM-unreliable).
# Probe each in order (installed SKF path first, src/ fallback); first hit wins.
# If neither candidate resolves, the section computes the result in-prompt;
# without the inventory helper §3 offers manifest skills only and §8b allows
# no purge.
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

Build and display a summary of every skill available to drop: every manifest-tracked skill, plus every on-disk skill SKF generated that is not in the manifest (draft/orphaned, eligible for purge only).

**Manifest-tracked skills** come from the `manifest` resolved in section 2 — for each key in `manifest.exports`, its `active_version` and its `versions` map (with each version's `status`) are already parsed. Order each skill's versions newest-first through the helper rather than by eye:

```bash
python3 {manifestOpsHelper} {skills_output_folder} affected-versions {skill-name}
```

`result.affected_versions` is that skill's versions deduped and sorted in the helper's numeric-descending order (see the frontmatter note). Annotate each with its `status` from `manifest.exports.{skill-name}.versions.{version}.status` and mark `active_version` with a trailing `*`.

**On-disk (not-in-manifest) skills** come from the inventory helper. **Resolve `{skillInventoryHelper}`** ← first existing path in `{skillInventoryProbeOrder}`; it scans `{skills_output_folder}/` and computes the exports∪on-disk merge for you — do not re-scan the directory in the prompt:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --forge-data-folder {forge_data_folder}
```

Each `result.skills[]` entry carries `ownership` — `"skf"` (SKF generated everything in the folder), `"mixed"` (SKF output plus entries SKF did not generate, listed in `foreign_entries`) or `"foreign"` (no SKF marker in the folder) — and `skf_skill` (the folder holds a skill SKF generated). Each `result.forge_groups[]` entry classifies that skill's folder in `{forge_data_folder}` the same way (see §8b), and `result.same_folder` is true when both settings name one folder. A `result.skills[].name` that is **not** a key in `manifest.exports` is a draft or orphaned skill — record it as "(not in manifest — purge only)" only when its `skf_skill` is true; no other folder absent from the manifest is offered. When the manifest is empty, every SKF skill on disk lands here. Bind `{not_offered}` ← the names in `result.not_skf_output` (folders holding a skill SKF did not generate) that are not keys in `manifest.exports`; when it is non-empty, show one line under the list: "Not offered — not SKF output: {not_offered}". The inventory lists only skills with an on-disk directory, so a manifest entry whose files were already removed still appears above via `manifest.exports`.

**If the combined roster is empty** (no `manifest.exports` entries AND no `result.skills[]` entry with `skf_skill` true):

- When a skill name was supplied as an argument and it is in `{not_offered}` (empty when §3 ran without the inventory helper), take the §4 refusal for that folder first, in either mode: display its message and HALT (exit code 5, `halt_reason: "not-skf-output"`). In headless mode, emit the error envelope per `{headlessContract}` with `skill: "{name}"`, `drop_mode: null`, `versions_affected: []`.
- Otherwise halt with "**Drop Skill — nothing to drop.** No skills found in `{skills_output_folder}/` and no entries in `.export-manifest.json`. Run `[CS] Create Skill` first." When `{not_offered}` is non-empty, append: "Left untouched (not SKF output): {not_offered}." HALT (exit code 3, `halt_reason: "nothing-to-drop"`). In headless mode, emit the error envelope per `{headlessContract}` with `skill: null`, `drop_mode: null`, `versions_affected: []`.

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

Not offered — not SKF output: my-module-skill
```

**If a helper does not resolve** (Python/helper unavailable): fall back to the in-prompt computation. Without `{manifestOpsHelper}`, list each `manifest.exports` skill's versions with `status`, active marked `*`, ordered newest-first by comparing version components numerically. Without `{skillInventoryHelper}`, list the `manifest.exports` skills and nothing else: folders on disk that are absent from `manifest.exports` are not offered in this mode, because without the inventory helper SKF cannot check that it generated them. §4 then binds `{target_ownership}` and `{target_forge_ownership}` to `"unknown"`, so §8b allows no purge. If the list is empty, take the "nothing to drop" HALT above.

### 4. Ask Which Skill

"**Which skill would you like to drop?**
Enter the skill name or its number from the list above, or `cancel` / `exit` / `:q` to abort."

Wait for user input. Accept either the numeric index or the skill name (exact match). **GATE [default: use args]** — If `{headless_mode}` and skill name was provided as argument: select that skill and auto-proceed. If not provided, HALT (exit code 2, `halt_reason: "input-missing"`): "headless mode requires skill name argument." In headless mode, emit the error envelope per `{headlessContract}` with `skill: null`, `drop_mode: null`.

- **If the input names a folder in `{not_offered}`:** display "**`{name}` is not SKF output — nothing was changed.** `{skills_output_folder}/{name}/` has no SKF marker in its `metadata.json`, so SKF will not delete it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{name}` yourself (to remove it, delete that folder). Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When that folder's `result.skills[]` entry has a non-empty `errors` list (for example, the folder is a link), show those errors in place of the marker sentence.
  - **Interactive:** Re-display the list and ask again.
  - **Headless (`{headless_mode}` is true):** HALT (exit code 5, `halt_reason: "not-skf-output"`). Emit the error envelope per `{headlessContract}` with `skill: "{name}"`, `drop_mode: null`, `versions_affected: []`.
- **If the user's input does not match any listed skill:**
  - **Interactive:** Re-display the list and ask again.
  - **Headless (`{headless_mode}` is true):** the supplied `skill_name` argument resolves to no skill in the combined list — there is no further input to re-prompt for. HALT (exit code 2, `halt_reason: "input-invalid"`): "headless mode: skill argument `{supplied value}` does not match any listed skill." Emit the error envelope per `{headlessContract}` with `skill: null`, `drop_mode: null`, `versions_affected: []`.

Store the selection as `target_skill`. Also store `target_in_manifest = true` if the selected skill has an entry in the manifest, `false` otherwise — subsequent sections use this flag to restrict the available drop options.

Bind `{target_ownership}` ← the `ownership` of the `result.skills[]` entry named `target_skill` (`"absent"` when the inventory has no entry for it, meaning nothing is on disk; `"unknown"` when §3 ran without the inventory helper), `{target_foreign_entries}` ← that entry's `foreign_entries`, and `{target_errors}` ← that entry's `errors` (both `[]` when there is no entry). §8b reads all three.

Also bind `{same_folder}` ← `same_folder` (false when the result has none), and `{target_forge_ownership}` ← the `ownership` of the `result.forge_groups[]` entry named `target_skill` (`"unknown"` when §3 ran without the inventory helper, when the result has no `same_folder` key, or when `{same_folder}` is false and no `forge_groups[]` entry has that name), `{target_forge_foreign_entries}` ← that entry's `foreign_entries` and `{target_forge_errors}` ← its `errors` (both `[]` without one). §8b reads them for the skill's forge folder.

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

**Note:** This skill has no manifest entry, so soft-deprecate is not available. Only a skill-level hard purge can be performed — the drop will delete the entire on-disk skill group and forge group (a forge folder SKF did not generate stays where it is).
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

**If `target_in_manifest = false`:** Skip this prompt — soft-deprecate is meaningless without a manifest entry to mark, so only a purge applies. Take the first case that matches:

1. A `mode` argument other than `purge`, or, when `{headless_mode}` is true, no `mode` argument while `{defaultMode}` is `"deprecate"`: HALT (exit code 2, `halt_reason: "input-invalid"`): "`{target_skill}` has no manifest entry, so there is nothing to deprecate. Re-run with `--mode purge` to delete it." In headless mode, emit the error envelope per `{headlessContract}` with `skill: "{target_skill}"`, `drop_mode: null`.
2. `{headless_mode}` is true and nothing asked for a purge (no `mode` argument and `{defaultMode}` is empty): HALT (exit code 2, `halt_reason: "input-missing"`): "headless mode: `{target_skill}` has no manifest entry, so only a purge applies; re-run with `--mode purge`." Emit the error envelope per `{headlessContract}` with `skill: "{target_skill}"`, `drop_mode: null`.
3. Otherwise force `drop_mode = "purge"` (record `mode_source = "draft-skill-forced-purge"`), inform the user: "**Mode forced to purge** — `{target_skill}` has no manifest entry, so there is nothing to deprecate. The skill's on-disk directories will be deleted.", and apply §8b. An interactive run still confirms the purge at §10. A headless run reaches this case only with `mode=purge` or a `{defaultMode}` of `"purge"`, which the On-Activation guard has already checked against `{forbidPurgeInHeadless}`.

**If `target_in_manifest = true`:**

**If a `mode` argument was supplied at invocation:** an explicit `mode` arg is the per-run override and takes precedence over `{defaultMode}`. If it is `"deprecate"` or `"purge"`, set `drop_mode` from it and record the decision source `mode_source = "--mode argument"`. If a `mode` arg was supplied but is not one of `deprecate` / `purge`, HALT (exit code 2, `halt_reason: "input-invalid"`): "invalid `--mode` value `{supplied}` — expected `deprecate` or `purge`." In headless mode, emit the error envelope per `{headlessContract}` with `skill: "{target_skill}"`, `drop_mode: null`.

**Else if `{defaultMode}` is non-empty (`"deprecate"` or `"purge"`)**: skip the prompt, set `drop_mode = "{defaultMode}"`, and record the decision source `mode_source = "customize.toml.workflow.default_mode"` for the headless decision trail.

**Otherwise (interactive):** If `{headless_mode}` is true at this point (no `mode` arg and no `{defaultMode}`), there is no input to prompt for — HALT (exit code 2, `halt_reason: "input-missing"`): "headless mode requires `--mode deprecate|purge` or `default_mode` in customize.toml to set the drop mode." Emit the error envelope per `{headlessContract}` with `skill: "{target_skill}"`, `drop_mode: null`. Otherwise, prompt the user. Before showing the menu, check whether §8b would refuse a purge at the current scope; if so, leave out **[P]** and add the line "Purge is not offered: {the §8b refusal reason}."

"**How should this be dropped?**

- **[D]** Deprecate (soft) — Mark the version as `deprecated` in the manifest. Files remain on disk. Export-skill will exclude it from all platform context files. Reversible by editing the manifest.
- **[P]** Purge (hard) — Deprecate AND delete files from disk (`{skill_package}` and `{forge_version}`, or full `{skill_group}` and `{forge_group}` for a skill-level drop; a forge folder SKF did not generate stays where it is). **Irreversible.**
- **[X]** Cancel and exit (or type `cancel` / `exit` / `:q`)"

Wait for user selection.

Set `drop_mode` to `"deprecate"` (on D) or `"purge"` (on P), and record `mode_source = "interactive-prompt"`.

### 8b. Purge Guard

A purge deletes only what SKF generated. Skip this section when `drop_mode == "deprecate"`. Otherwise decide from `{target_ownership}`:

- `"skf"` or `"absent"`: the purge proceeds.
- `"mixed"`: a skill-level purge (`is_skill_level = true`) deletes the whole folder, entries SKF did not generate included, so refuse it. A single-version purge proceeds unless `{target_foreign_entries}` lists the selected version, with or without a trailing `/`, or an entry inside it (`{version}/<entry>`). The helper lists a version folder SKF did not generate with the `/`, a linked one by its bare name, and an entry SKF did not put in a marked version folder as `{version}/<entry>`; a purge through a link would delete the files it points to, and a version purge deletes the whole `{version}/` folder.
- `"foreign"` or `"unknown"`: refuse every purge. `"unknown"` means §3 ran without the inventory helper, so SKF cannot check what it would delete.

On a refusal, HALT (exit code 5, `halt_reason: "not-skf-output"`) with the message that fits. In headless mode, emit the error envelope per `{headlessContract}` with `skill: "{target_skill}"`, `drop_mode: "purge"`, `versions_affected: []`.

- Mixed, whole skill: "**Purge refused — `{skills_output_folder}/{target_skill}/` also holds entries SKF did not generate:** {target_foreign_entries}. Nothing was deleted. Move them out of the folder and re-run. For a skill in the manifest, you can also purge a single version SKF generated, or use `--mode deprecate`. A version folder with no `metadata.json` can also be one that an interrupted update-skill run left behind; delete it yourself in that case."
- Mixed, selected version: "**Purge refused — SKF did not generate `{skills_output_folder}/{target_skill}/{version}`** (it has no SKF marker in its `metadata.json`, or it is a link). Nothing was deleted. Use `--mode deprecate` to mark the version deprecated in the manifest only, or remove it yourself." When `{target_foreign_entries}` lists entries inside the version instead, show them in place of the parenthesis: "(it also holds entries SKF did not generate: {those entries}; move them out and re-run)".
- Foreign or unknown: "**Purge refused — SKF cannot confirm that it generated `{skills_output_folder}/{target_skill}/`:** {reason}. Nothing was deleted. Use `--mode deprecate` to remove the manifest entry only, or delete the folder yourself." `{reason}` is `{target_errors}` when it is non-empty (for example, the folder is a link), "the inventory helper is missing" for `"unknown"`, and otherwise "its `metadata.json` has no SKF marker".

**Forge folder.** A purge also deletes the skill's folder in `{forge_data_folder}`: the whole folder for a skill-level purge, `{version}/` in it for a single-version purge. When `{same_folder}` is true, that folder is the skill folder the rules above already decided: skip this block. Otherwise decide from `{target_forge_ownership}`:

- `"skf"`, `"empty"` or `"absent"`: the purge covers the forge folder too (nothing to delete when absent).
- `"foreign"` or `"reserved"`: the purge proceeds but leaves the forge folder where it is — SKF did not generate it: another tool's folder of the same name, a link or a path that is not a folder (`{target_forge_errors}` says which), or SKF's own `improvement-queue`. §9 leaves it out of `affected_directories` and binds `{forge_left_in_place}`.
- `"mixed"`: refuse a skill-level purge. A single-version purge proceeds unless `{target_forge_foreign_entries}` lists an entry inside the selected version (`{version}/<entry>`); when it lists the version itself, with or without a trailing `/`, that forge version folder is not SKF output, so the purge leaves it where it is (§9 binds `{forge_left_in_place}` to it).
- `"unknown"`: refuse every purge; the installed inventory helper does not report `forge_groups`, so SKF cannot check what it would delete there.

Forge refusals take the same HALT (exit code 5, `halt_reason: "not-skf-output"`) and headless envelope as above, with the message that fits:

- Mixed, whole skill: "**Purge refused — `{forge_data_folder}/{target_skill}/` also holds entries SKF did not generate:** {target_forge_foreign_entries}. Nothing was deleted. Move them out of the folder and re-run. For a skill in the manifest, you can also purge a single version SKF generated, or use `--mode deprecate`."
- Mixed, selected version: "**Purge refused — `{forge_data_folder}/{target_skill}/{version}/` holds entries SKF did not generate:** {those entries}. Nothing was deleted. Move them out and re-run, or use `--mode deprecate`."
- Unknown: "**Purge refused — SKF cannot check `{forge_data_folder}/{target_skill}/`:** the installed `skf-skill-inventory.py` does not classify the forge folder. Nothing was deleted. Re-install SKF and re-run, or use `--mode deprecate`."

### 9. Compute Affected Directories

Using the templates from `{versionPathsKnowledge}`, resolve the list of directories that would be affected:

**If `is_skill_level = false` (version-level drop):**

- `{skill_package}` = `{skills_output_folder}/{target_skill}/{version}/{target_skill}`
- The enclosing version directory = `{skills_output_folder}/{target_skill}/{version}`
- `{forge_version}` = `{forge_data_folder}/{target_skill}/{version}`, unless §8b's forge block leaves it in place

**If `is_skill_level = true` (skill-level drop):**

- `{skill_group}` = `{skills_output_folder}/{target_skill}`
- `{forge_group}` = `{forge_data_folder}/{target_skill}`, unless §8b's forge block leaves it in place

Write every path without a trailing `/`: a trailing `/` makes a delete or a size walk follow a link. When `{same_folder}` is true, the forge path is the skill path: list it once. Bind `{forge_left_in_place}` ← the forge path §8b left in place, or null.

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
    {if forge_left_in_place:} Left in place (not SKF output): {forge_left_in_place}{if target_forge_errors is non-empty: " — " + target_forge_errors}

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
- `target_ownership` — the §4 ownership verdict (`"skf"`, `"mixed"`, `"foreign"`, `"absent"` or `"unknown"`) that §8b checked
- `target_foreign_entries` — the entries of the skill folder SKF did not generate (`[]` when none)
- `target_errors` — the inventory's `errors` for the skill folder (`[]` when none)
- `same_folder` — the §4 binding (true when `skills_output_folder` and `forge_data_folder` name one folder)
- `target_forge_ownership` — the §4 forge-folder verdict (`"skf"`, `"mixed"`, `"empty"`, `"foreign"`, `"reserved"`, `"absent"` or `"unknown"`) that §8b checked
- `target_forge_foreign_entries` — the entries of the forge folder SKF did not generate (`[]` when none)
- `target_forge_errors` — the inventory's `errors` for the forge folder (`[]` when none)
- `forge_left_in_place` — the forge path a purge leaves in place because SKF did not generate it, or null
- `confirm_source` — how the §10 gate was cleared, set inline at §10 (`"headless-auto"` or `"user-explicit"`)

### 12. Load Next Step

`{nextStepFile}` performs the destructive mutation, so reach it only after the §10 gate returned `Y` and §11 stored the decisions — chaining any earlier would drop without the user's explicit consent (the sequence above enforces this ordering). Load, read the full file, and then execute it.

