---
nextStepFile: 'report.md'
versionPathsKnowledge: 'knowledge/version-paths.md'
managedSectionLogic: 'skf-export-skill/assets/managed-section-format.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in
# order (installed SKF module path first, src/ dev-checkout fallback);
# first existing path wins. §4 uses its `flip-link` action to create the
# `active` link again (under a lock, renamed into place, and a directory
# junction on Windows without symlink rights), because `ln -s` in Git Bash
# without symlink rights writes a copy of the folder instead. §6 uses its
# `write` action to restore the manifest from its backup (stage to
# .skf-tmp, fsync, rename), so a kill or a full disk mid-restore cannot
# leave a half-written manifest. HALT if neither candidate exists.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# Resolve `{manifestOpsHelper}` similarly. §6 uses the `rename` action
# for atomic re-key (preserves `active_version`, `versions` map, all
# fields, then writes via temp + rename).
manifestOpsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py'
  - '{project-root}/src/shared/scripts/skf-manifest-ops.py'
# Resolve `{rebuildManagedSectionsHelper}` similarly. §7 uses the
# `replace` action for the surgical between-marker rewrite.
rebuildManagedSectionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py'
  - '{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py'
# Resolve `{rewriteSkillNameHelper}` similarly. §3 uses it for the four
# field-scoped in-file rename transforms (SKILL.md frontmatter `name`,
# metadata.json `name`, provenance-map.json `skill_name`, context-snippet
# header + `root:` paths) — each a JSON round-trip or anchored-region edit
# plus the atomic write in one call, so the LLM never hand-edits JSON (which
# risks key reorder/drop) or eyeballs "only within the frontmatter" (which
# mis-fires when {old_name} is a substring, e.g. rename -> renamer).
rewriteSkillNameProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rewrite-skill-name.py'
  - '{project-root}/src/shared/scripts/skf-rewrite-skill-name.py'
# Resolve `{verifyNoTraceHelper}` similarly. §5 uses it for the commit-point
# no-trace gate: a fixed-file-set, name-token scan over affected_versions with
# the SKILL.md frontmatter/body region split (frontmatter = hard failure, body
# = advisory warning) and the directory-listing check, returned as JSON.
verifyNoTraceProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-no-trace.py'
  - '{project-root}/src/shared/scripts/skf-verify-no-trace.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Execute Rename (Transactional)

## STEP GOAL:

Execute the rename decisions recorded in step 1 as a transaction. Copy the old `{skill_group}` and, when step 1 set `{forge_move}`, `{forge_group}` to the new name, rename inner directories, rewrite every in-file reference, verify no trace of the old name remains inside the new location, update the export manifest, rebuild platform context files, and only then delete the old directories. Any failure before the final delete rolls back by removing the new directories — the old skill remains intact.

## Rules

- Execute sections strictly in order — each section depends on the previous one
- Do not re-prompt the user — decisions were made in step 1
- Do not delete anything from old directories before section 8
- Do not proceed past a verification failure in section 5
- Report each section's outcome as it completes

**Headless error envelope (self-contained).** Every HALT below that says *"emit the error envelope"* means: write this single line to **stderr**, mirroring SKILL.md's Result Contract (Headless) so this stage stays parseable even if SKILL.md is out of context on a `nextStepFile` chain —

```
SKF_RENAME_SKILL_RESULT_JSON: {"status":"error","old_name":"{old_name}","new_name":"{new_name}","versions_renamed":[],"manifest_rekeyed":false,"context_files_updated":[],"exit_code":<code>,"halt_reason":"<reason>","headless_decisions":{headless_decisions}}
```

Set `exit_code` and `halt_reason` to the values named at that HALT site (see `references/exit-codes.md`); `old_name`/`new_name` are both resolved by step 1 before this stage runs. `{headless_decisions}` is the audit trail carried from step 1 (the §6 source-authority override if it fired; `[]` otherwise) — emit it verbatim so a halt in this stage still preserves the decision trail.

## MANDATORY SEQUENCE

**Transactional boundary.** After section 1 (copy), the old skill is untouched; a failure in any of sections 2-7 deletes the new skill folder and, when `{forge_move}` is true, the new forge folder, reports, and halts with the old skill intact. Section 8 (delete old) is the only irreversible point.

### 0. Re-read Version-Paths Knowledge + Resolve Helpers

Read `{versionPathsKnowledge}` again and confirm the templates (`{skill_package}`, `{skill_group}`, `{forge_version}`, `{forge_group}`) and the Rename section. Also read `{managedSectionLogic}` for the managed-section format template and the skill index rebuild rules that will be reused in section 7.

**Resolve helpers** in parallel — these are independent file-existence checks that batch into one tool-call message:

- `{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` (used in §4 to create the `active` link again and in §6 for the crash-safe manifest restore)
- `{rewriteSkillNameHelper}` ← first existing path in `{rewriteSkillNameProbeOrder}` (used in §3 for the field-scoped in-file rename transforms + atomic write)
- `{verifyNoTraceHelper}` ← first existing path in `{verifyNoTraceProbeOrder}` (used in §5 for the deterministic no-trace commit gate)
- `{manifestOpsHelper}` ← first existing path in `{manifestOpsProbeOrder}` (used in §6 for the manifest re-key)
- `{rebuildManagedSectionsHelper}` ← first existing path in `{rebuildManagedSectionsProbeOrder}` (used in §7 for between-marker swap)

If any helper has no existing candidate, release the lock and HALT (exit code 4, `halt_reason: "write-failed"`) — the rename's safety guarantees depend on these helpers, and a fall-through to LLM-driven writes/scans would silently regress atomicity (the write helpers) or the deterministic transform and commit-gate checks (`{rewriteSkillNameHelper}`, `{verifyNoTraceHelper}`).

**Lock release contract:** every halt path in this step ends with `rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"` before exiting. The terminal health-check (step 4) is the success-path release.

### 1. Copy skill_group and forge_group

**Precondition:** Both `{new_skill_group}` and `{new_forge_group}` must NOT exist (step 1 validated this in the collision check, but verify again before copying).

1. If `{new_skill_group}` or `{new_forge_group}` exists on disk (a file or link counts): release the lock (`rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`) and halt with "**Collision detected at execution time.** `{new_skill_group}` or `{new_forge_group}` now exists on disk — it did not exist during step 1 selection. Aborting before any files are touched." HALT (exit code 4, `halt_reason: "copy-failed"`). In headless, emit the error envelope.

2. Copy `{old_skill_group}` to `{new_skill_group}`, naming both without a trailing `/` — equivalent to `cp -a {old_skill_group} {new_skill_group}`. §4a refused a linked skill folder and one holding a linked version, so the only link the copy can meet is `active`. The copy normally carries it as a link, but a shell that cannot create links (Git Bash on Windows without symlink rights) may copy the folder it points to instead; §4 creates `{new_skill_group}/active` again either way.
   - If the copy fails: release the lock (`rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`) and halt with "**Copy failed:** `{old_skill_group}` → `{new_skill_group}`: {error}. No files were modified. Old skill is intact." HALT (exit code 4, `halt_reason: "copy-failed"`). In headless, emit the error envelope.

3. Only when `{forge_move}` is true, copy `{old_forge_group}` to `{new_forge_group}` the same way. If the copy fails: **rollback** by deleting `{new_skill_group}` and whatever the copy created at `{new_forge_group}` (§1.1 confirmed nothing was there), release the lock (`rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`), then halt with "**Copy failed:** `{old_forge_group}` → `{new_forge_group}`: {error}. Rolled back the new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "copy-failed"`). In headless, emit the error envelope. When `{forge_move}` is false, skip this copy: the forge folder is absent, left in place (`{forge_left_in_place}`), or — with `{same_folder}` — already copied with the skill folder.

**Rollback procedure for this section:** `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`. Old skill is untouched.

Report: "**Copied** `{old_skill_group}` → `{new_skill_group}`{if forge_move: ' and `{old_forge_group}` → `{new_forge_group}`'}." Name only what was copied.

### 2. Rename Inner Version Directories

For each version `v` in `affected_versions`:

1. Resolve the old inner directory: `{new_skill_group}/{v}/{old_name}/`
2. Resolve the new inner directory: `{new_skill_group}/{v}/{new_name}/`
3. Rename the directory (move within the same parent): `mv {new_skill_group}/{v}/{old_name} {new_skill_group}/{v}/{new_name}`
4. If the old inner directory does not exist (orphaned version with no skill package: a manifest version with no folder, or a version folder an interrupted run left without one), skip with a warning recorded in `section2_warnings`

Record each version whose inner directory this section renamed in `renamed_versions`. §5 verifies only those: a skipped version has no package to check.

**Rollback on any rename failure:**

- `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`
- Release the lock: `rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`
- Halt with: "**Inner directory rename failed** at `{v}/{old_name}`: {error}. Rolled back the new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "write-failed"`). In headless, emit the error envelope.

Report: "**Renamed {count} inner directories** to `{new_name}/`."

### 3. Update File Contents Inside the New Location

For each version `v` in `affected_versions`, operate on the files inside `{new_skill_group}/{v}/{new_name}/` (the freshly renamed inner directory) and, only when `{forge_move}` or `{same_folder}` is true, `{new_forge_group}/{v}/`.

**Transform semantics (apply to 3a / 3b / 3c / 3d):** `{rewriteSkillNameHelper}` performs each field-scoped substitution AND the crash-safe write (stage to `<target>.skf-tmp`, fsync, atomic rename) in one call — do NOT compute file content in the prompt. Each `--kind` edits exactly one field/region and leaves everything else byte-for-byte intact, so there is no key reorder/drop from hand-editing JSON and no wrong-region substitution when `{old_name}` is a substring (e.g. `rename` → `renamer`). Invoke it once per file:

```bash
python3 {rewriteSkillNameHelper} "{target_path}" \
  --kind {skill-frontmatter|metadata-json|context-snippet|provenance-json} \
  --old-name {old_name} --new-name {new_name}
```

Read the JSON result (`changed`, `wrote`, and per-kind fields). Exit 0 = processed (written only if the content changed). A non-zero exit — a missing structural region (no frontmatter delimiters), invalid JSON, or a write failure — is a **file update failure**: trigger the rollback below. Check file existence first: if the target file does not exist, skip the invocation and record it in `section3_warnings` per the per-item notes (a missing file is not a failure).

**3a. SKILL.md frontmatter** — `--kind skill-frontmatter` on `{new_skill_group}/{v}/{new_name}/SKILL.md`. Replaces the top-level `name:` value inside the frontmatter block only (anchored on `^name:`, so a nested `name:` or a longer key like `renamed:` is untouched); body text is preserved verbatim, so a legitimate mention of `{old_name}` below the closing `---` survives. If the file is missing, record it in `section3_warnings` and continue.

**3b. metadata.json** — `--kind metadata-json` on `{new_skill_group}/{v}/{new_name}/metadata.json`. Sets `name` = `{new_name}` via a JSON round-trip (key order preserved). If the file is missing, record it in `section3_warnings` and continue.

**3c. context-snippet.md** — `--kind context-snippet` on `{new_skill_group}/{v}/{new_name}/context-snippet.md`. Rewrites the display header `[{old_name} v...]` → `[{new_name} v...]` (version suffix preserved) and every `root:` path: it parses `root: {prefix}{old_name}/`, keeps the prefix verbatim, and swaps the trailing `{old_name}/` segment for `{new_name}/` — handling any IDE prefix (`.claude/skills/`, `.windsurf/skills/`, `.github/skills/`, the draft `skills/` prefix) generically, and flattening the legacy `root: skills/{old_name}/active/{old_name}/` form to `root: skills/{new_name}/`. If the file is missing, record it in `section3_warnings` and continue.

**3d. provenance-map.json** — `--kind provenance-json` on `{new_forge_group}/{v}/provenance-map.json`. Sets `skill_name` = `{new_name}` via a JSON round-trip. If the file is missing (some versions may not have a provenance map), record it in `section3_warnings` and continue. Skip 3d when `{forge_move}` and `{same_folder}` are both false: there is no SKF forge folder to rewrite.

**Rollback on any update failure (not just a missing file):**

- `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`
- Release the lock: `rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`
- Halt with: "**File update failed** at `{path}`: {error}. Rolled back the new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "write-failed"`). In headless, emit the error envelope.

Report: "**Updated file contents** across {affected_versions_count} version(s): SKILL.md, metadata.json, context-snippet.md{if forge_move or same_folder: ', provenance-map.json'}." Name only what was rewritten.

### 4. Fix the `active` Symlink in the New Location

The §1 copy carries `{old_skill_group}/active` into `{new_skill_group}` as it found it. A relative link (`active -> 0.6.0`) still names the right version folder, but an absolute link or one through `..` still points into `{old_skill_group}`, which §8 deletes, and a shell that cannot create links may have copied the folder the link points to. So this section removes whatever the copy made at `{new_skill_group}/active` and creates the link again with the `flip-link` action of `{atomicWriteHelper}`, the call create-skill, quick-skill and create-stack-skill use to set it. The helper creates the link under a temporary name and renames it over `active` while it holds a lock on `{new_skill_group}/active.skf-lock`, and it refuses to replace an `active` that is a real folder or file. On Windows, when `os.symlink` fails for lack of privilege, it creates a directory junction (`mklink /J`) instead, which needs neither Developer Mode nor admin rights. Never create the link with `ln -s`: Git Bash on Windows without symlink rights writes a copy of the folder instead. `{new_skill_group}` is this run's own copy, which no manifest entry or context file names until §6 and §7, so removing the copied entry before the flip is safe.

1. If nothing is at `{old_skill_group}/active`, not even a broken link (`[ ! -e "{old_skill_group}/active" ] && [ ! -L "{old_skill_group}/active" ]`), skip to the report at the end of this section: there is no link to carry over.
2. If `{old_skill_group}/active` is not a link (`[ ! -L "{old_skill_group}/active" ]`), take the rollback below with the reason: "`{old_skill_group}/active` is a real folder or file, not a link. `ln -s` in Git Bash on Windows without symlink rights writes such a copy. Check that it only copies a version folder, remove it and re-run the rename, then point the renamed skill's link at a version with `uv run {atomicWriteHelper} flip-link --link "{new_skill_group}/active" --target <version>`."
3. Read the link. Set `{old_active_link}` to what the first line prints, the link text as stored, and `{target_version}` to what the second line prints, its last path component:

   ```bash
   readlink "{old_skill_group}/active"
   basename "$(readlink "{old_skill_group}/active")"
   ```

   For an `{old_active_link}` of `0.6.0`, `{old_skill_group}/0.6.0` or `../{old_name}/0.6.0/`, `{target_version}` is `0.6.0`.
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

   On exit 0 the helper prints `{"link": …, "points_to": …, "kind": …, "status": "ok"}` on stdout: bind `{active_link_kind}` ← `kind` (`symlink` or `junction`). On exit 2 with a `{"status": "error", "message": …}` line on stderr (something that is not a link is at `{new_skill_group}/active`, or another process holds the lock), bind `{flip_error}` ← `message`. On any other failure, an exit 2 without that line (an argument error) or exit 1 (any other error, such as Windows refusing both a symlink and a junction, reported as a Python traceback), set `{flip_error}` to the helper's stderr. Take the rollback below with `{flip_error}` as the reason.

**Rollback on a failure in step 2, 4 or 6:**

- `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`
- Release the lock: `rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`
- Halt with: "**Failed to repair the `active` link** in `{new_skill_group}`: {reason}. Rolled back the new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "write-failed"`). In headless, emit the error envelope.

Report: "**`active` link:** `{new_skill_group}/active` → `{target_version}` ({active_link_kind}).{if `{old_active_link}` is not `{target_version}`: ' Repointed from `{old_active_link}`.'}" When step 1 skipped this section: "**`active` link:** none in `{old_skill_group}`, nothing to carry over."

### 5. Verify — No Trace of `{old_name}` Inside the New Location

This is the commit-point check. If any structural reference to `{old_name}` remains, the rename is not safe to commit. `{verifyNoTraceHelper}` performs the whole scan deterministically — a fixed-file-set, name-token scan across every `affected_versions` entry, the SKILL.md frontmatter/body region split, and the directory-listing check — and returns the verdict as JSON. Invoke it once:

```bash
python3 {verifyNoTraceHelper} "{new_skill_group}" \
  --forge-group "{new_forge_group}" \
  --old-name {old_name} --new-name {new_name} \
  --versions {comma-separated renamed_versions}
```

Per version `v`, the helper scans `SKILL.md` (frontmatter matches → `hard_matches`; matches in the body below the closing `---` → `body_warnings`), `metadata.json`, `context-snippet.md`, and `provenance-map.json` (any match → `hard_matches`), plus the `{new_skill_group}/{v}/` listing (an `{old_name}/` directory present, or the `{new_name}/` directory missing → `dir_violations`). It matches `{old_name}` only as a complete skill-name token — bounded by non-name characters — so a correctly-renamed `{new_name}` that contains `{old_name}` as a substring (e.g. `rename` → `rename-skill`) is never a false leftover, and the frontmatter=hard / body=warning split is applied by region with no meaning-interpretation. A missing file is recorded under `skipped`, not treated as a match. When `{forge_move}` and `{same_folder}` are both false, `{new_forge_group}` does not exist and the helper records each provenance map under `skipped`. Exit 0 = clean; exit 1 = at least one hard match or dir violation.

Read the JSON and decide. An exit code of 2 with no JSON on stdout (the helper refuses an empty `--versions` list) counts as `clean` false: take the rollback below.

- **If `clean` is `true` (empty `hard_matches` AND empty `dir_violations`):** the rename is safe to commit. Set `verification_warnings` = the returned `body_warnings` (informational SKILL.md body mentions of `{old_name}` that are retained). Proceed.
- **If `clean` is `false`:** this is a hard failure —
  - `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true (this run created it), each without a trailing `/`
  - Release the lock: `rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`
  - Halt with: "**Verification failed.** `{old_name}` still appears in: {the files from `hard_matches` plus any `dir_violations`}. Rolled back the new directories. Old skill is intact." HALT (exit code 5, `halt_reason: "verify-failed"`). In headless, emit the error envelope.

Report: "**Verified** — no structural references to `{old_name}` remain inside the new location across {affected_versions_count} version(s). {if verification_warnings is non-empty: 'Informational body-text mentions retained in SKILL.md: {list}.'}"

### 6. Update Export Manifest

**If `manifest_exists = false` (step 1 recorded no manifest on disk):**

Skip this section entirely. Set `manifest_updated = false` and `manifest_backup = null`. There is no manifest to re-key — the skill was never exported. Section 7 will find no platform context files to rebuild either (no manifest means no prior export, so no `<!-- SKF:BEGIN -->` markers exist), and any platform file that happens to be present will be left alone by the section 2 marker check.

Report: "**Manifest update skipped** — no `.export-manifest.json` on disk. The rename is a pure on-disk operation."

**If `manifest_exists = true`:**

1. **Keep the manifest's text** as `manifest_backup` for the rollback below: read `{skills_output_folder}/.export-manifest.json` once and hold its exact text, not a parsed or re-serialized copy, so a restore writes back the same bytes.
2. **Re-key via the helper.** If the manifest contains `exports.{old_name}`, invoke:

   ```bash
   python3 {manifestOpsHelper} {skills_output_folder} rename {old_name} {new_name}
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
- Release the lock: `rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`
- Halt with: "**Manifest update failed:** {manifest_error}. {if `{manifest_restore}` is `unchanged`: 'This run did not change the manifest.'}{if `restored`: 'Restored the manifest from the backup.'}{if `restore-failed`: 'Could not restore the manifest, which may still list `{new_name}` in place of `{old_name}`: re-key it back with `uv run {manifestOpsHelper} "{skills_output_folder}" rename {new_name} {old_name}`.'} Rolled back the new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "manifest-write-failed"`). In headless, emit the error envelope.

Set context flag `manifest_updated = true`.

Report: "**Manifest updated** — re-keyed `exports.{old_name}` → `exports.{new_name}`."

### 7. Rebuild Context Files

After §6 re-keys the manifest from `{old_name}` to `{new_name}`, every IDE's context file (`CLAUDE.md`, `.cursorrules`, `AGENTS.md`, etc.) still carries the old name in its managed-section snippet rows. This section rewrites each one in-place via the surgical between-marker swap so the on-disk managed sections reflect the new name. It runs only on the success path — the §4–§6 rollback jumps never reach here.

**7a. Resolve `target_context_files`.** Load the `ides` list from `config.yaml`. The installer writes IDE identifiers — map each to a context file and skill root via the "IDE → Context File Mapping" table in `{managedSectionLogic}`:

1. For each entry in `config.yaml.ides`, look up its `context_file` and `skill_root` from the mapping table.
2. For any entry not in the table, default to `{unknownIdeDefaultContextFile}` / `{unknownIdeDefaultSkillRoot}` and emit a warning: `Unknown IDE '{value}' in config.yaml — defaulting to {unknownIdeDefaultContextFile}`.
3. Deduplicate by `context_file` — when multiple IDEs map to the same context file, use the first configured IDE's `skill_root`.
4. If `config.yaml.ides` is absent or the mapping yields an empty list, fall back to `[{context_file: "{unknownIdeDefaultContextFile}", skill_root: "{unknownIdeDefaultSkillRoot}"}]` and emit a note: `No IDEs configured in config.yaml — defaulting to {unknownIdeDefaultContextFile}`.

**7b. Per-file loop.** For each entry in `target_context_files`:

1. **Resolve the target file** at `{context_file}` (absolute path).
2. **Read the current file:**
   - If it does not exist, skip (nothing to rebuild — export-skill re-creates it on its next run).
   - If it exists but has no `<!-- SKF:BEGIN -->` marker, skip (no managed section to rewrite).
   - If it has `<!-- SKF:BEGIN -->` but no matching `<!-- SKF:END -->`, record the error against that file and continue to the next entry — do not halt the whole rename on one malformed context file.
3. **Build the exported skill set (version-aware, deprecated-excluded)** using the same logic as `skf-export-skill/references/update-context.md` §4b (skill set) and §4c (snippet resolution):
   - Read the manifest's `exports` object (already updated in §6, so `{new_name}` is present and `{old_name}` is absent).
   - For each skill, resolve its `active_version`; if `versions.{active_version}.status == "deprecated"`, skip that skill.
   - For each remaining `{skill-name, active_version}` pair, read `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/context-snippet.md`; if missing, fall back to the `active` symlink path; if still missing, skip with a warning.
4. **Rewrite root paths** using the generic algorithm from `skf-export-skill/references/update-context.md` §4d: parse each snippet's `root:` line (`root: {prefix}{skill-name}/`), strip the trailing `{skill-name}/` to extract the current prefix, and replace it with the effective target prefix if different. The effective target prefix is `snippet_skill_root_override` when that key is set in `config.yaml` (applied uniformly to every snippet so the managed section references the real on-disk location and never mixes override and per-IDE paths), otherwise the current entry's `skill_root`.
5. **Sort and count.** Sort skills alphabetically by name; count totals (skills, stack skills).
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

7. **Surgical replacement — atomic, deterministic.** Invoke `{rebuildManagedSectionsHelper}` (resolved in §0) for the between-marker swap:

   ```bash
   python3 {rebuildManagedSectionsHelper} {context_file} replace --content "{new_managed_section_text}"
   ```

   The helper handles marker location, the between-marker swap, atomic temp-file + rename, and post-write verification (markers preserved, content outside markers byte-identical). It exits non-zero on any failure with a clear `stderr` reason — treat any non-zero exit as a per-file failure.
8. **On per-file failure**, record the error against that context file and continue to the next entry. Do not halt the rename on a recoverable per-context-file error — the manifest and filesystem are already consistent, so context files can be re-rebuilt later via `[EX] Export Skill`.

**7c. After the loop**, record:

- `context_files_updated` — list of files successfully rewritten
- `context_files_failed` — list of any that failed

Report: `**Rebuilt managed sections in:** {list of updated files}. {if any failed: 'Failed: {list} — re-run [EX] Export Skill to retry.'}` Then proceed to §8.

**Note:** §7 failures do not trigger a rollback. Platform context files are derived artifacts; the manifest and on-disk skill directories are the canonical state.

### 8. Delete Old Directories (Point of No Return)

This is the only section after which rollback is impossible. Precondition: §1–7 have fully materialized and verified the new name (the new directories renamed, no `{old_name}` references remaining, manifest re-keyed, context files rebuilt best-effort) — only now is deleting the old name safe.

Execute the deletes:

1. Verify `{old_skill_group}` (no trailing `/`) is inside `{skills_output_folder}` and is not a link or junction.
2. `rm -rf {old_skill_group}`.
3. Verify deletion succeeded.
4. Only when `{forge_move}` is true: verify `{old_forge_group}` is inside `{forge_data_folder}` and is not a link or junction; `rm -rf {old_forge_group}` (no trailing `/`); verify deletion succeeded. Otherwise leave it: `{forge_left_in_place}` keeps its name, and with `{same_folder}` step 2 already deleted it.

A path that fails the link check is not deleted: record "a link; SKF never deletes through a link" in `deletion_errors`.

**On deletion error:**

- Record the error in `deletion_errors` against the specific path
- Continue attempting the other path — partial cleanup is still better than none
- Do NOT attempt any rollback — the new name is already committed and the old name's remnants can be removed manually

Report: "**Deleted old directories:** `{old_skill_group}`{if forge_move: ' and `{old_forge_group}`'}. {if deletion_errors is non-empty: 'Errors: {list} — remove manually with `rm -rf {path}`.'}"

### 9. Store Results in Context

Store the following for step 3:

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
- `forge_move` — carried from step 1 (true when the forge folder was moved)
- `forge_left_in_place` — carried from step 1 (the forge folder left under the old name, or null)
- `same_folder` — carried from step 1 (true when `skills_output_folder` and `forge_data_folder` name one folder)
- `headless_decisions` — the audit trail of confirmation gates auto-resolved under `{headless_mode}`, carried forward from step 1 unchanged (empty in interactive runs). Step 3 surfaces it in the result envelope and the per-run result JSON.

### 10. Load Next Step

Load, read the full file, and then execute `{nextStepFile}`.

