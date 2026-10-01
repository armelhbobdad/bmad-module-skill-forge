---
nextStepFile: 'report.md'
# §0 resolves each helper below from its probe order (installed SKF module
# path first, src/ dev-checkout fallback; the first existing path wins).
# {atomicWriteHelper}: the §4 `flip-link` and the §6 manifest restore.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# {manifestOpsHelper}: the §6 re-key.
manifestOpsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py'
  - '{project-root}/src/shared/scripts/skf-manifest-ops.py'
# {rebuildManagedSectionsHelper}: the §7 context-file rebuild.
rebuildManagedSectionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py'
  - '{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py'
# {rewriteSkillNameHelper}: the §3 in-file rename, one file per call.
rewriteSkillNameProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rewrite-skill-name.py'
  - '{project-root}/src/shared/scripts/skf-rewrite-skill-name.py'
# {verifyNoTraceHelper}: the §5 no-trace commit gate.
verifyNoTraceProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-no-trace.py'
  - '{project-root}/src/shared/scripts/skf-verify-no-trace.py'
# {skillInventoryHelper}: the §8 guarded delete.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# {runLockHelper} and {emitEnvelopeHelper}: bound since step 1 §1.
runLockProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py'
  - '{project-root}/src/shared/scripts/skf-run-lock.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Execute Rename (Transactional)

## STEP GOAL:

Execute the rename decisions recorded in step 1 as a transaction. Copy the old `{skill_group}` and, when step 1 set `{forge_move}`, `{forge_group}` to the new name, rename inner directories, rewrite every in-file reference, verify no trace of the old name remains inside the new location, update the export manifest, rebuild platform context files, and only then delete the old directories. A failure in sections 1 to 6 rolls back by removing the new directories, so the old skill remains intact; the context-file rebuild in section 7 is best-effort and never rolls back.

## Rules

- Execute sections strictly in order — each section depends on the previous one
- Do not re-prompt the user — decisions were made in step 1
- Do not delete anything from old directories before section 8
- Do not proceed past a verification failure in section 5
- Report each section's outcome as it completes

**Halt procedure.** Every HALT below names, in parentheses, its exit code, its `halt_reason` and the phase its `emit-halt` reports (see `references/exit-codes.md`). After its rollback, when it has one, it runs these, in order, before it stops:

1. Release the run lock step 1 §4b took (a release never removes a lock another run holds). From `{project-root}`:

   ```bash
   uv run {runLockHelper} release --lock "{forge_data_folder}/.skf-rename-{old_name}.lock" --owner "{lock_owner}"
   ```

   When it exits non-zero or prints no JSON, tell the user in one line that the lock file stays, and add `"warnings": ["run-lock-not-released: {forge_data_folder}/.skf-rename-{old_name}.lock"]` to the payload below.

2. In `{headless_mode}`, pass the halt to the shared emitter, which prints its envelope on **stderr** with the decisions and warnings the run recorded, step 1's included. Write each string as JSON (escape `"`, `\` and control characters, and write every path with `/`):

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-rename-skill --run-dir "{run_dir}" --target stderr <<'SKF_HALT'
   {"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the message the halt displays>", "path": "<the path the halt names; leave the key out when it names none>", "old_name": "{old_name}", "new_name": "{new_name}"}
   SKF_HALT
   ```

   Display the `SKF_RENAME_SKILL_RESULT_JSON:` line it prints verbatim. When it exits non-zero and its `message` names the payload, fix the payload once and run it again. Only when `{emitEnvelopeHelper}` is missing, or the emitter still fails or prints no line, display the halt's message alone.

The halt leaves `{run_dir}` in place.

## MANDATORY SEQUENCE

**Transactional boundary.** After section 1 (copy), the old skill is untouched; a failure in any of sections 2-6 deletes the new skill folder and, when `{forge_move}` is true, the new forge folder, reports, and halts with the old skill intact. Section 7 (context-file rebuild) is best-effort and never rolls back: by then the manifest and the skill folders are consistent under the new name, so a context file that fails to rebuild is recorded in `context_files_failed`, `{new_skill_group}` stays, and the rename goes on. Section 8 (delete old) is the only irreversible point.

### 0. Resolve Helpers

**Resolve helpers** in parallel: these are independent file-existence checks that batch into one tool-call message.

- `{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` (used in §4 and §6)
- `{rewriteSkillNameHelper}` ← first existing path in `{rewriteSkillNameProbeOrder}` (used in §3)
- `{verifyNoTraceHelper}` ← first existing path in `{verifyNoTraceProbeOrder}` (used in §5)
- `{manifestOpsHelper}` ← first existing path in `{manifestOpsProbeOrder}` (used in §6)
- `{rebuildManagedSectionsHelper}` ← first existing path in `{rebuildManagedSectionsProbeOrder}` (used in §7)
- `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` (used in §8)
- `{runLockHelper}` and `{emitEnvelopeHelper}`: bound since step 1 §1 (when a binding was lost, ← first existing path in `{runLockProbeOrder}` and `{emitEnvelopeProbeOrder}`)

If any helper has no existing candidate, HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `execute:resolve-helpers`) before anything is copied: no section does a helper's write, transform or check by hand.

### 1. Copy skill_group and forge_group

**Renew the run lock first.** A run that waited at a step 1 gate past 60 minutes may have lost it to another rename; an acquire by its owner renews it. From `{project-root}`, run:

```bash
uv run {runLockHelper} acquire \
    --lock "{forge_data_folder}/.skf-rename-{old_name}.lock" \
    --owner "{lock_owner}" \
    --stale-after 60
```

- **Exit 0 with `refreshed` true:** the lock is still this run's, now renewed; continue.
- **Exit 0 with `refreshed` false, or exit 3:** this run's lock lapsed while it waited, so another rename of `{old_name}` may have run since step 1 checked the names. Display "**This rename of `{old_name}` lost its run lock while it waited.** Nothing was changed. Run the rename again{on exit 3: ' once the other run ends. {message}', with the helper's `message`}." and HALT (exit code 5, `halt_reason: "halted-for-concurrent-run"`, `emit-halt` phase `execute:run-lock`, with the lock file as `path`) before anything is copied.
- **Any other exit, or no JSON:** HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `execute:run-lock`, with the lock file as `path`) before anything is copied: "**The run lock could not be renewed:** {the `message` the helper printed on stderr}. Nothing was changed."

**Precondition:** Both `{new_skill_group}` and `{new_forge_group}` must NOT exist (step 1 validated this in the collision check, but verify again before copying).

1. If `{new_skill_group}` or `{new_forge_group}` exists on disk (a file or link counts): halt with "**Collision detected at execution time.** `{new_skill_group}` or `{new_forge_group}` now exists on disk; it did not exist during step 1 selection. Aborting before any files are touched." HALT (exit code 4, `halt_reason: "copy-failed"`, `emit-halt` phase `execute:copy`).

2. Copy `{old_skill_group}` to `{new_skill_group}`, naming both without a trailing `/`, as `cp -a {old_skill_group} {new_skill_group}` does. §4a refused a linked skill folder and one holding a linked version, so the only link the copy can meet is `active`. The copy carries it as a link, or as a copy of the folder it points to in a shell that cannot create links; §4 creates `{new_skill_group}/active` again either way.
   - If the copy fails: halt with "**Copy failed:** `{old_skill_group}` → `{new_skill_group}`: {error}. No files were modified. Old skill is intact." HALT (exit code 4, `halt_reason: "copy-failed"`, `emit-halt` phase `execute:copy`).

3. Only when `{forge_move}` is true, copy `{old_forge_group}` to `{new_forge_group}` the same way. If the copy fails: **rollback** by deleting `{new_skill_group}` and whatever the copy created at `{new_forge_group}` (§1.1 confirmed nothing was there), then halt with "**Copy failed:** `{old_forge_group}` → `{new_forge_group}`: {error}. Rolled back the new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "copy-failed"`, `emit-halt` phase `execute:copy`). When `{forge_move}` is false, skip this copy: the forge folder is absent, left in place (`{forge_left_in_place}`), or, with `{same_folder}`, already copied with the skill folder.

**Rollback procedure for this section:** `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`. Old skill is untouched.

Report: "**Copied** `{old_skill_group}` → `{new_skill_group}`{if forge_move: ' and `{old_forge_group}` → `{new_forge_group}`'}." Name only what was copied.

### 2. Rename Inner Version Directories

For each version `v` in `affected_versions`: when `{new_skill_group}/{v}/{old_name}/` exists, move it within its parent, `mv {new_skill_group}/{v}/{old_name} {new_skill_group}/{v}/{new_name}`, and add `v` to `renamed_versions`. When it does not (a manifest version with no folder, or a version folder an interrupted run left without a package), add a warning to `section2_warnings` and skip the version: an absent package is not a failure, and §5 verifies only `renamed_versions`. Only a failed `mv` takes the rollback below.

**Rollback on a failed move:**

- `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`
- Halt with: "**Inner directory rename failed** at `{v}/{old_name}`: {error}. Rolled back the new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `execute:inner-rename`).

Report: "**Renamed {count} inner directories** to `{new_name}/`."

### 3. Update File Contents Inside the New Location

For each version `v` in `affected_versions`, operate on the files inside `{new_skill_group}/{v}/{new_name}/` (the freshly renamed inner directory) and, only when `{forge_move}` or `{same_folder}` is true, `{new_forge_group}/{v}/`.

**One helper call per file (3a to 3d).** `{rewriteSkillNameHelper}` rewrites the name in one file and writes it atomically. Never compute file content in the prompt: a hand edit can reorder JSON keys, or rewrite the wrong place when `{old_name}` is part of a longer name (`rename` in `renamer`). Invoke it once per file:

```bash
uv run {rewriteSkillNameHelper} "{target_path}" \
  --kind {skill-frontmatter|metadata-json|context-snippet|provenance-json} \
  --old-name {old_name} --new-name {new_name} [--moved-folder "{folder}"]
```

**Moved folders (3b and 3d only).** Pass `--moved-folder "{skills_output_folder}"`, and also `--moved-folder "{forge_data_folder}"` when `{forge_move}` or `{same_folder}` is true: those are the folders this rename moves `{old_name}/` out of. A forge folder left in place keeps its name, so paths into it stay as they are.

Check that the target file exists first: a missing file is not a failure, so skip the call and record the file in `section3_warnings`. On exit 0, when its `wrote` is not null, add `{kind, path}` (the `--kind` and the `wrote` path) to `files_rewritten`, the record step 3 counts and lists the rewritten files from. A non-zero exit is a **file update failure**: take the rollback below.

**3a. SKILL.md frontmatter**: `--kind skill-frontmatter` on `{new_skill_group}/{v}/{new_name}/SKILL.md`. It rewrites the frontmatter `name` only: a mention of `{old_name}` in the body stays.

**3b. metadata.json**: `--kind metadata-json` on `{new_skill_group}/{v}/{new_name}/metadata.json`, with the moved folders above. It sets `name` and points the paths into the moved folders at `{new_name}`; the values that name the upstream source stay.

**3c. context-snippet.md**: `--kind context-snippet` on `{new_skill_group}/{v}/{new_name}/context-snippet.md`. It rewrites the name where SKF's snippet template writes it: the header, the `|IMPORTANT:` line and each `root:` path. Nothing else in the snippet changes: a name anywhere else stays, §5 reports it and the rename rolls back rather than commit a changed snippet.

**3d. provenance-map.json**: `--kind provenance-json` on `{new_forge_group}/{v}/provenance-map.json`. It sets `skill_name` and, with the moved folders above, points the paths into them at `{new_name}` as 3b does. Skip 3d when `{forge_move}` and `{same_folder}` are both false: there is no SKF forge folder to rewrite.

**Rollback on any update failure (not just a missing file):**

- `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`
- Halt with: "**File update failed** at `{path}`: {error}. Rolled back the new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `execute:rewrite`).

Report: "**Updated file contents:** {each file name `files_rewritten` holds, with the number of its entries, for example 'SKILL.md ×3, metadata.json ×3'}." Name only what `files_rewritten` holds, counted from it, never from the version count.

### 4. Fix the `active` Symlink in the New Location

The §1 copy carries `{old_skill_group}/active` into `{new_skill_group}` as it found it: an absolute link, or a relative one that climbs out of the skill folder, still points into `{old_skill_group}`, which §8 deletes, and a shell that cannot create links may have copied the folder. So this section removes whatever the copy made at `{new_skill_group}/active` and creates the link again with the `flip-link` action of `{atomicWriteHelper}`, the call create-skill, quick-skill and create-stack-skill use; it refuses to replace an `active` that is a real folder, so remove the copied entry first. Never create the link with `ln -s`: Git Bash on Windows without symlink rights writes a copy of the folder instead. `{new_skill_group}` is this run's own copy, which no manifest entry or context file names until §6 and §7, so removing the copied entry before the flip is safe.

1. If nothing is at `{old_skill_group}/active`, not even a broken link (`[ ! -e "{old_skill_group}/active" ] && [ ! -L "{old_skill_group}/active" ]`), skip to the report at the end of this section: there is no link to carry over.
2. If `{old_skill_group}/active` is not a link (`[ ! -L "{old_skill_group}/active" ]`), take the rollback below with the reason: "`{old_skill_group}/active` is a real folder or file, not a link. Check that it only copies a version folder, remove it and re-run the rename, then point the renamed skill's link at a version with `uv run {atomicWriteHelper} flip-link --link "{new_skill_group}/active" --target <version>`."
3. Read the link. Set `{old_active_link}` to what the first line prints, the link text as stored, and `{target_version}` to what the second line prints, its last path component:

   ```bash
   readlink "{old_skill_group}/active"
   basename "$(readlink "{old_skill_group}/active")"
   ```

   For an `{old_active_link}` of `0.6.0`, of `{old_skill_group}/0.6.0`, or of a relative path that climbs out of the skill folder and back into its `0.6.0` folder, `{target_version}` is `0.6.0`.
4. If `{target_version}` is not one of `renamed_versions` (§2), the link does not name a version folder holding the package this rename moved: it is broken, or it names a folder §2 skipped. Take the rollback below with the reason: "`{old_skill_group}/active` points at `{old_active_link}`, which is not one of the versions this rename moved ({renamed_versions}). Point it at one of them with `uv run {atomicWriteHelper} flip-link --link "{old_skill_group}/active" --target <version>`, or remove it, then re-run the rename."
5. Remove what the copy made at `{new_skill_group}/active`. A link is removed as a link, so nothing it points to is touched; only a real folder, which the copy made from the link, is removed with its contents:

   ```bash
   if [ -L "{new_skill_group}/active" ]; then rm -f "{new_skill_group}/active"
   elif [ -e "{new_skill_group}/active" ]; then rm -rf "{new_skill_group}/active"
   fi
   ```

6. Create the link:

   ```bash
   uv run {atomicWriteHelper} flip-link \
     --link "{new_skill_group}/active" \
     --target "{target_version}"
   ```

   On exit 0, bind `{active_link_kind}` ← `kind` (`symlink` or `junction`) from the JSON it prints on stdout. On any other exit, bind `{flip_error}` ← `message` from the `{"status": "error", "message": …}` line it prints on stderr, or set it to the helper's whole stderr when there is no such line, and take the rollback below with `{flip_error}` as the reason.

**Rollback on a failure in step 2, 4 or 6:**

- `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`
- Halt with: "**Failed to repair the `active` link** in `{new_skill_group}`: {reason}. Rolled back the new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `execute:active-link`).

Report: "**`active` link:** `{new_skill_group}/active` → `{target_version}` ({active_link_kind}).{if `{old_active_link}` is not `{target_version}`: ' Repointed from `{old_active_link}`.'}" When step 1 skipped this section: "**`active` link:** none in `{old_skill_group}`, nothing to carry over."

### 5. Verify — No Trace of `{old_name}` Inside the New Location

This is the commit-point check: if any structural reference to `{old_name}` remains, the rename is not safe to commit. Invoke `{verifyNoTraceHelper}` once:

```bash
uv run {verifyNoTraceHelper} "{new_skill_group}" \
  --forge-group "{new_forge_group}" \
  --old-name {old_name} --new-name {new_name} \
  --versions {comma-separated renamed_versions}
```

It scans each renamed version's SKILL.md, metadata.json, context-snippet.md and provenance-map.json and the version's folder listing, and returns `clean`, `hard_matches` (the old name where it must not stay), `body_warnings` (mentions in a SKILL.md body, which stay) and `dir_violations`. A value that names the upstream source never counts, since §3 leaves it unchanged, and a missing file is listed under `skipped`, never as a match. Exit 0 = clean; exit 1 = at least one hard match or dir violation.

Read the JSON and decide. An exit code of 2 with no JSON on stdout (the helper refuses an empty `--versions` list) counts as `clean` false: take the rollback below.

- **If `clean` is `true` (empty `hard_matches` AND empty `dir_violations`):** the rename is safe to commit. Set `verification_warnings` = the returned `body_warnings` (informational SKILL.md body mentions of `{old_name}` that are retained). Proceed.
- **If `clean` is `false`:** this is a hard failure —
  - `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`
  - Halt with: "**Verification failed.** `{old_name}` still appears in: {the files from `hard_matches` plus any `dir_violations`}. Rolled back the new directories. Old skill is intact." HALT (exit code 5, `halt_reason: "verify-failed"`, `emit-halt` phase `execute:verify`).

Report: "**Verified:** no structural references to `{old_name}` remain inside the new location across the {number of `renamed_versions`} version(s) it checked. {if verification_warnings is non-empty: 'Informational body-text mentions retained in SKILL.md: {list}.'}"

### 6. Update Export Manifest

**If `manifest_exists = false` (step 1 read no entry in the manifest):**

Skip this section entirely. Set `manifest_rekeyed = false` and `manifest_backup = null`. There is no manifest entry to re-key: the skill was never exported. Section 7 still rebuilds any managed section it finds, which drops a row of `{old_name}` if one is there.

Report: "**Manifest update skipped:** the export manifest has no entries. The rename is a pure on-disk operation."

**If `manifest_exists = true`:**

1. **Keep the manifest's text** as `manifest_backup` for the rollback below: read `{skills_output_folder}/.export-manifest.json` once and hold its exact text, not a parsed or re-serialized copy, so a restore writes back the same bytes.
2. **Re-key via the helper.** If the manifest contains `exports.{old_name}`, invoke:

   ```bash
   uv run {manifestOpsHelper} {skills_output_folder} rename {old_name} {new_name}
   ```

   The helper preserves `active_version`, `versions` map, and all fields, then writes the manifest atomically via temp + rename. It prints its result as JSON on stdout, errors included, and exits 0 only when `status` is `"ok"`. On a non-zero exit, bind `{manifest_error}` ← `error` and `{manifest_status}` ← `status`. A `not_found` result carries no `error`, because `exports.{old_name}` left the manifest after the check above: when `{manifest_status}` is `not_found`, set `{manifest_error}` to "`exports.{old_name}` is no longer in the manifest". When stdout holds no JSON (a Python traceback), set `{manifest_error}` to the helper's stderr. If the manifest does NOT contain `exports.{old_name}` (the skill was on disk but never exported), skip the invocation — the manifest has nothing to change.

**Rollback on helper non-zero exit:**

- Read the manifest again. The helper writes it in one rename at its very end, so the only change a failed re-key can leave is the finished re-key. Only when `exports.{new_name}` is there and `exports.{old_name}` is gone, restore the backup, pasting `manifest_backup` unchanged between the two heredoc lines:

  ```bash
  uv run {atomicWriteHelper} write --target "{skills_output_folder}/.export-manifest.json" <<'SKF_MANIFEST_BACKUP'
  {manifest_backup}
  SKF_MANIFEST_BACKUP
  ```

  Set `{manifest_restore}` to `restored` when it exits 0, else to `restore-failed`. In every other state (`exports.{old_name}` still there, `exports.{new_name}` absent, or a manifest that is missing or does not parse), this run did not change the manifest, and another process may have written it since step 1: set `{manifest_restore}` to `unchanged` and write nothing.
- `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`
- Halt with: "**Manifest update failed:** {manifest_error}. {if `{manifest_restore}` is `unchanged`: 'This run did not change the manifest.'}{if `restored`: 'Restored the manifest from the backup.'}{if `restore-failed`: 'Could not restore the manifest, which may still list `{new_name}` in place of `{old_name}`: re-key it back with `uv run {manifestOpsHelper} "{skills_output_folder}" rename {new_name} {old_name}`.'} Rolled back the new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "manifest-write-failed"`, `emit-halt` phase `execute:manifest`).

Set context flag `manifest_rekeyed = true` when the helper ran and exited 0, else `false` (no `exports.{old_name}` to re-key).

Report: "**Manifest updated:** re-keyed `exports.{old_name}` → `exports.{new_name}`." When it skipped the call: "**Manifest unchanged:** it has no `exports.{old_name}` entry."

### 7. Rebuild Context Files

After §6 re-keys the manifest from `{old_name}` to `{new_name}`, every IDE's context file (`CLAUDE.md`, `.cursorrules`, `AGENTS.md`, etc.) still carries the old name in its managed-section rows. This section rebuilds each one through `{rebuildManagedSectionsHelper}` (resolved in §0), the way export-skill writes it. It runs only on the success path: the §1 to §6 rollbacks never reach here. It is best-effort: nothing here halts or rolls back the rename.

**7a. Resolve the context files.** Map the `ides` list of `config.yaml` (an absent key is an empty list) through the IDE mapping export-skill writes the section with:

```bash
python3 {rebuildManagedSectionsHelper} resolve-targets --ides "{ides}"
```

`{ides}` is the comma-joined list. Store `targets` as `target_context_files` (one `{context_file, skill_root, ides}` entry per file; an IDE the mapping does not list, and an empty list, resolve to AGENTS.md with `.agents/skills/`), and show each `warnings[]` and `notes[]` line. When the helper exits non-zero, rebuild nothing: leave `context_files_updated` empty, set `context_files_failed` to the one entry `all context files: resolve-targets failed: {error}` (the helper's stderr when stdout holds no JSON), and go to §7c.

A target's file is `{context_path}`, its `{context_file}` in `{project-root}`, and `{target_paths}` is the `{context_path}` of every target, each quoted, space-separated, in the order of `target_context_files`.

**7b. Per-file loop.** For each entry in `target_context_files`:

1. **Check the file.**

   ```bash
   python3 {rebuildManagedSectionsHelper} "{context_path}" check
   ```

   Its `case` decides. `create` (no file) or `append` (no managed section): skip this file, since there is no section to rebuild (export-skill adds one on its next run). `malformed` or `unreadable`: bind `{context_error}` ← `error` and take item 4. `regenerate`: continue.

2. **Build the section body.**

   ```bash
   python3 {rebuildManagedSectionsHelper} assemble "{context_path}" \
     --skills-folder "{skills_output_folder}" --skill-root "{skill_root}" \
     --renamed {old_name}:{new_name} --orphan-sources {target_paths} \
     [--skill-root-override "{snippet_skill_root_override}"]
   ```

   Add `--skill-root-override` only when `snippet_skill_root_override` is set in `config.yaml`. The helper builds the body export-skill would write for the re-keyed manifest, with the rows of skills the manifest does not know (orphan rows) kept verbatim; `--renamed {old_name}:{new_name}` keeps the renamed skill's old rows from staying as orphan rows. It writes the body to `{context_path}.skf-content` and prints its result as JSON: show each `warnings[]` line and each `skipped_*` entry as a warning. On a non-zero exit, bind `{context_error}` ← `error` and take item 4.

3. **Replace the section.** Feed the staged body to the helper on stdin. Never pass the body inline as `--content "…"` or through `echo`: the shell would expand the backticks and `$` the snippets carry.

   ```bash
   python3 {rebuildManagedSectionsHelper} "{context_path}" replace < "{context_path}.skf-content"
   ```

   Delete `{context_path}.skf-content` once the helper returns, whatever its exit code. It refuses a body that holds a marker of its own, and then leaves the file unchanged. It exits 0 only when the `status` of its JSON is `"ok"`. On a non-zero exit, bind `{context_error}` ← `error`, or the helper's stderr when stdout holds no JSON.

4. **On per-file failure**, record `{context_error}` against that context file and continue to the next entry. Do not halt the rename on a per-context-file error: the manifest and filesystem are already consistent, so the context files can be rebuilt later with `[EX] Export Skill`.

**7c. After the loop**, record:

- `context_files_updated` — list of files successfully rewritten
- `context_files_failed` — list of any that failed

Report: `**Rebuilt managed sections in:** {list of updated files}. {if any failed: 'Failed: {list} — re-run [EX] Export Skill to retry.'}` Then proceed to §8.

**Note:** §7 failures do not trigger a rollback, and never delete `{new_skill_group}`. Platform context files are derived artifacts; the manifest and on-disk skill directories are the canonical state.

### 8. Delete Old Directories (Point of No Return)

This is the only section after which rollback is impossible. Precondition: §1–7 have fully materialized and verified the new name (the new directories renamed, no `{old_name}` references remaining, manifest re-keyed, context files rebuilt best-effort) — only now is deleting the old name safe.

Delete the old folders through the guarded delete of `{skillInventoryHelper}` (resolved in §0), never by hand, with the skills folder and the forge folder as the only folders it may delete inside:

```bash
uv run {skillInventoryHelper} guarded-delete --root "{skills_output_folder}" --root "{forge_data_folder}" "{old_skill_group}"
```

Only when `{forge_move}` is true, add `"{old_forge_group}"` after `"{old_skill_group}"`. Otherwise the forge folder stays: `{forge_left_in_place}` keeps its name, and with `{same_folder}` the skill folder is the forge folder. The helper removes any trailing `/`, deletes only a plain folder inside a root that no link or junction leads to (SKF never deletes through a link), and checks that each one is gone. Bind `deletion_errors` ← `delete_failures` (each `{path, error}`). On a non-zero exit, or no JSON on stdout, record the helper's `error` (its stderr when stdout holds no JSON) against each path in `deletion_errors`.

**On deletion error:**

- Do NOT attempt any rollback — the new name is already committed and the old name's remnants can be removed manually

Report: "**Deleted old directories:** `{old_skill_group}`{if forge_move: ' and `{old_forge_group}`'}. {if deletion_errors is non-empty: 'Errors: {list} — remove manually with `rm -rf {path}`.'}"

### 9. Store Results in Context

Store the following for step 3:

- `old_name`: the previous skill name
- `new_name`: the new skill name
- `affected_versions`: every version step 1 §7 listed, the version folders §1 copied, including any whose package §2 skipped
- `renamed_versions`: the versions whose package §2 renamed, the versions the rename moved; the envelope's `versions_renamed`
- `files_rewritten`: the `{kind, path}` of every file a §3 helper call wrote; step 3 counts each kind from it and lists the paths in the result file
- `manifest_rekeyed`: true only when section 6 ran the re-key and the helper exited 0
- `context_files_updated`: list of successfully rebuilt files
- `context_files_failed`: list of files that failed to rebuild (empty if none)
- `section2_warnings`: list of orphaned version warnings (empty if none)
- `section3_warnings`: list of missing file warnings (empty if none)
- `verification_warnings`: list of informational SKILL.md body mentions of `{old_name}` retained (empty if none)
- `deletion_errors`: list of post-commit deletion errors (empty if none)
- `forge_move`: carried from step 1 (true when the forge folder was moved)
- `forge_left_in_place`: carried from step 1 (the forge folder left under the old name, or null)
- `same_folder`: carried from step 1 (true when `skills_output_folder` and `forge_data_folder` name one folder)
- `run_id`, `run_dir` and `lock_owner`: carried from step 1

The run's auto-decisions stay in `{run_dir}`, where step 1's gates recorded them.

### 10. Load Next Step

Load, read the full file, and then execute `{nextStepFile}`.

