---
nextStepFile: 'execute.md'
# §1 resolves each probe order below (installed SKF module path first,
# src/ dev-checkout fallback; the first existing path wins).
# {manifestOpsHelper}: the §7 `affected-versions`.
manifestOpsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py'
  - '{project-root}/src/shared/scripts/skf-manifest-ops.py'
# {skillInventoryHelper}: §4a `--rename-check` and §6 `resolve`.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# {skillRosterHelper}: the §2 roster.
skillRosterProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-roster.py'
  - '{project-root}/src/shared/scripts/skf-skill-roster.py'
# {rewriteSkillNameHelper}: the §7b prediction.
rewriteSkillNameProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rewrite-skill-name.py'
  - '{project-root}/src/shared/scripts/skf-rewrite-skill-name.py'
# {renameNameValidator}: this skill's own new-name gate, run in §5.
renameNameValidator: 'scripts/skf-validate-rename-name.py'
# {runLockHelper} and {emitEnvelopeHelper}: §4b and the halt procedure.
runLockProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py'
  - '{project-root}/src/shared/scripts/skf-run-lock.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Select Rename Target

## STEP GOAL:

Identify the skill the user wants to rename, validate the new name against the agentskills.io spec (kebab-case, length, uniqueness), warn about source authority implications, enumerate every version that will be touched, and obtain explicit user confirmation before any filesystem operation is scheduled. Every selection decision is stored in context so step 2 can execute the rename transactionally.

## Rules

- Focus only on selection, validation, and confirmation: this step writes only the run's own files (its run folder and run lock), never the manifest or a skill's files
- Do not proceed without explicit user confirmation at the final gate
- Do not accept a new name that fails validation (kebab-case, length, uniqueness)
- Present the list of affected versions clearly so the user understands the scope

**Halt procedure.** Every HALT below names, in parentheses, its exit code, its `halt_reason` and the phase its `emit-halt` reports, and runs these, in order, before it stops:

1. Once §4b has bound `{lock_owner}`, release the run lock (a release never removes a lock another run holds). From `{project-root}`:

   ```bash
   uv run {runLockHelper} release --lock "{forge_data_folder}/.skf-rename-{old_name}.lock" --owner "{lock_owner}"
   ```

   When it exits non-zero or prints no JSON, tell the user in one line that the lock file stays. In `{headless_mode}`, also record that in the run sink, where the emitter reads it for the halt's envelope; when `record` exits non-zero, show its message in one line and go on with the halt:

   ```bash
   uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "run-lock-not-released: {forge_data_folder}/.skf-rename-{old_name}.lock"
   ```

2. In `{headless_mode}`, pass the halt to the shared emitter, which builds the payload from the options and prints its envelope on **stderr**. The heredoc holds the message the halt displays, as displayed and unescaped: helper JSON values, the lists it printed, the user's argument and paths included. Where that message quotes the stderr of the call that just failed, write `<message>` in its place: the emitter takes the diagnostic from `--stderr-from "{run_dir}/call.err"` and folds it to one line. Leave out `--stderr-from` for a halt that quotes no stderr, `--path` for a halt that names none (`<path>` written with `/`), `--old-name` until §4 binds `{old_name}` and `--new-name` until §5 binds `{new_name}`, and pass `--run-dir "{run_dir}"` once §1 has bound it, even when the folder could not be created:

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-rename-skill --run-dir "{run_dir}" --target stderr --phase '<phase>' --halt-reason '<halt_reason>' --path "<path>" --old-name "{old_name}" --new-name "{new_name}" --stderr-from "{run_dir}/call.err" --reason - <<'SKF_REASON'
   <the message the halt displays>
   SKF_REASON
   ```

   Display the `SKF_RENAME_SKILL_RESULT_JSON:` line it prints verbatim. When it exits 1 and its `message` names an option, a field or `<message>`, fix the call once and run it again. Only when `{emitEnvelopeHelper}` is missing, or the emitter still fails or prints no line, display the halt's message alone, reading any stderr it quotes from `{run_dir}/call.err`.

The halt leaves `{run_dir}` in place.

## MANDATORY SEQUENCE

### 1. Start the Run

Resolve, as one batch of file-existence checks, `{runLockHelper}` ← first existing path in `{runLockProbeOrder}`, `{emitEnvelopeHelper}` ← first existing path in `{emitEnvelopeProbeOrder}`, `{manifestOpsHelper}` ← first existing path in `{manifestOpsProbeOrder}`, `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}`, `{skillRosterHelper}` ← first existing path in `{skillRosterProbeOrder}` and `{rewriteSkillNameHelper}` ← first existing path in `{rewriteSkillNameProbeOrder}`; all six stay bound for the rest of the run. From `{project-root}`, take the run id:

```bash
uv run {runLockHelper} run-id
```

Bind `{run_id}` ← its `run_id` and `{run_dir}` ← `{project-root}/_bmad-output/.skf-run/skf-rename-skill-{run_id}`. Then create the run folder and probe the folders the run writes, so a read-only mount or a full disk stops the run here rather than at step 2's copy:

```bash
for dir in "{run_dir}" "{skills_output_folder}" "{forge_data_folder}"; do
  { mkdir -p "$dir" && printf 'probe' > "$dir/.skf-write-probe" && rm "$dir/.skf-write-probe"; } \
    || { echo "not writable: $dir" >&2; exit 1; }
done
```

- When a helper has no existing candidate, or `run-id` exits non-zero or prints no JSON: HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `select:start-run`) with "**Rename Skill cannot start:** {the missing helper (`skf-run-lock.py`, `skf-emit-result-envelope.py`, `skf-manifest-ops.py`, `skf-skill-inventory.py`, `skf-skill-roster.py` or `skf-rewrite-skill-name.py`), or the helper's error}. Nothing was changed. Re-install SKF, then re-run." With no run id yet, its `emit-halt` leaves out `--run-dir "{run_dir}"`.
- When the loop exits non-zero: HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `select:write-probe`, with the folder its stderr names as `path`) with "**Cannot write to `{that folder}`.** Nothing was changed. Check that the path exists as a folder you can write to and that the disk has free space, then re-run."

Neither halt has a run folder to save stderr in: its heredoc holds the helper's error, or the folder, as displayed, with no `--stderr-from`.

Once the loop passes and `{customization_resolver_unavailable}` is set (SKILL.md On Activation step 3), record the reason in the run sink: write `customization_resolver_unavailable: {customization_resolver_unavailable}` to `{run_dir}/resolver-warning.txt` with a file write, never `echo` (the reason can hold quotes or `$( )`), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"`, and delete that file (`rm -f "{run_dir}/resolver-warning.txt"`), so the report step's `rmdir` still finds the folder empty.

### 2. Read the Skill Roster

Take the roster from `{skillRosterHelper}`, never by eye: it reads the export manifest through the manifest helper (a v1 manifest migrates), scans `{skills_output_folder}` and joins the two:

```bash
uv run {skillRosterHelper} skills "{skills_output_folder}" --forge-data-folder "{forge_data_folder}" 2> "{run_dir}/call.err"
```

- **`code` is `manifest-corrupt`** (the manifest does not parse, or is not a manifest): halt with "**Export manifest is corrupt** at `{path}`: {error}. Fix or remove the file before renaming." HALT (exit code 3, `halt_reason: "manifest-corrupt"`, `emit-halt` phase `select:read-manifest`, with its `path` as `path`).
- **Any other error, or no JSON on stdout** (a helper it reads is missing, the scan failed, or it could not run): HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `select:list-skills`) with "**Rename Skill cannot list the skills:** {its `error`, or the helper's stderr}. Nothing was changed. Re-install SKF, then re-run." An interactive run reads that stderr in `{run_dir}/call.err`.
- **`status` is `ok`**: §3 lists its `skills`. A skill the manifest does not list (a draft, or one never exported) can still be renamed.

### 3. List Available Skills

The roster's `skills` holds only the skills SKF generated: rename copies and then deletes the whole folder, so a folder SKF did not generate is never offered. The §4a rename check decides whether the skill the user picks can move. Bind `{not_skf_output}` ← `not_skf_output` (folders holding a skill SKF did not generate); when it is non-empty, show one line under the list: "Not offered (not SKF output): {not_skf_output}".

**If `empty` is true** (no skill SKF generated):

- When `{old_name_arg}` is set and it is in `{not_skf_output}`, take the §4a refusal for a folder SKF did not generate first, in either mode (exit code 5, `halt_reason: "not-skf-output"`, `emit-halt` phase `select:ownership-check`, with `--old-name "{old_name}"`).
- Otherwise halt with "**Rename Skill: nothing to rename.** No skill SKF generated was found in `{skills_output_folder}/`. Run `[CS] Create Skill` first." When `{not_skf_output}` is non-empty, append: "Left untouched (not SKF output): {not_skf_output}." HALT (exit code 3, `halt_reason: "nothing-to-rename"`, `emit-halt` phase `select:list-skills`).

Display the list only when §4 asks for the skill, one line per entry of `skills` as `{name} ({version_count} versions, active: {active_version})`, with "(not in manifest)" appended when its `in_manifest` is false:

```
**Rename Skill — select target**

Available skills:
1. cognee (3 versions, active: 0.6.0)
2. express (1 version, active: 4.18.0)
3. legacy-helper (not in manifest)

Not offered (not SKF output): my-module-skill
```

### 4. Ask Which Skill

**GATE [default: use args]**: When `{old_name_arg}` is set, it is the input below in either mode, and the question is not shown. Otherwise, in `{headless_mode}`, HALT (exit code 2, `halt_reason: "input-missing"`, `emit-halt` phase `select:ask-old-name`): "headless mode requires old_name argument." Otherwise display the §3 list and ask:

"**Which skill would you like to rename?**
Enter the skill name or its number from the list above, or `cancel` / `exit` / `:q` to abort."

Wait for user input. Accept either the numeric index or the skill name (exact match); `{old_name_arg}` must be a name.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q`: Display "Cancelled: no changes were made." and HALT (exit code 6, `halt_reason: "user-cancelled"`, `emit-halt` phase `select:ask-old-name`).
- **If the input names a folder in `{not_skf_output}`:** take the §4a refusal for a folder SKF did not generate.
- **If the user's input does not match any listed skill:**
  - **Interactive:** say that it matches no listed skill, display the §3 list and ask again.
  - **Headless (`{headless_mode}` is true):** the supplied `old_name` argument matches no listed skill and there is no further input to re-prompt for. HALT (exit code 2, `halt_reason: "input-invalid"`, `emit-halt` phase `select:ask-old-name`): "headless mode: old_name argument `{supplied value}` does not match any listed skill."

Store the selection as `old_name`.

### 4a. Ownership Check

Rename copies the whole `{skills_output_folder}/{old_name}/` folder and its forge folder, then deletes the old ones, so it only renames a skill SKF generated in the versioned layout. The inventory helper decides that; never decide by hand whether SKF generated a folder. Run:

```bash
uv run {skillInventoryHelper} "{skills_output_folder}" --skill {old_name} --rename-check --forge-data-folder "{forge_data_folder}"
```

From its `rename_check`, bind `{rename_verdict}` ← `verdict`, `{rename_reason}` ← `reason`, `{rename_detail}` ← `detail`, `{rename_entries}` ← `offending_entries`, `{target_errors}` ← `errors`, `{forge_move}` ← `forge_move`, `{forge_left_in_place}` ← `forge_left_in_place` and `{same_folder}` ← `same_folder`. The helper applies the rules below in order, to the skill folder and, unless both settings name one folder, to its forge folder, and returns the first that refuses. When the call exits non-zero, or its result has no `rename_check` (an installed `skf-skill-inventory.py` older than the flag), refuse with rule 1.

When `{rename_verdict}` is not `"ok"`, display the message of the rule that applies and HALT (exit code 5, `halt_reason: "{rename_verdict}"`, `emit-halt` phase `select:ownership-check`, with `--old-name "{old_name}"`): `not-skf-output`, or `flat-layout` for rule 4. No lock is held yet (§4b takes it), so the halt releases none.

1. No verdict (a failed call, or no `rename_check`) → `not-skf-output`: "**SKF cannot check that it generated `{old_name}`:** the rename check of `skf-skill-inventory.py` failed, or the installed one has none. Nothing was changed. Re-install SKF and re-run the rename."
2. `{rename_reason}` is `foreign`, `reserved-name` or `absent` (no skill SKF generated at `{skills_output_folder}/{old_name}`) → `not-skf-output`: "**`{old_name}` is not SKF output: nothing was changed.** `{skills_output_folder}/{old_name}/` has no SKF marker in its `metadata.json`, so SKF will not rename it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{old_name}` yourself. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When `{target_errors}` is non-empty (for example, the folder is a link), or the reason is `reserved-name` or `absent`, show `{rename_detail}` in place of the marker sentence.
3. `mixed` → `not-skf-output`: "**`{skills_output_folder}/{old_name}/` also holds entries SKF did not generate:** {rename_entries}. Nothing was changed. Rename moves and then deletes the whole folder, so SKF will not rename it. Move those entries out of the folder and re-run. A version folder with no `metadata.json` can also be one that an interrupted update-skill run left behind; delete it yourself in that case."
4. `flat-layout` → `flat-layout`: "**`{old_name}` still uses the flat layout.** Nothing was changed. Rename works on the versioned layout only: run `@Ferris TS {old_name}` (or US, AS or EX) once to move it into that layout, then re-run the rename."
5. `forge-link`, `forge-not-a-folder` or `forge-unreadable` (the forge folder is a link, is not a folder, or cannot be listed) → `not-skf-output`: "**SKF will not move `{forge_data_folder}/{old_name}`:** {rename_detail}. Nothing was changed." For `forge-link`, add: "SKF never moves or deletes through a link: the copy would take the files from where the link points, and removing the old name or rolling back would empty that folder. Replace the link with the folder it points to, then re-run." Otherwise (the path is not a folder, or SKF cannot list it), add: "Rename moves a forge folder only when it is a folder SKF can read. Move that path out of the way or fix its permissions, then re-run."
6. `forge-mixed` → `not-skf-output`: "**`{forge_data_folder}/{old_name}/` also holds entries SKF did not generate:** {rename_entries}. Nothing was changed. Rename moves and then deletes the whole forge folder, so SKF will not rename it. Move those entries out of the folder and re-run."

When no rule applies, `{forge_move}` and `{forge_left_in_place}` come from the helper. Then continue to §4b.

### 4b. Concurrency Guard

**Skip this section when `{dry_run}` is true:** a dry run writes nothing to the skill, so it takes no lock and never blocks a rename.

Two concurrent rename runs against the same `old_name` would corrupt state mid-copy: one would `rm -rf` the other's freshly-staged new directories, or both would race on the manifest re-key. Take the run lock, a file that names the run holding it. From `{project-root}`, run:

```bash
uv run {runLockHelper} acquire \
    --lock "{forge_data_folder}/.skf-rename-{old_name}.lock" \
    --owner "rename-skill:{old_name}:{run_id}" \
    --stale-after 60 2> "{run_dir}/call.err"
```

The helper creates `{forge_data_folder}` when it is missing.

It prints one JSON line. Dispatch on its exit code:

- **0** (`acquired` true): bind `{lock_owner}` ← `owner`; every renewal and release passes that value. When `stale_replaced` is not null, a run that stopped without releasing its lock left it: display the helper's `message` and record the warning in the run sink, with `an unnamed owner` for a null `held_by` (a lock file an older SKF version wrote):

  ```bash
  uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "run-lock-replaced: {stale_replaced.held_by} since {stale_replaced.held_since}"
  ```

  When `record` exits non-zero, show its message and go on: the warning is advisory.

- **3** (`acquired` false): another rename of `{old_name}` holds a lock that has not gone stale. Display "**Another rename of `{old_name}` is in progress.** {message}", with the helper's `message`, and HALT (exit code 5, `halt_reason: "halted-for-concurrent-run"`, `emit-halt` phase `select:concurrency-guard`, with the lock file as `path`). This run took no lock, so the halt releases none.
- **Any other exit, or no JSON:** HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `select:concurrency-guard`, with the lock file as `path`): "**The run lock could not be taken:** {the `message` the helper printed on stderr}. Nothing was changed." An interactive run reads that stderr in `{run_dir}/call.err`. No lock was taken, so none is released.

### 5. Ask for New Name

**GATE [default: use args]**: When `{new_name_arg}` is set, it is the candidate in either mode, and the question is not shown. Otherwise, in `{headless_mode}`, HALT (exit code 2, `halt_reason: "input-missing"`, `emit-halt` phase `select:ask-new-name`): "headless mode requires new_name argument." Otherwise ask:

"**What is the new name for this skill?**
The new name must be kebab-case: lowercase alphanumeric with hyphens, 1-64 characters, matching the regex `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` (starts and ends with a lowercase letter or digit; a single letter or digit is valid). Or type `cancel` / `exit` / `:q` to abort."

Wait for user input. Trim whitespace.

- If the user enters `cancel`, `exit`, `[X]`, `q`, or `:q`: display "Cancelled: no changes were made." and HALT (exit code 6, `halt_reason: "user-cancelled"`, `emit-halt` phase `select:ask-new-name`).

**Validate the candidate deterministically** with `{renameNameValidator}`, which applies format, length, identity and collision in that order and returns the verdict as JSON:

```bash
uv run {renameNameValidator} \
  --old-name {old_name} --new-name {candidate} \
  --skills-output-folder {skills_output_folder} \
  --forge-data-folder {forge_data_folder} 2> "{run_dir}/call.err"
```

When it prints no JSON, HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `select:validate-new-name`) with "**Rename Skill cannot check the new name:** {the validator's stderr}. Nothing was changed. Re-install SKF, then re-run." An interactive run reads that stderr in `{run_dir}/call.err`.

Read `valid`, `first_failure`, `checks`, `interrupted_rename`, `interrupted_after_rekey` and `leftover_folders`. If `valid` is true, store the input as `new_name` and proceed to §6. When `interrupted_after_rekey` is true, take the recovery halt below the list, in both modes. Otherwise branch on `first_failure`. Interactive: display the message and ask the question above again, also when the candidate came from `{new_name_arg}`. Headless: HALT with the mapped code:

- **`format`** → "**Invalid name format.** The new name must be lowercase alphanumeric with hyphens, starting and ending with a lowercase letter or digit. Try again." (headless HALT: exit code 2, `halt_reason: "input-invalid"`, `emit-halt` phase `select:validate-new-name`)
- **`length`** → "**Invalid name length.** The new name must be 1-64 characters. Try again." (headless HALT: exit code 2, `halt_reason: "input-invalid"`, `emit-halt` phase `select:validate-new-name`)
- **`identity`** → "**The new name is identical to the current name.** Nothing to rename. Try again or abort the workflow." (headless HALT: exit code 2, `halt_reason: "input-invalid"`, `emit-halt` phase `select:validate-new-name`)
- **`collision`** → "**Name collision.** `{new-name}` already exists at: {the `path` of each entry in `checks.collision.locations`}. Pick a different name." When `checks.collision.locations` has a `reserved` entry, say instead: "**Reserved name.** `improvement-queue` is SKF's own folder in `{forge_data_folder}`. Pick a different name." When `interrupted_rename` is true, append: "This may be a stranded partial rename from an earlier interrupted run: `{new_name}` was staged but `{old_name}` was never removed. Confirm the `{new_name}` directories are not a skill you want to keep, then remove `{skills_output_folder}/{new_name}`, and `{forge_data_folder}/{new_name}` only when it holds a copy of `{old_name}`'s forge folder, and re-run this rename." (headless HALT: exit code 5, `halt_reason: "name-collision"`, `emit-halt` phase `select:validate-new-name`)

**Recovery after the manifest re-key.** When `interrupted_after_rekey` is true, an earlier rename of `{old_name}` to `{new_name}` stopped between its manifest re-key and its delete, and `leftover_folders` lists the old folders it left. Re-asking would invite a third name and a second copy of the skill, so in both modes display "**An earlier rename of `{old_name}` to `{new_name}` stopped after it moved the export manifest to `{new_name}`.** `{new_name}` is the renamed skill, and these old folders are still on disk: {leftover_folders}. Nothing was changed. If `{old_name}` is not a skill you want to keep, finish that rename: delete them with SKF's checked delete, `uv run {skillInventoryHelper} guarded-delete --root "{skills_output_folder}" --root "{forge_data_folder}" {each path in leftover_folders, quoted}`, then run `[EX] Export Skill` to rebuild the context files that may still name `{old_name}`." and HALT (exit code 5, `halt_reason: "name-collision"`, `emit-halt` phase `select:validate-new-name`).

### 6. Source Authority Check

Take `source_authority` from the `metadata.json` of the version `resolve` picks (the manifest's `active_version`, or the `active` link's when the manifest lags it), never by opening the file:

```bash
uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {old_name} --forge-data-folder "{forge_data_folder}"
```

From its `resolve` object bind `{source_authority}` ← `source_authority` (null when that version has no `metadata.json`, or the file gives no such string). When the call fails, treat `source_authority` as absent.

**If `source_authority == "official"`:**

Display the warning:

```
⚠️  **source_authority: "official"**
This skill has `source_authority: "official"`. Renaming locally will diverge from any
published skill at agentskills.io under this name. Consumers fetching from the
registry will still get the original name. Rename is a LOCAL operation only — it
does not rename anything at the registry.
```

**GATE [default: HALT in headless]**: When `{acknowledge_official}` is true, `--acknowledge-official` answers this warning for this run in either mode: proceed without asking. Otherwise, in `{headless_mode}`, proceed only when `{forceSourceAuthorityInHeadless}` is true; when it is not, HALT (exit code 5, `halt_reason: "source-authority-blocked"`, `emit-halt` phase `select:source-authority`) with "**`{old_name}` is an official skill** (its `source_authority` is `official`). Nothing was changed. To rename it in a headless run, pass `--acknowledge-official` with the invocation, or set `force_source_authority_in_headless = "true"` under `[workflow]` in `{project-root}/_bmad/custom/skf-rename-skill.toml` (or `.user.toml`) to approve every headless rename of an official skill." Otherwise ask: "**Continue anyway?** [Y/N] (or `cancel` / `exit` / `:q` to abort)"

Wait for response.
- **If `N`** (or `cancel` / `exit` / `[X]` / `:q`) → display "**Cancelled.** No changes were made." and HALT (exit code 6, `halt_reason: "user-cancelled"`, `emit-halt` phase `select:source-authority`).
- **If `Y`** → proceed.

**Record a headless pass.** When `{headless_mode}` is true and the run proceeded past the warning, record the decision in the run sink, with `{source_authority_reason}` ← `--acknowledge-official flag` when `{acknowledge_official}` is true, else `force_source_authority_in_headless override`. From `{project-root}`:

```bash
cat > "{run_dir}/decision.json" <<'SKF_DECISION'
{"gate": "source-authority", "default_action": "halt", "taken_action": "proceed", "reason": "{source_authority_reason}"}
SKF_DECISION
uv run {emitEnvelopeHelper} record --workflow skf-rename-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json" 2> "{run_dir}/call.err"
```

When `record` exits non-zero, the decision cannot reach the audit trail: HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `select:source-authority`) with its message, which an interactive run reads in `{run_dir}/call.err`.

**If `source_authority` is absent, or any value other than `"official"`:** skip the warning and proceed.

### 7. Enumerate Affected Versions

Enumerate every version the rename must touch, the manifest's and the ones on disk, through the `affected-versions` action of `{manifestOpsHelper}`:

```bash
uv run {manifestOpsHelper} {skills_output_folder} affected-versions {old_name} 2> "{run_dir}/call.err"
```

Store `affected_versions` = `result.affected_versions` (newest first) and `affected_versions_count` = `result.count`. When it prints no JSON, or its `status` is not `"ok"`, HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `select:affected-versions`) with "**Rename Skill cannot list the versions of `{old_name}`:** {its `error`, or the helper's stderr}. Nothing was changed." An interactive run reads that stderr in `{run_dir}/call.err`.

Also bind the four outer paths, each absolute and without a trailing `/`:

- `old_skill_group` = `{skills_output_folder}/{old_name}`
- `new_skill_group` = `{skills_output_folder}/{new_name}`
- `old_forge_group` = `{forge_data_folder}/{old_name}`
- `new_forge_group` = `{forge_data_folder}/{new_name}`

### 7b. Predict the Verification

Step 2 §5 rolls the rename back when `{old_name}` stays where it must not. Check that now, before anything is copied: with `--predict`, `{rewriteSkillNameHelper}` applies step 2 §2's rewrite to `{old_skill_group}` in memory, writes nothing, and runs step 2 §5's scan on the result. From `{project-root}`:

```bash
uv run {rewriteSkillNameHelper} --predict --skill-group "{old_skill_group}" \
  --versions {comma-separated affected_versions} \
  --old-name {old_name} --new-name {new_name} --moved-folder "{skills_output_folder}" \
  [--forge-group "{old_forge_group}" --moved-folder "{forge_data_folder}"] 2> "{run_dir}/call.err"
```

Pass the bracketed group only when `{forge_move}` or `{same_folder}` is true, as step 2 §2 does.

- **`status` is `ok` and `clean` is true:** go on to §8.
- **`status` is `ok` and `clean` is false:** display "**Renaming `{old_name}` would leave its old name in:** {each `hard_matches` entry as `{file}` line {line}: `{text}`}. Nothing was changed. Where a line is a note an earlier run wrote, or a `context-snippet.md` line such as `|gotchas:`, edit it in that file, then re-run. Where it names the library or repository the skill is named after (a `description`, an export, a source path), or `{old_name}` is a word of the snippet template itself, such as `api`, `root` or `data`, the skill cannot be renamed: create it again as `{new_name}` with `[BS] Brief Skill` and `[CS] Create Skill`. The troubleshooting guide's `verify-failed` entry has the details." and HALT (exit code 5, `halt_reason: "verify-failed"`, `emit-halt` phase `select:predict-verify`), in a dry run too.
- **`status` is `error`, or no JSON on stdout:** HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `select:predict-verify`) with "**Rename Skill cannot check the rename:** {its `error.message` at `{error.path}`, or the helper's stderr}. Nothing was changed. Fix the file or folder it names, or re-install SKF when the error names a helper, then re-run." An interactive run reads that stderr in `{run_dir}/call.err`.

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
  Copies installed in your IDE skill folders (`npx skills add`) are not renamed;
  unless `snippet_skill_root_override` is set, the report names any it finds.

Operation is **transactional**: the new name will be fully materialized and verified
before the old name is removed. If a step fails up to the manifest re-key, the new
directories are removed and the old skill remains intact. A context file that fails
to rebuild afterwards is reported and never undoes the rename.

Proceed? [Y/N]
```

**If `{dry_run}` is true**, which takes precedence over the headless auto-confirm below: skip the Y/N prompt entirely and display "**[DRY RUN] No changes were made: the preview above shows what would be renamed.**" The dry run took no lock (§4b), so it releases none. In `{headless_mode}`, emit the dry-run envelope on **stdout**. From `{project-root}`:

```bash
cat > "{run_dir}/result-context.json" <<'SKF_RESULT'
{"status": "dry-run", "old_name": "{old_name}", "new_name": "{new_name}", "versions_renamed": <affected_versions as a JSON array>, "manifest_rekeyed": false, "context_files_updated": [], "halt_reason": null}
SKF_RESULT
uv run {emitEnvelopeHelper} emit --workflow skf-rename-skill --run-dir "{run_dir}" < "{run_dir}/result-context.json"
```

Without `--result-dir` it writes no result file. It prints the complete line, `SKF_RENAME_SKILL_RESULT_JSON: {"status":"dry-run","old_name":"{old_name}","new_name":"{new_name}","versions_renamed":[<affected_versions>],"manifest_rekeyed":false,"context_files_updated":[],"exit_code":0,"halt_reason":null,"headless_decisions":[<the §6 source-authority decision, when it fired>],"run_id":"{run_id}","result_path":null}` (with `warnings` after `headless_decisions` when the run recorded one). When it exits non-zero or prints no line, display its error, keep `{run_dir}` and say in one line that it holds the run's decisions, its warnings and the payload the emitter refused. Otherwise, in both modes, delete the run folder:

```bash
rm -f "{run_dir}/result-context.json" "{run_dir}/decision.json" "{run_dir}/headless-decisions.jsonl" "{run_dir}/warnings.jsonl" "{run_dir}/call.err" && rmdir "{run_dir}"
```

Then, in a headless run, display the line the emitter printed verbatim, after the delete and with nothing after it, so a `claude -p` caller reads it as the final message. In both modes, and whether or not the emitter printed a line, the dry run then ends with exit code 0: no copy, no manifest re-key, no delete.

**GATE [default: Y]**: Otherwise (not a dry run), if `{headless_mode}`: auto-proceed with [Y] (log line: "headless: auto-confirmed rename {old_name} → {new_name}") and record `{"gate": "confirm-rename", "default_action": "proceed", "taken_action": "proceed", "reason": "headless auto-confirm"}` in the run sink with §6's two commands, staged as `{run_dir}/decision.json`; when `record` exits non-zero, HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `select:confirm`) with its message, which an interactive run reads in `{run_dir}/call.err`.

Wait for explicit user response.

- **If `Y`** → proceed to section 9
- **If `N`** (or `cancel` / `exit` / `[X]` / `:q`) → display "**Cancelled.** No changes were made." and HALT (exit code 6, `halt_reason: "user-cancelled"`, `emit-halt` phase `select:confirm`).
- **Any other input** → re-display the confirmation and ask again

### 9. Store Decisions in Context

Step 2 reads the decisions this step bound where it made them: `run_dir` (§1), `old_name` (§4), `forge_move`, `forge_left_in_place` and `same_folder` (§4a), `lock_owner` (§4b), `new_name` (§5), and `affected_versions`, `old_skill_group`, `new_skill_group`, `old_forge_group` and `new_forge_group` (§7). The run's auto-decisions stay in `{run_dir}`, where each gate recorded them for the emitter.

### 10. Load Next Step

Load, read the full file, and then execute `{nextStepFile}`.

