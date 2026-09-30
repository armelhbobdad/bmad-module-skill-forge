---
nextStepFile: 'execute.md'
versionPathsKnowledge: 'knowledge/version-paths.md'
# Resolve `{manifestOpsHelper}` by probing `{manifestOpsProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. §2 reads the manifest with its `read` action (v1 migration and a
# file that does not parse reported as JSON), and §7 uses its
# `affected-versions` action to enumerate the versions a rename must touch:
# the union of manifest version keys and on-disk version dirs, deduped and
# semver-sorted (numeric, so 0.10.0 precedes 0.9.0). Unlike execute.md's write
# helpers this one is not atomicity-critical: if neither path resolves, §2
# and §7 fall back to the prompt.
manifestOpsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py'
  - '{project-root}/src/shared/scripts/skf-manifest-ops.py'
# Resolve `{skillInventoryHelper}` by probing `{skillInventoryProbeOrder}`
# (installed SKF module path first, src/ dev-checkout fallback). §3 uses it to
# enumerate the rename candidates: the union of manifest `exports` and on-disk
# skill directories, each with its version list, active version and
# `skf_skill`. §4a runs its `--rename-check`, the rename verdict for the skill
# folder and its forge folder, so a rename never moves a folder SKF did not
# generate. If neither path resolves, §3 lists manifest skills only and §4a
# refuses the rename.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# `{renameNameValidator}` is this skill's own deterministic new-name gate. §5
# uses it for the format / length / identity / collision checks (one correct
# answer per (name, filesystem, manifest) state) and the interrupted-rename
# recovery fingerprint; §5 falls back to the same checks in-prompt if Python is
# unavailable.
renameNameValidator: 'scripts/skf-validate-rename-name.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Select Rename Target

## STEP GOAL:

Identify the skill the user wants to rename, validate the new name against the agentskills.io spec (kebab-case, length, uniqueness), warn about source authority implications, enumerate every version that will be touched, and obtain explicit user confirmation before any filesystem operation is scheduled. Every selection decision is stored in context so step 2 can execute the rename transactionally.

## Rules

- Focus only on selection, validation, and confirmation — do not modify manifest, copy, or delete files
- Do not proceed without explicit user confirmation at the final gate
- Do not accept a new name that fails validation (kebab-case, length, uniqueness)
- Present the list of affected versions clearly so the user understands the scope

**Headless error envelope (self-contained).** Where a halt below says *"emit the error envelope per SKILL.md 'Result Contract (Headless)'"*, write this single line to **stderr** (restated here so selection halts stay parseable even if SKILL.md is out of context) —

```
SKF_RENAME_SKILL_RESULT_JSON: {"status":"error","old_name":"…|null","new_name":"…|null","versions_renamed":[],"manifest_rekeyed":false,"context_files_updated":[],"exit_code":<code>,"halt_reason":"<reason>","headless_decisions":[]}
```

Use the `old_name`/`new_name`, `exit_code`, and `halt_reason` named at each halt site (see `references/exit-codes.md`) — `old_name`/`new_name` are `null` until resolved in §4/§5. `headless_decisions` is `[]` at every selection-stage halt: the only decision this step records (the §6 source-authority override) means *proceed*, so no recorded decision is ever paired with a halt here.

## MANDATORY SEQUENCE

### 1. Load Knowledge

Read `{versionPathsKnowledge}` completely and extract:

- Path templates: `{skill_package}`, `{skill_group}`, `{forge_version}`, `{forge_group}`
- Export manifest v2 schema (`schema_version`, `exports`, `active_version`, `versions` map, `status` field values)
- The Rename section under "Skill Management Operations" — the complete list of 9 locations that must be updated coherently

You will use these templates and rules to build directory paths, enumerate affected versions, and plan the transactional rename in step 2.

### 2. Read Export Manifest

**Resolve `{manifestOpsHelper}`** ← first existing path in `{manifestOpsProbeOrder}`, and read the manifest through it rather than by eye: the helper migrates v1 to v2, normalizes `platforms` to `ides`, and reports a file that does not parse:

```bash
python3 {manifestOpsHelper} {skills_output_folder} read
```

- **`status == "error"`** (the file exists but does not parse): halt with "**Export manifest is corrupt** at `{skills_output_folder}/.export-manifest.json`: {error}. Fix or remove the file before renaming." HALT (exit code 3, `halt_reason: "manifest-corrupt"`). In headless mode, emit the error envelope per SKILL.md "Result Contract (Headless)" with `old_name: null`, `new_name: null`.
- **`status == "ok"`**: use `result.manifest` (already in the v2 shape) as `manifest` for the rest of this step. Set `manifest_exists = true` when `manifest.exports` has at least one entry, else `false` (a missing file reads back as an empty `exports`). With no entry, §3's on-disk scan is the whole roster: drafted or never-exported skills can still be renamed, and step 2 §6 has no manifest entry to re-key.

**If neither `{manifestOpsProbeOrder}` candidate resolves:** read the manifest file in-prompt: a missing or empty file, or one with no `exports` entries, is `manifest_exists = false`; a file with `exports` entries is `true` (no `schema_version` field means v1: treat each entry as a single active version); a file that is not valid JSON takes the corrupt-manifest HALT above.

### 3. List Available Skills

Enumerate every skill available for rename deterministically. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and run:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --forge-data-folder {forge_data_folder}
```

Read the JSON. Each entry in `skills[]` carries `name`, its `versions` array, and `active_version` (the helper unions the manifest `exports` with the on-disk directories and dedupes, so manifest-tracked and orphaned skills both appear), plus `skf_skill`. List only the entries whose `skf_skill` is true: rename copies and then deletes the whole folder, so a folder SKF did not generate is never offered. A listed skill whose `name` is absent from `manifest.exports` is a draft/orphan the rename workflow can still handle: annotate it "(not in manifest)". The §4a rename check decides whether the skill the user picks can move. Bind `{not_skf_output}` ← `not_skf_output` (folders holding a skill SKF did not generate); when it is non-empty, show one line under the list: "Not offered (not SKF output): {not_skf_output}".

**If `{skillInventoryHelper}` has no existing candidate** (neither probe path resolves — e.g. Python/`uv` unavailable): build the list from the manifest `exports` only (if `manifest_exists`), reading each one's `active_version` and version count. Folders on disk that are absent from `exports` are not offered: without the helper SKF cannot check that it generated them, and §4a refuses the rename in this mode.

**If the list to display is empty** (no `skills[]` entry whose `skf_skill` is true, or, without `{skillInventoryHelper}`, no manifest `exports` entry):

- When `old_name` was supplied as an argument and it is in `{not_skf_output}` (empty without `{skillInventoryHelper}`), take the §4a refusal for a folder SKF did not generate first, in either mode (exit code 5, `halt_reason: "not-skf-output"`, with `old_name: "{old_name}"`, `new_name: null` in the headless envelope).
- Otherwise halt with "**Rename Skill — nothing to rename.** No skill SKF generated was found in `{skills_output_folder}/`. Run `[CS] Create Skill` first." When `{not_skf_output}` is non-empty, append: "Left untouched (not SKF output): {not_skf_output}." HALT (exit code 3, `halt_reason: "nothing-to-rename"`). In headless mode, emit the error envelope with `old_name: null`, `new_name: null`.

Display the list, one line per skill as `{name} ({n} versions, active: {active_version})` (append "(not in manifest)" for orphans):

```
**Rename Skill — select target**

Available skills:
1. cognee (3 versions, active: 0.6.0)
2. express (1 version, active: 4.18.0)
3. legacy-helper (not in manifest)

Not offered (not SKF output): my-module-skill
```

### 4. Ask Which Skill

"**Which skill would you like to rename?**
Enter the skill name or its number from the list above, or `cancel` / `exit` / `:q` to abort."

Wait for user input. Accept either the numeric index or the skill name (exact match). **GATE [default: use args]** — If `{headless_mode}` and old skill name was provided as argument: select that skill and auto-proceed. If not provided, HALT (exit code 2, `halt_reason: "input-missing"`): "headless mode requires old_name argument." In headless, emit the error envelope.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q`: Display "Cancelled — no changes were made." and HALT (exit code 6, `halt_reason: "user-cancelled"`).
- **If the input names a folder in `{not_skf_output}`:** take the §4a refusal for a folder SKF did not generate.
- **If the user's input does not match any listed skill:**
  - **Interactive:** Re-display the list and ask again.
  - **Headless (`{headless_mode}` is true):** the supplied `old_name` argument matches no listed skill and there is no further input to re-prompt for. HALT (exit code 2, `halt_reason: "input-invalid"`): "headless mode: old_name argument `{supplied value}` does not match any listed skill." Emit the error envelope with `old_name: null`, `new_name: null`.

Store the selection as `old_name`.

### 4a. Ownership Check

Rename copies the whole `{skills_output_folder}/{old_name}/` folder and its forge folder, then deletes the old ones, so it only renames a skill SKF generated in the versioned layout. The inventory helper decides that; never decide by hand whether SKF generated a folder. Run:

```bash
uv run {skillInventoryHelper} "{skills_output_folder}" --skill {old_name} --rename-check --forge-data-folder "{forge_data_folder}"
```

From its `rename_check`, bind `{rename_verdict}` ← `verdict`, `{rename_reason}` ← `reason`, `{rename_detail}` ← `detail`, `{rename_entries}` ← `offending_entries`, `{target_errors}` ← `errors`, `{forge_move}` ← `forge_move`, `{forge_left_in_place}` ← `forge_left_in_place` and `{same_folder}` ← `same_folder`. The helper applies the rules below in order, to the skill folder and, unless both settings name one folder, to its forge folder, and returns the first that refuses. When §3 ran without `{skillInventoryHelper}`, the call exits non-zero, or its result has no `rename_check` (an installed `skf-skill-inventory.py` older than the flag), refuse with rule 1.

When `{rename_verdict}` is not `"ok"`, display the message of the rule that applies and HALT (exit code 5) with `halt_reason: "{rename_verdict}"` (`not-skf-output`, or `flat-layout` for rule 4). In headless mode, emit the error envelope with `old_name: "{old_name}"`, `new_name: null`. No lock is held yet (§4b acquires it), so there is nothing to release.

1. No verdict (no helper, a failed call, or no `rename_check`) → `not-skf-output`: "**SKF cannot check that it generated `{old_name}`** because `skf-skill-inventory.py` is missing, or the installed one has no rename check. Nothing was changed. Re-install SKF and re-run the rename."
2. `{rename_reason}` is `foreign`, `reserved-name` or `absent` (no skill SKF generated at `{skills_output_folder}/{old_name}`) → `not-skf-output`: "**`{old_name}` is not SKF output: nothing was changed.** `{skills_output_folder}/{old_name}/` has no SKF marker in its `metadata.json`, so SKF will not rename it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{old_name}` yourself. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When `{target_errors}` is non-empty (for example, the folder is a link), or the reason is `reserved-name` or `absent`, show `{rename_detail}` in place of the marker sentence.
3. `mixed` → `not-skf-output`: "**`{skills_output_folder}/{old_name}/` also holds entries SKF did not generate:** {rename_entries}. Nothing was changed. Rename moves and then deletes the whole folder, so SKF will not rename it. Move those entries out of the folder and re-run. A version folder with no `metadata.json` can also be one that an interrupted update-skill run left behind; delete it yourself in that case."
4. `flat-layout` → `flat-layout`: "**`{old_name}` still uses the flat layout.** Nothing was changed. Rename works on the versioned layout only: run `@Ferris TS {old_name}` (or US, AS or EX) once to move it into that layout, then re-run the rename."
5. `forge-link`, `forge-not-a-folder` or `forge-unreadable` (the forge folder is a link, is not a folder, or cannot be listed) → `not-skf-output`: "**SKF will not move `{forge_data_folder}/{old_name}`:** {rename_detail}. Nothing was changed." For `forge-link`, add: "SKF never moves or deletes through a link: the copy would take the files from where the link points, and removing the old name or rolling back would empty that folder. Replace the link with the folder it points to, then re-run." Otherwise (the path is not a folder, or SKF cannot list it), add: "Rename moves a forge folder only when it is a folder SKF can read. Move that path out of the way or fix its permissions, then re-run."
6. `forge-mixed` → `not-skf-output`: "**`{forge_data_folder}/{old_name}/` also holds entries SKF did not generate:** {rename_entries}. Nothing was changed. Rename moves and then deletes the whole forge folder, so SKF will not rename it. Move those entries out of the folder and re-run."

When no rule applies, `{forge_move}` and `{forge_left_in_place}` come from the helper. A link at or above `{forge_data_folder}` itself is the user's configuration; SKF checks the forge folder and everything in it (a linked folder inside it makes it `"mixed"`). Then continue to §4b.

### 4b. Concurrency Guard

Two concurrent rename runs against the same `old_name` would corrupt state mid-copy: one would `rm -rf` the other's freshly-staged new directories, or both would race on the manifest re-key. The lock below catches the common accidental-double-invoke case. It is a **best-effort PID-file guard**, not a held flock — the LLM-driven workflow spans many turn boundaries and no single bash invocation can hold flock across them.

**Mirror this exactly so the guard works the same way every run:**

```bash
LOCK={forge_data_folder}/.skf-rename-{old_name}.lock
mkdir -p "{forge_data_folder}"

if [ -f "$LOCK" ]; then
  HELD_PID=$(head -n1 "$LOCK" 2>/dev/null | awk '{print $1}')
  if [ -n "$HELD_PID" ] && kill -0 "$HELD_PID" 2>/dev/null; then
    echo "skf-rename-skill: another rename is in progress (pid=$HELD_PID, started $(awk 'NR==2' "$LOCK" 2>/dev/null))"
    exit 1
  fi
  echo "skf-rename-skill: clearing stale lock from pid=$HELD_PID"
fi

printf '%s\n%s\n' "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LOCK"
```

The lock sits beside the forge folders, never inside one: a skill can have no forge folder, or one SKF did not generate, and a lock inside it would be copied into the new one.

**Halt protocol on live-PID collision:**

- Display: `"**Another rename is in progress.** The skill {old_name} is locked by pid={HELD_PID} (started {timestamp from line 2 of the lock file}). Wait for that run to finish, or — if you know that pid is no longer running — delete {LOCK} manually and re-run."`
- HALT (exit code 5, `halt_reason: "halted-for-concurrent-run"`). In `{headless_mode}`, emit the error envelope per SKILL.md "Result Contract (Headless)" with `old_name: "{old_name}"`, `new_name: null`. **No `headless_decisions[]` entry** — this is a hard halt before any gate fires.

**Release contract:**

- This run owns the lock only after the `printf … > "$LOCK"` line above runs — i.e. once §4b has cleared the live-PID check and written this run's PID. The live-PID collision halt directly above is the **sole exception**: it exits *before* that line, so the lock belongs to the other live run and this run must **never** delete it (clearing a live lock it just honored would let a third invocation run concurrently).
- The terminal health-check step (step 4) deletes the lock as its final action on the success path.
- **Every halt from §5 onward — after this run has acquired the lock — must delete it before exiting** (`rm -f "$LOCK"` per halt site): the §5 input/format/collision halts, the §6 source-authority and cancel halts, the §8 cancel and dry-run exits, and execute.md's copy/verify/manifest/write rollbacks. Otherwise the next attempt would see a stale lock from this run.

### 5. Ask for New Name

"**What is the new name for this skill?**
The new name must be kebab-case: lowercase alphanumeric with hyphens, 1-64 characters, matching the regex `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` (starts and ends with a lowercase letter or digit; a single letter or digit is valid). Or type `cancel` / `exit` / `:q` to abort."

Wait for user input. Trim whitespace. **GATE [default: use args]** — If `{headless_mode}` and new_name was provided as argument: use it and auto-proceed through validation. If not provided, release the lock and HALT (exit code 2, `halt_reason: "input-missing"`): "headless mode requires new_name argument." In headless, emit the error envelope.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q`: release the lock (`rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`), display "Cancelled — no changes were made.", and HALT (exit code 6, `halt_reason: "user-cancelled"`).

**Validate the candidate deterministically.** Run `{renameNameValidator}` (a per-skill helper, always shipped with the skill) — it applies format, length, identity, and collision in that order and returns the verdict as JSON:

```bash
python3 {renameNameValidator} \
  --old-name {old_name} --new-name {candidate} \
  --skills-output-folder {skills_output_folder} \
  --forge-data-folder {forge_data_folder}
```

The checks: **format** = the kebab regex `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` (the module's canonical rule, same as `skf-validate-output.py` / `skf-validate-brief-inputs.py`, so a digit-leading name like `3d-tools` renames cleanly); **length** = 1-64 characters (agentskills.io spec); **identity** = differs from `{old_name}`; **collision** = the name is not a manifest `exports` key or an entry in `{skills_output_folder}` or `{forge_data_folder}` (a file or link counts), and not `improvement-queue`.

Read `valid`, `first_failure`, `checks`, and `interrupted_rename`. If `valid` is true, store the input as `new_name` and proceed to §6. Otherwise branch on `first_failure` — interactive: display the message and re-ask; headless: release the lock (`rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`), HALT with the mapped code, and emit the error envelope:

- **`format`** → "**Invalid name format.** The new name must be lowercase alphanumeric with hyphens, starting and ending with a lowercase letter or digit. Try again." (headless HALT: exit code 2, `halt_reason: "input-invalid"`)
- **`length`** → "**Invalid name length.** The new name must be 1-64 characters. Try again." (headless HALT: exit code 2, `halt_reason: "input-invalid"`)
- **`identity`** → "**The new name is identical to the current name.** Nothing to rename. Try again or abort the workflow." (headless HALT: exit code 2, `halt_reason: "input-invalid"`)
- **`collision`** → "**Name collision.** `{new-name}` already exists at: {the `path` of each entry in `checks.collision.locations`}. Pick a different name." When `checks.collision.locations` has a `reserved` entry, say instead: "**Reserved name.** `improvement-queue` is SKF's own folder in `{forge_data_folder}`. Pick a different name." When `interrupted_rename` is true, append: "This may be a stranded partial rename from an earlier interrupted run — `{new_name}` was staged but `{old_name}` was never removed. Confirm the `{new_name}` directories are not a skill you want to keep, then remove `{skills_output_folder}/{new_name}`, and `{forge_data_folder}/{new_name}` only when it holds a copy of `{old_name}`'s forge folder, and re-run this rename." — this gives headless pipelines a named recovery path instead of a dead-end collision halt. (headless HALT: exit code 5, `halt_reason: "name-collision"`)

**If `{renameNameValidator}` cannot run** (Python/`uv` unavailable): apply the same four checks in the same order in the prompt — the kebab regex, the 1-64 length bound, inequality with `{old_name}`, and the collision lookup (the three sources plus the reserved name), plus the interrupted-rename fingerprint: the new name collides only on disk (not in the manifest, not reserved), `{skills_output_folder}/{old_name}` is still a folder, `{skills_output_folder}/{new_name}` is a folder holding nothing a copy of it could not (every entry in it also exists in `{skills_output_folder}/{old_name}`, of the same kind, with at most a version's `{old_name}/` package renamed to `{new_name}/`), and `{forge_data_folder}/{new_name}` exists only when `{forge_data_folder}/{old_name}` does — using the identical messages and halt mapping.

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

Ask: "**Continue anyway?** [Y/N] (or `cancel` / `exit` / `:q` to abort)"

Wait for response.
- **If `N`** (or `cancel` / `exit` / `[X]` / `:q`) → release the lock (`rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`), display "**Cancelled.** No changes were made.", HALT (exit code 6, `halt_reason: "user-cancelled"`).
- **If `Y`** → proceed. Set `source_authority_override = true`.

**Headless behavior:** If `{headless_mode}` is true AND `{forceSourceAuthorityInHeadless}` is `"true"`, auto-proceed and record `{gate: "source-authority", default_action: "halt", taken_action: "proceed", reason: "force_source_authority_in_headless override"}` in `headless_decisions[]`. Otherwise, release the lock and HALT (exit code 5, `halt_reason: "source-authority-blocked"`) and emit the error envelope — the safe default protects against silent registry-divergence on `published`-tagged skills.

**If `source_authority` is absent, or any value other than `"official"`:** skip the warning and proceed.

### 7. Enumerate Affected Versions

Resolve `{manifestOpsHelper}` ← first existing path in `{manifestOpsProbeOrder}` (installed SKF module path first, `src/` dev-checkout fallback). Enumerate every version the rename must touch deterministically via its `affected-versions` action:

```bash
python3 {manifestOpsHelper} {skills_output_folder} affected-versions {old_name}
```

Read the JSON result. Store `affected_versions` = `result.affected_versions` and `affected_versions_count` = `result.count`. The helper unions the manifest's `exports.{old_name}.versions` keys with the on-disk version directories under `{skills_output_folder}/{old_name}` (every entry that is not the `active` symlink), so it handles both manifest-tracked and orphaned on-disk versions, deduplicates, and applies a **numeric** semver-descending sort (so `0.10.0` correctly precedes `0.9.0`, which a lexical sort gets wrong). An incomplete union would risk leaving a version internally un-renamed in the new copy — a leftover that step 2 §5 only catches for the versions it was told about.

**If `{manifestOpsHelper}` has no existing candidate** (neither probe path resolves — e.g. Python/`uv` unavailable): compute `affected_versions` in the prompt instead — read every key under `exports.{old_name}.versions` in the manifest, list every directory under `{skills_output_folder}/{old_name}` that is not `active`, union the two sets, and sort descending (newest first, comparing version components numerically). Store the list as `affected_versions` and its length as `affected_versions_count`.

Also resolve the four outer paths using the templates from `{versionPathsKnowledge}`, each without a trailing `/`:

- `old_skill_group` = `{skills_output_folder}/{old_name}`
- `new_skill_group` = `{skills_output_folder}/{new_name}`
- `old_forge_group` = `{forge_data_folder}/{old_name}`
- `new_forge_group` = `{forge_data_folder}/{new_name}`

### 8. Confirmation Gate

Display the full operation summary:

```
**About to rename:**

  From: {old_name}
  To:   {new_name}
  Versions affected: {affected_versions_count} ({comma-separated affected_versions})

  Directories that will be copied then removed:
    {old_skill_group}  →  {new_skill_group}
    {if forge_move:}{old_forge_group}  →  {new_forge_group}
    {if forge_left_in_place:}Left in place (not SKF output): {forge_left_in_place} — SKF did not generate it, so it keeps its name.

  Inside each version, the inner `{old_name}/` directory will be renamed to `{new_name}/`,
  and the following files will be updated:
    - SKILL.md (frontmatter `name` field)
    - metadata.json (`name` field, and paths into the moved folders)
    - context-snippet.md (the name in its header, its IMPORTANT line and its root paths)
    {if forge_move or same_folder:}- provenance-map.json (`skill_name` field and paths into the moved folders, under {old_forge_group})

  Manifest `exports.{old_name}` will be re-keyed to `exports.{new_name}`.
  Platform context files (CLAUDE.md, .cursorrules, AGENTS.md) will be rebuilt so
  the managed section references `{new_name}` instead of `{old_name}`.

Operation is **transactional**: the new name will be fully materialized and verified
before the old name is removed. If a step fails up to the manifest re-key, the new
directories are removed and the old skill remains intact. A context file that fails
to rebuild afterwards is reported and never undoes the rename.

Proceed? [Y/N]
```

**GATE [default: Y]** — If `{headless_mode}`: auto-proceed with [Y] and append `{gate: "confirm-rename", default_action: "proceed", taken_action: "proceed", reason: "headless auto-confirm"}` to `headless_decisions[]` (log line: "headless: auto-confirmed rename {old_name} → {new_name}"). Skip this append when `--dry-run` is set — a dry run does not execute the rename, so there is no confirmation to record.

Wait for explicit user response.

**If `--dry-run` was passed**: skip the Y/N prompt entirely. Release the lock (`rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`), display "**[DRY RUN] No changes were made — preview above shows what would be renamed.**", and emit the success envelope per SKILL.md "Result Contract (Headless)" with `status: "dry-run"`, the resolved `old_name`, `new_name`, `versions_renamed: {affected_versions}`, and `headless_decisions: {headless_decisions}` (carries the §6 source-authority override entry if it fired, else `[]`), then HALT (exit code 0). No copy, no manifest re-key, no delete.

- **If `Y`** → proceed to section 9
- **If `N`** (or `cancel` / `exit` / `[X]` / `:q`) → release the lock (`rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`), display "**Cancelled.** No changes were made.", HALT (exit code 6, `halt_reason: "user-cancelled"`). In headless mode, emit the error envelope per SKILL.md "Result Contract (Headless)" with the resolved `old_name` and `new_name`.
- **Any other input** → re-display the confirmation and ask again

### 9. Store Decisions in Context

Store the following decisions in workflow context for step 2:

- `old_name` — the current skill name
- `new_name` — the validated new name
- `affected_versions` — list of version strings for every version that must be updated
- `affected_versions_count` — integer count of the above
- `old_skill_group` — absolute path `{skills_output_folder}/{old_name}` (no trailing `/`, like the three below)
- `new_skill_group` — absolute path `{skills_output_folder}/{new_name}`
- `old_forge_group` — absolute path `{forge_data_folder}/{old_name}`
- `new_forge_group` — absolute path `{forge_data_folder}/{new_name}`
- `forge_move` — boolean from §4a (true when this rename moves the forge folder)
- `forge_left_in_place` — the forge folder §4a leaves under the old name because SKF did not generate it, or null
- `same_folder` — boolean from §4a (true when `skills_output_folder` and `forge_data_folder` name one folder)
- `source_authority_override` — boolean (true if the user acknowledged the `"official"` warning, false/absent otherwise)
- `headless_decisions` — the audit trail of confirmation gates auto-resolved under `{headless_mode}` (the §6 source-authority override and the §8 auto-confirm entries appended above). Initialize to `[]`; in interactive runs it stays `[]`. Step 2 carries it forward and step 3 surfaces it in the result envelope.

### 10. Load Next Step

Load, read the full file, and then execute `{nextStepFile}`.

