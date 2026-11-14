---
nextStepFile: 'verify-publish.md'
# Resolve `{hashContentHelper}` to the first existing path; HALT if neither
# candidate exists. §1 uses its `manual-verify` subcommand to verify SKILL.md
# against the byte-exact [MANUAL] inventory step 4 §4 amended; a
# marker-count comparison would pass a block whose interior was truncated
# without changing the marker count.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# Resolve `{buildChangeManifestHelper}` to the first existing path; HALT if
# neither exists: §3's `apply` writes the provenance map and §3b's `metadata`
# call metadata.json, from this run's records, never by hand.
buildChangeManifestProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-build-change-manifest.py'
  - '{project-root}/src/shared/scripts/skf-build-change-manifest.py'
# Resolve `{rebuildManagedSectionsHelper}` to the first existing path: §5
# reads and writes the snippet's gotchas line with its `gotchas` action.
# HALT if neither exists.
rebuildManagedSectionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py'
  - '{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py'
# SKILL.md binds `{emitEnvelopeHelper}` and `{runStateHelper}` for every
# stage; resolve them again when a binding was lost: first existing path wins.
# The warnings go to the run log through the first; the halt procedure runs
# the second.
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

Verify the merged SKILL.md that merge-write.md §6b wrote to disk and write the derived artifacts (metadata.json, provenance-map.json, evidence-report.md, context-snippet.md); verify-publish.md then checks the written package and only then points the active symlink at the new version.

## Rules

- Focus only on verifying merged files and writing derived artifacts — merge content was already written in step 4
- Do not modify merged SKILL.md or `references/` content: verify-publish.md §6 and §7 make the only edits after the merge. Any mismatch detected during verification triggers HALT, not repair
- Do not skip provenance map update — critical for future audits
- HALT immediately on verification failure: §1 halts before any derived artifact is written, and verify-publish.md §8 points the `active` link at the new version only after verify-publish.md §6 and §7, the last checks that can halt, so every halt in this step rolls back a version no reader sees yet. A partial-write skill package is worse than an unchanged one
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

Pass `--tree` when load-baseline.md §6b bound `{source_tree}`, always `--lock` and `--owner`, and `--emit` in `{headless_mode}`. Until verify-publish.md §10 closes the window, the helper first undoes what this run wrote, keeping a version the `active` link already names (verify-publish.md §8, its `kept`); then it removes the private source tree, releases the run lock and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line, with a warning (`rollback-incomplete`, `source-tree-not-removed`, `run-lock-not-released`) for each step it could not finish: do none of it yourself. Tell the user in one line what it restored, removed or kept, and name each path its `failed[]` lists for the user to restore or delete by hand. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "write:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place.

A `Write` or `Edit` call in §2 to §5 that errors (permission denied, disk full, path invalid) HALTs with status `halted-for-write-failure`: the halt procedure takes `phase: "write:artifact-write"`, `path: "{the file that failed}"`, `reason: "<the error>"`. verify-publish.md §6 checks what `metadata.json` and `provenance-map.json` hold.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 1. Verify SKILL.md Write

SKILL.md was written in merge-write.md §6b. Verify the write landed intact before proceeding to any derived-artifact writes.

- Verify the resolved `{skill_package}` path matches the version directory step 4 wrote to (outside gap-driven mode, merge-write.md §6b created `{skill_group}/{new_version}/` and rebound `{skill_package}` and `{forge_version}` to the new version)
- Run the deterministic [MANUAL]-integrity verifier against the byte-exact inventory step 4 §4 amended with the user's [MANUAL] decisions (the load-baseline.md §5 inventory, when there were none):

  ```bash
  uv run {hashContentHelper} manual-verify "{skill_package}/SKILL.md" \
      --inventory "{manual_inventory}"
  ```

  The verdict JSON is `{"preserved":[...], "modified":[...], "missing":[...], "moved":[...], "ok":bool}`. A `modified` block is one whose byte-exact interior changed (an interior truncation); a `missing` block lost its markers entirely; a `moved` block is byte-identical but relocated with its logical parent section (clean — does not fail the gate). `ok == (modified empty AND missing empty)`.
- If `ok == true` and the path resolves: proceed to section 2. merge-write.md §6b checked the same file against the same inventory before it published it, so this is the confirmation that the write landed
- **If `ok == false`: HALT immediately** with status `halted-for-manual-mismatch`. Do not write `metadata.json`, `provenance-map.json`, or any other artifact: further writes would compound the inconsistency. The halt procedure takes `phase: "write:verify-manual-integrity"`, `path: "{skill_package}/SKILL.md"`, `reason: "[MANUAL] blocks differ from the approved inventory: modified {modified}; missing {missing}"`. Alert the user:

  "**[MANUAL] section integrity failure after write.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Relocated-but-intact (advisory only): {moved}. Verified against the inventory `{manual_inventory}`, on disk at `{skill_package}/SKILL.md`. {manual_recovery}"

  `{manual_recovery}` depends on the mode:

  - **Outside gap-driven mode** (merge-write.md §6b created a new version folder): "The previous version at `{skill_group}/{baseline_version}/` is unchanged, and the halt removed `{skill_group}/{new_version}/` and `{forge_data_folder}/{skill_name}/{new_version}/`, which step 4 created for this update: re-run update-skill."
  - **Gap-driven mode** (the repair edited the current version in place): "The halt restored the package, with its [MANUAL] blocks, its provenance map and evidence report, and the skill brief, from the snapshot step 4 took before its first write: the skill is as it was. Re-run update-skill."

### 2. Prepare the Write Inputs

Prepare what §3's `apply` and §3b's `metadata` call read, before either runs:
- **Apply the queued metadata patches.** When merge Priority 8b wrote `{run_dir}/metadata-patches.json` (gap-driven `metadata update` entries; no file, no patch), set in `{skill_package}/metadata.json`, before §3's `apply` reads it, each field of the `set` of each of its `metadata_patches[]` (`a.b` names a nested field). Leave out a field §3b's `metadata` call writes (its `--help` lists them, e.g., `exports_documented`), whose value it would overwrite, and `exports[]`, which §3's `apply` builds from the list it reads. For each field, append the record `metadata_patch_outcome: {gap_id, field, outcome, why}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `metadata_patch_outcome`: `outcome` `applied` with `why` null, or `left-out` with `why` the reason (`the metadata call writes it`, `apply builds exports[]`). §3b adds a `dropped` line for an applied field the call drops, so a still-stale value surfaces in both reports rather than being silently overwritten.
- `--version "{new_version}"` is the version merge-write.md §6b chose; never pick another. From here on `{version}` is `{new_version}`.
- Bind `{generation_date}` ← the current UTC time to the second, read from the clock with `date -u +%Y-%m-%dT%H:%M:%SZ`, never typed: load-baseline.md §4b offers a test report only when it is newer. It is the only update bookkeeping metadata.json carries, in every mode: §3's update operation block records `last_update` and `update_type` in provenance-map.json, and the `metadata` call removes either key an older SKF version left in metadata.json.
- **Record the source commit** (when `{source_tree_status}` is `ready` or `offline`): pass `--source-commit "{target_commit}"` to §3b's `metadata` call, the commit every step of this run read, and, when `{target_ref_override}` is set, `--source-ref "{target_ref}"`. The call leaves `source_root` as metadata.json records it: it names the clone SKF keeps for the repository; never write `{source_tree}` or any other path of this run into an artifact. For any other source (a local folder, gap-driven mode, docs-only) pass neither, which keeps both. When `{source_root_override}` is set (load-baseline.md §6: a local source that moved, named by `--source-root` or by the user), also pass `--source-root "{source_root_override}"`, gap-driven mode included, so later runs read the source there; otherwise the call leaves `source_root` as it is. Bind `{map_source_commit}` ← `{target_commit}` when `{source_tree_status}` is `ready` or `offline`, else the `source_commit` metadata.json records, and `{map_source_ref}` ← `{target_ref}` when `{target_ref_override}` is set, else its `source_ref`, each `""` for a null one: the values §3b's call leaves in metadata.json, which §3's `apply` writes to the map. The in-context `{source_commit}` stays the value load-baseline.md §6 read; verify-publish.md §9 needs it.

### 3. Write Updated provenance-map.json

Write `{forge_version}/provenance-map.json` with `{buildChangeManifestHelper}` `apply` (resolve it ← first existing path in `{buildChangeManifestProbeOrder}`), never by hand: it reads `{provenance_map_path}`, the map the update started from (load-baseline.md §4: the current version's map, else the flat one an older skill keeps in `{forge_data_folder}/{skill_name}/`), and this run's records in `{run_dir}`, and writes the whole updated map through a temporary file and one rename. When merge-write.md §6b created a new version, `{forge_version}` is its forge folder, which holds a copy of the previous map when there was one, the same bytes `apply` reads: write the whole updated map there, and leave the previous version's map as it was. In a repair `{provenance_map_path}` is the only map there is: `apply` writes the updated map to `{forge_version}`, and a flat map stays as it was. A repair of a skill whose forge data is flat (load-baseline.md §4 bound the flat map) may find no forge folder for its version, and `apply` writes only into a folder that exists. In gap-driven mode, first create it, as report.md §5b does. From `{project-root}`, run:

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

`{update_type}` follows the run's mode as report.md §2 names it (`{update_mode}`): `incremental` for `normal`, `gap-driven` for `gap-driven`, `full` for `degraded` (a degraded run has no map: leave out `--provenance-map`, and `apply` starts a new one). Pass each `{run_dir}` file the run wrote: the change manifest and the records in every mode, `category-c.json` and `ccc-pairs.json` (step 2's Category C and its CCC check), `extraction.json` and `export-details.json` when step 2 wrote them, `merge-records.json` when step 4 did, the Category D files (`category-d-compare.json`, and `new-files.json` when step 2 wrote it: a skill with no brief has none) with `--source-root` when step 2 ran Category D, and `promoted-docs.json` when reconcile-scope.md §1b wrote it. `{generation_date}` is the value §2 bound, `--test-report-run-id` goes only with a gap-driven run (the `{test_report_run_id}` of the report it applied), `{manual_sections_preserved}` is `len(preserved) + len(moved)` from the §1 `manual-verify` verdict (never a marker count), and `{map_source_commit}` and `{map_source_ref}` are the values §2 bound, the `source_commit` and `source_ref` §3b's `metadata` call leaves in `metadata.json` (an empty string for a null one): audit-skill reads its baseline commit from the map's top-level `source_commit` and `source_ref`. Pass `--drift-head` and `--drift-pinned` only when `{workspace_drift_status}` is `overridden` (gap-driven.md §3). Pass `--metadata-in` and `--lists-out` in every mode: `apply` writes there the lists §3b's `metadata` call reads. Every entry `apply` writes carries `signature_source`, which §3b's stats helper bins (an entry the map held with none, or with a value other than `T1`, `T1-low`, `T2` or `T3`, as a map written before the key existed does, takes its `confidence` when that is `T1-low`, `T2` or `T3`, else `T1` when its `extraction_method` is `ast-grep` or `ast_bridge`, else `T1-low`), and `apply` sets the map's update operation block (`"last_update"`, `"update_type"` and its other keys), replacing an earlier update's.

Dispatch on its exit code:

- **0:** it printed `{status: "written", entries, not_public, relabeled, signature_source_backfilled, file_entries, warnings, map}` to `{run_dir}/apply.json`. Bind `{provenance_spot_check_warnings}` ← its `warnings`, and add each to `warnings[]`, recording them in one call, from `{project-root}`: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warnings-file "{run_dir}/apply.json"`; the update report lists each as a WARN (report.md §2). In gap-driven mode a `NEW_EXPORT` or `MODIFIED_EXPORT` the map holds whose spot-check ended `missing` or `unknown` keeps its entry unchanged, whatever its severity, with one of these warnings, which names the cause of an `unknown` (several map entries of its name, no definition line or several at the entry, a file no rule covers, a failed or skipped check, a citation of another file than the map's entries of its name); for a blocking gap (any severity but `Medium`, `Low` or `Info`) it also names the gap and the one fix a re-run acts on (gap-spot-check.md §4 bullet 1): fix the entry by hand, or, for several entries of its name, give the gap a `file:line` Source at the definition when that file holds only one of them, then re-run update-skill. A `cited-elsewhere` gap, whatever its severity, takes its own warning and fix in their place (gap-spot-check.md §4 bullet 1). A rule R5 `MOVED_EXPORT` whose map entry's file is gone keeps its entry unchanged too, whatever its severity, with a warning that names the file and the hand fix. An `outside-scope` gap (the skill brief's scope leaves out the file it names), whatever its severity, adds no entry, a placeholder included, and is never refused, with its own warning, which names the files left out and the fix: when the skill covers that file, change the brief's scope so it takes it (its `scope.include` or `scope.exclude`), then re-run update-skill; otherwise re-run Test Skill (gap-spot-check.md §4 bullet 1). `not_public` lists, `{name, file}`, each new export of a `public-api` skill it did not add in normal mode as off the public surface (the `public: false` mark of `reextract-records.json`, else the same rule over the `scope.type` and `entry_point_diff` of `extraction.json`), and one of its `warnings` counts them. When `extraction.json` names `public-api` but gives no surface the rule can read (Quick tier, a runner failure, an incomplete run), it adds every name, with one warning that says so. `relabeled` lists, `{name, file, from, to}`, each entry whose `signature_source` a gap-driven repair changed when it wrote the signature §4a's record gave (a record read by eye moves an `ast-grep` entry from T1 to T1-low), each with one of its `warnings`: §3b adds each name to `{provenance_relabels}`. `signature_source_backfilled` counts, by value, the entries it gave a `signature_source` because they lacked or held an unrecognized one (`{"T1-low": 2}`, `{}` when none), with one of its `warnings`, which also lists each unrecognized value it replaced (`name: old -> new`); it does not list them in `entries.updated`. In a map naming several libraries, one of its `warnings` counts and names each new entry it gave the map's first `source_library` because the entry's file or folder did not settle which (`<name> in <file>`, or `<name> (no file)`): check that entry's `source_library` in `{forge_version}/provenance-map.json` and correct it by hand when it names the wrong library.
- **3** (`status` `refused`): a blocking gap reached the provenance write with no source line (`blocking_unresolved[]`: a `NEW_EXPORT` the map does not hold, `unknown` for any cause but `outside-scope`, with a severity other than `Medium`, `Low` or `Info`, a missing one included). gap-spot-check.md §4 sends every such gap to its §4a and halts with `halted-for-remediation-path` before merge when §4a does not find it, so this happens only when that check was skipped or bypassed: `apply` wrote nothing, and no null citation is written. HALT with status `blocked` and write no `metadata.json`, `provenance-map.json` or other artifact. Tell the user: "**A blocking gap reached the provenance write with no source line:** {each export name, with its severity or "no severity"}. gap-spot-check.md §4 should have stopped on it with `halted-for-remediation-path`. The halt restored SKILL.md and references/ from the snapshot step 4 took; give each gap a `file:line` Source or name the file that defines its export in its Remediation (or downgrade it to Medium, Low or Info), then re-run update-skill." The halt procedure takes `phase: "write:provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "blocking-gap-unresolved: {export names}: gap-spot-check.md §4 should have halted with halted-for-remediation-path"`.
- **Exit 1, no JSON, or no candidate resolves:** HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:provenance-map"`, `path: "{forge_version}/provenance-map.json"`, `reason: "<its stderr, or skf-build-change-manifest.py is missing; re-install SKF>"`).

**For script/asset file changes:** `apply` updates the rows; copy or remove the files themselves in `{skill_package}`, each path the change manifest's `category_d` lists: a `scripts_*` path under `scripts/`, an `assets_*` path under `assets/`:
- MODIFIED_FILE (`*_modified`): copy the file from `{source_root}` (the row's `content_hash` is updated by `apply`)
- DELETED_FILE (`*_deleted`): remove the file
- NEW_FILE (`*_added`): copy the file from `{source_root}` (`apply` adds its row)
- A `docs_*` path is source-tracked, never bundled: copy and remove nothing for it.

### 3b. Write Updated metadata.json

Load, read the full file and follow `references/write-metadata.md`, then go on to §4.

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
- Body split: {each section verify-publish.md §7 moved and the references/ file it added, or none}
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

**Scope and Targeted Re-Extraction population:** read `{run_dir}/evidence-records.jsonl`, where reconcile-scope.md §1b and §1c, detect-changes.md §2.2 and gap-spot-check.md §4 appended their records, one JSON line each. Write each record under its key as it was recorded, and `none` for a key no line holds (or when the file does not exist), so a headless decision such as a deletion-ratio continue stays visible after the run.

**Repairs Applied population:** read the same file's `structural_fix` and `metadata_patch` lines (merge Priorities 8 and 8b), its `metadata_patch_outcome` lines (§2 and §3b) and its `reclassified` lines (gap-spot-check.md §4): only a gap-driven repair appends them. Write each line under its row as it was recorded, one item per line, and `none` for a row no line holds (or when the file does not exist), so each fix, patch and reclassified export the repair made reaches the user.

**Validation Summary population:** §4 writes `[MANUAL] integrity` from §1's `manual-verify` verdict (`PASS` when `ok`) and `Confidence tiers` from §3b (`PASS` when the stats helper reported no label violation, else `WARN` naming `{provenance_relabels}`), with placeholders for the rest. verify-publish.md §6 fills `Provenance`, and verify-publish.md §7 fills `Spec compliance`, `Diff` and `Security`, and `Body split` (`none` when no split ran), each in the on-disk report, as §5 fills the Context Snippet sub-block.

### 5. Regenerate context-snippet.md

**Regenerate `context-snippet.md` if stale:**

`context-snippet.md` is a `{skill_package}` deliverable that goes stale whenever **headline exports**, **version**, **gotchas** or **section anchors** change in this run. Regenerate it only when at least one of these triggers fired.

**Staleness triggers:** run the two `gotchas` calls of the regeneration paragraph below first, before you check any trigger: `gotchas prior` binds the `prior_api` the **Headline exports changed** ranking starts from, and `gotchas resolve` returns the line **Gotchas changed** compares. When no trigger fires, nothing is written from them.

- **Headline exports changed**: the api names `skf-export-skill/references/generate-snippet.md` §3b ranks for this run differ from the prior snippet's `|api:` line (a listed name left `exports` or is now deprecated, or a `NEW_EXPORT` took a free slot). In gap-driven mode it fires only when a name of the prior line left `exports` or SKILL.md now marks it deprecated or removed: a line that differs by the ranking alone (its order, a free slot or the tier's limit) waits for the next export.
- **Version changed**: §3b's `metadata` call wrote a version other than the one the run started from (never in gap-driven mode, which keeps its version, merge-write.md §6b).
- **Gotchas changed**: the `line` `gotchas resolve` returned (`skf-export-skill/references/generate-snippet.md` §3a, from the merged SKILL.md and this run's evidence report: at most 3 pitfalls, in its order) differs from the prior snippet's `|gotchas:` line, `[CARRIED]` markers aside.
- **Anchors changed**: the prior snippet's `|quick-start:` or `|key-types:` anchor differs from the one `generate-snippet.md` §3b item 4 gives for the merged SKILL.md (an anchor points into `references/` although SKILL.md has the heading, or a heading moved). Record it as `anchors` in `Triggers fired`.

**Record the decision on the on-disk evidence report:** open `{forge_version}/evidence-report.md` (written by §4 with placeholder values in the `### Context Snippet` sub-block) and update that sub-block under the Update Operation section just written: `Regenerated: true` with each trigger that fired in `Triggers fired:` (`headline-exports`, `version`, `gotchas`, `anchors`), or `Regenerated: false` with `Triggers fired:` left at the template's empty mark (a gap-driven repair, or a run that changed only internals), and always a one-sentence `Notes:` reason.

**If no trigger fired:** skip regeneration: do not touch `context-snippet.md` on disk. The snippet remains valid against the prior run's surface. Skip to the last paragraph of this section.

**If at least one trigger fired:** regenerate the snippet. Its content comes from `skf-export-skill/references/generate-snippet.md` §3a and §3b, as the paragraph below says; `skf-create-skill/assets/skill-sections.md` gives only its line format (pipe-delimited indexed format), not the `()` its `|api:` placeholder gives functions: §3b item 2 sets each api name's `()`.

Use the **flat draft form** for the `root:` path in the draft snippet: `root: skills/{skill-name}/`. The per-IDE skill root (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/`; see `skf-export-skill/assets/managed-section-format.md`) is applied later by `export-skill` step 2 when the skill is exported. Do not choose an IDE-specific prefix in update-skill: that is an export-time decision that depends on config.yaml.

Take the version from the updated metadata.json and the inline summaries from the merged SKILL.md. Rank the api names and verify the section anchors as `skf-export-skill/references/generate-snippet.md` §3b states, and derive the gotchas as its §3a states: the merged SKILL.md, this run's evidence report (`{forge_version}/evidence-report.md`) and the provenance map §3 wrote (`{forge_version}/provenance-map.json`, its `{forge_provenance_map}`) are the current sources. That file's two `gotchas` calls read and write the line, on the prior snippet before the regenerated one replaces it, and run before the staleness triggers above, which read them: resolve `{rebuildManagedSectionsHelper}` ← first existing path in `{rebuildManagedSectionsProbeOrder}` and, from `{project-root}`, run `uv run {rebuildManagedSectionsHelper} gotchas prior "{skill_package}/context-snippet.md" --skills-folder "{skills_output_folder}" --skill {skill_name}` and bind `prior_api`, `prior_gotchas` and `is_first_export` as its §2.5 does; write the judgments its §3a gives to `{run_dir}/gotchas-judgments.json` with a file write, then run `uv run {rebuildManagedSectionsHelper} gotchas resolve "{skill_package}/context-snippet.md" --skills-folder "{skills_output_folder}" --skill {skill_name} --judgments "{run_dir}/gotchas-judgments.json"`, write its `line` as the `|gotchas:` value (leave the line out when it is null), and add each warning its §3a emits to `warnings[]`, recorded as **Warnings go to the run log** says. Until an export records the skill, `is_first_export` is true here too, so `resolve` writes an unbacked prior pitfall unmarked and marks it `[CARRIED]` only once the skill has been exported. When `resolve` exits non-zero, correct the judgments file as its `error` says and run it once more. When `prior` fails, or `resolve` fails again, HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:context-snippet"`, `path: "{skill_package}/context-snippet.md"`, `reason: "<its error>"`).

Write the regenerated snippet to `{skill_package}/context-snippet.md`, preserving file permissions.

This step auto-proceeds: no user choices. Once §5 has run, load, read the full file, then execute `{nextStepFile}`, which checks the written package and publishes it.
