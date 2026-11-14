---
# `{renderMetadataStatsHelper}`: the `stats` block and
# `confidence_distribution`, the helper create-skill compiles them with.
# HALT if neither resolves: never bin them by hand.
renderMetadataStatsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-metadata-stats.py'
  - '{project-root}/src/shared/scripts/skf-render-metadata-stats.py'
# `{extractPublicApiHelper}`: the public API counts, the runner's or those
# `{entryPointsByHandData}` has it make. If neither exists, the count halts.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
entryPointsByHandData: 'skf-create-skill/references/entry-points-by-hand.md'
# `{verifyProvenanceCompletenessHelper}`: the label relabel. Advisory: if
# neither exists, each label violation is a WARN.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# `{extractionPatternsData}`: the Relabel Rule. If neither exists, relabel
# nothing: list each label violation as a WARN.
extractionPatternsDataProbeOrder:
  - '{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md'
  - '{project-root}/src/skf-create-skill/references/extraction-patterns.md'
# `{buildChangeManifestHelper}`: the `metadata` call. HALT if neither resolves:
# metadata.json is never written by hand.
buildChangeManifestProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-build-change-manifest.py'
  - '{project-root}/src/shared/scripts/skf-build-change-manifest.py'
# `{compareDocHashesHelper}`: a docs-only skill's `refresh-hashes`.
# HALT if neither resolves, or the next update finds the same documents changed
# again.
compareDocHashesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5 §3b: Write Updated metadata.json

write.md §3b loads this file, then goes on to write.md §4. Every HALT below runs write.md's **Halt procedure**, and every warning follows write.md's **Warnings go to the run log** rule.

The `metadata` call below writes `{skill_package}/metadata.json` from the map and the lists write.md §3's `apply` wrote, never by hand:
- **Compute the `stats` block and `confidence_distribution` deterministically** with `{renderMetadataStatsHelper}` (resolve from `{renderMetadataStatsProbeOrder}`; first existing path wins): the same helper sibling create-skill compiles them with, so create and update emit byte-identical stats for identical inputs. The helper owns all the arithmetic: it bins each provenance `entries[]` row once by its `signature_source` tier into `confidence_distribution.{t1,t1_low,t2,t3}`, sets `exports_documented` = the entry count for the library shape (for a reference app, the Pattern Surface row count; see **Shape** below), and derives `exports_total` = `exports_public_api` + `exports_internal`, `public_api_coverage` = documented / public_api (`null` if public_api is 0), `total_coverage` = documented / total (`null` if total is 0), plus `scripts_count` / `assets_count` from the inventory arrays. Run `uv run {renderMetadataStatsHelper} --help` for the full contract. You supply only the payload:

  **Payload (passed as JSON on stdin):**
  - `exports_public_api` and `exports_internal`, unless the drift override below applies. At Quick tier, count them by `{entryPointsByHandData}`, as create-skill does, and pass the `counts` of `{run_dir}/denominator.json`. Otherwise, from `{project-root}`, run `uv run {extractPublicApiHelper} --mode full --source-root "{source_root}" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] [--language "{language}"] [--scope-type "{scope_type}"] --head-cap 0 -o "{run_dir}/public-api.json"` once over the whole scope (no `--files-from`), with the longest timeout your shell tool takes (a large tree takes minutes), as create-skill's extract.md §4 does, and pass its `counts.exports_public_api` and `counts.exports_internal`, as its compile.md §4 does. Pass `--brief` when that file exists (merge-write.md §6b wrote a rescope's amendment into it), and `--language` and `--scope-type` when metadata.json records them. On exit 1 (`incomplete`) run it once more. In gap-driven mode, gap-spot-check.md §4 already ran it over the same scope when it wrote `{run_dir}/public-api.json` with `status` `ok` and `counts.rescoped` of `{run_dir}/gap-records.json` is 0 (no rescope amended that scope): then read that JSON as this bullet says instead of running it again. When its `files_without_recipes` is not empty (in-scope files no recipe reads), count those files' entry points' names by steps 2 to 4 of `{entryPointsByHandData}`, with `--extraction "{run_dir}/public-api.json"`, as create-skill's extract.md §4b does, and pass the `counts` of `{run_dir}/denominator.json` in place of the runner's: they hold its names. Still incomplete, or on exit 2 or 3, no JSON, no candidate, or `entry_points.status` `no-entry-point`, count them by `{entryPointsByHandData}` and pass the `counts` of `{run_dir}/denominator.json`. On exit 2 (an input error, such as a skill brief it cannot read, or a failure it did not foresee), also add `public-api-counted-by-hand: {line}` to `warnings[]`, `{line}` being the stderr line that holds `error:`, recorded as **Warnings go to the run log** says, and show it to the user: the runner should have made these counts. When a call of `{entryPointsByHandData}` fails as its step 4 says, HALT with status `blocked` (halt procedure: `phase: "write:public-api"`, its `error:` line, or the helper that does not resolve, as `reason`). A docs-only skill has no tree to count: pass the values metadata.json records, as the drift override does.
  - `effective_denominator`: the `counts.effective_denominator` of the JSON whose two counts you passed above, when its `counts.effective_denominator_decision.store` is true and the skill brief's `scope.notes` documents the stratification: `skf-extract-public-api.py` decides `store` as it does for create-skill, so the count follows the source and the brief this update read. Under the drift override, and for a docs-only skill, pass the value `stats.effective_denominator` records once the queued `metadata_patches[]` are applied, when it records one. Otherwise leave it out, and `metadata.json` keeps no `stats.effective_denominator`: remove one an earlier run recorded.
  - `scripts` / `assets`: the scripts / assets inventory arrays (or `[]` when empty); the helper sets `scripts_count` / `assets_count` from their lengths
  - `pattern_surfaces_documented` (reference app only): none in the payload, and never typed. `--skill-md "{skill_package}/SKILL.md"` has the helper count the data rows of the merged SKILL.md's `## Pattern Surface` tables, as create-skill's compile.md §4 has it do. The helper uses the count as `exports_documented` and emits it as `stats.pattern_surfaces_documented`, the count test-skill measures a reference app's coverage by.

  **Public API counts under the drift override** (`{workspace_drift_status}` is `overridden`, gap-driven.md §3): count nothing at `{source_root}`, which is HEAD, not the pinned commit. Pass as `exports_public_api` and `exports_internal` the values `{skill_package}/metadata.json` records in `stats` once the queued `metadata_patches[]` above are applied (0 for one it does not record, with a WARN).

  **Shape:** read `scope_type` from `{skill_package}/metadata.json` before this section rewrites it (create-skill records the brief's `scope.type` there). When it is `reference-app`, pass `--shape reference-app` and `--skill-md "{skill_package}/SKILL.md"`, which counts `pattern_surfaces_documented`, as create-skill's compile.md §4 does; for any other `scope_type`, or none, pass no `--shape` (the helper's default, the library shape).

  **Invoke**: the helper reads the `entries[]` of the map write.md §3's `apply` wrote; the scripts / assets inventory arrays are the `scripts` and `assets` lists `apply` wrote to `{run_dir}/metadata-lists.json`:

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

  If its `coherence.ok` (in `{run_dir}/stats.json`, which the `metadata` call reads) is false, fix the provenance map and re-run the helper; never hand-edit the stats. A `confidence_distribution` violation means some provenance entries carry a missing or unrecognized `signature_source`, which only an edit made after write.md §3's `apply` leaves: `apply` gives every entry one, so set each the way it does (its `confidence` when that is `T1-low`, `T2` or `T3`, else `T1` when its `extraction_method` is `ast-grep` or `ast_bridge`, else `T1-low`).

  **Label violations.** A violation whose `field` is `provenance.entries[<i>].<field>` means entry `<i>` (its `export_name` is in the violation) carries a label its `extraction_method` does not allow: relabel it by the `## Relabel Rule` section of `{extractionPatternsData}`, which the verifier's `relabel` below applies, with `{source_root}` as the tree its node-kind lookup reads; never relabel an entry by hand. **Under the drift override** (`{workspace_drift_status}` is `overridden`, gap-driven.md §3) run no recipe at `{source_root}`, so no `kind-at`: HEAD is not the pinned commit, so a kind read there says nothing about the entry. Pass `--no-kind-at`: it leaves each violation that needs a kind from the tree in place (`kind-at-skipped`); list it as a WARN ending ` (drift override: HEAD {head_short_sha} is not pinned {pinned_short_sha})`; a relabel that reads nothing from the tree still applies. With the status `ok` or `skipped`, run the lookup as the rule says: pass `--source-root "{source_root}"` when there is a local source tree. This relabel applies to every entry the helper flags, including a gap-driven `verified` entry (write.md §3). Resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}` and `{extractionPatternsData}` ← first existing path in `{extractionPatternsDataProbeOrder}`, and, from `{project-root}`, run:

  ```bash
  uv run {verifyProvenanceCompletenessHelper} relabel \
      --provenance "{forge_version}/provenance-map.json" \
      --violations "{run_dir}/stats.json" \
      --recipes "{extractionPatternsData}" \
      [--records "{run_dir}/reextract-records.json"] \
      [--source-root "{source_root}"] [--no-kind-at] \
      -o "{run_dir}/relabel.json"
  ```

  Pass `--records` when that file exists: an entry's record there names the recipe that matched it and the tool that produced it. On exit 0 or 1 it printed `relabeled[]` (each field it set, with `from` and `to`) and `left_as_warn[]` (each label it left, with its `why`), and wrote the map through one rename when its `files_written[]` names it: re-read the map into write.md §3's in-context copy, list each left item as a WARN, then re-run the helper with the same payload, `--shape` and `-o` (and `--skill-md` for a reference app), whose file the `metadata` call reads: a relabeled `signature_source` moves the distribution, and a violation left as a WARN does not block the write. With no candidate for either, or on exit 2 (then with its stderr line), relabel nothing and list each label violation as a WARN. Record the export names of `relabeled[]`, each item left, and each name write.md §3's `apply` listed in `relabeled`, as `{provenance_relabels}` in workflow context: the update report lists them under its Confidence Tier Breakdown (report.md), so no entry moves from T1 to T1-low unannounced.
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

  It sets `tool_versions` to the toolchain this run used, as create-skill stamps it: `skf` read from the installed SKF under `--skf-root`, `ast_grep` from the `ast_grep.version` of `--extraction`, `qmd` from `--qmd-version`; a tool this run did not use keeps the version metadata.json records. Pass `--extraction` when step 2 wrote `{run_dir}/extraction.json`, and `--qmd-version` when re-extract.md §3 queried QMD and bound `{qmd_version}`. Pass `--source-commit`, `--source-ref` and `--source-root` as write.md §2's **Record the source commit** says. When the `effective_denominator` this run stores differs from the one metadata.json records, or only one of them has one, it drops each `effective_denominator_*` stats key, which explained the old count; `dropped_stats` lists each key it drops, a stats helper field this run's stats left out included. On exit 0, add each of its `warnings` to `warnings[]`, recorded as **Warnings go to the run log** says, so the report lists each dropped key, each `unknown` tool version and each stats key create-skill does not write that an earlier run left. Leave out only a warning that a stats key was `kept from an earlier run` when this run's `metadata_patches[]` wrote that key; a dropped key's warning always goes to `warnings[]`. Then, for each `stats.<key>` field write.md §2 applied (its `metadata_patch_outcome` line reads `applied`) whose `<key>` the call's `dropped_stats` names, append one more `metadata_patch_outcome` line to `{run_dir}/evidence-records.jsonl`, with `outcome` `dropped` and `why` `the metadata call dropped it`, under the `gap_id` and `field` of that `applied` line.

  On exit 1, fix the input its stderr names and run it again; when it fails again, prints no JSON or no candidate resolves, HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:metadata"`, `path: "{skill_package}/metadata.json"`, `reason: "<its stderr>"`).

**A docs-only skill's document hashes.** When step 2 wrote `{run_dir}/doc-hashes.json` (its docs-only branch), record the new hash of each document it found changed, after the writes above, so the next update compares against the documents this one read. Resolve `{compareDocHashesHelper}` ← first existing path in `{compareDocHashesProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {compareDocHashesHelper} refresh-hashes "{skill_package}/metadata.json" --compare "{run_dir}/doc-hashes.json"
```

It sets the `content_hash` and `recorded_at` of each `doc_sources[]` entry whose URL is in the comparison's `changed[]`, keeps every other entry and field, and rewrites `metadata.json` through one rename: never edit `doc_sources` by hand. On exit 2, no JSON, or no candidate resolves: HALT with status `halted-for-write-failure` (halt procedure: `phase: "write:doc-sources"`, `path: "{skill_package}/metadata.json"`, `reason: "<its error, or skf-detect-docs.py is missing; re-install SKF>"`).
