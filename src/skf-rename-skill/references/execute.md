---
nextStepFile: 'report.md'
versionPathsKnowledge: 'knowledge/version-paths.md'
managedSectionLogic: 'skf-export-skill/assets/managed-section-format.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in
# order (installed SKF module path first, src/ dev-checkout fallback);
# first existing path wins. §3 + §6 use it for crash-safe file rewrites
# (stage to .skf-tmp, fsync, rename) — letting the LLM write directly
# risks half-written artifacts on process kill or disk-full mid-write.
# HALT if neither candidate exists.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# Resolve `{updateActiveSymlinkHelper}` similarly. §4 uses it to
# atomically repair the `active` symlink with `flock` and the Windows
# junction fallback — `rm + ln -s` would race against concurrent readers
# and silently break on Windows.
updateActiveSymlinkProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-active-symlink.py'
  - '{project-root}/src/shared/scripts/skf-update-active-symlink.py'
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

Execute the rename decisions recorded in step 1 as a transaction. Copy the old `{skill_group}` and `{forge_group}` to the new name, rename inner directories, rewrite every in-file reference, verify no trace of the old name remains inside the new location, update the export manifest, rebuild platform context files, and only then delete the old directories. Any failure before the final delete rolls back by removing the new directories — the old skill remains intact.

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

**Transactional boundary.** After section 1 (copy), the old skill is untouched; a failure in any of sections 2-7 deletes the two new directories (`{new_skill_group}`, `{new_forge_group}`), reports, and halts with the old skill intact. Section 8 (delete old) is the only irreversible point.

### 0. Re-read Version-Paths Knowledge + Resolve Helpers

Read `{versionPathsKnowledge}` again and confirm the templates (`{skill_package}`, `{skill_group}`, `{forge_version}`, `{forge_group}`) and the Rename section. Also read `{managedSectionLogic}` for the managed-section format template and the skill index rebuild rules that will be reused in section 7.

**Resolve helpers** in parallel — these are independent file-existence checks that batch into one tool-call message:

- `{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` (used in §6 for crash-safe manifest restore)
- `{rewriteSkillNameHelper}` ← first existing path in `{rewriteSkillNameProbeOrder}` (used in §3 for the field-scoped in-file rename transforms + atomic write)
- `{updateActiveSymlinkHelper}` ← first existing path in `{updateActiveSymlinkProbeOrder}` (used in §4 for atomic symlink repair)
- `{verifyNoTraceHelper}` ← first existing path in `{verifyNoTraceProbeOrder}` (used in §5 for the deterministic no-trace commit gate)
- `{manifestOpsHelper}` ← first existing path in `{manifestOpsProbeOrder}` (used in §6 for the manifest re-key)
- `{rebuildManagedSectionsHelper}` ← first existing path in `{rebuildManagedSectionsProbeOrder}` (used in §7 for between-marker swap)

If any helper has no existing candidate, release the lock and HALT (exit code 4, `halt_reason: "write-failed"`) — the rename's safety guarantees depend on these helpers, and a fall-through to LLM-driven writes/scans would silently regress atomicity (the write helpers) or the deterministic transform and commit-gate checks (`{rewriteSkillNameHelper}`, `{verifyNoTraceHelper}`).

**Lock release contract:** every halt path in this step ends with `rm -f "{forge_data_folder}/{old_name}/.skf-rename.lock"` before exiting. The terminal health-check (step 4) is the success-path release.

### 1. Copy skill_group and forge_group

**Precondition:** Both `{new_skill_group}` and `{new_forge_group}` must NOT exist (step 1 validated this in the collision check, but verify again before copying).

1. If `{new_skill_group}` or `{new_forge_group}` exists on disk: release the lock (`rm -f "{forge_data_folder}/{old_name}/.skf-rename.lock"`) and halt with "**Collision detected at execution time.** `{new_skill_group}` or `{new_forge_group}` now exists on disk — it did not exist during step 1 selection. Aborting before any files are touched." HALT (exit code 4, `halt_reason: "copy-failed"`). In headless, emit the error envelope.

2. Copy `{old_skill_group}` to `{new_skill_group}` recursively:
   - Preserve file permissions, timestamps, and symlinks
   - Equivalent to `cp -a {old_skill_group} {new_skill_group}` (preserves symlinks) or `cp -r` followed by explicit symlink re-creation in section 4
   - If the copy fails: release the lock (`rm -f "{forge_data_folder}/{old_name}/.skf-rename.lock"`) and halt with "**Copy failed:** `{old_skill_group}` → `{new_skill_group}`: {error}. No files were modified. Old skill is intact." HALT (exit code 4, `halt_reason: "copy-failed"`). In headless, emit the error envelope.

3. Copy `{old_forge_group}` to `{new_forge_group}` the same way:
   - If the copy fails: **rollback** by deleting `{new_skill_group}` (just created in step 2), release the lock (`rm -f "{forge_data_folder}/{old_name}/.skf-rename.lock"`), then halt with "**Copy failed:** `{old_forge_group}` → `{new_forge_group}`: {error}. Rolled back new skill_group. Old skill is intact." HALT (exit code 4, `halt_reason: "copy-failed"`). In headless, emit the error envelope.

**Rollback procedure for this section:** `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}` (whichever exist). Old skill is untouched.

Report: "**Copied** `{old_skill_group}` → `{new_skill_group}` and `{old_forge_group}` → `{new_forge_group}`."

### 2. Rename Inner Version Directories

For each version `v` in `affected_versions`:

1. Resolve the old inner directory: `{new_skill_group}/{v}/{old_name}/`
2. Resolve the new inner directory: `{new_skill_group}/{v}/{new_name}/`
3. Rename the directory (move within the same parent): `mv {new_skill_group}/{v}/{old_name} {new_skill_group}/{v}/{new_name}`
4. If the old inner directory does not exist (orphaned version with no skill package), skip with a warning recorded in `section2_warnings`

**Rollback on any rename failure:**

- `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}`
- Release the lock: `rm -f "{forge_data_folder}/{old_name}/.skf-rename.lock"`
- Halt with: "**Inner directory rename failed** at `{v}/{old_name}`: {error}. Rolled back both new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "write-failed"`). In headless, emit the error envelope.

Report: "**Renamed {count} inner directories** to `{new_name}/`."

### 3. Update File Contents Inside the New Location

For each version `v` in `affected_versions`, operate on the files inside `{new_skill_group}/{v}/{new_name}/` (the freshly renamed inner directory) and `{new_forge_group}/{v}/`.

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

**3d. provenance-map.json** — `--kind provenance-json` on `{new_forge_group}/{v}/provenance-map.json`. Sets `skill_name` = `{new_name}` via a JSON round-trip. If the file is missing (some versions may not have a provenance map), record it in `section3_warnings` and continue.

**Rollback on any update failure (not just a missing file):**

- `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}`
- Release the lock: `rm -f "{forge_data_folder}/{old_name}/.skf-rename.lock"`
- Halt with: "**File update failed** at `{path}`: {error}. Rolled back both new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "write-failed"`). In headless, emit the error envelope.

Report: "**Updated file contents** across {affected_versions_count} version(s): SKILL.md, metadata.json, context-snippet.md, provenance-map.json."

### 4. Fix the `active` Symlink in the New Location

Recreate or repair the `active` symlink in `{new_skill_group}` via `{updateActiveSymlinkHelper}` — the helper holds an `flock` on `{new_skill_group}/active.lock`, surfaces a clear error on Windows non-dev-mode (no silent fallback), and uses the `ln -sfn tmp && mv -Tf tmp link` pattern to make the flip atomic against concurrent readers.

1. Inspect `{old_skill_group}/active` to determine the target version (the value the symlink points to — typically just the version string, not an absolute path). If `{old_skill_group}/active` does not exist, skip this section — there is no symlink to repair.
2. Invoke:

   ```bash
   python3 {updateActiveSymlinkHelper} flip-link \
     --link {new_skill_group}/active \
     --target {target_version}
   ```

3. The helper handles all four cases (missing, present-and-correct, present-and-stale, present-and-invalid) uniformly via atomic replace.

**Rollback on helper non-zero exit:**

- `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}`
- Release the lock: `rm -f "{forge_data_folder}/{old_name}/.skf-rename.lock"`
- Halt with: "**Failed to repair `active` symlink** in `{new_skill_group}`: {captured stderr}. Rolled back both new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "write-failed"`). In headless, emit the error envelope.

### 5. Verify — No Trace of `{old_name}` Inside the New Location

This is the commit-point check. If any structural reference to `{old_name}` remains, the rename is not safe to commit. `{verifyNoTraceHelper}` performs the whole scan deterministically — a fixed-file-set, name-token scan across every `affected_versions` entry, the SKILL.md frontmatter/body region split, and the directory-listing check — and returns the verdict as JSON. Invoke it once:

```bash
python3 {verifyNoTraceHelper} "{new_skill_group}" \
  --forge-group "{new_forge_group}" \
  --old-name {old_name} --new-name {new_name} \
  --versions {comma-separated affected_versions}
```

Per version `v`, the helper scans `SKILL.md` (frontmatter matches → `hard_matches`; matches in the body below the closing `---` → `body_warnings`), `metadata.json`, `context-snippet.md`, and `provenance-map.json` (any match → `hard_matches`), plus the `{new_skill_group}/{v}/` listing (an `{old_name}/` directory present, or the `{new_name}/` directory missing → `dir_violations`). It matches `{old_name}` only as a complete skill-name token — bounded by non-name characters — so a correctly-renamed `{new_name}` that contains `{old_name}` as a substring (e.g. `rename` → `rename-skill`) is never a false leftover, and the frontmatter=hard / body=warning split is applied by region with no meaning-interpretation. A missing file is recorded under `skipped`, not treated as a match. Exit 0 = clean; exit 1 = at least one hard match or dir violation.

Read the JSON and decide:

- **If `clean` is `true` (empty `hard_matches` AND empty `dir_violations`):** the rename is safe to commit. Set `verification_warnings` = the returned `body_warnings` (informational SKILL.md body mentions of `{old_name}` that are retained). Proceed.
- **If `clean` is `false`:** this is a hard failure —
  - `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}`
  - Release the lock: `rm -f "{forge_data_folder}/{old_name}/.skf-rename.lock"`
  - Halt with: "**Verification failed.** `{old_name}` still appears in: {the files from `hard_matches` plus any `dir_violations`}. Rolled back both new directories. Old skill is intact." HALT (exit code 5, `halt_reason: "verify-failed"`). In headless, emit the error envelope.

Report: "**Verified** — no structural references to `{old_name}` remain inside the new location across {affected_versions_count} version(s). {if verification_warnings is non-empty: 'Informational body-text mentions retained in SKILL.md: {list}.'}"

### 6. Update Export Manifest

**If `manifest_exists = false` (step 1 recorded no manifest on disk):**

Skip this section entirely. Set `manifest_updated = false` and `manifest_backup = null`. There is no manifest to re-key — the skill was never exported. Section 7 will find no platform context files to rebuild either (no manifest means no prior export, so no `<!-- SKF:BEGIN -->` markers exist), and any platform file that happens to be present will be left alone by the section 2 marker check.

Report: "**Manifest update skipped** — no `.export-manifest.json` on disk. The rename is a pure on-disk operation."

**If `manifest_exists = true`:**

1. **Hold a deep copy in memory** as `manifest_backup` — required for rollback in this section and section 7 on failure. Read `{skills_output_folder}/.export-manifest.json` once and stash the parsed object.
2. **Re-key via the helper.** If the manifest contains `exports.{old_name}`, invoke:

   ```bash
   python3 {manifestOpsHelper} {skills_output_folder} rename {old_name} {new_name}
   ```

   The helper preserves `active_version`, `versions` map, and all fields, then writes the manifest atomically via temp + rename. If the manifest does NOT contain `exports.{old_name}` (the skill was on disk but never exported), skip the invocation — the manifest has nothing to change.

**Rollback on helper non-zero exit:**

- Restore the manifest from `manifest_backup` via `{atomicWriteHelper} write {skills_output_folder}/.export-manifest.json` (re-pipe the JSON-serialized backup)
- `rm -rf {new_skill_group}` and `rm -rf {new_forge_group}`
- Release the lock: `rm -f "{forge_data_folder}/{old_name}/.skf-rename.lock"`
- Halt with: "**Manifest update failed:** {captured stderr}. Restored manifest from backup and rolled back new directories. Old skill is intact." HALT (exit code 4, `halt_reason: "manifest-write-failed"`). In headless, emit the error envelope.

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

This is the only section after which rollback is impossible. Precondition: §1–7 have fully materialized and verified the new name (both new directories renamed, no `{old_name}` references remaining, manifest re-keyed, context files rebuilt best-effort) — only now is deleting the old name safe.

Execute the deletes:

1. Verify `{old_skill_group}` is inside `{skills_output_folder}` (defense in depth)
2. `rm -rf {old_skill_group}` — delete the old skill_group recursively
3. Verify deletion succeeded (the path no longer exists)
4. Verify `{old_forge_group}` is inside `{forge_data_folder}` (defense in depth)
5. `rm -rf {old_forge_group}` — delete the old forge_group recursively
6. Verify deletion succeeded

**On deletion error:**

- Record the error in `deletion_errors` against the specific path
- Continue attempting the other path — partial cleanup is still better than none
- Do NOT attempt any rollback — the new name is already committed and the old name's remnants can be removed manually

Report: "**Deleted old directories:** `{old_skill_group}` and `{old_forge_group}`. {if deletion_errors is non-empty: 'Errors: {list} — remove manually with `rm -rf {path}`.'}"

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
- `headless_decisions` — the audit trail of confirmation gates auto-resolved under `{headless_mode}`, carried forward from step 1 unchanged (empty in interactive runs). Step 3 surfaces it in the result envelope and the per-run result JSON.

### 10. Load Next Step

Load, read the full file, and then execute `{nextStepFile}`.

