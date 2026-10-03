---
nextStepFile: 'execute.md'
# {dropRosterHelper}: the §2 roster.
dropRosterHelper: 'scripts/drop-roster.py'
# {skillInventoryHelper}: the §8b purge check.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# {dirSizesHelper}: the §9b size of the folders in scope.
dirSizesHelper: 'scripts/dir-sizes.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Select Drop Target

## STEP GOAL:

Identify exactly what the user wants to drop — which skill, which version(s), and whether the drop is a soft deprecation (manifest-only) or a hard purge (files deleted). Enforce the active version guard, gather the list of affected directories, and obtain explicit user confirmation before any write or delete operation is scheduled.

## Rules

- Focus only on selection, validation, and confirmation: do not change the manifest, a context file or a skill folder (this step writes only its envelope payloads, in `{run_dir}`)
- Do not proceed without explicit user confirmation at the final gate
- Do not drop an active version when other non-deprecated versions exist
- Present selections clearly so the user can verify scope, mode, and blast radius
- **Interactive cancel (every gate below):** at any prompt, `cancel` / `exit` / `[X]` / `q` / `:q` → display "Cancelled: no changes were made." and HALT (exit code 6, `halt_reason: "user-cancelled"`). Stated once here; the §10 commit gate adds its own tip on top of this.

## MANDATORY SEQUENCE

### 1. Halt Envelope

Every HALT in this step names its exit code, `halt_reason` and phase. In headless mode it also prints its envelope through the shared emitter before it stops (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On-Activation §4): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "exit_code": <code>}` plus the envelope fields the site names (and `"path"` when the halt names one), then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-drop-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. The emitter gives every field the site leaves out its default (`null`, `[]` or `false`) and checks `exit_code` against `halt_reason`. If it exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message, emits nothing and then deletes the run folder (`rm -rf "{run_dir}"`), which nothing reads after it.

### 2. Read the Roster

Read every skill this drop can offer in one call:

```bash
uv run {dropRosterHelper} skills "{skills_output_folder}" --forge-data-folder "{forge_data_folder}" [--skill "{skill_name}"]
```

Pass `--skill` when a `skill_name` argument was supplied: the roster then holds that skill only. Bind `{roster}` ← the result.

- **`code` is `manifest-corrupt`** (the file exists but does not parse): halt with "**Export manifest is corrupt** at `{skills_output_folder}/.export-manifest.json`: fix or remove the file before dropping." HALT (exit code 3, `halt_reason: "manifest-corrupt"`, phase `select:manifest-read`, path `{skills_output_folder}/.export-manifest.json`) with the §1 halt envelope.
- **Any other non-zero exit, or no JSON on stdout:** HALT (exit code 4, `halt_reason: "write-failed"`, phase `select:roster`) with the §1 halt envelope: "SKF cannot list the skills to drop: {the result's `error`, or the first stderr line}. Nothing was changed. Re-install SKF."

### 3. List Available Skills

`{roster}.skills` holds every skill in the export manifest and every skill SKF generated that the manifest does not list (`purge_only` true: a draft, which only a purge can drop), each with its `versions` newest first. Bind `{not_offered}` ← the names in `{roster}.not_offered`: folders holding a skill SKF did not generate, which the roster never offers. When `{roster}.inventory` is false (the inventory helper could not run), the roster holds the manifest skills alone, because SKF cannot check that it generated a folder the manifest does not list, and `{not_offered}` is empty.

**If the combined roster is empty** (`{roster}.empty` is true):

- When a skill name was supplied as an argument and it is in `{not_offered}`, take the §4 refusal for that folder first, in either mode: display its message and HALT (exit code 5, `halt_reason: "not-skf-output"`, phase `select:roster`), with `skill: "{name}"` in the §1 halt envelope.
- Otherwise halt with "**Drop Skill: nothing to drop.** No skills found in `{skills_output_folder}/` and no entries in `.export-manifest.json`. Run `[CS] Create Skill` first." When `{not_offered}` is non-empty, append: "Left untouched (not SKF output): {not_offered}." HALT (exit code 3, `halt_reason: "nothing-to-drop"`, phase `select:roster`) with the §1 halt envelope.

When a `skill_name` argument was supplied, show no list: §4 takes the name. Otherwise display the combined list, each skill's versions in the roster's order, each with its `status` ("on disk only" when its `in_manifest` is false) and a trailing `*` on the one whose `active` is true; a `purge_only` skill shows "(not in manifest: purge only)" in place of its versions. When `{not_offered}` is non-empty, show one line under the list: "Not offered (not SKF output): {not_offered}".

```
**Drop Skill — select target**

Available skills:
1. cognee
   - 0.6.0 (active) *
   - 0.5.0 (archived)
   - 0.1.0 (deprecated)
2. express
   - 4.18.0 (active) *
3. legacy-helper (not in manifest: purge only)

Not offered (not SKF output): my-module-skill
```

### 4. Ask Which Skill

**GATE [default: use args]:** when a `skill_name` argument was supplied, take it as the answer below in either mode, without showing the prompt; the two checks that follow still apply, and an interactive run whose supplied name fails one runs §2's call again without `--skill` and shows §3's list before it asks. When none was supplied, headless mode HALTs (exit code 2, `halt_reason: "input-missing"`, phase `select:skill`) with the §1 halt envelope: "headless mode requires skill name argument." Interactive mode asks:

"**Which skill would you like to drop?**
Enter the skill name or its number from the list above, or `cancel` / `exit` / `:q` to abort."

Wait for user input. Accept either the numeric index or the skill name (exact match).

- **If the input names a folder in `{not_offered}`:** display "**`{name}` is not SKF output: nothing was changed.** `{skills_output_folder}/{name}/` has no SKF marker in its `metadata.json`, so SKF will not delete it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{name}` yourself (to remove it, delete that folder). Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When that folder's `{roster}.not_offered` entry has a non-empty `errors` list (for example, the folder is a link), show those errors in place of the marker sentence.
  - **Interactive:** Re-display the list and ask again.
  - **Headless (`{headless_mode}` is true):** HALT (exit code 5, `halt_reason: "not-skf-output"`, phase `select:skill`), with `skill: "{name}"` in the §1 halt envelope.
- **If the user's input does not match any listed skill:**
  - **Interactive:** Re-display the list and ask again.
  - **Headless (`{headless_mode}` is true):** the supplied `skill_name` argument resolves to no skill in the combined list, and there is no further input to re-prompt for. HALT (exit code 2, `halt_reason: "input-invalid"`, phase `select:skill`) with the §1 halt envelope: "headless mode: skill argument `{supplied value}` does not match any listed skill."

Store the selection as `target_skill`, and `target_in_manifest` ← its `{roster}.skills` entry's `in_manifest`: the sections below restrict the drop options of a skill the manifest does not list.

### 5. Display Version Details

Bind `{version_rows}` ← the `versions` of `{target_skill}`'s roster entry (the manifest's and the on-disk versions, newest first, each with its manifest `status`, `in_manifest`, `on_disk`, `last_exported` and `ides`) and `{version_counts}` ← its `counts` (`non_deprecated` counts the manifest versions whose `status` is not `"deprecated"`, and `on_disk` the version folders); §6 to §9b read them.

**If `target_in_manifest = true`**, display every `{version_rows}` entry with `in_manifest` true:

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

  {each `{version_rows}` entry whose `on_disk` is true, newest first, or "(flat layout)" when the roster entry's `layout` is "flat"}

**Note:** This skill has no manifest entry, so soft-deprecate is not available. Only a skill-level hard purge can be performed — the drop will delete the entire on-disk skill group and forge group (a forge folder SKF did not generate stays where it is).
```

### 6. Ask Scope

**GATE [default: use args]:** the `version` argument answers this section in either mode, so a supplied value is never asked for again.

**If `target_in_manifest = false`:** a draft skill can only be dropped as a whole. A `version` argument other than `all` asks for less, and the drop never widens it to every version: HALT (exit code 2, `halt_reason: "input-invalid"`, phase `select:scope`) in either mode, with `skill: "{target_skill}"` in the §1 halt envelope: "`{target_skill}` has no manifest entry, so only the whole skill can be dropped. Re-run with `version=all`." Otherwise (no `version` argument, or `all`), skip the prompt: set `target_versions = "all"` and `is_skill_level = true`, then proceed to section 7.

**If `target_in_manifest = true`:** a `version` argument of `all` takes **[A]** below, and any other value takes **[N]** with that value as the answer to "Which version?", without showing either prompt. With no `version` argument, headless mode HALTs (exit code 2, `halt_reason: "input-missing"`, phase `select:scope`), with `skill: "{target_skill}"` in the §1 halt envelope, rather than guess between one version and the whole skill: "headless mode requires a `version` argument for `{target_skill}`: `all`, or one of its versions ({each `{version_rows}` entry with `in_manifest` true})." Interactive mode asks:

"**Drop which version(s)?**

- **[N]** Specific version — soft deprecate or hard purge a single version
- **[A]** All versions — drops the entire skill (skill-level operation)
- **[X]** Cancel and exit (or type `cancel` / `exit` / `:q`)"

Wait for user selection.

**If [N] Specific version:**

"**Which version?** Enter the version string (e.g. `0.5.0`)."

Wait for user input (a supplied `version` argument is the input). Validate that the version is a `{version_rows}` entry with `in_manifest` true.

- **If it does not match (interactive):** repeat the prompt.
- **If it does not match (headless, `{headless_mode}` is true):** the supplied `version` argument is not a `{version_rows}` entry with `in_manifest` true, and there is no further input to re-prompt for. HALT (exit code 2, `halt_reason: "input-invalid"`, phase `select:scope`), with `skill: "{target_skill}"` in the §1 halt envelope: "headless mode: version argument `{supplied value}` does not exist in `{target_skill}`'s versions."

Set `target_versions = [<selected version>]` and `is_skill_level = false`.

**If [A] All versions:**

Set `target_versions = "all"` and `is_skill_level = true`.

### 7. Active Version Guard

**Does not apply when `target_in_manifest = false`:** A draft skill has no manifest-recorded active version, so the guard is a no-op. Proceed to section 8.

**Applies only when `target_in_manifest = true` AND `is_skill_level = false` (specific version selected):**

1. Read the selected version's `status` from its `{version_rows}` entry
2. If `status != "active"` → skip this guard, the version is safe to drop
3. If `status == "active"`:
   a. Read `{version_counts}.non_deprecated` (§5): the manifest versions of `{target_skill}` whose `status` is not `"deprecated"` (`active`, `archived` or `draft`), this one included. The guard never counts by hand.
   b. If that count is above `1` → REFUSE the drop:

      "**Cannot drop the active version `{version}`.**
      Other non-deprecated versions of `{target_skill}` still exist. To proceed, either:

      **(a)** Make the version you keep active first: point the `active` link at it (`ln -sfn <version to keep> {skills_output_folder}/{target_skill}/active`), run `[EX] Export Skill` for `{target_skill}`, which exports that version and archives `{version}`, then return here to drop `{version}`, OR

      **(b)** Use the `[A] All versions` option to drop every version of `{target_skill}` at once."

      In (a), `<version to keep>` is the first `{version_rows}` entry other than `{version}` whose `in_manifest` and `on_disk` are true and whose `status` is not `"deprecated"` (the rows are newest first); with no such entry, show `<version to keep>` as written.

      HALT (exit code 5, `halt_reason: "active-version-guard-refused"`, phase `select:active-version-guard`), with `skill: "{target_skill}"` and `versions_affected: ["{version}"]` in the §1 halt envelope. Do not proceed.

   c. Otherwise (a count of `1`, or no other version in the manifest) → the active version is the ONLY non-deprecated version; allow the drop to continue (it is functionally equivalent to a skill-level drop on a single-version skill)

### 8. Ask Mode

**GATE [default: use args]:** a `mode` argument answers this section in either mode, and an interactive run with none asks; the cases below say when the run HALTs instead. When `{headless_mode}` is true, record the `drop_mode` this section sets as an auto-decision before §8b runs: stage `{run_dir}/decision.json` as `{"gate": "select.mode", "default_action": "use args", "taken_action": "<drop_mode>", "reason": "<mode_source>"}` and run

```bash
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
```

The emitter folds each recorded decision into the result record's `headless_decisions`, and §10 records its auto-confirm the same way. If the command fails, go on: only that entry is lost.

**If `target_in_manifest = false`:** Skip this prompt — soft-deprecate is meaningless without a manifest entry to mark, so only a purge applies. Take the first case that matches:

1. A `mode` argument other than `purge`: HALT (exit code 2, `halt_reason: "input-invalid"`, phase `select:mode`), with `skill: "{target_skill}"` in the §1 halt envelope: "`{target_skill}` has no manifest entry, so there is nothing to deprecate. Re-run with `--mode purge` to delete it."
2. `{headless_mode}` is true and no `mode` argument was passed: HALT (exit code 2, `halt_reason: "input-missing"`, phase `select:mode`), with `skill: "{target_skill}"` in the §1 halt envelope: "headless mode: `{target_skill}` has no manifest entry, so only a purge applies; re-run with `--mode purge`."
3. Otherwise force `drop_mode = "purge"` (record `mode_source = "draft-skill-forced-purge"`), inform the user: "**Mode forced to purge:** `{target_skill}` has no manifest entry, so there is nothing to deprecate. The skill's on-disk directories will be deleted.", and apply §8b. An interactive run still confirms the purge at §10. A headless run reaches this case only with `mode=purge`, which the On-Activation guard has already checked against `{forbidPurgeInHeadless}`.

**If `target_in_manifest = true`:**

**If a `mode` argument was supplied at invocation:** if it is `"deprecate"` or `"purge"`, set `drop_mode` from it and record the decision source `mode_source = "--mode argument"`. If a `mode` arg was supplied but is not one of `deprecate` / `purge`, HALT (exit code 2, `halt_reason: "input-invalid"`, phase `select:mode`), with `skill: "{target_skill}"` in the §1 halt envelope: "invalid `--mode` value `{supplied}`: expected `deprecate` or `purge`."

**Otherwise:** If `{headless_mode}` is true (no `mode` arg), there is no input to prompt for: HALT (exit code 2, `halt_reason: "input-missing"`, phase `select:mode`), with `skill: "{target_skill}"` in the §1 halt envelope: "headless mode requires `--mode deprecate|purge` to set the drop mode." Otherwise, prompt the user. Before showing the menu, run the §8b purge check at the current scope; when `{purge_verdict}` is not `"ok"`, leave out **[P]** and add the line "Purge is not offered: {the §8b refusal message for `{purge_reason}`}."

"**How should this be dropped?**

- **[D]** Deprecate (soft): mark the version as `deprecated` in the manifest. Files remain on disk. Export-skill will exclude it from all platform context files. Reversible by editing the manifest.
- **[P]** Purge (hard): deprecate and delete {affected_directories} from disk (a forge folder SKF did not generate stays where it is). **Irreversible.**
- **[X]** Cancel and exit (or type `cancel` / `exit` / `:q`)"

Wait for user selection.

Set `drop_mode` to `"deprecate"` (on D) or `"purge"` (on P), and record `mode_source = "interactive-prompt"`.

### 8b. Purge Guard

A purge deletes only what SKF generated, and the inventory helper decides what that is: never decide by hand whether SKF generated a folder.

**The purge check.** Run it once, at the scope §6 chose, and reuse its result wherever this step reads it (§8's menu, the guard below and §9). Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}`:

```bash
uv run {skillInventoryHelper} "{skills_output_folder}" --skill {target_skill} --purge-check [--purge-version {version}] --forge-data-folder "{forge_data_folder}"
```

Pass `--purge-version {version}` for a single-version drop (`is_skill_level = false`) and leave it out for a whole skill. From its `purge_check`, bind `{purge_verdict}` ← `verdict`, `{purge_reason}` ← `reason`, `{purge_detail}` ← `detail`, `{purge_entries}` ← `offending_entries`, `{affected_directories}` ← `affected_directories`, `{forge_left_in_place}` ← `forge_left_in_place` and `{forge_errors}` ← `forge_errors`. The helper alone decides what a purge may delete: `{purge_reason}` names the rule that refused, and `{forge_left_in_place}` the forge folder a purge leaves where it is because SKF did not generate it.

When `{skillInventoryHelper}` resolves to no path, `{roster}.inventory` is false, the call exits non-zero, or its result has no `purge_check` (an installed `skf-skill-inventory.py` older than the flag), bind `{purge_verdict}` and `{purge_reason}` to `"unknown"`: SKF cannot check what it would delete.

**The guard.** Skip it when `drop_mode == "deprecate"`. When `{purge_verdict}` is not `"ok"`, HALT (exit code 5, `halt_reason: "not-skf-output"`, phase `select:purge-guard`) with the message for `{purge_reason}`, and `skill: "{target_skill}"` and `drop_mode: "purge"` in the §1 halt envelope.

- `skill-mixed-whole`: "**Purge refused: `{skills_output_folder}/{target_skill}/` also holds entries SKF did not generate:** {purge_entries}. Nothing was deleted. Move them out of the folder and re-run. For a skill in the manifest, you can also purge a single version SKF generated, or use `--mode deprecate`. A version folder with no `metadata.json` can also be one that an interrupted update-skill run left behind; delete it yourself in that case."
- `skill-version-not-skf`: "**Purge refused: SKF did not generate `{skills_output_folder}/{target_skill}/{version}`** (it has no SKF marker in its `metadata.json`, or it is a link). Nothing was deleted. Use `--mode deprecate` to mark the version deprecated in the manifest only, or remove it yourself."
- `skill-version-mixed`: "**Purge refused: `{skills_output_folder}/{target_skill}/{version}` also holds entries SKF did not generate:** {purge_entries}. Nothing was deleted. Move them out and re-run, or use `--mode deprecate`."
- `skill-foreign`, `reserved-name` or `unknown`: "**Purge refused: SKF cannot confirm that it generated `{skills_output_folder}/{target_skill}/`:** {reason}. Nothing was deleted. Use `--mode deprecate` to mark it deprecated in the manifest only, or delete the folder yourself." `{reason}` is `{purge_detail}` (it names a link, or a `metadata.json` with no SKF marker), and for `unknown` "the inventory helper is missing, or the installed `skf-skill-inventory.py` has no purge check; re-install SKF".
- `forge-mixed-whole`: "**Purge refused: `{forge_data_folder}/{target_skill}/` also holds entries SKF did not generate:** {purge_entries}. Nothing was deleted. Move them out of the folder and re-run. For a skill in the manifest, you can also purge a single version SKF generated, or use `--mode deprecate`."
- `forge-version-mixed`: "**Purge refused: `{forge_data_folder}/{target_skill}/{version}/` holds entries SKF did not generate:** {purge_entries}. Nothing was deleted. Move them out and re-run, or use `--mode deprecate`."

### 9. Compute Affected Directories

`affected_directories` is the §8b purge check's list: the folders a purge at this scope deletes. In deprecate mode the list shows what the drop keeps on disk, and §10 presents it as retained. When the purge check has no verdict (`"unknown"`), build it from these paths instead: `{skills_output_folder}/{target_skill}/{version}` and `{forge_data_folder}/{target_skill}/{version}` for a single version, `{skills_output_folder}/{target_skill}` and `{forge_data_folder}/{target_skill}` for a whole skill, each without a trailing `/`, and only once when both settings name one folder.

#### 9b. Compute Blast-Radius Metrics (for §10 summary)

Compute the three scalars §10's `Scope:` line shows:

1. **`versions_count`**: the number of skill versions in scope, never counted by hand:
   - Version-level drop: `1`
   - Skill-level drop: `{version_counts}.non_deprecated` (§5) for a skill in the manifest (the deprecated versions are already absent from the active managed sections), and `{version_counts}.on_disk` for a draft

2. **`bytes_total`**: the on-disk size of `affected_directories`. Delegate the recursive sum and the human label to the sizing helper rather than adding file sizes in-prompt:

   ```bash
   uv run {dirSizesHelper} sizes {each path in affected_directories, quoted, space-separated}
   ```

   Read `total_human` (e.g. `"4.2 MB"`) as `bytes_total`; a path that does not exist adds nothing. If the helper is unavailable, fall back to `du -sb` per path: the display is best-effort.

3. **`context_files_count`**: the number of context files step 2 rebuilds. Map the `ides` list of `config.yaml` (an absent key is an empty list) through the IDE mapping export-skill writes the section with, using the `{rebuildManagedSectionsHelper}` On-Activation §4 resolved:

   ```bash
   python3 {rebuildManagedSectionsHelper} resolve-targets --ides "{ides}"
   ```

   `{ides}` is the comma-joined list. Store `targets` as `target_context_files` (one `{context_file, skill_root, ides}` entry per file; an IDE the mapping does not list, and an empty list, resolve to AGENTS.md with `.agents/skills/`), set `context_files_count` to its length, and show each `warnings[]` and `notes[]` line. When the helper exits non-zero, HALT (exit code 4, `halt_reason: "context-rebuild-failed"`, phase `select:context-files`), with `skill: "{target_skill}"` and `drop_mode: "{drop_mode}"` in the §1 halt envelope: "SKF cannot resolve the context files to rebuild: {the helper's `error`, or its stderr when stdout holds no JSON}. Nothing was changed. Re-install SKF."

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
    {if forge_left_in_place:} Left in place (not SKF output): {forge_left_in_place}{if forge_errors is non-empty: ": " + forge_errors}

{if drop_mode == "purge":}
  ⚠️  This operation cannot be undone. Files will be permanently deleted.
{else:}
  Files remain on disk. Reversible by manually editing the manifest.

Proceed? [Y/N]
```

**If `--dry-run` was passed**, it takes precedence over the headless auto-confirm: skip the Y/N prompt even when `{headless_mode}` is true, change nothing, and display the `[DRY RUN]` line with the resolved selection, so the user can re-run with the same values when ready to commit:

```
**[DRY RUN] No changes were made — preview above shows what would be dropped.**

Resolved selection:
  Skill:   {target_skill}
  Version: {target_versions[0] if is_skill_level == false else "all"}
  Mode:    {Deprecate (soft) | Purge (hard)}
```

When `{headless_mode}` is true, stage the preview as `{run_dir}/result-context.json` and print its envelope. `would_delete` lists the folders a purge would delete, so an automator can check the blast radius before it runs the drop:

```json
{"status": "dry-run", "skill": "{target_skill}", "drop_mode": "{drop_mode}", "versions_affected": {target_versions}, "would_delete": {affected_directories when drop_mode is purge, else []}, "forge_left_in_place": {forge_left_in_place when drop_mode is purge, else null}}
```

```bash
uv run {emitEnvelopeHelper} emit --workflow skf-drop-skill --run-dir "{run_dir}" < "{run_dir}/result-context.json"
```

Display the line it prints verbatim (the `message` of its stderr JSON when it exits non-zero). A dry run passes no `--result-dir`, so it writes no result file. Then, in either mode, delete the run folder (`rm -rf "{run_dir}"`) and HALT (exit code 0). The manifest, filesystem, and context files are untouched.

**Otherwise (not a dry-run), GATE [default: Y]:** If `{headless_mode}`: auto-proceed with [Y], record `confirm_source = "headless-auto"`, stage `{run_dir}/decision.json` as `{"gate": "select.confirm", "default_action": "Y", "taken_action": "Y", "reason": "headless auto-confirm"}` and run the §8 `record` command, and log: "headless: auto-confirmed drop of {target_skill}"

Wait for explicit user response.

- **If `Y`** → record `confirm_source = "user-explicit"` and proceed to section 11
- **If `N`** (or `cancel` / `exit` / `[X]` / `:q`) → "**Cancelled.** No changes were made. (Tip: invoke with `--dry-run` next time to preview the operation without reaching the commit prompt.)" HALT (exit code 6, `halt_reason: "user-cancelled"`, phase `select:confirm`).
- **Any other input** → re-display the confirmation and ask again

### 11. Store Decisions in Context

Step 2 reads the decisions this step bound where it made them: `target_skill`, `target_in_manifest`, `target_versions`, `drop_mode`, `is_skill_level`, `affected_directories`, `mode_source`, `forge_left_in_place`, `target_context_files` and `confirm_source`.

### 12. Load Next Step

`{nextStepFile}` performs the destructive mutation, so reach it only after the §10 gate returned `Y` and §11 stored the decisions — chaining any earlier would drop without the user's explicit consent (the sequence above enforces this ordering). Load, read the full file, and then execute it.

