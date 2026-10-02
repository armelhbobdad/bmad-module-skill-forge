---
nextStepFile: 'report.md'
# Resolve `{descriptionGuardProtocol}` (the guard's prose protocol, not its
# helper script) by probing `{descriptionGuardProtocolProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. Advisory: if neither path exists, skip the load and
# continue, because §0 states every guard rule this step acts on and the
# protocol only explains them.
descriptionGuardProtocolProbeOrder:
  - '{project-root}/_bmad/skf/shared/references/description-guard-protocol.md'
  - '{project-root}/src/shared/references/description-guard-protocol.md'
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
# Advisory: if neither resolves, §2 and §6 look up no node kind and §6 runs
# its by-hand set comparison, since the files it checks are already written.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# Resolve `{extractionPatternsData}` to the first existing path. If neither
# exists, §2 relabels nothing and §6 fixes no node kind: list each label
# violation and each node-kind finding as a WARN.
extractionPatternsDataProbeOrder:
  - '{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md'
  - '{project-root}/src/skf-create-skill/references/extraction-patterns.md'
# Resolve `{atomicWriteHelper}` to the first existing path. Advisory: if
# neither resolves, §6 fixes no node kind and lists each one as a WARN.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# Resolve `{hashContentHelper}` to the first existing path; HALT if neither
# candidate exists. §1 and §7 use its `manual-verify` subcommand to verify
# SKILL.md against the byte-exact [MANUAL] inventory step 4 §4 amended; a
# marker-count comparison would pass a block whose interior was truncated
# without changing the marker count.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# Resolve `{renderMetadataStatsHelper}` by probing `{renderMetadataStatsProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. HALT if neither resolves — §2's `stats` block and
# `confidence_distribution` are computed values that must not be hand-binned,
# and this is the same helper sibling create-skill compiles them with.
renderMetadataStatsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-metadata-stats.py'
  - '{project-root}/src/shared/scripts/skf-render-metadata-stats.py'
# Resolve `{sourceTreeHelper}` to the first existing path. §9 uses its
# `advance` subcommand to move the workspace clone to the commit §2
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
# neither exists: §3's `apply` writes the provenance map from this run's
# records, never by hand.
buildChangeManifestProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-build-change-manifest.py'
  - '{project-root}/src/shared/scripts/skf-build-change-manifest.py'
# Resolve `{compareDocHashesHelper}` to the first existing path when step 2
# wrote `{run_dir}/doc-hashes.json` (a docs-only skill); HALT if neither
# exists: §2 records the changed documents' new hashes with its
# `refresh-hashes`, so the next update does not find them changed again.
compareDocHashesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
# Resolve `{validateOutputHelper}` to the first existing path when §7 finds no
# skill-check. If neither exists, §7 records the spec check as skipped.
validateOutputProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-output.py'
  - '{project-root}/src/shared/scripts/skf-validate-output.py'
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

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the halt helper SKILL.md On Activation resolved.

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

### 0. Description Guard Protocol

**Used by:** §7 (`skill-check check --fix` and `skill-check split-body --write`).

Resolve `{descriptionGuardProtocol}` ← first existing path in `{descriptionGuardProtocolProbeOrder}` and load it for the full prose explanation of the four-phase guard (why it exists, what counts as divergence, why token-stream comparison is the right shape). The load is advisory: if neither path exists, continue, because the rules below are all this step needs from it. The deterministic phases are executed via `{descriptionGuardHelper}` — §7 invokes the helper at the capture and verify-restore points around every `skill-check` call.

**Guard outputs.** Bind `{guarded_description}` ← `description` from each `capture`, run while the in-context SKILL.md copy matches the file on disk. Bind `{guard_restored}` ← `restored` and `{guard_diff_kind}` ← `diff_kind` from each `verify-restore`. When `{guard_restored}` is true, set the in-context `description` to `{guarded_description}` so later sections do not work from the tool-mutated value, and record `description_guard_restored: true` with the tool name and `description_guard_diff_kind: {guard_diff_kind}` in workflow context for the evidence report (§4). A later `verify-restore` that exits 0 with `{guard_restored}` false leaves those records in place.

**Empty-snapshot rule.** `verify-restore` refuses an empty or whitespace-only `--captured-description` (exit 1, file untouched). Never re-run it with the empty value: writing it back would blank the field the guard protects. If the merged description is still in context (the in-context SKILL.md copy), re-run `verify-restore` with that value. Otherwise record `description_guard_restored: false` and `description_guard_refused: empty-capture` with the tool name; the evidence report (§4) renders that as a fired guard, not as a clean run.

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

### 2. Write Updated metadata.json

**Renew the run lock first:** step 4 §8 may have waited at its gate since step 4 §6b renewed it. From `{project-root}`, run the renewal step 4 §6b ran:

```bash
uv run {runLockHelper} acquire \
    --lock "{forge_data_folder}/{skill_name}/.skf-update.lock" \
    --owner "{lock_owner}" \
    --stale-after 60
```

- **Exit 0 with `refreshed` true:** continue.
- **Exit 0 with `refreshed` false, or exit 3:** this run's lock lapsed while it waited, so another update may have changed the skill since this run read it (on exit 3 that update holds the lock). HALT with status `halted-for-concurrent-run` before writing `metadata.json`: display "**This update of {skill_name} lost its run lock while it waited.** {lock_recovery}", with the helper's `message` on exit 3. The halt procedure takes `phase: "write:run-lock"`, `path: "{forge_data_folder}/{skill_name}/.skf-update.lock"`, `reason: "run-lock-lost: this run's lock lapsed while it waited; another update may have changed the skill since this run read it"`, or on exit 3 `reason: "another update in progress: {message}"`.
- **Any other exit, or no JSON:** HALT with status `blocked` the same way: display "**The run lock could not be renewed:** {the message the helper printed on stderr}. {lock_recovery}", with `reason: "run-lock-failed: {that message}"`.

`{lock_recovery}` is, outside gap-driven mode, "The previous version is unchanged, and the halt removed `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/`, which step 4 created for this update: re-run update-skill once no other update of {skill_name} runs." and, in gap-driven mode, "This repair already wrote SKILL.md in place; the halt restored the package and the skill brief from the snapshot step 4 took, so the skill is as it was: re-run update-skill once no other update of {skill_name} runs."

Update `{skill_package}/metadata.json`:
- **First, apply any queued `metadata_patches[]`** (staged by merge Priority 8b from gap-driven `metadata update` entries): apply each surgical patch described in the gap's remediation (reconcile a divergent count, add an explanatory stat, etc.) *before* the automatic recount below, so the recount overrides only the fields it owns and the patch survives for any field it does not. If a patch and the recount disagree on a field the recount owns (e.g., `exports_documented`), the recount wins — log the divergence so a still-stale stat surfaces in the report rather than being silently overwritten.
- **For gap-driven rescopes** (`DELETED_EXPORT` / verification `rescoped`): the removed exports are already dropped from the `exports` array below, and `stats` recompute from that reduced surface: never set a `stats` count by hand to match the documented total. The reduction is justified by the `brief.scope.exclude` + `scope.amendments[]` (`action: "excluded"`) step 4 §6b wrote from step 2's rule R1; the recount simply reflects the smaller surface.
- Update `version` to `{new_version}`, the version step 4 §6b chose: **if `update_mode == "gap-driven"`, that is the unchanged version**: the skill is being repaired against the same source commit, so of the fields that mark an update only `generation_date` below changes, and step 4 wrote into the existing version directory (step 1 §6c records no source version in gap-driven mode). Otherwise it is the version whose folder step 4 §6b created: `{source_version_detected}` when step 1 §6c recorded `source_version_detected`, else the next patch version. Never pick another value here: `version` must name the folder `metadata.json` sits in, the one §8 points the `active` link at. From here on `{version}` is `{new_version}`.
- Update `generation_date` timestamp to the current UTC time to the second, `YYYY-MM-DDTHH:MM:SSZ`, read from the clock (`date -u +%Y-%m-%dT%H:%M:%SZ`), never typed: step 1 §4b offers a test report only when it is newer. It is the only update bookkeeping metadata.json carries, in every mode: §3's update operation block records `last_update` and `update_type` in provenance-map.json. Write neither key into metadata.json, and remove a `last_update` or `update_type` an older SKF version left there, so metadata.json never keeps the date or type of an earlier update beside the map's current one.
- **Record the source commit** (when `{source_tree_status}` is `ready` or `offline`): set `source_commit` to `{target_commit}`, the commit every step of this run read, and, when `{target_ref_override}` is set, `source_ref` to `{target_ref}`. Leave `source_root` as metadata.json records it: it names the clone SKF keeps for the repository; never write `{source_tree}` or any other path of this run into an artifact. For any other source (a local folder, gap-driven mode, docs-only) leave `source_commit` and `source_ref` unchanged. The in-context `{source_commit}` stays the value init.md §6 read; §9 needs it.
- Update `exports` array to reflect current export list
- **Compute the `stats` block and `confidence_distribution` deterministically** with `{renderMetadataStatsHelper}` (resolve from `{renderMetadataStatsProbeOrder}`; first existing path wins): the same helper sibling create-skill compiles them with, so create and update emit byte-identical stats for identical inputs. The helper owns all the arithmetic: it bins each provenance `entries[]` row once by its `signature_source` tier into `confidence_distribution.{t1,t1_low,t2,t3}`, sets `exports_documented` = the entry count for the library shape (for a reference app, the Pattern Surface row count; see **Shape** below), and derives `exports_total` = `exports_public_api` + `exports_internal`, `public_api_coverage` = documented / public_api (`null` if public_api is 0), `total_coverage` = documented / total (`null` if total is 0), plus `scripts_count` / `assets_count` from the inventory arrays. Run `uv run {renderMetadataStatsHelper} --help` for the full contract. Do not hand-bin the distribution: binning T2 annotations + T3 doc items on top of the per-export tiers double-counts, which per-entry binning by `signature_source` makes structurally impossible. You supply only the judgment payload:

  **Judgment payload (what you decide — passed as JSON on stdin):**
  - `exports_public_api`: count of exports from public entry points (`__init__.py`, `index.ts`, `lib.rs`, or equivalent)
  - `exports_internal`: count of all other non-underscore-prefixed exports
  - `scripts` / `assets`: the scripts / assets inventory arrays (or `[]` when empty) — the helper sets `scripts_count` / `assets_count` from their lengths
  - `pattern_surfaces_documented` (reference app only): the number of rows in the `## Pattern Surface` table of the merged SKILL.md, the count create-skill's compile.md §4 passes. The helper uses it as `exports_documented` and emits it as `stats.pattern_surfaces_documented`, the count test-skill measures a reference app's coverage by.

  **Public API counts under the drift override** (`{workspace_drift_status}` is `overridden`, step 3 §0.a): count nothing at `{source_root}`, which is HEAD, not the pinned commit. Pass as `exports_public_api` and `exports_internal` the values `{skill_package}/metadata.json` records in `stats` once the queued `metadata_patches[]` above are applied (0 for one it does not record, with a WARN).

  **Shape:** read `scope_type` from `{skill_package}/metadata.json` before this section rewrites it (create-skill records the brief's `scope.type` there). When it is `reference-app`, pass `--shape reference-app` and put `pattern_surfaces_documented` in the payload, as create-skill's compile.md §4 does; for any other `scope_type`, or none, pass no `--shape` (the helper's default, the library shape).

  **Invoke** — since the helper reads `entries[]`, stage §3's `provenance-map.json` write first (§3 does not depend on these stats):

  ```bash
  echo '{"exports_public_api": {N}, "exports_internal": {M}, "scripts": {scripts-inventory-or-[]}, "assets": {assets-inventory-or-[]}}' \
    | uv run {renderMetadataStatsHelper} {forge_version}/provenance-map.json
  ```

  For a reference app, the same call with the Pattern Surface row count and the shape:

  ```bash
  echo '{"exports_public_api": {N}, "exports_internal": {M}, "pattern_surfaces_documented": {P}, "scripts": {scripts-inventory-or-[]}, "assets": {assets-inventory-or-[]}}' \
    | uv run {renderMetadataStatsHelper} {forge_version}/provenance-map.json --shape reference-app
  ```

  Write the returned `stats` and `confidence_distribution` objects into `metadata.json` **verbatim**. If the helper reports `coherence.ok: false`, fix the provenance map and re-run the helper; never hand-edit the stats. A `confidence_distribution` violation means some provenance entries carry a missing or unrecognized `signature_source` (§3 must write it on every entry).

  **Label violations.** A violation whose `field` is `provenance.entries[<i>].<field>` means entry `<i>` (its `export_name` is in the violation) carries a label its `extraction_method` does not allow: relabel it by the `## Relabel Rule` section of `{extractionPatternsData}`, with `{source_root}` as the tree its node-kind lookup reads. **Under the drift override** (`{workspace_drift_status}` is `overridden`, step 3 §0.a) run no recipe at `{source_root}`, so no `kind-at`: HEAD is not the pinned commit, so a kind read there says nothing about the entry. Leave each violation that needs a kind from the tree in place and list it as a WARN ending ` (drift override: HEAD {head_short_sha} is not pinned {pinned_short_sha})`; a relabel that reads nothing from the tree still applies. With the status `ok` or `skipped`, run the lookup as the rule says. Rewrite `{forge_version}/provenance-map.json` with the relabeled entries, re-run the helper with the same payload and `--shape`, and write the `stats` and `confidence_distribution` it returns: a relabeled `signature_source` moves the distribution, and a violation left as a WARN does not block the write. This relabel applies to every entry the helper flags, including a gap-driven `verified` entry (§3). Record the relabeled export names, and each WARN left, as `{provenance_relabels}` in workflow context: the update report lists them under its Confidence Tier Breakdown (report.md), so no entry moves from T1 to T1-low unannounced.

**A docs-only skill's document hashes.** When step 2 wrote `{run_dir}/doc-hashes.json` (its docs-only branch), record the new hash of each document it found changed, after the writes above, so the next update compares against the documents this one read. Resolve `{compareDocHashesHelper}` ← first existing path in `{compareDocHashesProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {compareDocHashesHelper} refresh-hashes "{skill_package}/metadata.json" --compare "{run_dir}/doc-hashes.json"
```

It sets the `content_hash` and `recorded_at` of each `doc_sources[]` entry whose URL is in the comparison's `changed[]`, keeps every other entry and field, and rewrites `metadata.json` through one rename: never edit `doc_sources` by hand. On exit 2, no JSON, or no candidate resolves: HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:doc-sources"`, `path: "{skill_package}/metadata.json"`, `reason: "<its error, or skf-detect-docs.py is missing; re-install SKF>"`).

### 3. Write Updated provenance-map.json

Write `{forge_version}/provenance-map.json` with `{buildChangeManifestHelper}` `apply` (resolve it ← first existing path in `{buildChangeManifestProbeOrder}`), never by hand: it reads the map the update started from and this run's records in `{run_dir}`, and writes the whole updated map through a temporary file and one rename. When step 4 §6b created a new version, `{forge_version}` is its forge folder, which holds a copy of the previous map when there was one: write the whole updated map there, and leave the previous version's map as it was. From `{project-root}`, run:

```bash
uv run {buildChangeManifestHelper} apply \
    --update-type "{update_type}" \
    [--provenance-map "{forge_version}/provenance-map.json"] \
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
    -o "{forge_version}/provenance-map.json"
```

`{update_type}` follows the run's mode as report.md §2 names it (`{update_mode}`): `incremental` for `normal`, `gap-driven` for `gap-driven`, `full` for `degraded` (a degraded run has no map: leave out `--provenance-map`, and `apply` starts a new one). Pass each `{run_dir}` file the run wrote: the change manifest and the records in every mode, `category-c.json` and `ccc-pairs.json` (step 2's Category C and its CCC check), `extraction.json` and `export-details.json` when step 2 wrote them, `merge-records.json` when step 4 did, the Category D files (`category-d-compare.json`, `new-files.json`) with `--source-root` when step 2 ran Category D, and `promoted-docs.json` when step 2 §1b wrote it. `{generation_date}` is the value §2 wrote, `--test-report-run-id` goes only with a gap-driven run (the `{test_report_run_id}` of the report it applied), `{manual_sections_preserved}` is `len(preserved) + len(moved)` from the §1 `manual-verify` verdict (never a marker count), and `{map_source_commit}` and `{map_source_ref}` are the `source_commit` and `source_ref` §2 writes to `metadata.json` (an empty string for a null one): audit-skill reads its baseline commit from the map's top-level `source_commit` and `source_ref`. Pass `--drift-head` and `--drift-pinned` only when `{workspace_drift_status}` is `overridden` (step 3 §0.a).

What `apply` writes, so no step re-does it:

- **Every entry this step writes or rewrites carries a `signature_source` (`T1` / `T1-low` / `T2` / `T3`)**: the tier that contributed the structural signature, matching create-skill's entry contract, set from the tool that produced it: an ast-grep match contributes `T1` (with `confidence: T1` and the recipe's `ast_node_type`), and a signature read by eye (`extraction_method: source-read`) contributes `T1-low` at any tier (with `ast_node_type: null`), never `T1`. §2's stats helper bins each entry on this field. An entry the run left alone keeps its exact value, apart from §2's relabel, and a rewritten one keeps every key the update does not set.
- **Normal mode** (`incremental`): a renamed export takes its new `export_name`; a modified one its `params[]`, `return_type`, `source_line`, `confidence`, `extraction_method` and `ast_node_type` from the fresh extraction; a moved one its `source_file` and `source_line`; a deleted export, and every entry of a deleted file, is removed; a new export, and each export of an added file, gets a full entry (`export_name`, `export_type`, `params[]`, `return_type`, `source_file`, `source_line`, `confidence`, `extraction_method`, `ast_node_type`, `signature_source`). A docs-only skill's re-fetched documents replace the entries of each changed URL.
- **Gap-driven mode** (`no_reextraction` true, step 3 §0): one write per verification record. A `verified` export the map holds stays byte-identical; a `moved` one takes the `source_line` (and `source_file`) the spot-check found, the line that defines the export; a `re-extracted` one (step 3 §0a) gets a full entry from its AST record; a `rescoped` one is removed. A cited `NEW_EXPORT` or `MODIFIED_EXPORT` the map does not hold, whose spot-check found its definition line and whose public-reachability gate passed, gets one `source-read` entry (`confidence: T1-low`, `extraction_method: source-read`, `ast_node_type: null`, `signature_source: T1-low`) at the line its `source_citation` names (`verified`) or at `new_location` (`moved`), at most one per `export_name` and `source_file`, with `export_type`, `params[]` and `return_type` from step 4's `merge-records.json`. An `unknown` `NEW_EXPORT` the map does not hold with a `Medium`, `Low` or `Info` severity gets an entry from merge's records with no `source_file` or `source_line`. A `missing` export, an `unknown` one the map holds, and an `unknown` `MOVED_EXPORT` stay as they are, for a person: `apply` names each in its `warnings` (`{export_name}: {outcome}`, ending with the test report's definition lines for a rule R5 gap, and naming the drift under the override).
- **Degraded mode** (`full`): every export the extraction found gets an entry.
- **`file_entries[]`**: a MODIFIED_FILE row takes the hash Category D read; a DELETED_FILE row is removed; each NEW_FILE script or asset gets a row (`file_name`, `file_type`, `source_file`, `confidence: "T1-low"`, `extraction_method: "file-copy"`, `content_hash`, hashed under `{source_root}`); each document `promoted_docs_new[]` holds gets a `doc` row (`file_name` `docs/authoritative/{path}`, `extraction_method: "promoted-authoritative"`, the hash step 2 §1b read).

Dispatch on its exit code:

- **0:** it printed `{status: "written", entries, file_entries, warnings, map}`. Bind `{provenance_spot_check_warnings}` ← its `warnings`, and add each to `warnings[]`; the update report lists each as a WARN (report.md §2).
- **3** (`status` `refused`): a blocking gap reached the provenance write with no source line (`blocking_unresolved[]`: a `NEW_EXPORT` the map does not hold, `unknown`, with a severity other than `Medium`, `Low` or `Info`, a missing one included). Step 3 §0 bullet 2 sends every such gap to §0a, which halts with `halted-for-remediation-path` before merge, so this happens only when step 3 was skipped or bypassed: `apply` wrote nothing, and no null citation is written. HALT with status `blocked` and write no `metadata.json`, `provenance-map.json` or other artifact. Tell the user: "**A blocking gap reached the provenance write with no source line:** {each export name, with its severity or "no severity"}. Step 3 should have stopped on it with `halted-for-remediation-path`. The halt restored SKILL.md and references/ from the snapshot step 4 took; give each gap a `file:line` Source or name the file that defines its export in its Remediation (or downgrade it to Medium, Low or Info), then re-run update-skill." The halt procedure takes `phase: "write:provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "blocking-gap-unresolved: {export names}: step 3 should have halted with halted-for-remediation-path"`.
- **Exit 1, no JSON, or no candidate resolves:** HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "<its stderr, or skf-build-change-manifest.py is missing; re-install SKF>"`).

**For script/asset file changes (if `file_entries` exists):** `apply` updates the rows; copy the files themselves into `{skill_package}`:
- MODIFIED_FILE: copy the file from `{source_root}` to `scripts/` or `assets/` (the row's `content_hash` is updated by `apply`)
- DELETED_FILE: remove file from `scripts/` or `assets/`
- NEW_FILE: copy the file from `{source_root}` to `scripts/` or `assets/` (`apply` adds its row with `file_name`, `file_type`, `source_file`, `confidence: "T1-low"`, `extraction_method: "file-copy"`, `content_hash`)
- A `doc` row is source-tracked, never bundled: copy and remove nothing for it.

**The update operation block** `apply` sets at the top level of `{forge_version}/provenance-map.json`, the one place an update is recorded: it sets these keys there, replacing the values an earlier update wrote, so the map holds one block, for the latest update, never a history. `update_type` follows the run's mode as report.md §2 names it (`{update_mode}`): `incremental` for `normal`, `gap-driven` for `gap-driven`, `full` for `degraded`. `last_update` is the `generation_date` §2 wrote, and `test_report_run_id` the `{test_report_run_id}` of the test report a gap-driven run applied (null in the other modes), which step 1 §4b then never offers again. Add no other update-history key; one an older SKF version wrote (`update_operations[]`, `update_metadata`) stays as it is. §2 writes neither `last_update` nor `update_type` into metadata.json and removes one an older SKF version left there.
```json
{
  "last_update": "{generation_date}",
  "update_type": "{incremental if normal | gap-driven if gap-driven | full if degraded}",
  "test_report_run_id": "{test_report_run_id if gap-driven, else null}",
  "files_changed": {count},
  "exports_affected": {count},
  "confidence_tier": "{tier}",
  "manual_sections_preserved": {count}
}
```

`manual_sections_preserved` = `len(preserved) + len(moved)` from the §1 `manual-verify` verdict (blocks that survived byte-identical, whether in place or relocated). Do not re-count markers by hand: the §1 verdict is the deterministic source. `files_changed` and `exports_affected` are `apply`'s own counts: the files and export changes of the change manifest, or in gap-driven mode the files of the entries the run changed and the verification records.

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

### Validation Summary
- Spec compliance: {PASS/WARN/FAIL/SKIP} (quality score {score}/100)
- [MANUAL] integrity: {PASS/FAIL}
- Confidence tiers: {PASS/WARN}
- Provenance: {PASS/WARN}
- Diff: {new} new, {fixed} fixed issues, or SKIP
- Security: {PASS/WARN/SKIP}

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

**Scope and Targeted Re-Extraction population:** read `{run_dir}/evidence-records.jsonl`, where step 2 (§1b, §1c and §2.2) and step 3 (§0a) appended their records, one JSON line each. Write each record under its key as it was recorded, and `none` for a key no line holds (or when the file does not exist), so a headless decision such as a deletion-ratio continue stays visible after the run.

**Validation Summary population:** §4 writes `[MANUAL] integrity` from §1's `manual-verify` verdict (`PASS` when `ok`) and `Confidence tiers` from §2 (`PASS` when the stats helper reported no label violation, else `WARN` naming `{provenance_relabels}`), with placeholders for the rest. §6 fills `Provenance`, and §7 fills `Spec compliance`, `Diff` and `Security`, each in the on-disk report, as §5 fills the Context Snippet sub-block.

**Description Guard population** (used by §7 Post-Write Validation when the §0 protocol fires): fill all four fields from context when `description_guard_restored == true` (triggering tool, whether restore succeeded, and what changed, based on the recorded `description_guard_diff_kind`). When `Restored: false`, the other three fields are `—` — this is the clean-run expected state — except when `description_guard_refused == "empty-capture"` (§0's empty-snapshot rule): then set `Triggering tool` to the recorded tool name, `Original description preserved: false`, and `Notes: guard refused — empty captured snapshot (empty-capture)`, so a refused restore is distinguishable from a run where the guard never fired. Same field semantics and populator logic as create-skill step 6 §8.

**Context Snippet population** (used by §5 after the staleness check runs): §4 writes the sub-block with placeholders; §5 updates the on-disk evidence report in place after deciding whether to regenerate. Set `Regenerated: true` and populate `Triggers fired` with any combination of `headline-exports`, `version`, `gotchas` when at least one trigger fired. Set `Regenerated: false` and `Triggers fired: —` when none fired (the gap-driven / internals-only outcome). Always fill `Notes` with a one-sentence reason (e.g., `"Gap-driven repair — no snippet surface changed"`, `"Version bumped 0.1.0 → 0.2.0; headline exports re-ranked"`).

### 5. Regenerate context-snippet.md

**Regenerate `context-snippet.md` if stale:**

`context-snippet.md` is a `{skill_package}` deliverable that goes stale whenever **headline exports**, **version**, or **gotchas** change in this run. Regenerate it only when at least one of these triggers fired; otherwise skip — a skip is the correct outcome for gap-driven repairs and other runs that touch internals below the snippet's surface, where regenerating would produce byte-identical content.

**Staleness triggers:**

- **Headline exports changed** — the top-K exports surfaced in the snippet differ from the prior snippet (a `NEW_EXPORT` was promoted into a headline slot, or a `MODIFIED_EXPORT` changed the signature/shape of a surfaced export).
- **Version changed** — §2 bumped `version` (normal mode with detected source drift; never fires in gap-driven mode per §2's carve-out).
- **Gotchas changed** — new gotchas surfaced from this run's evidence that were not in the prior snippet, or a prior gotcha was invalidated and removed.

**Record the decision on the on-disk evidence report:** open `{forge_version}/evidence-report.md` (written by §4 with placeholder values in the `### Context Snippet` sub-block) and update that sub-block under the Update Operation section just written. Set `Regenerated: true|false`, fill `Triggers fired:` with the list of triggers that fired (or `—` when none), and write a one-sentence `Notes:` entry. See §4's "Context Snippet population" note for field semantics.

**If no trigger fired:** skip regeneration: do not touch `context-snippet.md` on disk. The snippet remains valid against the prior run's surface. Continue to §6.

**If at least one trigger fired:** regenerate the snippet using the format from `skf-create-skill/assets/skill-sections.md` (pipe-delimited indexed format).

Use the **flat draft form** for the `root:` path in the draft snippet: `root: skills/{skill-name}/`. The per-IDE skill root (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/` — see `skf-export-skill/assets/managed-section-format.md`) is applied later by `export-skill` step 3 when the skill is exported. Do not choose an IDE-specific prefix in update-skill — that is an export-time decision that depends on config.yaml.

Pull values for the regenerated snippet from the updated metadata.json (version, top exports), the merged SKILL.md (section anchors, inline summaries), and the evidence report (new gotchas). If gotchas cannot be derived from the updated evidence but the prior snippet has a `|gotchas:` line, carry forward the prior line with the `[CARRIED]` marker — see `skf-export-skill/references/generate-snippet.md` for the carry-forward protocol (one-cycle limit).

Write the regenerated snippet to `{skill_package}/context-snippet.md`, preserving file permissions.

### 6. Provenance Completeness

Provenance completeness is a deterministic set-diff plus citation resolution over `metadata.json` (§2) and `provenance-map.json` (§3). Run it against the just-written artifacts via `{verifyProvenanceCompletenessHelper}`:

```bash
uv run {verifyProvenanceCompletenessHelper} verify \
    --metadata "{skill_package}/metadata.json" \
    --provenance "{forge_version}/provenance-map.json" \
    --source-root "{source_root}" \
    --skill-dir "{skill_package}" \
    --check-node-kinds \
    -o "{forge_data_folder}/{skill_name}/.skf-update-verify.json"
```

The helper reads its `--source-root` (falling back to the provenance map's own `source_root` field when the flag is omitted); pass the resolved `{source_root}` so citation resolution runs against the same tree re-extraction read. When `{source_root}` is null, empty or a URL (a docs-only skill), leave out the `--source-root` line: an empty flag value fails the helper's arguments, and the citation check must still run. When `{source_tree_status}` is `ready` or `offline`, `{source_root}` is still the tree init.md §6b prepared (step 7 removes it), so citations resolve against the commit §2 recorded. It writes its JSON to `{forge_data_folder}/{skill_name}/.skf-update-verify.json`, beside the §1b lock (each run overwrites it). **Read that JSON and do NOT recompute the set operations by eye, since an LLM set-diff can silently pass a dropped or orphaned entry:**

- `missing[]` — documented exports (metadata `exports[]`) with no provenance entry: a coverage gap.
- `orphaned[]` — provenance `entries[].export_name` whose export was removed but the entry remains.
- `summary.set_diff`: `not-applicable` for a reference app (`scope_type: reference-app` in `{skill_package}/metadata.json`), whose `exports[]` is empty by design while its entries follow each citation: the helper then diffs no sets, `missing[]` and `orphaned[]` stay empty, and its `status` comes from `stale[]`, `citations[]` and `node_kinds[]` alone. `checked` for every other skill.
- `stale[]`: entries whose `source_file:source_line` no longer resolves or is not the line that defines the export; each carries a `reason` of `file-missing`, `line-out-of-bounds`, `line-invalid` or `line-not-definition`. A `line-not-definition` item lists in `definition_lines` every line of the file that defines the export (the `def` or declaration line itself, not a decorator or blank line above it). An empty list means the rules found no definition line, which may be a shape they do not cover: the entry is unverified, not gone. Internal names are canonicalized through `reexport_map` before the diff, so a barrel-renamed export does not read as missing or orphaned.
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

   Pass `--no-line-moves` when `{workspace_drift_status}` is `overridden` (step 3 §0.a): the tree read is not the recorded commit, so its lines prove nothing about the map. `fix` prints `applied[]` (each fix it made), `left_as_warn[]` (each finding it left for a person, with its `why`), `files_written[]` and `manual_verify` (the SKILL.md [MANUAL] blocks checked against `{manual_inventory}` after its writes).
   - **`manual_verify.ok` is false** (a [MANUAL] block changed): HALT with status `halted-for-manual-mismatch`. The halt procedure takes `phase: "write:verify-manual-integrity"`, `path: "{skill_package}/SKILL.md"`, `reason: "[MANUAL] blocks changed after the provenance fixes: ..."`, as §1's does. Alert the user: "**[MANUAL] section integrity failure after the provenance fixes.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Verified against the inventory `{manual_inventory}`. {manual_recovery}", with `{manual_recovery}` as §1 gives it: §8 has not pointed the `active` link at a new version yet, so this halt rolls back as §1's does.
   - **Exit 2** (no JSON; its stderr line names any file it already wrote): record `Provenance: WARN (not fixed: verifier error)` with that line, re-read each file it names into context, and go on to step 2.
   - **Otherwise:** re-read each file in `files_written[]` into the in-context copies (the merged SKILL.md and `references/` content and §3's provenance map), so later sections and the report read the fixed text, and add `SKILL.md` and `provenance-map.json` to `files_written[]` (report.md §5b) when `fix` wrote them.
2. **Node kinds.** For each `node_kinds[]` item, take the entry at its `entry_index` in `{forge_version}/provenance-map.json` as step 1 left it (its `export_name` and `source_file` confirm it). When this run's extraction record (re-extract.md `Per-file extractions` or a §0a `re-extracted` record) names the recipe that matched that export (`ast_recipe`), set the entry's `ast_node_type` to the `kind` that recipe declares in `{extractionPatternsData}` (the ast-grep Patterns table in create-skill's `extraction-patterns-by-hand.md`, which that section of `{extractionPatternsData}` points to, gives the kind of a `find_code` pattern). When no record names one (a `verified` or `moved` entry has none), look the kind up at the entry's `source_file` and `source_line`: from `{project-root}`, run `uv run {verifyProvenanceCompletenessHelper} kind-at --source-root "{source_root}" --file "{source_file}" --line {source_line} --name "{export_name}" --recipes "{extractionPatternsData}"` and set the `kind` it prints when `status` is `found`. List a WARN, with the status, for any other status or an exit 2, when there is no local source tree, or when `{workspace_drift_status}` is `overridden` (step 3 §0.a: the tree read is not the recorded commit, so run no `kind-at`). Never invent a kind, and never change `extraction_method` to clear the finding. Write the map with `python3 {atomicWriteHelper} write --target {forge_version}/provenance-map.json` (resolve it ← first existing path in `{atomicWriteProbeOrder}`, the new map on stdin); if neither path resolves, fix no node kind and list each one as a WARN. Apply the same change to §3's in-context map, and add `provenance-map.json` to `files_written[]`.

These fixes apply to any entry, a gap-driven `verified` or `moved` entry included (§3). Fix nothing else: each `left_as_warn[]` item stays for a person to decide, and so do `missing` / `orphaned` exports. A `line-not-definition` item with an empty `definition_lines` is never fixed: list its export as unverified.

Map the re-run's `status` to the `Provenance:` line of the §4 evidence report's Validation Summary: `PASS` when `status == "pass"`, `WARN` when `status == "findings"`. For a reference app that status comes from its stale lines, citation prefixes and node kinds alone (`summary.set_diff` `not-applicable`): note `set diff not applicable: reference app` in the Validation Summary, never as a WARN. Provenance findings are **advisory**: they do not block the update. In the evidence report's Validation Summary, list the source lines, citation prefixes and node kinds this section fixed (`fix`'s `applied[]` and step 2's kinds) and the unverified exports, then each `left_as_warn[]` item and each other `missing` / `orphaned` / `stale` / `citations` / `node_kinds` finding the re-run still reports as a WARN so the user can decide, and note `source lines not checked: no local source tree` when `stale_check` was `skipped-no-source-root`, `node kinds not checked: no ast-grep CLI` or `node kinds not checked: unrecognized ast-grep` when `node_kind_check` was `skipped-no-ast-grep` or `skipped-unrecognized-ast-grep`, each `node_kinds_unchecked[]` entry with its `reason`, and `summary.node_kind_check_skipped` when it is above 0. Add each of those WARNs, the unverified exports and each entry of `{provenance_spot_check_warnings}` (§3) to the envelope's `warnings[]` with a `provenance:` prefix (for example `provenance: search line 26 does not define it; definition lines 27, 31`).

**Under the drift override** (`{workspace_drift_status}` is `overridden`, step 3 §0.a), the verifier read `{source_root}` at HEAD, not the pinned commit, and a file or line missing at HEAD may still be at the pinned commit: end the `Provenance:` line of the Validation Summary, and each WARN this section lists for a `stale[]` finding (`file-missing`, `line-out-of-bounds`, `line-invalid`, `line-not-definition`), an unverified export or a finding `fix` left as `line-moves-skipped`, with ` (drift override: HEAD {head_short_sha} is not pinned {pinned_short_sha})`.

**Graceful degradation:** if neither probe path resolves (no `uv` / script available), fall back to the manual set comparison the script encapsulates: enumerate metadata `exports[]` and provenance `entries[].export_name` (canonicalizing internal names through `reexport_map`), diff the two sets for missing/orphaned entries, and spot-check that each `source_file:source_line` still points at a real line in the source tree. Skip the set diff for a reference app (`scope_type: reference-app` in `{skill_package}/metadata.json`), as the helper does: its `exports[]` is empty by design while its entries follow each citation, so spot-check the lines only and note `set diff not applicable: reference app`. The definition-line, citation-prefix and node-kind checks do not run in this fallback, and nothing is fixed: record `line, citation and node-kind checks not run: verifier missing` in the Validation Summary. Prefer the script: it does this deterministically.

### 7. Run Post-Write Validation

skill-check runs once per update, here, against the written package. Check that it is available, never assume it: run `npx skill-check -h`.

**Description Guard Protocol:** every invocation below that may modify SKILL.md (`skill-check check --fix` and any `split-body` write) must run inside the four-phase guard defined in §0. Invoke `{descriptionGuardHelper}` at the capture and verify-restore points around each call:

```bash
# Phase 1: capture before any frontmatter-touching tool call
uv run {descriptionGuardHelper} capture "{skill_package}/SKILL.md"
# stash returned `description` as `guarded_description`

# Phase 2: run the tool (skill-check --fix, split-body --write)

# Phases 3+4: verify and restore after the tool call
uv run {descriptionGuardHelper} verify-restore "{skill_package}/SKILL.md" \
    --captured-description "{guarded_description}"
```

Do not rely on per-call ad-hoc preservation logic: use the helper.

**If skill-check is available:**

- Run `npx skill-check check "{skill_package}" --fix --format json` **inside the §0 guard**. One call validates the package against the spec, scores it, fixes what has one answer and runs the security scan (on unless `--no-security-scan` is passed). Read the JSON, not the exit code: the quality score (`scores[].score`, the entry matching the skill, or a top-level `qualityScore` on an older skill-check), the remaining `diagnostics[]`, `fixed[]` and the security findings. When the scan could not run (no `SNYK_TOKEN`), record `Security: SKIP (SNYK_TOKEN not configured)`.
- **Context sync after --fix:** if `fixed[]` is non-empty, re-read the SKILL.md `--fix` changed into the in-context copy, so the report does not work from a copy that differs from the file on disk. The §0 guard has already restored `description` if it diverged.
- If `body.max_lines` is reported, prefer a selective split: extract only the largest Tier 2 section(s) to `references/`, keeping Tier 1 inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). **Never move a section that holds a `[MANUAL]` block:** init.md §5 inventories SKILL.md only, so a block moved to `references/` would leave the next update's inventory. Fall back to `npx skill-check split-body "{skill_package}" --write`, **inside the §0 guard** (it can also touch frontmatter), only when SKILL.md holds no `[MANUAL]` block (§1's verdict lists none): it moves every section. Verify anchors resolve after a split.
- When a previous version is on disk (outside gap-driven mode), run `npx skill-check diff "{skill_group}/{baseline_version}/{skill_name}" "{skill_package}"` and record its new and fixed issues as informational; otherwise record `Diff: SKIP`.

**Re-check the [MANUAL] blocks** once `--fix` and any split have run, from `{project-root}`:

```bash
uv run {hashContentHelper} manual-verify "{skill_package}/SKILL.md" \
    --inventory "{manual_inventory}"
```

On `ok` false, HALT with status `halted-for-manual-mismatch`, as §1 does. The halt procedure takes `phase: "write:verify-manual-integrity"`, `path: "{skill_package}/SKILL.md"`, `reason: "[MANUAL] blocks changed after skill-check: modified {modified}; missing {missing}"`. Alert the user: "**[MANUAL] section integrity failure after skill-check.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Verified against the inventory `{manual_inventory}`. {manual_recovery}", with `{manual_recovery}` as §1 gives it: §8 has not pointed the `active` link at a new version yet, so this halt rolls back as §1's does.

**If skill-check is unavailable:** record `Diff: SKIP` and `Security: SKIP (skill-check unavailable)`, and check the structure by script instead: resolve `{validateOutputHelper}` ← first existing path in `{validateOutputProbeOrder}` and, from `{project-root}`, run `uv run {validateOutputHelper} "{skill_package}"`. Record `Spec compliance: PASS (skf-validate-output.py)` when it reports no issue, and `Spec compliance: WARN (skf-validate-output.py)` with each issue it reports otherwise; when no candidate resolves, record `Spec compliance: SKIP (skill-check unavailable, no validator)`. Nothing here changes SKILL.md, so the [MANUAL] re-check above does not run.

Record the results in the evidence report's Validation Summary (§4): `Spec compliance` from the score and the remaining `diagnostics[]`, `Diff` and `Security`, with any `description_guard_restored` event the §0 protocol recorded. They are advisory: do not block on warnings.

### 8. Update the Active Symlink

Flip `{skill_group}/active` to point at the current `{version}` via the helper, now that §6 and §7 have checked the written package. The call is **always** run: atomic, idempotent, and verified in one shot. The helper's no-op path handles the "version did not change" case (gap-driven mode, or no source drift) without writing to disk:

```bash
uv run {updateActiveSymlinkHelper} update \
    --skill-group {skill_group} \
    --version {version}
```

The helper emits a result envelope with `status` ∈ `{ok, flipped, mismatch, missing-target}` and a pre-formatted `log_message`. Log the message to the evidence report.

**Dispatch on `status`:**

- **`ok`** (exit 0): symlink already points at `{version}`, so no disk write. Continue to §8a.
- **`flipped`** (exit 0): symlink was atomically updated (temp-and-replace). Continue to §8a.
- **`missing-target`** (exit 2): `{skill_group}/{version}/` does not exist on disk, so step 4 §6b did not create it. HALT and display `halt_message` verbatim.
- **`mismatch`** (exit 2): the link still points elsewhere after the flip. HALT and display `halt_message` verbatim.

Both exit-2 halts carry status `halted-for-write-failure`; the halt procedure takes `phase: "write:active-symlink"`, `path: "{skill_group}/active"`, `reason: "<status>: <halt_message>"`. Its rollback removes the new version (the `active` link does not name it) or, in gap-driven mode, restores the package from the snapshot.

### 8a. Verify the Active Symlink

Check, read-only, that the `active` link resolves to the version §2 wrote to `metadata.json`, in every mode (consumers that do not read the export manifest fall back to the link, `knowledge/version-paths.md` §Reading Workflows step 5):

```bash
uv run {updateActiveSymlinkHelper} verify \
    --skill-group {skill_group} \
    --version {version}
```

On `mismatch` (exit 2), HALT with status `halted-for-write-failure` and display the helper's `halt_message` verbatim: it names the diverged target, the expected version and the recovery command. The halt procedure takes `phase: "write:verify-active-symlink"`, `path: "{skill_group}/active"`, `reason: "mismatch: <halt_message>"`.

### 9. Move the Workspace Clone to the Recorded Commit

Run only when `{source_tree_status}` is `ready` and `{workspace_clone}` is not null. test-skill and audit-skill read the skill's source from metadata.json `source_root`, the clone SKF keeps for this repository, and test-skill compares its HEAD with the `source_commit` §2 just wrote. From `{project-root}`, resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}`, `{cccGitHygieneHelper}` ← first existing path in `{cccGitHygieneProbeOrder}` and `{checkWorkspaceDriftHelper}` ← first existing path in `{checkWorkspaceDriftProbeOrder}`, then run:

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

Pass `--hygiene-helper` and `--drift-helper` only when they resolved. `{source_commit}` is the commit init.md §6 read from metadata.json, before §2 recorded `{target_commit}`, and `{tree_timeout}` is the time limit init.md §6b chose: the helper stops itself within it.

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

