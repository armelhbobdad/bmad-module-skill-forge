---
nextStepFile: 'write.md'
# `{atomicWriteHelper}`: §6b stages and publishes the version folder.
# HALT if neither resolves: a folder copied in place would leave a half-copied
# version behind.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# `{skillInventoryHelper}`: §6b's next patch version. HALT if neither resolves:
# never pick it by hand.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# `{hashContentHelper}`: §6b's check of the merged SKILL.md against the
# [MANUAL] inventory merge.md §4 amended. HALT if neither resolves.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# `{verifyProvenanceCompletenessHelper}`: §6b's citation moves (Priority 2).
# HALT if neither resolves: never move a citation by hand.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# `{emitEnvelopeHelper}` and `{runStateHelper}`: SKILL.md binds both, and a
# lost binding resolves here, first existing path wins. The warnings go to the
# run log through the first; the halt procedure and §6b's `begin` run the
# second.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runStateProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-run-state.py'
  - '{project-root}/src/shared/scripts/skf-update-run-state.py'
# `{runLockHelper}`: init.md §1b binds it, and §6b's renewal resolves it again
# when the binding was lost.
runLockProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py'
  - '{project-root}/src/shared/scripts/skf-run-lock.py'
# `{writeSkillBriefHelper}`: §6b writes a repair's rescopes into the skill
# brief. HALT if neither resolves: never edit the brief by hand.
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4b: Write the Merged Files

## STEP GOAL:

Write the merge step 4 compiled to disk, once: renew the run lock, choose the version this update writes, record what this run writes, then write the merged SKILL.md and `references/*.md` into a new version folder (in place in gap-driven mode), checking the [MANUAL] blocks before anything is published.

## Rules

- Focus only on writing what merge.md compiled: change no merge decision
- Write the merged files to disk at section 6b, once §6b has recorded what this run writes (`{runStateHelper}` `begin`), and verify the merged SKILL.md against the [MANUAL] inventory the user approved before it is published: in a staged version folder outside gap-driven mode, in `{run_dir}` in gap-driven mode. Later steps verify the files on disk
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}`, `{runStateHelper}` in `{runStateProbeOrder}` and `{runLockHelper}` in `{runLockProbeOrder}`.

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the `{runStateHelper}` `halt` call below.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "<normal, gap-driven or degraded>"}
SKF_JSON
```

Pass `--tree` when load-baseline.md §6b bound `{source_tree}`, always `--lock` and `--owner`, and `--emit` in `{headless_mode}`. Once §6b has run `begin`, the helper first undoes what this run wrote; then it removes the private source tree, releases the run lock and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line, with a warning (`rollback-incomplete`, `source-tree-not-removed`, `run-lock-not-released`) for each step it could not finish: do none of it yourself. Tell the user in one line what it restored and removed, and name each path its `failed[]` lists for the user to restore or delete by hand. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "merge:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 6b. Write Merged Files to Disk

Write the merged content produced by merge.md sections 3–4 to disk now. Later steps read these files from disk. The write must happen exactly once, here.

**Renew the run lock** before anything below writes: this run may have waited at a gate past the time init.md §1b's lock goes stale. From `{project-root}`, run the acquire init.md §1b ran, with this run's own owner:

```bash
uv run {runLockHelper} acquire \
    --lock "{forge_data_folder}/{skill_name}/.skf-update.lock" \
    --owner "{lock_owner}" \
    --stale-after 60
```

- **Exit 0 with `refreshed` true:** the lock is still this run's, now renewed; continue.
- **Exit 0 with `refreshed` false, or exit 3:** this run's lock lapsed while it waited, so another update may have changed the skill since this run read it. On exit 0 the lock was gone, or `stale_replaced` names another update's stale lock, and this acquire took it again; on exit 3 another update holds it. HALT with status `halted-for-concurrent-run` before this section writes anything: display "**This update of {skill_name} lost its run lock while it waited.** Another update of the skill may have run in the meantime, so this update wrote nothing to the skill package: run it again{on exit 3: once that update ends. {message}}." The halt procedure takes `phase: "merge:run-lock"`, `path: "{forge_data_folder}/{skill_name}/.skf-update.lock"`, `reason: "run-lock-lost: this run's lock lapsed while it waited; another update may have changed the skill since this run read it"`, or on exit 3 `reason: "another update in progress: {message}"`. The halt's release (step 3 of the halt procedure) removes a lock this acquire took.
- **Any other exit, or no JSON:** HALT with status `blocked` before this section writes anything: display "**The run lock could not be renewed:** {the message the helper printed on stderr}. This update wrote nothing to the skill package." The halt procedure takes `phase: "merge:run-lock"`, `path: "{forge_data_folder}/{skill_name}/.skf-update.lock"`, `reason: "run-lock-failed: {that message}"`.

**Choose the version this update writes** and bind `{new_version}`:

- **Gap-driven mode** (`update_mode` is `gap-driven`): a repair keeps the version it repairs: `{new_version}` is the metadata.json `version`, SKILL.md is written into the current `{skill_package}`, and the version folder below is skipped.
- **Every other mode** (normal, degraded and docs-only): `{new_version}` is `{source_version_detected}` when load-baseline.md §6c recorded one (a higher version than the previous metadata version), otherwise the previous version with its patch number incremented, as `{skillInventoryHelper}` computes it (resolve it ← first existing path in `{skillInventoryProbeOrder}`). From `{project-root}`, run `uv run {skillInventoryHelper} version next-patch "{version}"` with the metadata.json `version` and bind `{new_version}` ← `next_patch`: `1.2.3` gives `1.2.4`, and a pre-release gives its release (`1.2.3-rc.1` gives `1.2.3`). Never increment it by hand. Both values are version folder names already: the helper drops build metadata. When no candidate resolves, or the command exits 1 (`code` `NOT_A_VERSION`: the metadata.json `version` names no version) or prints no JSON, HALT with status `halted-for-write-failure` before writing anything: "**The next version of {skill_name} could not be computed:** {the helper's `error`, or 'skf-skill-inventory.py is missing; re-install SKF'}. Nothing was written. When the metadata.json `version` names no version, set the version the skill was forged at there, then re-run." The halt procedure takes `phase: "merge:new-version-folder"`, `path: "{skill_package}/metadata.json"`, `reason: "next-version-failed: {that message}"`.

  **Skip an emptied version folder.** While `{skill_group}/{new_version}/` exists and holds no `{skill_name}/` folder (the test init.md §1's `resolve` applies to a version folder: an `active` link to an emptied folder names it, and `resolve` chose an older version), bind `{new_version}` ← the `next_patch` of `uv run {skillInventoryHelper} version next-patch "{new_version}"`, with the halt above. Then add, for each folder skipped, `version-folder-skipped: {skill_group}/{that version}/ holds no skill; this update writes {new_version}` to `warnings[]`. The folder skipped stays as it is: this update writes into no folder the `active` link names and overwrites nothing. A version folder that holds the package, and a forge folder alone, still take the version-exists halt below.

**Record what this run writes**, before its first write, so a later halt, or the next update after a crash, can undo it. From `{project-root}`, with `{runStateHelper}`:

- **Gap-driven mode:** snapshot everything the repair may write in place:

  ```bash
  uv run {runStateHelper} begin --run-dir "{run_dir}" --mode in-place \
      --package "{skill_package}" \
      --forge-version "{forge_version}" \
      --brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"
  ```

  It copies the package (each link as a link), the version's `provenance-map.json` and `evidence-report.md`, and the brief into `{run_dir}/snapshot/`. On a non-zero exit or no JSON, HALT with status `halted-for-write-failure` before writing anything (halt procedure: `phase: "merge:snapshot"`, `path: "{skill_package}"`, `reason: "snapshot-failed: {its failed[], or its message}"`).
- **Every other mode:** record the folders the next section creates:

  ```bash
  uv run {runStateHelper} begin --run-dir "{run_dir}" --mode new-version \
      --created "{skill_group}/{new_version}" \
      --created "{forge_data_folder}/{skill_name}/{new_version}" \
      --staging "{skill_group}/{new_version}.skf-tmp" \
      --skill-group "{skill_group}"
  ```

  Exit 3 (`status` `exists`) is the version-exists halt in step 1 below, with the folder its `path` names. Any other non-zero exit, or no JSON: HALT with status `halted-for-write-failure` before writing anything (halt procedure: `phase: "merge:run-state"`, `path: "{run_dir}"`, its message as `reason`).

**Create the version folder** (every mode but gap-driven). Each version keeps a folder of its own (`knowledge/version-paths.md`), so the previous version stays on disk unchanged and verify-publish.md §8 can point the `active` link at the new one:

1. **Never overwrite a version.** When `begin` above exited 3, `{skill_group}/{new_version}/` or `{forge_data_folder}/{skill_name}/{new_version}/` already exists: HALT with status `halted-for-write-failure` before writing anything: "**Version {new_version} of {skill_name} already exists** at `{the folder that exists}`. Update Skill writes each version into a folder of its own, never overwrites one, and updates the version the `active` link names, which is not {new_version}. If an earlier update stopped after creating {new_version}, delete `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/` by hand, then re-run. If you keep {new_version} on purpose, move both folders out of the way by hand before updating. Drop Skill removes a single version only when the export manifest lists it (`@Ferris DS {skill_name}`, choose {new_version}, with `--purge`); for a skill that was never exported it can only drop every version." The halt procedure takes `phase: "merge:new-version-folder"`, `path: "{the folder that exists}"`, `reason: "version {new_version} already exists; update-skill never overwrites a version"`; its rollback removes nothing, since `begin` recorded nothing. An interrupted update's folders rarely reach this halt: the next update's init.md §1b removes them when it takes over that run's stale lock.
2. **Stage the package.** Resolve `{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {atomicWriteHelper} stage-dir --target "{skill_group}/{new_version}"
   ```

   Bind `{version_staging}` ← `staging`: the empty folder `{skill_group}/{new_version}.skf-tmp` it created (it clears one an interrupted run left).
3. **Copy the current package** `{skill_package}` to `{version_staging}/{skill_name}`, naming both without a trailing `/`, equivalent to `cp -a "{skill_package}" "{version_staging}/{skill_name}"`: SKILL.md, metadata.json, context-snippet.md, `references/`, `scripts/`, `assets/` and every other entry, each link copied as a link and never followed. The files this update does not rewrite carry over to the new version this way.
4. **Write and verify the merged SKILL.md in the staged package**, before anything is published. Use the `Edit` or `Write` tool to write the merged SKILL.md content (UTF-8) to `{version_staging}/{skill_name}/SKILL.md`, and each `references/*.md` the merge changed or added, at any priority, into `{version_staging}/{skill_name}/references/`, and delete from there each one the merge removed. When `counts.exports_moved` of `{run_dir}/change-manifest.json` is above 0, move the moved exports' citations (Priority 2) in the staged package: resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {verifyProvenanceCompletenessHelper} fix \
       --moves "{run_dir}/change-manifest.json" \
       --provenance "{provenance_map_path}" \
       --skill-dir "{version_staging}/{skill_name}" \
       -o "{run_dir}/citation-moves.json"
   ```

   It moves each citation of a `MOVED_EXPORT`, in SKILL.md and every `references/*.md`, once, in one pass, so a chain (`LIMIT` from 6 to 7, `DEFAULT` from 7 to 8) never moves a citation twice, and it changes no provenance map. On exit 0 or 1 with JSON, record its `warnings` (one `provenance:` line per citation it left in place), from `{project-root}`: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warnings-file "{run_dir}/citation-moves.json"`, re-read each file in its `files_written[]` into context and continue. On exit 2, no JSON or no candidate resolves: HALT with status `halted-for-write-failure` before the version is published (halt procedure: `phase: "merge:move-citations"`, `path: "{version_staging}/{skill_name}"`, `reason: "<its stderr, or skf-verify-provenance-completeness.py is missing; re-install SKF>"`); its rollback removes `{version_staging}`. Then, from `{project-root}`, check the [MANUAL] blocks against the inventory merge.md §4 amended:

   ```bash
   uv run {hashContentHelper} manual-verify "{version_staging}/{skill_name}/SKILL.md" \
       --inventory "{manual_inventory}"
   ```

   On `ok` true, continue. On `ok` false, or a failing command: HALT with status `halted-for-manual-mismatch` before the version is published: "**[MANUAL] section integrity failure in the merged SKILL.md.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Nothing was published: the previous version is unchanged." The halt procedure takes `phase: "merge:verify-manual-integrity"`, `path: "{version_staging}/{skill_name}/SKILL.md"`, `reason: "[MANUAL] blocks differ from the approved inventory: modified {modified}; missing {missing}"`, and its rollback removes `{version_staging}`.
5. **Publish it.** Run:

   ```bash
   uv run {atomicWriteHelper} commit-dir --target "{skill_group}/{new_version}"
   ```

   It renames the staged folder to `{skill_group}/{new_version}/` in one step, so no reader ever sees a half-copied version.
6. **Create the forge folder** `{forge_data_folder}/{skill_name}/{new_version}/` and copy into it each of `provenance-map.json`, `evidence-report.md` and `extraction-rules.yaml`: from `{forge_version}` when it is there, else from `{forge_data_folder}/{skill_name}/` when it is there and load-baseline.md §4 bound `{provenance_map_path}` to that flat folder's map (an older skill's flat forge data, `knowledge/version-paths.md`). Copy, never move: the previous version's files and the flat ones stay as they are. Step 5 updates the provenance map and appends this update to the evidence report there; the extraction rules record how the skill was extracted. Test reports, drift reports and result files belong to the version they were made for and stay where they are.
7. **Rebind** `{skill_package}` ← `{skill_group}/{new_version}/{skill_name}` and `{forge_version}` ← `{forge_data_folder}/{skill_name}/{new_version}`. Every later step reads and writes the new version there; `{manual_inventory}` keeps the amended path merge.md §4 bound.

If no `{atomicWriteProbeOrder}` candidate resolves, or the stage, copy, write, publish or forge-folder step fails, HALT with status `halted-for-write-failure`, naming the failed step (for a missing helper: "skf-atomic-write.py is missing; re-install SKF"). The halt procedure takes `phase: "merge:new-version-folder"`, `path: "{skill_group}/{new_version}"`, `reason: "<the failed step>: <its error>"`; its rollback removes what this section created, `{version_staging}`, `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/`, none of which existed before `begin` recorded them. The previous version is unchanged.

**Write the merged files in place** (gap-driven mode only; every other mode wrote them in step 4 above):

1. **The rescopes' brief amendments**, when a manifest entry has a `rescope` (rule R1): write them all in one call. Resolve `{writeSkillBriefHelper}` ← first existing path in `{writeSkillBriefProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {writeSkillBriefHelper} amend --target "{forge_data_folder}/{skill_name}/skill-brief.yaml" <<'SKF_BRIEF_DECISION'
   {"exclude": ["<each rescope's exclude>"], "amendments": [<each rescope's amendment object>]}
   SKF_BRIEF_DECISION
   ```

   Write each payload value as a JSON string: escape `"` and `\`, write a line break or tab inside a value as `\n` or `\t`, and write every path with `/`. It appends each `exclude` path `scope.exclude` does not list and each amendment whose path and category do not already have its action as their latest (`skipped_duplicates` counts the others), so a re-run never adds them twice, and keeps every other field. On a non-zero exit, no JSON or no candidate, HALT with status `halted-for-write-failure` (halt procedure: `phase: "merge:brief-amend"`, `path: "{forge_data_folder}/{skill_name}/skill-brief.yaml"`, `reason: "<its stderr, or skf-write-skill-brief.py is missing; re-install SKF>"`); its rollback restores the brief from the snapshot.
2. **Stage and verify SKILL.md in the run folder.** Write the merged SKILL.md (UTF-8) to `{run_dir}/SKILL.md`, and each `references/*.md` the merge changed or added, at any priority, to `{run_dir}/references/`, and list each one it removed, one `references/<name>.md` path a line, in `{run_dir}/references-removed.txt`, then, from `{project-root}`:

   ```bash
   uv run {hashContentHelper} manual-verify "{run_dir}/SKILL.md" \
       --inventory "{manual_inventory}"
   ```

   On `ok` false, or a failing command: HALT with status `halted-for-manual-mismatch` before the package changes (halt procedure: `phase: "merge:verify-manual-integrity"`, `path: "{run_dir}/SKILL.md"`, `reason: "[MANUAL] blocks differ from the approved inventory: modified {modified}; missing {missing}"`); its rollback restores the brief step 1 amended.
3. **Copy it over the package.** Copy `{run_dir}/SKILL.md` to `{skill_package}/SKILL.md`, and each file in `{run_dir}/references/`, every `references/*.md` the merge changed or added at any priority, into `{skill_package}/references/`, and delete from the package each path `{run_dir}/references-removed.txt` lists.
4. **Move the moved exports' citations** (Priority 2) in the package, when `counts.moved` of `{run_dir}/gap-records.json` is above 0: every file of the package, since step 2 staged only the files the merge changed. Resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {verifyProvenanceCompletenessHelper} fix \
       --moves "{run_dir}/reextract-records.json" \
       --provenance "{provenance_map_path}" \
       --skill-dir "{skill_package}" \
       --manual-inventory "{manual_inventory}" \
       -o "{run_dir}/citation-moves.json"
   ```

   It moves the citations of each record marked `moved` that the provenance map holds, as the version folder's step 4 above says, and checks SKILL.md's [MANUAL] blocks against the inventory after its writes. On `manual_verify.ok` false: HALT with status `halted-for-manual-mismatch`, as step 2's check does (halt procedure: `phase: "merge:verify-manual-integrity"`, `path: "{skill_package}/SKILL.md"`, `reason: "[MANUAL] blocks differ from the approved inventory: modified {modified}; missing {missing}"`). Otherwise act on its exit as that step says, with `path: "{skill_package}"` on a halt, whose rollback restores the package and the brief from the snapshot.

**Rewrite the run context** once the writes above are done, in every mode: write `{run_dir}/run-context.json` again, as load-baseline.md §8 wrote it, with the key `new_version` added and `skill_package`, `forge_version` and `manual_inventory` at their values now (the new version's paths step 7 rebound, outside gap-driven mode, and the inventory merge.md §4 amended), keeping every other key as the file holds it. Step 5 reads a binding it lost back from there.

**Do NOT write here:**
- `metadata.json`, `provenance-map.json`, `evidence-report.md`: derived from the merge output, written by step 5 sections 2–4 (the version folder above only copies the previous version's files, which step 5 then rewrites)
- `context-snippet.md`: regenerated from the on-disk SKILL.md + metadata.json by step 5 section 5

**Halt-on-tool-failure:** If any `Edit`/`Write` call or copy errors (permission denied, disk full, path invalid, etc.), HALT with status `halted-for-write-failure` and report the failure; do not proceed to step 5. The halt procedure takes `phase: "merge:write-skill-md"`, `path: "{the file that failed}"`, `reason: "<the error>"`, and its rollback puts the skill back as it was: it removes `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/` when this run created them, and in gap-driven mode restores the package and the brief from the snapshot.

### 7. Report Progress

Display one line from merge.md §6's counts: "**Merged:** {exports_updated} updated, {exports_added} added, {exports_removed} removed, {manual_sections_preserved} [MANUAL] sections preserved, {manual_conflicts_resolved} conflicts resolved." The report (step 6) shows the full counts.

### 8. Route to Write

Display "**Merge written: proceeding to write...**", then load, read the full file, and execute {nextStepFile}: a clean merge and one whose conflicts merge.md §4 resolved go straight on, since §6b has written the merge.
