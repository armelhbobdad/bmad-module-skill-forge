---
nextStepFile: 'report.md'
# Resolve `{descriptionGuardHelper}` by probing `{descriptionGuardProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback);
# first existing path wins. HALT if neither resolves — letting an external
# tool's rewrite of the merged description field stand would silently
# regress discovery quality and re-introduce angle-bracket tokens.
descriptionGuardProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-description-guard.py'
  - '{project-root}/src/shared/scripts/skf-description-guard.py'
# Resolve `{updateActiveSymlinkHelper}` to the first existing path; HALT if
# neither candidate exists. §8 uses it to atomically flip the active
# symlink; §8a uses it (verify mode) to confirm the post-state. Without
# the helper, an "rm and recreate" pattern would leave a brief window where
# concurrent readers see a missing symlink.
updateActiveSymlinkProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-active-symlink.py'
  - '{project-root}/src/shared/scripts/skf-update-active-symlink.py'
# Resolve `{verifyProvenanceCompletenessHelper}` to the first existing path.
# Advisory: if neither resolves, §3b and §6 relabel nothing (each label
# violation and node-kind finding is a WARN), and §6 records `Provenance:
# SKIP (verifier missing; re-install SKF)` with a warning: the files it
# checks are already written, and no set is compared by hand.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# Resolve `{extractionPatternsData}` to the first existing path. If neither
# exists, §3b relabels nothing and §6 fixes no node kind: list each label
# violation and each node-kind finding as a WARN.
extractionPatternsDataProbeOrder:
  - '{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md'
  - '{project-root}/src/skf-create-skill/references/extraction-patterns.md'
# Resolve `{hashContentHelper}` to the first existing path; HALT if neither
# candidate exists. §1 and §7 use its `manual-verify` subcommand to verify
# SKILL.md against the byte-exact [MANUAL] inventory step 4 §4 amended; a
# marker-count comparison would pass a block whose interior was truncated
# without changing the marker count. §7 also runs its `hash` subcommand
# around `skill-check --fix` to tell whether the call changed SKILL.md.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# Resolve `{renderMetadataStatsHelper}` by probing `{renderMetadataStatsProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. HALT if neither resolves: §3b's `stats` block and
# `confidence_distribution` are computed values that must not be hand-binned,
# and this is the same helper sibling create-skill compiles them with.
renderMetadataStatsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-metadata-stats.py'
  - '{project-root}/src/shared/scripts/skf-render-metadata-stats.py'
# Resolve `{sourceTreeHelper}` to the first existing path. §9 uses its
# `advance` subcommand to move the workspace clone to the commit §3b
# recorded. If neither path exists, skip the call and continue: it never
# gates the workflow.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
# Resolve `{cccGitHygieneHelper}` to the first existing path. It keeps ccc's
# index folders and SKF's workspace lock out of git, and undoes the
# `.gitignore` edit `ccc init` makes in a workspace clone. If neither path
# exists, skip the call and continue: it never gates the workflow.
cccGitHygieneProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-ccc-git-hygiene.py'
  - '{project-root}/src/shared/scripts/skf-ccc-git-hygiene.py'
# Resolve `{checkWorkspaceDriftHelper}` to the first existing path. §9
# passes it to the advance, which moves the workspace clone only when the
# helper confirms the clone still holds the skill's previous commit. If
# neither path exists, run the advance without `--drift-helper`: it then
# leaves an existing clone where it is (`head-unverified`), and §9 warns.
checkWorkspaceDriftProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-check-workspace-drift.py'
  - '{project-root}/src/shared/scripts/skf-check-workspace-drift.py'
# Resolve `{buildChangeManifestHelper}` to the first existing path; HALT if
# neither exists: §3's `apply` writes the provenance map and §3b's `metadata`
# call metadata.json, from this run's records, never by hand.
buildChangeManifestProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-build-change-manifest.py'
  - '{project-root}/src/shared/scripts/skf-build-change-manifest.py'
# Resolve `{compareDocHashesHelper}` to the first existing path when step 2
# wrote `{run_dir}/doc-hashes.json` (a docs-only skill); HALT if neither
# exists: §3b records the changed documents' new hashes with its
# `refresh-hashes`, so the next update does not find them changed again.
compareDocHashesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
# Resolve `{validateOutputHelper}` to the first existing path when §7 finds no
# skill-check. If neither exists, §7 records the spec check as skipped.
validateOutputProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-output.py'
  - '{project-root}/src/shared/scripts/skf-validate-output.py'
# Resolve `{securityScanHelper}` to the first existing path. §7 runs it on
# the written package; if neither path exists, §7 records the scan as
# skipped and continues: the scan is optional and never gates the workflow.
securityScanProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-security-scan.py'
  - '{project-root}/src/shared/scripts/skf-security-scan.py'
# Resolve `{shardBodyHelper}` to the first existing path. §7 splits an
# oversized body with it when skill-check reports `body.max_lines` or
# `body.max_tokens`. If neither exists, §7 falls back to `skill-check
# split-body` for `body.max_lines` when SKILL.md holds no [MANUAL] block,
# and otherwise splits nothing and records a WARN.
shardBodyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-shard-body.py'
  - '{project-root}/src/shared/scripts/skf-shard-body.py'
# Resolve `{rebuildManagedSectionsHelper}` to the first existing path: §5
# reads and writes the snippet's gotchas line with its `gotchas` action.
# HALT if neither exists.
rebuildManagedSectionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py'
  - '{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py'
# `{extractPublicApiHelper}`: §3b's public API counts, the runner's or those
# `{entryPointsByHandData}` has it make; if neither exists, §3b halts.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
entryPointsByHandData: 'skf-create-skill/references/entry-points-by-hand.md'
# SKILL.md binds `{emitEnvelopeHelper}` and `{runStateHelper}` for every
# stage; resolve them again when a binding was lost: first existing path wins.
# The warnings go to the run log through the first; the halt procedure and
# §10's finish run the second.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runStateProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-run-state.py'
  - '{project-root}/src/shared/scripts/skf-update-run-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Write Updated Files

## STEP GOAL:

Verify the merged SKILL.md that step 4 section 6b wrote to disk, write the derived artifacts (metadata.json, provenance-map.json, evidence-report.md, context-snippet.md), check the written package, and only then point the active symlink at the new version.

## Rules

- Focus only on verifying merged files and writing derived artifacts — merge content was already written in step 4
- Do not modify merged SKILL.md or `references/` content, apart from §6's citation line and prefix fixes outside `[MANUAL]` blocks, and §7's `skill-check check --fix` edits and body split, which moves no section that holds a `[MANUAL]` block; §7 re-checks the [MANUAL] blocks after them. Any mismatch detected during verification triggers HALT, not repair
- Do not skip provenance map update — critical for future audits
- HALT immediately on verification failure: §1 halts before any derived artifact is written, and §8 points the `active` link at the new version only after §6 and §7, the last checks that can halt, so every halt in this step rolls back a version no reader sees yet. A partial-write skill package is worse than an unchanged one
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}` and `{runStateHelper}` in `{runStateProbeOrder}`.

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the `{runStateHelper}` `halt` call below.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version the run started from>", "previous_version": "<the same>", "update_mode": "<normal, gap-driven or degraded>", "files_written": [<what stands: none after a rollback; the artifacts this step wrote when the helper kept a live version>]}
SKF_JSON
```

Pass `--tree` when init.md §6b bound `{source_tree}`, always `--lock` and `--owner`, and `--emit` in `{headless_mode}`. Until §10 closes the window, the helper first undoes what this run wrote: in gap-driven mode it restores the package, the version's provenance map and evidence report, and the skill brief from the snapshot step 4 §6b took; in every other mode it removes the version folders step 4 created, unless the `active` link already names them (§8), which keeps that version, now the skill's live one (its `kept`). Then it removes the private source tree, releases the run lock (never one another run holds) and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line through the shared emitter, which adds the decisions recorded so far, the `error` object and a warning for each step the helper could not finish (`rollback-incomplete`, `source-tree-not-removed`, `run-lock-not-released`); it never stops on a result. Tell the user in one line what it restored, removed or kept, and name each path its `failed[]` lists for the user to restore or delete by hand. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "write:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place.

A `Write` or `Edit` call in §2 to §5 that errors (permission denied, disk full, path invalid) HALTs with status `halted-for-write-failure`: the halt procedure takes `phase: "write:artifact-write"`, `path: "{the file that failed}"`, `reason: "<the error>"`. §6 checks what `metadata.json` and `provenance-map.json` hold.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 0. Description Guard Protocol

**Used by:** §7 (`skill-check check --fix`, the `{shardBodyHelper}` body split and `skill-check split-body --write`).

The deterministic phases are executed via `{descriptionGuardHelper}`: §7 invokes the helper at the capture and verify-restore points around every `skill-check` call.

**Guard outputs.** Each `capture`, run while the in-context SKILL.md copy matches the file on disk, writes the description it reads from `{skill_package}/SKILL.md` to `{run_dir}/description-guard.json`, and each `verify-restore` reads it there with `--captured-file`, so the description never passes through a shell string. Bind `{guarded_description}` ← that file's `description`. Bind `{guard_restored}` ← `restored` and `{guard_diff_kind}` ← `diff_kind` from each `verify-restore`. When `{guard_restored}` is true, set the in-context `description` to `{guarded_description}` so later sections do not work from the tool-mutated value, and record `description_guard_restored: true` with the tool name and `description_guard_diff_kind: {guard_diff_kind}` in workflow context for the evidence report (§4). A later `verify-restore` that exits 0 with `{guard_restored}` false leaves those records in place.

**Empty-snapshot rule.** `verify-restore` refuses an empty or whitespace-only description in `{run_dir}/description-guard.json`, and a file it cannot read (exit 1, file untouched). Never re-run it with the empty value: writing it back would blank the field the guard protects. If the merged description is still in context (the in-context SKILL.md copy), re-run `verify-restore` with that value: write `{"description": <that value as a JSON string>}` to `{run_dir}/description-guard.json` with a file write, never `echo` (the value can hold quotes, `$` or backticks), and run the same `verify-restore` line again, once. Otherwise, or when that re-run exits 1 too, record `description_guard_restored: false` and `description_guard_refused: empty-capture` with the tool name; the evidence report (§4) renders that as a fired guard, not as a clean run.

### 1. Verify SKILL.md Write

SKILL.md was written in step 4 section 6b. Verify the write landed intact before proceeding to any derived-artifact writes.

- Verify the resolved `{skill_package}` path matches the version directory step 4 wrote to (outside gap-driven mode, step 4 §6b created `{skill_group}/{new_version}/` and rebound `{skill_package}` and `{forge_version}` to the new version)
- Run the deterministic [MANUAL]-integrity verifier against the byte-exact inventory step 4 §4 amended with the user's [MANUAL] decisions (the step 1 §5 inventory, when there were none):

  ```bash
  uv run {hashContentHelper} manual-verify "{skill_package}/SKILL.md" \
      --inventory "{manual_inventory}"
  ```

  The verdict JSON is `{"preserved":[...], "modified":[...], "missing":[...], "moved":[...], "ok":bool}`. A `modified` block is one whose byte-exact interior changed (an interior truncation); a `missing` block lost its markers entirely; a `moved` block is byte-identical but relocated with its logical parent section (clean — does not fail the gate). `ok == (modified empty AND missing empty)`.
- If `ok == true` and the path resolves: proceed to section 2. Step 4 §6b checked the same file against the same inventory before it published it, so this is the confirmation that the write landed
- **If `ok == false`: HALT immediately** with status `halted-for-manual-mismatch`. Do not write `metadata.json`, `provenance-map.json`, or any other artifact: further writes would compound the inconsistency. The halt procedure takes `phase: "write:verify-manual-integrity"`, `path: "{skill_package}/SKILL.md"`, `reason: "[MANUAL] blocks differ from the approved inventory: modified {modified}; missing {missing}"`. Alert the user:

  "**[MANUAL] section integrity failure after write.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Relocated-but-intact (advisory only): {moved}. Verified against the inventory `{manual_inventory}`, on disk at `{skill_package}/SKILL.md`. {manual_recovery}"

  `{manual_recovery}` depends on the mode:

  - **Outside gap-driven mode** (step 4 §6b created a new version folder): "The previous version at `{skill_group}/{baseline_version}/` is unchanged, and the halt removed `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/`, which step 4 created for this update: re-run update-skill."
  - **Gap-driven mode** (the repair edited the current version in place): "The halt restored the package, with its [MANUAL] blocks, its provenance map and evidence report, and the skill brief, from the snapshot step 4 took before its first write: the skill is as it was. Re-run update-skill."

### 2. Prepare the Write Inputs

Prepare what §3's `apply` and §3b's `metadata` call read, before either runs:
- **Apply the queued metadata patches.** When merge Priority 8b wrote `{run_dir}/metadata-patches.json` (gap-driven `metadata update` entries; no file, no patch), set in `{skill_package}/metadata.json`, before §3's `apply` reads it, each field of the `set` of each of its `metadata_patches[]` (`a.b` names a nested field). Leave out a field §3b's `metadata` call writes (its `--help` lists them, e.g., `exports_documented`), whose value it would overwrite, and `exports[]`, which §3's `apply` builds from the list it reads. For each field, append the record `metadata_patch_outcome: {gap_id, field, outcome, why}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `metadata_patch_outcome`: `outcome` `applied` with `why` null, or `left-out` with `why` the reason (`the metadata call writes it`, `apply builds exports[]`). §3b adds a `dropped` line for an applied field the call drops, so a still-stale value surfaces in both reports rather than being silently overwritten.
- `--version "{new_version}"` is the version step 4 §6b chose; never pick another. From here on `{version}` is `{new_version}`.
- Bind `{generation_date}` ← the current UTC time to the second, read from the clock with `date -u +%Y-%m-%dT%H:%M:%SZ`, never typed: step 1 §4b offers a test report only when it is newer. It is the only update bookkeeping metadata.json carries, in every mode: §3's update operation block records `last_update` and `update_type` in provenance-map.json, and the `metadata` call removes either key an older SKF version left in metadata.json.
- **Record the source commit** (when `{source_tree_status}` is `ready` or `offline`): pass `--source-commit "{target_commit}"` to §3b's `metadata` call, the commit every step of this run read, and, when `{target_ref_override}` is set, `--source-ref "{target_ref}"`. The call leaves `source_root` as metadata.json records it: it names the clone SKF keeps for the repository; never write `{source_tree}` or any other path of this run into an artifact. For any other source (a local folder, gap-driven mode, docs-only) pass neither, which keeps both. When `{source_root_override}` is set (init.md §6: a local source that moved, named by `--source-root` or by the user), also pass `--source-root "{source_root_override}"`, gap-driven mode included, so later runs read the source there; otherwise the call leaves `source_root` as it is. Bind `{map_source_commit}` ← `{target_commit}` when `{source_tree_status}` is `ready` or `offline`, else the `source_commit` metadata.json records, and `{map_source_ref}` ← `{target_ref}` when `{target_ref_override}` is set, else its `source_ref`, each `""` for a null one: the values §3b's call leaves in metadata.json, which §3's `apply` writes to the map. The in-context `{source_commit}` stays the value init.md §6 read; §9 needs it.

### 3. Write Updated provenance-map.json

Write `{forge_version}/provenance-map.json` with `{buildChangeManifestHelper}` `apply` (resolve it ← first existing path in `{buildChangeManifestProbeOrder}`), never by hand: it reads `{provenance_map_path}`, the map the update started from (init.md §4: the current version's map, else the flat one an older skill keeps in `{forge_data_folder}/{skill_name}/`), and this run's records in `{run_dir}`, and writes the whole updated map through a temporary file and one rename. When step 4 §6b created a new version, `{forge_version}` is its forge folder, which holds a copy of the previous map when there was one, the same bytes `apply` reads: write the whole updated map there, and leave the previous version's map as it was. In a repair `{provenance_map_path}` is the only map there is: `apply` writes the updated map to `{forge_version}`, and a flat map stays as it was. A repair of a skill whose forge data is flat (init.md §4 bound the flat map) may find no forge folder for its version, and `apply` writes only into a folder that exists. In gap-driven mode, first create it, as report.md §5b does. From `{project-root}`, run:

```bash
mkdir -p "{forge_version}"
```

On a non-zero exit, HALT with status `halted-for-write-failure` before `apply` runs: display "**The forge folder of this version of {skill_name} could not be created** at `{forge_version}`: {its stderr}. This repair already wrote SKILL.md in place; the halt restored the package and the skill brief from the snapshot step 4 took, so the skill is as it was. Make `{forge_data_folder}/{skill_name}/` writable, or move what is at `{forge_version}` out of the way, then re-run update-skill." The halt procedure takes `phase: "write:provenance-map"`, `path: "{forge_version}"`, `reason: "forge-folder-not-created: <its stderr>"`. Then, in a repair whose `{provenance_map_path}` is the flat map, copy into `{forge_version}` each of `evidence-report.md` and `extraction-rules.yaml` from `{forge_data_folder}/{skill_name}/` when it is there and `{forge_version}` does not hold it yet. Copy, never move: the flat files stay as they are, and a file `{forge_version}` already holds is never overwritten. §4 appends this update to the evidence report there; the extraction rules record how the skill was extracted. When a copy fails, HALT with the same status and phase, `path: "{forge_version}/<the file>"` and `reason: "forge-file-not-copied: <its error>"`. A later halt removes the map and evidence report this run writes or copies there, which `begin` found absent, and leaves the folder empty but for a copied `extraction-rules.yaml`, a copy of the flat file and harmless; every reader looks for a file in it and falls back to the flat one, so an empty folder reads as none. Then, from `{project-root}`, run:

```bash
uv run {buildChangeManifestHelper} apply \
    --update-type "{update_type}" \
    [--provenance-map "{provenance_map_path}"] \
    [--manifest "{run_dir}/change-manifest.json"] \
    [--category-c "{run_dir}/category-c.json"] \
    [--ccc-pairs "{run_dir}/ccc-pairs.json"] \
    [--extraction "{run_dir}/extraction.json"] \
    [--export-details "{run_dir}/export-details.json"] \
    [--reextract-records "{run_dir}/reextract-records.json"] \
    [--merge-records "{run_dir}/merge-records.json"] \
    [--file-compare "{run_dir}/category-d-compare.json"] \
    [--new-files "{run_dir}/new-files.json"] \
    [--promoted-docs "{run_dir}/promoted-docs.json"] \
    [--source-root "{source_root}"] \
    --skill-name "{skill_name}" \
    --generation-date "{generation_date}" \
    [--test-report-run-id "{test_report_run_id}"] \
    --confidence-tier "{forge_tier}" \
    --manual-sections-preserved "{manual_sections_preserved}" \
    --source-commit "{map_source_commit}" \
    --source-ref "{map_source_ref}" \
    [--drift-head "{head_short_sha}" --drift-pinned "{pinned_short_sha}"] \
    --metadata-in "{skill_package}/metadata.json" \
    --lists-out "{run_dir}/metadata-lists.json" \
    -o "{forge_version}/provenance-map.json" \
    > "{run_dir}/apply.json"
```

`{update_type}` follows the run's mode as report.md §2 names it (`{update_mode}`): `incremental` for `normal`, `gap-driven` for `gap-driven`, `full` for `degraded` (a degraded run has no map: leave out `--provenance-map`, and `apply` starts a new one). Pass each `{run_dir}` file the run wrote: the change manifest and the records in every mode, `category-c.json` and `ccc-pairs.json` (step 2's Category C and its CCC check), `extraction.json` and `export-details.json` when step 2 wrote them, `merge-records.json` when step 4 did, the Category D files (`category-d-compare.json`, and `new-files.json` when step 2 wrote it: a skill with no brief has none) with `--source-root` when step 2 ran Category D, and `promoted-docs.json` when step 2 §1b wrote it. `{generation_date}` is the value §2 bound, `--test-report-run-id` goes only with a gap-driven run (the `{test_report_run_id}` of the report it applied), `{manual_sections_preserved}` is `len(preserved) + len(moved)` from the §1 `manual-verify` verdict (never a marker count), and `{map_source_commit}` and `{map_source_ref}` are the values §2 bound, the `source_commit` and `source_ref` §3b's `metadata` call leaves in `metadata.json` (an empty string for a null one): audit-skill reads its baseline commit from the map's top-level `source_commit` and `source_ref`. Pass `--drift-head` and `--drift-pinned` only when `{workspace_drift_status}` is `overridden` (gap-driven.md §3). Pass `--metadata-in` and `--lists-out` in every mode: `apply` writes there the lists §3b's `metadata` call reads. Every entry `apply` writes carries `signature_source`, which §3b's stats helper bins (an entry the map held with none, or with a value other than `T1`, `T1-low`, `T2` or `T3`, as a map written before the key existed does, takes its `confidence` when that is `T1-low`, `T2` or `T3`, else `T1` when its `extraction_method` is `ast-grep` or `ast_bridge`, else `T1-low`), and `apply` sets the map's update operation block (`"last_update"`, `"update_type"` and its other keys), replacing an earlier update's.

Dispatch on its exit code:

- **0:** it printed `{status: "written", entries, not_public, relabeled, signature_source_backfilled, file_entries, warnings, map}` to `{run_dir}/apply.json`. Bind `{provenance_spot_check_warnings}` ← its `warnings`, and add each to `warnings[]`, recording them in one call, from `{project-root}`: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warnings-file "{run_dir}/apply.json"`; the update report lists each as a WARN (report.md §2). In gap-driven mode a `NEW_EXPORT` or `MODIFIED_EXPORT` the map holds whose spot-check ended `missing` or `unknown` keeps its entry unchanged, whatever its severity, with one of these warnings, which names the cause of an `unknown` (several map entries of its name, no definition line or several at the entry, a file no rule covers, a failed or skipped check, a citation of another file than the map's entries of its name); for a blocking gap (any severity but `Medium`, `Low` or `Info`) it also names the gap and the one fix a re-run acts on (gap-driven.md §4 bullet 1): fix the entry by hand, or, for several entries of its name, give the gap a `file:line` Source at the definition when that file holds only one of them, then re-run update-skill. A `cited-elsewhere` gap, whatever its severity, takes its own warning and fix in their place (gap-driven.md §4 bullet 1). A rule R5 `MOVED_EXPORT` whose map entry's file is gone keeps its entry unchanged too, whatever its severity, with a warning that names the file and the hand fix. An `outside-scope` gap (the skill brief's scope leaves out the file it names), whatever its severity, adds no entry, a placeholder included, and is never refused, with its own warning, which names the files left out and the fix: when the skill covers that file, change the brief's scope so it takes it (its `scope.include` or `scope.exclude`), then re-run update-skill; otherwise re-run Test Skill (gap-driven.md §4 bullet 1). `not_public` lists, `{name, file}`, each new export of a `public-api` skill it did not add in normal mode as off the public surface (the `public: false` mark of `reextract-records.json`, else the same rule over the `scope.type` and `entry_point_diff` of `extraction.json`), and one of its `warnings` counts them. When `extraction.json` names `public-api` but gives no surface the rule can read (Quick tier, a runner failure, an incomplete run), it adds every name, with one warning that says so. `relabeled` lists, `{name, file, from, to}`, each entry whose `signature_source` a gap-driven repair changed when it wrote the signature §4a's record gave (a record read by eye moves an `ast-grep` entry from T1 to T1-low), each with one of its `warnings`: §3b adds each name to `{provenance_relabels}`. `signature_source_backfilled` counts, by value, the entries it gave a `signature_source` because they lacked or held an unrecognized one (`{"T1-low": 2}`, `{}` when none), with one of its `warnings`, which also lists each unrecognized value it replaced (`name: old -> new`); it does not list them in `entries.updated`. In a map naming several libraries, one of its `warnings` counts and names each new entry it gave the map's first `source_library` because the entry's file or folder did not settle which (`<name> in <file>`, or `<name> (no file)`): check that entry's `source_library` in `{forge_version}/provenance-map.json` and correct it by hand when it names the wrong library.
- **3** (`status` `refused`): a blocking gap reached the provenance write with no source line (`blocking_unresolved[]`: a `NEW_EXPORT` the map does not hold, `unknown` for any cause but `outside-scope`, with a severity other than `Medium`, `Low` or `Info`, a missing one included). gap-driven.md §4 sends every such gap to its §4a and halts with `halted-for-remediation-path` before merge when §4a does not find it, so this happens only when that check was skipped or bypassed: `apply` wrote nothing, and no null citation is written. HALT with status `blocked` and write no `metadata.json`, `provenance-map.json` or other artifact. Tell the user: "**A blocking gap reached the provenance write with no source line:** {each export name, with its severity or "no severity"}. gap-driven.md §4 should have stopped on it with `halted-for-remediation-path`. The halt restored SKILL.md and references/ from the snapshot step 4 took; give each gap a `file:line` Source or name the file that defines its export in its Remediation (or downgrade it to Medium, Low or Info), then re-run update-skill." The halt procedure takes `phase: "write:provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "blocking-gap-unresolved: {export names}: gap-driven.md §4 should have halted with halted-for-remediation-path"`.
- **Exit 1, no JSON, or no candidate resolves:** HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "<its stderr, or skf-build-change-manifest.py is missing; re-install SKF>"`).

**For script/asset file changes:** `apply` updates the rows; copy or remove the files themselves in `{skill_package}`, each path the change manifest's `category_d` lists: a `scripts_*` path under `scripts/`, an `assets_*` path under `assets/`:
- MODIFIED_FILE (`*_modified`): copy the file from `{source_root}` (the row's `content_hash` is updated by `apply`)
- DELETED_FILE (`*_deleted`): remove the file
- NEW_FILE (`*_added`): copy the file from `{source_root}` (`apply` adds its row)
- A `docs_*` path is source-tracked, never bundled: copy and remove nothing for it.

### 3b. Write Updated metadata.json

The `metadata` call below writes `{skill_package}/metadata.json` from the map and the lists §3's `apply` wrote, never by hand:
- **Compute the `stats` block and `confidence_distribution` deterministically** with `{renderMetadataStatsHelper}` (resolve from `{renderMetadataStatsProbeOrder}`; first existing path wins): the same helper sibling create-skill compiles them with, so create and update emit byte-identical stats for identical inputs. The helper owns all the arithmetic: it bins each provenance `entries[]` row once by its `signature_source` tier into `confidence_distribution.{t1,t1_low,t2,t3}`, sets `exports_documented` = the entry count for the library shape (for a reference app, the Pattern Surface row count; see **Shape** below), and derives `exports_total` = `exports_public_api` + `exports_internal`, `public_api_coverage` = documented / public_api (`null` if public_api is 0), `total_coverage` = documented / total (`null` if total is 0), plus `scripts_count` / `assets_count` from the inventory arrays. Run `uv run {renderMetadataStatsHelper} --help` for the full contract. You supply only the payload:

  **Payload (passed as JSON on stdin):**
  - `exports_public_api` and `exports_internal`, unless the drift override below applies. At Quick tier, count them by `{entryPointsByHandData}`, as create-skill does, and pass the `counts` of `{run_dir}/denominator.json`. Otherwise, from `{project-root}`, run `uv run {extractPublicApiHelper} --mode full --source-root "{source_root}" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] [--language "{language}"] [--scope-type "{scope_type}"] --head-cap 0 -o "{run_dir}/public-api.json"` once over the whole scope (no `--files-from`), with the longest timeout your shell tool takes (a large tree takes minutes), as create-skill's extract.md §4 does, and pass its `counts.exports_public_api` and `counts.exports_internal`, as its compile.md §4 does. Pass `--brief` when that file exists (step 4 §6b wrote a rescope's amendment into it), and `--language` and `--scope-type` when metadata.json records them. On exit 1 (`incomplete`) run it once more. In gap-driven mode, gap-driven.md §4 already ran it over the same scope when it wrote `{run_dir}/public-api.json` with `status` `ok` and `counts.rescoped` of `{run_dir}/gap-records.json` is 0 (no rescope amended that scope): then read that JSON as this bullet says instead of running it again. When its `files_without_recipes` is not empty (in-scope files no recipe reads), count those files' entry points' names by steps 2 to 4 of `{entryPointsByHandData}`, with `--extraction "{run_dir}/public-api.json"`, as create-skill's extract.md §4b does, and pass the `counts` of `{run_dir}/denominator.json` in place of the runner's: they hold its names. Still incomplete, or on exit 2 or 3, no JSON, no candidate, or `entry_points.status` `no-entry-point`, count them by `{entryPointsByHandData}` and pass the `counts` of `{run_dir}/denominator.json`. On exit 2 (an input error, such as a skill brief it cannot read, or a failure it did not foresee), also add `public-api-counted-by-hand: {line}` to `warnings[]`, `{line}` being the stderr line that holds `error:`, recorded as **Warnings go to the run log** says, and show it to the user: the runner should have made these counts. When a call of `{entryPointsByHandData}` fails as its step 4 says, HALT with status `blocked` (halt procedure: `phase: "write:public-api"`, its `error:` line, or the helper that does not resolve, as `reason`). A docs-only skill has no tree to count: pass the values metadata.json records, as the drift override does.
  - `effective_denominator`: the `counts.effective_denominator` of the JSON whose two counts you passed above, when its `counts.effective_denominator_decision.store` is true and the skill brief's `scope.notes` documents the stratification: `skf-extract-public-api.py` decides `store` as it does for create-skill, so the count follows the source and the brief this update read. Under the drift override, and for a docs-only skill, pass the value `stats.effective_denominator` records once the queued `metadata_patches[]` are applied, when it records one. Otherwise leave it out, and `metadata.json` keeps no `stats.effective_denominator`: remove one an earlier run recorded.
  - `scripts` / `assets`: the scripts / assets inventory arrays (or `[]` when empty); the helper sets `scripts_count` / `assets_count` from their lengths
  - `pattern_surfaces_documented` (reference app only): none in the payload, and never typed. `--skill-md "{skill_package}/SKILL.md"` has the helper count the data rows of the merged SKILL.md's `## Pattern Surface` tables, as create-skill's compile.md §4 has it do. The helper uses the count as `exports_documented` and emits it as `stats.pattern_surfaces_documented`, the count test-skill measures a reference app's coverage by.

  **Public API counts under the drift override** (`{workspace_drift_status}` is `overridden`, gap-driven.md §3): count nothing at `{source_root}`, which is HEAD, not the pinned commit. Pass as `exports_public_api` and `exports_internal` the values `{skill_package}/metadata.json` records in `stats` once the queued `metadata_patches[]` above are applied (0 for one it does not record, with a WARN).

  **Shape:** read `scope_type` from `{skill_package}/metadata.json` before this section rewrites it (create-skill records the brief's `scope.type` there). When it is `reference-app`, pass `--shape reference-app` and `--skill-md "{skill_package}/SKILL.md"`, which counts `pattern_surfaces_documented`, as create-skill's compile.md §4 does; for any other `scope_type`, or none, pass no `--shape` (the helper's default, the library shape).

  **Invoke**: the helper reads the `entries[]` of the map §3's `apply` wrote; the scripts / assets inventory arrays are the `scripts` and `assets` lists `apply` wrote to `{run_dir}/metadata-lists.json`:

  ```bash
  echo '{"exports_public_api": {N}, "exports_internal": {M}, "scripts": {scripts-inventory-or-[]}, "assets": {assets-inventory-or-[]}}' \
    | uv run {renderMetadataStatsHelper} {forge_version}/provenance-map.json -o "{run_dir}/stats.json"
  ```

  For a reference app, the same call with the shape and the SKILL.md whose Pattern Surface rows it counts:

  ```bash
  echo '{"exports_public_api": {N}, "exports_internal": {M}, "scripts": {scripts-inventory-or-[]}, "assets": {assets-inventory-or-[]}}' \
    | uv run {renderMetadataStatsHelper} {forge_version}/provenance-map.json --shape reference-app --skill-md "{skill_package}/SKILL.md" -o "{run_dir}/stats.json"
  ```

  On its exit 2 (SKILL.md has no `Pattern Surface` heading or cannot be read, or the scan helper beside it is missing), HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:stats"`, `path: "{skill_package}/SKILL.md"`, its stderr as `reason`).

  If its `coherence.ok` (in `{run_dir}/stats.json`, which the `metadata` call reads) is false, fix the provenance map and re-run the helper; never hand-edit the stats. A `confidence_distribution` violation means some provenance entries carry a missing or unrecognized `signature_source`, which only an edit made after §3's `apply` leaves: `apply` gives every entry one, so set each the way it does (its `confidence` when that is `T1-low`, `T2` or `T3`, else `T1` when its `extraction_method` is `ast-grep` or `ast_bridge`, else `T1-low`).

  **Label violations.** A violation whose `field` is `provenance.entries[<i>].<field>` means entry `<i>` (its `export_name` is in the violation) carries a label its `extraction_method` does not allow: relabel it by the `## Relabel Rule` section of `{extractionPatternsData}`, which the verifier's `relabel` below applies, with `{source_root}` as the tree its node-kind lookup reads; never relabel an entry by hand. **Under the drift override** (`{workspace_drift_status}` is `overridden`, gap-driven.md §3) run no recipe at `{source_root}`, so no `kind-at`: HEAD is not the pinned commit, so a kind read there says nothing about the entry. Pass `--no-kind-at`: it leaves each violation that needs a kind from the tree in place (`kind-at-skipped`); list it as a WARN ending ` (drift override: HEAD {head_short_sha} is not pinned {pinned_short_sha})`; a relabel that reads nothing from the tree still applies. With the status `ok` or `skipped`, run the lookup as the rule says: pass `--source-root "{source_root}"` when there is a local source tree. This relabel applies to every entry the helper flags, including a gap-driven `verified` entry (§3). Resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}` and `{extractionPatternsData}` ← first existing path in `{extractionPatternsDataProbeOrder}`, and, from `{project-root}`, run:

  ```bash
  uv run {verifyProvenanceCompletenessHelper} relabel \
      --provenance "{forge_version}/provenance-map.json" \
      --violations "{run_dir}/stats.json" \
      --recipes "{extractionPatternsData}" \
      [--records "{run_dir}/reextract-records.json"] \
      [--source-root "{source_root}"] [--no-kind-at] \
      -o "{run_dir}/relabel.json"
  ```

  Pass `--records` when that file exists: an entry's record there names the recipe that matched it and the tool that produced it. On exit 0 or 1 it printed `relabeled[]` (each field it set, with `from` and `to`) and `left_as_warn[]` (each label it left, with its `why`), and wrote the map through one rename when its `files_written[]` names it: re-read the map into §3's in-context copy, list each left item as a WARN, then re-run the helper with the same payload, `--shape` and `-o` (and `--skill-md` for a reference app), whose file the `metadata` call reads: a relabeled `signature_source` moves the distribution, and a violation left as a WARN does not block the write. With no candidate for either, or on exit 2 (then with its stderr line), relabel nothing and list each label violation as a WARN. Record the export names of `relabeled[]`, each item left, and each name §3's `apply` listed in `relabeled`, as `{provenance_relabels}` in workflow context: the update report lists them under its Confidence Tier Breakdown (report.md), so no entry moves from T1 to T1-low unannounced.
- **Write metadata.json** once the stats helper's last run wrote `{run_dir}/stats.json`. From `{project-root}`, run:

  ```bash
  uv run {buildChangeManifestHelper} metadata \
      --metadata "{skill_package}/metadata.json" \
      --lists "{run_dir}/metadata-lists.json" \
      --stats "{run_dir}/stats.json" \
      --version "{new_version}" \
      --generation-date "{generation_date}" \
      --skf-root "{project-root}/_bmad/skf" \
      [--extraction "{run_dir}/extraction.json"] [--qmd-version "{qmd_version}"] \
      [--source-commit "{target_commit}"] [--source-ref "{target_ref}"] \
      [--source-root "{source_root_override}"]
  ```

  It sets `tool_versions` to the toolchain this run used, as create-skill stamps it: `skf` read from the installed SKF under `--skf-root`, `ast_grep` from the `ast_grep.version` of `--extraction`, `qmd` from `--qmd-version`; a tool this run did not use keeps the version metadata.json records. Pass `--extraction` when step 2 wrote `{run_dir}/extraction.json`, and `--qmd-version` when re-extract.md §3 queried QMD and bound `{qmd_version}`. Pass `--source-commit`, `--source-ref` and `--source-root` as §2's **Record the source commit** says. When the `effective_denominator` this run stores differs from the one metadata.json records, or only one of them has one, it drops each `effective_denominator_*` stats key, which explained the old count; `dropped_stats` lists each key it drops, a stats helper field this run's stats left out included. On exit 0, add each of its `warnings` to `warnings[]`, recorded as **Warnings go to the run log** says, so the report lists each dropped key, each `unknown` tool version and each stats key create-skill does not write that an earlier run left. Leave out only a warning that a stats key was `kept from an earlier run` when this run's `metadata_patches[]` wrote that key; a dropped key's warning always goes to `warnings[]`. Then, for each `stats.<key>` field §2 applied (its `metadata_patch_outcome` line reads `applied`) whose `<key>` the call's `dropped_stats` names, append one more `metadata_patch_outcome` line to `{run_dir}/evidence-records.jsonl`, with `outcome` `dropped` and `why` `the metadata call dropped it`, under the `gap_id` and `field` of that `applied` line.

  On exit 1, fix the input its stderr names and run it again; when it fails again, prints no JSON or no candidate resolves, HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:metadata"`, `path: "{skill_package}/metadata.json"`, `reason: "<its stderr>"`).

**A docs-only skill's document hashes.** When step 2 wrote `{run_dir}/doc-hashes.json` (its docs-only branch), record the new hash of each document it found changed, after the writes above, so the next update compares against the documents this one read. Resolve `{compareDocHashesHelper}` ← first existing path in `{compareDocHashesProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {compareDocHashesHelper} refresh-hashes "{skill_package}/metadata.json" --compare "{run_dir}/doc-hashes.json"
```

It sets the `content_hash` and `recorded_at` of each `doc_sources[]` entry whose URL is in the comparison's `changed[]`, keeps every other entry and field, and rewrites `metadata.json` through one rename: never edit `doc_sources` by hand. On exit 2, no JSON, or no candidate resolves: HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:doc-sources"`, `path: "{skill_package}/metadata.json"`, `reason: "<its error, or skf-detect-docs.py is missing; re-install SKF>"`).

### 4. Write Updated evidence-report.md

Append update operation section to `{forge_version}/evidence-report.md` (create the file with a standard header if it does not yet exist):

```markdown
## Update Operation — {current_date}

**Trigger:** {manual / audit-skill chain}
**Forge Tier:** {tier}
**Mode:** {normal / degraded}
**Source commit:** {source_commit_line}

### Changes Detected
- Files modified: {count}
- Files added: {count}
- Files deleted: {count}
- Exports affected: {total}

### Merge Results
- Exports updated: {count}
- Exports added: {count}
- Exports removed: {count}
- [MANUAL] sections preserved: {count}
- Conflicts resolved: {count}

### Scope and Targeted Re-Extraction
- Authoritative files: {authoritative_files_mirror, or none}
- Scope reconciliation before detection: {scope_reconciliation_pre, or none}
- Scope reconciliation after detection: {scope_reconciliation_post, or none}
- Targeted re-extraction: {targeted_reextraction, or none}

### Repairs Applied
- Structural fixes: {structural_fix, or none}
- Metadata patches: {metadata_patch, or none}
- Metadata patch outcomes: {metadata_patch_outcome, or none}
- Reclassified exports: {reclassified, or none}

### Validation Summary
- Spec compliance: {PASS/WARN/FAIL/SKIP} (quality score {score}/100)
- Body split: {each section §7 moved and the references/ file it added, or none}
- [MANUAL] integrity: {PASS/FAIL}
- Confidence tiers: {PASS/WARN}
- Provenance: {PASS/WARN/SKIP}
- Diff: {new} new, {fixed} fixed issues, or SKIP
- Security: {PASS/WARN/SKIP} ({note})

### Description Guard
- Restored: {true/false}
- Triggering tool: {tool_name or —}
- Original description preserved: {true/false}
- Notes: {one-sentence detail or —}

### Context Snippet
- Regenerated: {true/false}
- Triggers fired: {list or —}
- Notes: {one-sentence detail or —}
```

**Scope and Targeted Re-Extraction population:** read `{run_dir}/evidence-records.jsonl`, where step 2 (§1b, §1c and §2.2) and gap-driven.md §4 appended their records, one JSON line each. Write each record under its key as it was recorded, and `none` for a key no line holds (or when the file does not exist), so a headless decision such as a deletion-ratio continue stays visible after the run.

**Repairs Applied population:** read the same file's `structural_fix` and `metadata_patch` lines (merge Priorities 8 and 8b), its `metadata_patch_outcome` lines (§2 and §3b) and its `reclassified` lines (gap-driven.md §4): only a gap-driven repair appends them. Write each line under its row as it was recorded, one item per line, and `none` for a row no line holds (or when the file does not exist), so each fix, patch and reclassified export the repair made reaches the user.

**Validation Summary population:** §4 writes `[MANUAL] integrity` from §1's `manual-verify` verdict (`PASS` when `ok`) and `Confidence tiers` from §3b (`PASS` when the stats helper reported no label violation, else `WARN` naming `{provenance_relabels}`), with placeholders for the rest. §6 fills `Provenance`, and §7 fills `Spec compliance`, `Diff` and `Security`, and `Body split` (`none` when no split ran), each in the on-disk report, as §5 fills the Context Snippet sub-block.

**Description Guard population** (used by §7 Post-Write Validation when the §0 protocol fires): fill all four fields from context when `description_guard_restored == true` (triggering tool, whether restore succeeded, and what changed, based on the recorded `description_guard_diff_kind`). When `Restored: false`, the other three fields are `—` — this is the clean-run expected state — except when `description_guard_refused == "empty-capture"` (§0's empty-snapshot rule): then set `Triggering tool` to the recorded tool name, `Original description preserved: false`, and `Notes: guard refused — empty captured snapshot (empty-capture)`, so a refused restore is distinguishable from a run where the guard never fired. Same field semantics and populator logic as create-skill step 6 §8.

**Context Snippet population** (used by §5 after the staleness check runs): §4 writes the sub-block with placeholders; §5 updates the on-disk evidence report in place after deciding whether to regenerate. Set `Regenerated: true` and populate `Triggers fired` with any combination of `headline-exports`, `version`, `gotchas` when at least one trigger fired. Set `Regenerated: false` and `Triggers fired: —` when none fired (the gap-driven / internals-only outcome). Always fill `Notes` with a one-sentence reason (e.g., `"Gap-driven repair — no snippet surface changed"`, `"Version bumped 0.1.0 → 0.2.0; headline exports re-ranked"`).

### 5. Regenerate context-snippet.md

**Regenerate `context-snippet.md` if stale:**

`context-snippet.md` is a `{skill_package}` deliverable that goes stale whenever **headline exports**, **version**, **gotchas** or **section anchors** change in this run. Regenerate it only when at least one of these triggers fired; otherwise skip: a skip is the correct outcome for gap-driven repairs and other runs that touch internals below the snippet's surface, where regenerating would produce byte-identical content.

**Staleness triggers:** run the two `gotchas` calls of the regeneration paragraph below first, before you check any trigger: `gotchas prior` binds the `prior_api` the **Headline exports changed** ranking starts from, and `gotchas resolve` returns the line **Gotchas changed** compares. When no trigger fires, nothing is written from them.

- **Headline exports changed**: the api names `skf-export-skill/references/generate-snippet.md` §3b ranks for this run differ from the prior snippet's `|api:` line (a listed name left `exports` or is now deprecated, or a `NEW_EXPORT` took a free slot). In gap-driven mode it fires only when a name of the prior line left `exports` or SKILL.md now marks it deprecated or removed: a line that differs by the ranking alone (its order, a free slot or the tier's limit) waits for the next export.
- **Version changed**: §3b's `metadata` call wrote a version other than the one the run started from (never in gap-driven mode, which keeps its version, step 4 §6b).
- **Gotchas changed**: the `line` `gotchas resolve` returned (`skf-export-skill/references/generate-snippet.md` §3a, from the merged SKILL.md and this run's evidence report: at most 3 pitfalls, in its order) differs from the prior snippet's `|gotchas:` line, `[CARRIED]` markers aside.
- **Anchors changed**: the prior snippet's `|quick-start:` or `|key-types:` anchor differs from the one `generate-snippet.md` §3b item 4 gives for the merged SKILL.md (an anchor points into `references/` although SKILL.md has the heading, or a heading moved). Record it as `anchors` in `Triggers fired`.

**Record the decision on the on-disk evidence report:** open `{forge_version}/evidence-report.md` (written by §4 with placeholder values in the `### Context Snippet` sub-block) and update that sub-block under the Update Operation section just written. Set `Regenerated: true|false`, fill `Triggers fired:` with the list of triggers that fired (or `—` when none), and write a one-sentence `Notes:` entry. See §4's "Context Snippet population" note for field semantics.

**If no trigger fired:** skip regeneration: do not touch `context-snippet.md` on disk. The snippet remains valid against the prior run's surface. Continue to §6.

**If at least one trigger fired:** regenerate the snippet. Its content comes from `skf-export-skill/references/generate-snippet.md` §3a and §3b, as the paragraph below says; `skf-create-skill/assets/skill-sections.md` gives only its line format (pipe-delimited indexed format), not the `()` its `|api:` placeholder gives functions: §3b item 2 sets each api name's `()`.

Use the **flat draft form** for the `root:` path in the draft snippet: `root: skills/{skill-name}/`. The per-IDE skill root (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/`; see `skf-export-skill/assets/managed-section-format.md`) is applied later by `export-skill` step 2 when the skill is exported. Do not choose an IDE-specific prefix in update-skill: that is an export-time decision that depends on config.yaml.

Take the version from the updated metadata.json and the inline summaries from the merged SKILL.md. Rank the api names and verify the section anchors as `skf-export-skill/references/generate-snippet.md` §3b states, and derive the gotchas as its §3a states: the merged SKILL.md, this run's evidence report (`{forge_version}/evidence-report.md`) and the provenance map §3 wrote (`{forge_version}/provenance-map.json`, its `{forge_provenance_map}`) are the current sources. That file's two `gotchas` calls read and write the line, on the prior snippet before the regenerated one replaces it, and run before the staleness triggers above, which read them: resolve `{rebuildManagedSectionsHelper}` ← first existing path in `{rebuildManagedSectionsProbeOrder}` and, from `{project-root}`, run `uv run {rebuildManagedSectionsHelper} gotchas prior "{skill_package}/context-snippet.md" --skills-folder "{skills_output_folder}" --skill {skill_name}` and bind `prior_api`, `prior_gotchas` and `is_first_export` as its §2.5 does; write the judgments its §3a gives to `{run_dir}/gotchas-judgments.json` with a file write, then run `uv run {rebuildManagedSectionsHelper} gotchas resolve "{skill_package}/context-snippet.md" --skills-folder "{skills_output_folder}" --skill {skill_name} --judgments "{run_dir}/gotchas-judgments.json"`, write its `line` as the `|gotchas:` value (leave the line out when it is null), and add each warning its §3a emits to `warnings[]`, recorded as **Warnings go to the run log** says. Until an export records the skill, `is_first_export` is true here too, so `resolve` writes an unbacked prior pitfall unmarked and marks it `[CARRIED]` only once the skill has been exported. When `resolve` exits non-zero, correct the judgments file as its `error` says and run it once more. When `prior` fails, or `resolve` fails again, HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:context-snippet"`, `path: "{skill_package}/context-snippet.md"`, `reason: "<its error>"`).

Write the regenerated snippet to `{skill_package}/context-snippet.md`, preserving file permissions.

### 6. Provenance Completeness

Provenance completeness is a deterministic set-diff plus citation resolution over `metadata.json` (§3b) and `provenance-map.json` (§3). Run it against the just-written artifacts via `{verifyProvenanceCompletenessHelper}`:

```bash
uv run {verifyProvenanceCompletenessHelper} verify \
    --metadata "{skill_package}/metadata.json" \
    --provenance "{forge_version}/provenance-map.json" \
    --source-root "{source_root}" \
    --skill-dir "{skill_package}" \
    --check-node-kinds \
    -o "{forge_data_folder}/{skill_name}/.skf-update-verify.json"
```

The helper reads its `--source-root` (falling back to the provenance map's own `source_root` field when the flag is omitted); pass the resolved `{source_root}` so citation resolution runs against the same tree re-extraction read. When `{source_root}` is null, empty or a URL (a docs-only skill), leave out the `--source-root` line: an empty flag value fails the helper's arguments, and the citation check must still run. When `{source_tree_status}` is `ready` or `offline`, `{source_root}` is still the tree init.md §6b prepared (step 7 removes it), so citations resolve against the commit §3b recorded. It writes its JSON to `{forge_data_folder}/{skill_name}/.skf-update-verify.json`, beside the §1b lock (each run overwrites it). **Read that JSON and do NOT recompute the set operations by eye, since an LLM set-diff can silently pass a dropped or orphaned entry:**

- `missing[]` — documented exports (metadata `exports[]`) with no provenance entry: a coverage gap.
- `orphaned[]` — provenance `entries[].export_name` whose export was removed but the entry remains.
- `summary.set_diff`: `not-applicable` for a reference app (`scope_type: reference-app` in `{skill_package}/metadata.json`), whose `exports[]` is empty by design while its entries follow each citation: the helper then diffs no sets, `missing[]` and `orphaned[]` stay empty, and its `status` comes from `stale[]`, `citations[]` and `node_kinds[]` alone. `checked` for every other skill.
- `stale[]`: entries whose `source_file:source_line` no longer resolves or is not the line that defines the export; each carries a `reason` of `file-missing`, `line-out-of-bounds`, `line-invalid` or `line-not-definition`. A `line-not-definition` item lists in `definition_lines` every line of the file that defines the export (the `def` or declaration line itself, not a decorator or blank line above it), except that a Python `@overload` group gives its first stub alone. An empty list means the rules found no definition line, which may be a shape they do not cover: the entry is unverified, not gone. A bookkeeping variant (`X_def`, `X_exact`, `a11y_X`) its file never names is checked against its base `X`, and its item names that base in `folded_to`. A bookkeeping variant (`X_def`, `X_exact`, `a11y_X`) its file never names is checked against its base `X`, and its item names that base in `folded_to`. Internal names are canonicalized through `reexport_map` before the diff, so a barrel-renamed export does not read as missing or orphaned.
- `citations[]`: `[AST:]` / `[SRC:]` citations in SKILL.md and `references/` whose prefix disagrees with the entry they cite (`prefix-mismatch`: `ast-grep` gives `[AST:]`, `source-read` gives `[SRC:]`), and `[AST:]` citations in a skill whose map has no `ast-grep` entry (`ast-without-ast-grep`). Each gives the markdown `file` and `line`, the `citation` text and its `expected_prefix`.
- `summary.stale_check` — `"checked"` when citations were resolved against the source tree, or `"skipped-no-source-root"` when no source root resolved on disk (the completeness + orphan diffs still ran; `stale` is empty by construction, not clean-by-verification).
- `summary.skill_citations_scanned` and `summary.skill_citations_matched`: when citations were scanned and none matched, no citation names a path and line the map records (the citations use another root), so the prefix check compared nothing. List that as a WARN.
- `node_kinds[]`: `ast-grep` entries whose `ast_node_type` is not shaped like a kind or that the ast-grep CLI does not know as a node kind of the entry's language (`invalid-kind`), or whose kind is `ERROR` (`error-kind`). Each gives the entry's `entry_index`, `export_name`, `source_file`, `source_line`, `ast_node_type` and `language`. `summary.node_kind_check` is `skipped-no-ast-grep` when no ast-grep CLI is on PATH, or `skipped-unrecognized-ast-grep` when the ast-grep found does not reject a kind no grammar has: either way ast-grep judged no kind. `node_kinds_unchecked[]` lists, with a `reason`, the entries whose kind ast-grep could not judge, and `summary.node_kind_check_skipped` counts the ast-grep entries in files ast-grep has no language for: list each unchecked entry, and the skipped count, as a WARN.

When the helper exits 2 it writes no JSON: record `Provenance: WARN (not run: verifier error)` with its stderr in the evidence report's Validation Summary and continue to §7. When the second run below exits 2, record the fixes already applied and `second run: verifier error` the same way and continue to §7.

**Fix the findings that have one answer**, in this order, then run the command above once more:

1. **Citation prefixes and source lines.** Never apply them by hand: from `{project-root}`, run the verifier's `fix` on the JSON the run above wrote:

   ```bash
   uv run {verifyProvenanceCompletenessHelper} fix \
       --verify "{forge_data_folder}/{skill_name}/.skf-update-verify.json" \
       --provenance "{forge_version}/provenance-map.json" \
       --skill-dir "{skill_package}" \
       --manual-inventory "{manual_inventory}" \
       [--no-line-moves]
   ```

   Pass `--no-line-moves` when `{workspace_drift_status}` is `overridden` (gap-driven.md §3): the tree read is not the recorded commit, so its lines prove nothing about the map. `fix` prints `applied[]` (each fix it made), `left_as_warn[]` (each finding it left for a person, with its `why`), `files_written[]` and `manual_verify` (the SKILL.md [MANUAL] blocks checked against `{manual_inventory}` after its writes).
   - **`manual_verify.ok` is false** (a [MANUAL] block changed): HALT with status `halted-for-manual-mismatch`. The halt procedure takes `phase: "write:verify-manual-integrity"`, `path: "{skill_package}/SKILL.md"`, `reason: "[MANUAL] blocks changed after the provenance fixes: ..."`, as §1's does. Alert the user: "**[MANUAL] section integrity failure after the provenance fixes.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Verified against the inventory `{manual_inventory}`. {manual_recovery}", with `{manual_recovery}` as §1 gives it: §8 has not pointed the `active` link at a new version yet, so this halt rolls back as §1's does.
   - **Exit 2** (no JSON; its stderr line names any file it already wrote): record `Provenance: WARN (not fixed: verifier error)` with that line, re-read each file it names into context, and go on to step 2.
   - **Otherwise:** re-read each file in `files_written[]` into the in-context copies (the merged SKILL.md and `references/` content and §3's provenance map), so later sections and the report read the fixed text, and add `SKILL.md` and `provenance-map.json` to `files_written[]` (report.md §5b) when `fix` wrote them.
2. **Node kinds.** Never set a kind by hand: from `{project-root}`, run the verifier's `relabel` on the `node_kinds[]` of the JSON the first run above wrote, over the map as step 1 left it:

   ```bash
   uv run {verifyProvenanceCompletenessHelper} relabel \
       --provenance "{forge_version}/provenance-map.json" \
       --node-kinds "{forge_data_folder}/{skill_name}/.skf-update-verify.json" \
       --recipes "{extractionPatternsData}" \
       [--records "{run_dir}/reextract-records.json"] \
       [--source-root "{source_root}"] [--no-kind-at] \
       -o "{run_dir}/relabel-node-kinds.json"
   ```

   It sets each entry's `ast_node_type` to the `kind` of the recipe this run's record of the export names (`ast_recipe`, in a `files` record of `{run_dir}/reextract-records.json`, which re-extract.md §4 or gap-driven.md §4 wrote), else to the kind `kind-at` finds at the entry's current `source_line`, and never changes `extraction_method`. Pass `--records` when that file exists, `--source-root` when there is a local source tree, and `--no-kind-at` when `{workspace_drift_status}` is `overridden` (gap-driven.md §3: the tree read is not the recorded commit, so run no `kind-at`). On exit 0 or 1, list each `left_as_warn[]` item as a WARN with its `why`, re-read the map into §3's in-context copy, and add `provenance-map.json` to `files_written[]` when its `files_written[]` names the map. With no candidate for the verifier or `{extractionPatternsData}`, or on exit 2 (then with its stderr line), fix no node kind and list each one as a WARN.

These fixes apply to any entry, a gap-driven `verified` or `moved` entry included (§3). Fix nothing else: each `left_as_warn[]` item stays for a person to decide, and so do `missing` / `orphaned` exports. A `line-not-definition` item with an empty `definition_lines` is never fixed: list its export as unverified.

Map the re-run's `status` to the `Provenance:` line of the §4 evidence report's Validation Summary: `PASS` when `status == "pass"`, `WARN` when `status == "findings"`. For a reference app that status comes from its stale lines, citation prefixes and node kinds alone (`summary.set_diff` `not-applicable`): note `set diff not applicable: reference app` in the Validation Summary, never as a WARN. Provenance findings are **advisory**: they do not block the update. In the evidence report's Validation Summary, list the source lines, citation prefixes and node kinds this section fixed (`fix`'s `applied[]` and the `relabeled[]` of step 2) and the unverified exports, then each `left_as_warn[]` item and each other `missing` / `orphaned` / `stale` / `citations` / `node_kinds` finding the re-run still reports as a WARN so the user can decide, and note `source lines not checked: no local source tree` when `stale_check` was `skipped-no-source-root`, `node kinds not checked: no ast-grep CLI` or `node kinds not checked: unrecognized ast-grep` when `node_kind_check` was `skipped-no-ast-grep` or `skipped-unrecognized-ast-grep`, each `node_kinds_unchecked[]` entry with its `reason`, and `summary.node_kind_check_skipped` when it is above 0. Add each of those WARNs and the unverified exports to `warnings[]` with a `provenance:` prefix (for example `provenance: search line 26 does not define it; definition lines 27, 31`); §3 recorded `{provenance_spot_check_warnings}` already.

**Under the drift override** (`{workspace_drift_status}` is `overridden`, gap-driven.md §3), the verifier read `{source_root}` at HEAD, not the pinned commit, and a file or line missing at HEAD may still be at the pinned commit: end the `Provenance:` line of the Validation Summary, and each WARN this section lists for a `stale[]` finding (`file-missing`, `line-out-of-bounds`, `line-invalid`, `line-not-definition`), an unverified export or a finding `fix` left as `line-moves-skipped`, with ` (drift override: HEAD {head_short_sha} is not pinned {pinned_short_sha})`.

**Verifier missing:** if neither probe path resolves, record `Provenance: SKIP (verifier missing; re-install SKF)` in the evidence report's Validation Summary, add `provenance: verifier missing; re-install SKF to check provenance completeness` to `warnings[]`, recorded as **Warnings go to the run log** says, and go on to §7. Compare no set and check no line by hand: an LLM set-diff can silently pass a dropped or orphaned entry.

### 7. Run Post-Write Validation

skill-check runs once per update, here, against the written package, and once more after a body split (below) to read the score the split left. Check that it is available, never assume it: run `npx skill-check -h`.

**Description Guard Protocol:** every invocation below that may modify SKILL.md (`skill-check check --fix`, the `{shardBodyHelper}` body split and any `split-body` write) must run inside the four-phase guard defined in §0. Invoke `{descriptionGuardHelper}` at the capture and verify-restore points around each call:

```bash
# Phase 1: capture before any frontmatter-touching tool call
uv run {descriptionGuardHelper} capture "{skill_package}/SKILL.md" > "{run_dir}/description-guard.json"
# the snapshot lands in the run folder; read its `description` as `guarded_description`

# Phase 2: run the tool (skill-check --fix, the body split, split-body --write)

# Phases 3+4: verify and restore after the tool call
uv run {descriptionGuardHelper} verify-restore "{skill_package}/SKILL.md" \
    --captured-file "{run_dir}/description-guard.json"
```

Do not rely on per-call ad-hoc preservation logic: use the helper.

**If skill-check is available:**

- **Hash before --fix:** before the §0 guard's `capture` for the `--fix` call below, run `uv run {hashContentHelper} hash "{skill_package}/SKILL.md"` from `{project-root}` and keep the `content_hash` it prints.
- Run `npx skill-check check "{skill_package}" --fix --format json --no-security-scan` **inside the §0 guard**, with its output captured apart (`> "{run_dir}/skill-check.json" 2> "{run_dir}/skill-check.stderr"; echo "skill-check exited $?"` after it). One call validates the package against the spec, scores it and fixes what has one answer; `--no-security-scan` leaves the security scan to **Security scan** below. Read the JSON, not the exit code: the quality score (`scores[].score`, the entry matching the skill, or a top-level `qualityScore` on an older skill-check), and the remaining `diagnostics[]`, from the JSON object at the start of `{run_dir}/skill-check.json` (stdout can go on after it, a `Wrote <path>` line when the project config sets a report path). Give the call the longest timeout your shell tool takes. When no "skill-check exited" line came back, the shell tool stopped the call before skill-check finished: still run the guard's `verify-restore` and the second `hash` call below before reading `{run_dir}/skill-check.json`.
- **Context sync after --fix:** after that call's `verify-restore`, run `uv run {hashContentHelper} hash "{skill_package}/SKILL.md"` again. When the `content_hash` it prints differs from the one kept before the call, or either `hash` call printed no `content_hash`, re-read SKILL.md into the in-context copy, so the report does not work from a copy that differs from the file on disk. The §0 guard has already restored `description` if it diverged.
- If `body.max_lines` or `body.max_tokens` is reported, split the body selectively with `{shardBodyHelper}` (resolve it ← first existing path in `{shardBodyProbeOrder}`), **inside the §0 guard**: from `{project-root}`, run `uv run {shardBodyHelper} "{skill_package}/SKILL.md" --budget 400 --word-budget 4500 --skip-manual`, with `--budget 500` in place of `--budget 400` when only `body.max_tokens` is reported. It moves the largest Tier 2 (`## Full`) sections to `references/`, each replaced by a `> See` pointer to a file it never overwrites, until the body is within that many lines and 4,500 words, the same headroom under skill-check's 5,000 that 400 lines leave under its 500, and keeps Tier 1 inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). **Never move a section that holds a `[MANUAL]` block:** init.md §5 inventories SKILL.md only, so a block moved to `references/` would leave the next update's inventory; `--skip-manual` keeps the helper off every section a block reaches into. No Tier 1 content is trimmed, and `split-body` never runs after the helper. Add each WARN below to `warnings[]` as well. Act on its report:
  - **Exit 1 or 2, or no JSON:** HALT with status `blocked` (halt procedure: `phase: "write:body-split"`, `path: "{skill_package}/SKILL.md"`, `reason: "body split failed: {its stderr line}"`). On exit 2 that line ends `already written: {each references/*.md file it wrote before the failure, or none}`: name each of those files in the halt message.
  - **`tier1_preserved` false (it then wrote nothing) or `xref_ok` false:** HALT with status `blocked` (halt procedure: `phase: "write:body-split"`, `path: "{skill_package}/SKILL.md"`, `reason: "body split: tier1_missing {tier1_missing}; xref_ok {xref_ok}"`).
  - **`under_budget` false:** record `Spec compliance: WARN (body.max_lines: no Tier 2 section without a [MANUAL] block left to move)`.
  - **`under_word_budget` false:** record `Spec compliance: WARN (body.max_tokens: no Tier 2 section without a [MANUAL] block left to move)`.
  - **No `{shardBodyProbeOrder}` candidate resolves:** when `body.max_lines` is reported and SKILL.md holds no `[MANUAL]` block (§1's verdict lists none), fall back to `npx skill-check split-body "{skill_package}" --write`, **inside the §0 guard** (it can also touch frontmatter): it moves every section. When `body.max_lines` is reported and SKILL.md holds a `[MANUAL]` block, split nothing and record `Spec compliance: WARN (body.max_lines: skf-shard-body.py missing)`; when only `body.max_tokens` is reported, split nothing and record `Spec compliance: WARN (body.max_tokens: skf-shard-body.py missing)`.

  After a split (the helper's `sections_extracted` is not empty, or the fallback ran), re-read SKILL.md and each new `references/*.md` file into the in-context copy, as after `--fix`; re-run `npx skill-check check "{skill_package}" --format json --no-security-scan` and take the quality score and the remaining `diagnostics[]` from it; list in the Validation Summary's `Body split` row each section moved and the `references/` file it added; and verify anchors resolve.
- When a previous version is on disk (outside gap-driven mode), run `npx skill-check diff "{skill_group}/{baseline_version}/{skill_name}" "{skill_package}"` and record its new and fixed issues as informational; otherwise record `Diff: SKIP`.

**Re-check the [MANUAL] blocks** once `--fix` and any split have run, from `{project-root}`:

```bash
uv run {hashContentHelper} manual-verify "{skill_package}/SKILL.md" \
    --inventory "{manual_inventory}"
```

On `ok` false, HALT with status `halted-for-manual-mismatch`, as §1 does. The halt procedure takes `phase: "write:verify-manual-integrity"`, `path: "{skill_package}/SKILL.md"`, `reason: "[MANUAL] blocks changed after skill-check: modified {modified}; missing {missing}"`. Alert the user: "**[MANUAL] section integrity failure after skill-check.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Verified against the inventory `{manual_inventory}`. {manual_recovery}", with `{manual_recovery}` as §1 gives it: §8 has not pointed the `active` link at a new version yet, so this halt rolls back as §1's does.

**If skill-check is unavailable:** record `Diff: SKIP`, and check the structure by script instead: resolve `{validateOutputHelper}` ← first existing path in `{validateOutputProbeOrder}` and, from `{project-root}`, run `uv run {validateOutputHelper} "{skill_package}"`. Record `Spec compliance: PASS (skf-validate-output.py)` when it reports no issue, and `Spec compliance: WARN (skf-validate-output.py)` with each issue it reports otherwise; when no candidate resolves, record `Spec compliance: SKIP (skill-check unavailable, no validator)`. Nothing here changes SKILL.md, so the [MANUAL] re-check above does not run.

**Security scan**, whether or not skill-check is available: resolve `{securityScanHelper}` ← first existing path in `{securityScanProbeOrder}` and, from `{project-root}`, run `uv run {securityScanHelper} run --package "{skill_package}"` with the longest timeout your shell tool takes (it ends within two minutes). It runs Snyk Agent Scan, at the version it pins, only when `SNYK_TOKEN` is set, and reads the scanner's own JSON report, so rely on the JSON it prints, never on an exit code. Record the Validation Summary's `Security` row from its `security_result` and `note`: `Security: PASS ({note})` for `pass`, `Security: WARN ({note}: {each findings[] entry's text})` for `warn`, each finding an advisory warning, and `Security: SKIP ({note})` for `skipped`. When no `{securityScanProbeOrder}` path exists, record `Security: SKIP (skf-security-scan.py missing)`; when the call prints no JSON object, record `Security: SKIP (skf-security-scan.py printed no result)`.

Record the results in the evidence report's Validation Summary (§4): `Spec compliance` from the score and the remaining `diagnostics[]`, `Diff`, and `Security` as the security scan rule above reads it (its first word `PASS`, `WARN` or `SKIP`, its note in parentheses after it), with any `description_guard_restored` event the §0 protocol recorded. They are advisory: do not block on warnings.

### 8. Update the Active Symlink

Flip `{skill_group}/active` to point at the current `{version}` via the helper, now that §6 and §7 have checked the written package. The call is **always** run: atomic, idempotent, and verified in one shot. The helper's no-op path handles the "version did not change" case (gap-driven mode, or no source drift) without writing to disk:

```bash
uv run {updateActiveSymlinkHelper} update \
    --skill-group {skill_group} \
    --version {version}
```

The helper emits a result envelope with `status` ∈ `{ok, flipped, mismatch, missing-target, busy}` and a pre-formatted `log_message`. Log the message to the evidence report.

**Dispatch on `status`:**

- **`ok`** (exit 0): symlink already points at `{version}`, so no disk write. Continue to §8a.
- **`flipped`** (exit 0): symlink was atomically updated (temp-and-replace). Continue to §8a.
- **`missing-target`** (exit 2): `{skill_group}/{version}/` does not exist on disk, so step 4 §6b did not create it. HALT with status `halted-for-write-failure` and display `halt_message` verbatim.
- **`mismatch`** (exit 2): the link still points elsewhere after the flip. HALT with status `halted-for-write-failure` and display `halt_message` verbatim.
- **`busy`** (exit 2): another flip of the link held its lock for the helper's whole wait, so the link is unchanged. HALT with status `halted-for-concurrent-run` and display `halt_message` verbatim.
- **Any other exit, or no JSON on stdout** (exit 1, or an exit 2 that prints no JSON: the helper could not run, could not move the link, or failed after moving it, and the last line it prints on stderr says why): HALT with status `halted-for-write-failure` and display that line, which is `exit <code>` when the helper prints nothing on stderr. The halt procedure takes `phase: "write:active-symlink"`, `path: "{skill_group}/active"`, `reason: "<that line>"`.

For each exit-2 halt, the halt procedure takes `phase: "write:active-symlink"`, `path: "{skill_group}/active"`, `reason: "<status>: <halt_message>"`. Its rollback removes the new version (the `active` link does not name it) or, in gap-driven mode, restores the package from the snapshot.

### 8a. Verify the Active Symlink

Check, read-only, that the `active` link resolves to the version §3b wrote to `metadata.json`, in every mode (consumers that do not read the export manifest fall back to the link, `knowledge/version-paths.md` §Reading Workflows step 5):

```bash
uv run {updateActiveSymlinkHelper} verify \
    --skill-group {skill_group} \
    --version {version}
```

On `mismatch` (exit 2), HALT with status `halted-for-write-failure` and display the helper's `halt_message` verbatim: it names the diverged target, the expected version and the recovery command. The halt procedure takes `phase: "write:verify-active-symlink"`, `path: "{skill_group}/active"`, `reason: "mismatch: <halt_message>"`.

On `ok` (exit 0), continue to §9. On any other exit, or no JSON on stdout (exit 1, or an exit 2 that prints no JSON: the helper could not run or could not read the link, as when a real folder has replaced `active` or the skill folder is gone since §8, and the last line it prints on stderr says why), HALT with status `halted-for-write-failure` and display that line, which is `exit <code>` when the helper prints nothing on stderr. The halt procedure takes `phase: "write:verify-active-symlink"`, `path: "{skill_group}/active"`, `reason: "<that line>"`.

### 9. Move the Workspace Clone to the Recorded Commit

Run only when `{source_tree_status}` is `ready` and `{workspace_clone}` is not null. test-skill and audit-skill read the skill's source from metadata.json `source_root`, the clone SKF keeps for this repository, and test-skill compares its HEAD with the `source_commit` §3b just wrote. From `{project-root}`, resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}`, `{cccGitHygieneHelper}` ← first existing path in `{cccGitHygieneProbeOrder}` and `{checkWorkspaceDriftHelper}` ← first existing path in `{checkWorkspaceDriftProbeOrder}`, then run:

```bash
uv run {sourceTreeHelper} advance \
    --clone "{workspace_clone}" \
    --source-repo "{source_repo}" \
    --expect-commit "{source_commit}" \
    --target "{target_commit}" \
    --target-ref "{target_ref}" \
    --tree "{source_tree}" \
    --timeout "{tree_timeout}" \
    [--hygiene-helper "{cccGitHygieneHelper}"] \
    [--drift-helper "{checkWorkspaceDriftHelper}"]
```

Pass `--hygiene-helper` and `--drift-helper` only when they resolved. `{source_commit}` is the commit init.md §6 read from metadata.json, before §3b recorded `{target_commit}`, and `{tree_timeout}` is the time limit init.md §6b chose: the helper stops itself within it.

The helper takes the clone's `.skf-workspace.lock`, the lock create-skill also takes, waiting up to a minute, and runs the git hygiene check inside it. It then does nothing when the clone already holds `{target_commit}`; otherwise it moves the clone there only when `{checkWorkspaceDriftHelper}` confirms the clone still holds `{source_commit}` and no tracked file has local changes, taking the commit from `{source_tree}` rather than the network. It never forces a checkout and never moves a clone another run moved. When the clone is missing, it clones it first, as create-skill does.

Bind `{advance_status}` ← `status`, `{advance_skip_reason}` ← `skip_reason`, `{advance_head}` ← `head_sha`, `{advance_log}` ← `log_message` and `{advance_warnings}` ← `warnings`. Log `{advance_log}` in the evidence report and add each `{advance_warnings}` entry to `warnings[]` as `source-tree: <entry>`.

- **`advanced` or `ok`:** continue.
- **`skipped`:** add `workspace-clone-not-updated: {advance_skip_reason}; {workspace_clone} holds {advance_head or "no commit"}, so test-skill stops with workspace-drift until it holds {target_commit}` to `warnings[]`, and continue.
- **`{sourceTreeHelper}` does not resolve, or the command fails or prints no JSON:** add the same warning with reason `helper-unavailable`, and continue.

This section never halts: the skill is written, and only the clone test-skill reads is out of step.

### 10. Close the Rollback Window

Once §9 has run, this run's writes stand: from `{project-root}`, run `uv run {runStateHelper} finish --run-dir "{run_dir}"`. It marks the run finished, then deletes the snapshot: from then on a halt undoes nothing. When it fails or prints no JSON, add `run-state-not-finished: {its message}` to `warnings[]`: no step after this one halts, and step 7 removes the run folder.

### 11. Route to Next Step

This step auto-proceeds: no user choices. Once §10 has run, display "**Proceeding to report...**", then load, fully read, and execute `{nextStepFile}` to display the change report.

