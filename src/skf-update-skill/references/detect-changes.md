---
nextStepFile: 're-extract.md'
noChangeReportFile: 'report.md'
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
# `{hashContentHelper}`: Category D's hash comparison. HALT if neither exists.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# `{buildChangeManifestHelper}`: §3's `build` (and §1's for a docs-only
# skill), §2.2's `deletion-ratio`, Category B's `baseline-gaps` and Category
# C's `rename-candidates`. HALT if neither exists.
buildChangeManifestProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-build-change-manifest.py'
  - '{project-root}/src/shared/scripts/skf-build-change-manifest.py'
# `{detectScriptsAssetsHelper}`: Category D's script and asset walk, the
# detector create-skill runs, over the whole source. HALT if neither exists.
detectScriptsAssetsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-scripts-assets.py'
  - '{project-root}/src/shared/scripts/skf-detect-scripts-assets.py'
# `{newFileDiffHelper}`: Category D's NEW_FILE set difference, kept to the
# skill brief's scope, bundled with this skill.
newFileDiffHelper: 'scripts/skf-new-file-diff.py'
# `{classifyChangedFilesHelper}`: §2.1 Category A. HALT if neither exists.
classifyChangedFilesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-classify-changed-files.py'
  - '{project-root}/src/shared/scripts/skf-classify-changed-files.py'
# `{extractPublicApiHelper}`: §2.1 Category B's recipe runner. If neither
# exists, read the files by eye.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
# `{structuralDiffHelper}`: §2.1 Category B's diff. HALT if neither exists.
structuralDiffProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-structural-diff.py'
  - '{project-root}/src/shared/scripts/skf-structural-diff.py'
# `{compareDocHashesHelper}`: §1's docs-only branch, the doc-hash comparison
# audit-skill's doc-drift step runs. HALT if neither exists.
compareDocHashesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
# SKILL.md binds `{emitEnvelopeHelper}` and `{runStateHelper}` for every
# stage; resolve them again when a binding was lost: first existing path wins.
# The warnings and gate decisions go to the run log through the first, and
# the halt procedure runs the second.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runStateProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-run-state.py'
  - '{project-root}/src/shared/scripts/skf-update-run-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Detect Changes

## STEP GOAL:

Compare current source code state against the provenance map to produce a complete change manifest identifying every changed, added, deleted, moved, and renamed file and export since last extraction.

## Rules

- Focus only on detecting and classifying changes: extract only what Category B's diff reads (step 3 reuses it), and merge nothing
- Run §2.1's categories in order, A, then B, then C: each reads the one before. Fan Category B's reading out in parallel batches (Pattern 4) only when its file list is long
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}` and `{runStateHelper}` in `{runStateProbeOrder}`.

## Steps

The helpers below and step 3 pass their JSON to each other through `{run_dir}`, the run folder SKILL.md On Activation created.

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the `{runStateHelper}` `halt` call below. This step writes nothing outside `{run_dir}`, so there is nothing to undo.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "<normal or degraded>"}
SKF_JSON
```

Pass `--tree` when load-baseline.md §6b bound `{source_tree}`, `--lock` and `--owner` when init.md §1b bound `{lock_owner}` (the read-only modes take no lock), and `--emit` in `{headless_mode}`. It removes the private source tree, releases the run lock and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line, with a warning (`source-tree-not-removed`, `run-lock-not-released`) for each step it could not finish: do none of it yourself. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "detect-changes:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place, with the decisions the gates below recorded before it.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 1. Scan Current Source State

**A docs-only skill** (`source_type: "docs-only"` in the brief or metadata.json) has no source tree for §2's categories to read: its drift is in the documents `doc_sources` records with their hashes. Compare them with the helper audit-skill's doc-drift step runs: resolve `{compareDocHashesHelper}` ← first existing path in `{compareDocHashesProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {compareDocHashesHelper} compare-hashes "{skill_package}/metadata.json" > "{run_dir}/doc-hashes.json"
```

It fetches each URL with a recorded hash and buckets it `changed`, `unchanged`, `fetch_failed` or `skipped_null_hash`, with `stats`: never fetch or hash a URL by hand. On exit 2, no JSON, or no candidate resolves, HALT with status `blocked` (halt procedure: `phase: "detect-changes:doc-hashes"`, `path: "{skill_package}/metadata.json"`, `reason: "<its error, or skf-detect-docs.py is missing; re-install SKF>"`). Add `doc-fetch-failed: {url} ({reason})` to `warnings[]` for each `fetch_failed` entry (a document that could not be read is not drift), `doc-not-hashed: {url}` for each `skipped_null_hash` entry, and `doc-drift-not-checked: metadata.json records no doc_sources` when `stats.total_tracked` is 0. Then skip §2 to §2.2 and §3's build, and have the helper write the change manifest from that output, never by hand:

```bash
uv run {buildChangeManifestHelper} build --doc-hashes "{run_dir}/doc-hashes.json" > "{run_dir}/change-manifest.json"
```

It writes `{"mode": "docs-only", "no_changes", "changed_urls", "fetch_failed", "counts": {"docs_changed", "docs_fetch_failed"}}`. On exit 1 or no JSON: HALT with status `blocked` (halt procedure: `phase: "detect-changes:change-manifest"`, its stderr as `reason`). §4 then reports no change only when every hashed document matches (`changed_urls` is empty); otherwise §5 routes to step 3, whose §1 re-fetches the changed URLs, and step 5 records their new hashes from `{run_dir}/doc-hashes.json`.

`{source_root}` is the tree load-baseline.md §6b prepared at `{target_commit}` when `{source_tree_status}` is `ready` or `offline`, and otherwise the skill's local source. **If `{source_tree_status}` is `ready` or `offline` and `{source_root}` no longer exists**, HALT with status `blocked` per SKILL.md's source-tree rule (halt procedure: `phase: "detect-changes:source-tree-missing"`, `path: "{source_root}"`, `reason: "source tree {source_root} disappeared mid-run"`): reading a missing tree would report every file deleted. §2.1's helpers walk `{source_root}` themselves: build no file inventory here.

Bind `{brief_path}` ← `{run_dir}/skill-brief.yaml` when that copy exists (reconcile-scope.md makes it in a read-only run), else `{forge_data_folder}/{skill_name}/skill-brief.yaml`.

**The scope type this run reads.** Bind `{scope_type}` ← the `scope_type` metadata.json records (init.md §2), else the `scope.type` of `{brief_path}` when that file exists and names one: a skill whose metadata.json records no scope type updates under its brief's. Category B's runner takes it as `--scope-type` and writes it to `{run_dir}/extraction.json` as `scope.type`, where step 3's `records` and step 5's `apply` read it: under `public-api`, a normal-mode update neither documents nor adds to the provenance map a new export off the runner's public surface (re-extract.md §4, write.md §3).

### 2. Compare Against Provenance Map

**In degraded mode (no provenance map),** run Category A without `--provenance-map`: its `full` mode lists every in-scope file as MODIFIED (with no brief, `--language` scopes the walk), so step 3 re-extracts every export. Run Category B's steps 1 and 2 only (re-extract.md §4's records come from them), and skip its step 3, Category C, Category D and §2.2: there is no map to compare against.

#### 2.0 Change-Detection Excludes

`promoted_docs_new[]` (reconcile-scope.md §1b) holds documents that reach the provenance map as `file_entries[]` rows through step 5's `apply`, never through code extraction. Category A leaves each of them out with `--exclude`: each is in scope and the map does not name it yet, so it would read as ADDED, and step 3 would send it to AST extraction, producing ghost entries. A path a `file_entries[]` row already names (a tracked document, script or asset) needs no exclude: Category A never lists one, and Category D compares its hash.

#### 2.1 Categories A, B and C, in Order

Category B reads the files Category A lists, and Category C pairs what A and B leave deleted and added. Category D (below) needs neither.

**Category A: file-level changes.** Resolve `{classifyChangedFilesHelper}` ← first existing path in `{classifyChangedFilesProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {classifyChangedFilesHelper} classify \
    --source-root "{source_root}" \
    [--provenance-map "{provenance_map_path}"] \
    [--brief "{brief_path}"] \
    [--language "{language}"] \
    --tree-status "{source_tree_status}" \
    --diff-status "{source_diff_status}" \
    --changed-files "{source_changed_files}" \
    [--exclude "<promoted document path>"] \
    --lists-dir "{run_dir}" \
    > "{run_dir}/category-a.json"
```

Pass `--provenance-map` whenever load-baseline.md §4 found one; `--brief` (as reconcile-scope.md §1c left it) when that file exists (a skill built without a brief, such as a quick skill after its degraded update, has none); `--language` when metadata.json records one; one `--exclude` for each `promoted_docs_new[]` path; and the three load-baseline.md §6b values as bound (an empty or `null` value counts as not given). In a tree it takes the changed files from git's list at `{source_changed_files}`, never from file times or sizes, which a checkout rewrites. Add each of its `warnings[]` to `warnings[]`. It writes `{run_dir}/modified-files.json` (the files Category B diffs) and `{run_dir}/extract-files.json` (the modified and added files and each moved file's new path, which Category B and step 3 read): never retype or re-derive a list. On exit 1 (an input it cannot read, named on stderr), no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-a"`, the helper's message as `reason`).

**Category B: export-level changes.** Skip it when `{run_dir}/extract-files.json` lists no file.

1. **The recipe runner.** At Forge tier and above, resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {extractPublicApiHelper} --mode full \
       --source-root "{source_root}" \
       --files-from "{run_dir}/extract-files.json" \
       [--language "{language}"] \
       [--scope-type "{scope_type}"] \
       --head-cap 0 \
       -o "{run_dir}/extraction.json"
   ```

   Pass `--language` when metadata.json records it, and `--scope-type` when §1 bound `{scope_type}`. It takes no `--brief`: Category A applied the scope, and a tracked file the brief's scope leaves out (gap-driven.md §1's rule R1 excludes a rescoped export's file) keeps its exports. `--head-cap 0` keeps every match, since a dropped one would read as a deleted export. Step 3 reads this file and never runs the runner again. **Exit 1** (`incomplete`, its JSON written): run it once more; when still incomplete, step 2 below reads by eye each listed file with no export in `exports[]` or that an `errors[]` item lists in `unread`, and tells the user which files were read by eye. **Exit 2** (an input error, such as a file list it cannot read, or a failure it did not foresee, named in one stderr line with no JSON; `uv` failing to start it exits 2 too): HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-b"`, the stderr line that holds `error:` as `reason`). No by-eye read stands in for it: the skill is not written yet, and reading every file by eye would hide the error. **Exit 3 (`no-ast-grep`), no JSON on another exit, no candidate resolves, or Quick tier:** write `{"exports": []}` to `{run_dir}/extraction.json`, with `"scope": {"type": "{scope_type}"}` when §1 bound `{scope_type}`, so step 5's `apply` can warn that a `public-api` surface was not applied; step 2 reads every listed file by eye (at Quick tier, by text pattern). Tell the user which files were read by eye.

   Then, at every tier (in degraded mode there is no map: skip it), list the map's entries the runner left out that their file still declares: the runner never reports a module, an alias that renames, a dunder such as `__version__` or another Python or Rust underscore name, and step 3's diff would read each as a deleted export. From `{project-root}`, run:

   ```bash
   uv run {buildChangeManifestHelper} baseline-gaps \
       --provenance-map "{provenance_map_path}" \
       --extraction "{run_dir}/extraction.json" \
       --files "{run_dir}/modified-files.json" \
       --source-root "{source_root}" \
       -o "{run_dir}/baseline-gaps.json"
   ```

   It writes `{"gaps": [{name, file, line, entry, export_type}], "unchecked": [{name, file, export_type}]}`: in `gaps[]` each entry of a modified file that no export of `{run_dir}/extraction.json` holds and whose file still declares it, at the line that declares it, by the verifier's rule (audit-skill's extraction snapshot applies the same one), and in `unchecked[]` each such entry no rule can check (its file neither Python nor TS/JS, a file the rule will not read, such as a test file or one with a symlink on its path, or a dotted module name), which step 2 reads by eye. Never add a gap or drop one by eye. On exit 1 (an input it cannot read, or a `skf-verify-provenance-completeness.py` beside it that cannot be loaded), no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-b"`, its stderr as `reason`): without it, every name the runner leaves out would read as deleted.

2. **What the recipes do not record.** Workers, in parallel batches (Pattern 4) when the list is long, read the modified and added files and each return ONLY `{"exports": [...]}`, with no prose and no fences. For each function export the runner found whose `params` it left null (it could not read the signature): `export_name` and `source_file` as it wrote them, with `params` (each parameter as the source writes it, `name: type`, the form the provenance map's `params` hold) and `return_type` (null when there is none), read at its `source_line`. For each export it could not find (a name `entry_point_diff.extraction_gaps[]` lists, a name `{run_dir}/baseline-gaps.json` lists in `gaps[]`, a form Known Limitation #11 in `{extractionPatternsData}` lists, an export of a file `file_issues[]` names or that was read by eye): the same, plus `export_type`, `source_line`, `confidence: T1-low` and `extraction_method: source-read`. Record a baseline gap at its `file` and `line` (`source_line`), with, as `export_type`, its `export_type` while the declaration there still has that kind, else the kind it has now (a `variable` now declared by a `def` is a `function`, which step 3 reports as a changed kind), and the declaration's kind when the gap gives none; `params` and `return_type` as the declaration writes them, null when it has none (a module, an alias or a variable). For each `unchecked[]` entry, read its file by eye and record it the same way, at the line that declares it, only when the file still declares it. Record each name and file once: when a file read by eye whole (at Quick tier, or when the runner could not run or left the file unread) holds a name a gap or an `unchecked[]` entry lists, that read's record stands and the gap adds none. Write the union of their `exports` arrays to `{run_dir}/export-details.json`.

3. **The diff.** Resolve `{structuralDiffHelper}` ← first existing path in `{structuralDiffProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {structuralDiffHelper} "{provenance_map_path}" "{run_dir}/extraction.json" \
       --current-extra "{run_dir}/export-details.json" \
       --files "{run_dir}/modified-files.json" \
       -o "{run_dir}/category-b-diff.json"
   ```

   Exit 0 (no difference) and exit 1 (differences) both wrote the diff, which §3's helper maps onto Category B: never re-diff by eye. On exit 2, no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-b"`, the helper's `error` as `reason`).

**Category C: rename detection.** The fixed rules pair Category A's `deleted` files with its `added` ones, and the diff's `removed[]` exports with its `added[]` ones and with the added files' exports, by script, never by eye. From `{project-root}`, run:

```bash
uv run {buildChangeManifestHelper} rename-candidates \
    --category-a "{run_dir}/category-a.json" \
    [--category-b-diff "{run_dir}/category-b-diff.json"] \
    --provenance-map "{provenance_map_path}" \
    [--extraction "{run_dir}/extraction.json"] \
    [--export-details "{run_dir}/export-details.json"] \
    --tier "{forge_tier}" \
    --source-root "{source_root}" \
    [--sizes-commit "{source_commit}"] \
    -o "{run_dir}/category-c.json"
```

Pass `--category-b-diff`, `--extraction` and `--export-details` when Category B wrote them, and `--sizes-commit` only when `{source_tree_status}` is `ready` or `offline`: in that tree the helper reads a deleted file's size at the pinned commit (`git cat-file -s`), while in a local source the file is gone and the size test is skipped. Skip Category C in degraded mode (there is no map). Content similarity above 80% (fixed, not configurable) is a rename: at Quick tier a file size within 20% and export names that overlap above 70% (export names above 80% alike), at Forge and above equal export signatures. The helper keeps a pair only when it is each side's best match, so a tie pairs nothing, and writes `category_c` (`renamed_files: [{old_path, new_path}]`, `renamed_exports: [{old_name, new_name, file, old_file?}]`, `old_file` only when it differs from `file`), the `evidence` of each pair and what it left `unpaired`. On exit 1, no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-c"`, its stderr as `reason`). Category A's `moved_files[]` (same-content moves) are not Category C's to pair, and §3's helper takes each pair out of the lists it was found in.

**CCC check (Forge+ and Deep, a local source only).** When `tools.ccc` is true and `{source_tree_status}` is neither `ready` nor `offline` (the tree load-baseline.md §6b prepared has no ccc index, and a search there could start indexing a folder step 7 deletes), you may pair what the rules left in `unpaired`: a deleted file with an added one that CCC ranks as the same code (`ccc_bridge.search` over the deleted file's export names; **Tool resolution:** `/ccc` skill search, ccc MCP or `ccc search`). This is the one judgment in Category C: add a pair only on CCC's evidence, name it in the report as a CCC pairing, and never undo a pair the rules made. Write only these pairs, with each path as `unpaired` gives it, to `{run_dir}/ccc-pairs.json` as `{"renamed_files": [{"old_path": "<deleted>", "new_path": "<added>"}]}`; the helpers below read `{run_dir}/category-c.json` themselves, so never copy its pairs.

**Category D: script, asset and tracked-document file changes.**

Run the bulk comparison once, keeping its output in the run folder (step 5's `apply` reads it):

```bash
uv run {hashContentHelper} compare "{source_root}" \
    --provenance-map "{provenance_map_path}" \
    > "{run_dir}/category-d-compare.json"
```

On exit 1, no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-d"`, its stderr as `reason`).

The helper emits:

```json
{
  "comparisons": [
    {"source_file": "...", "classification": "UNCHANGED|MODIFIED_FILE|DELETED_FILE",
     "stored_hash": "sha256:...", "current_hash": "sha256:..."|null,
     "current_size_bytes": N|null}, ...
  ],
  "stats": {"total": N, "unchanged": U, "modified": M, "deleted": D}
}
```

A map with no `file_entries` field, or a null one (a skill with no script, asset or promoted document, or a map written before the field existed), tracks no file: the comparison lists no row and the set difference below subtracts nothing.

The compare helper reports only tracked files; NEW_FILE detection (a file present in source but absent from the provenance map) is a set-difference, so it runs through a script rather than the prompt. **When `{brief_path}` does not exist** (a skill built without a brief, such as a quick skill), skip it: with no scope to keep to, the walk would read every script and asset of the repository as new. Add `new-files-not-checked: no skill brief, so no new script or asset was looked for` to `warnings[]`, write no `{run_dir}/new-files.json`, and leave `--new-files` out of §3's `build` and step 5's `apply`. Otherwise pipe the detector create-skill step 3 §4c runs (resolved via `detectScriptsAssetsProbeOrder`), which walks the whole source, into `{newFileDiffHelper}`, which keeps what the brief takes and subtracts what the map tracks:

```bash
uv run {detectScriptsAssetsHelper} detect "{source_root}" \
    | uv run {newFileDiffHelper} "{provenance_map_path}" [--brief "{brief_path}"] \
    > "{run_dir}/new-files.json"
```

Pass `--brief` as Category A does, `{brief_path}` as reconcile-scope.md §1c left it (in a read-only run, its copy in `{run_dir}`). On exit 2 (the detector's JSON, the map or the brief it cannot read, named in its JSON `error` on stderr, which also catches a detector that printed nothing), no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "detect-changes:category-d"`, its `error` as `reason`).

It writes `{"new_files":[{source_file, kind}], "skipped_manual":[...], "already_tracked":[...], "tracked_code":[...], "out_of_scope":[...], "intent_none":[...], "stats":{...}}`. §3's `build` reads both files, typing each compare row by its `file_entries[]` row's `file_type` and each new file by its `kind`: sort no row by hand. `skipped_manual[]` are user-authored files under `scripts/[MANUAL]/` or `assets/[MANUAL]/`, preserved and not touched; `already_tracked[]` were handled by the compare above; `tracked_code[]` are code files the map's `entries[]` cite, which Categories A and B compare; `out_of_scope[]` are paths the brief's scope leaves out, by Category A's in-scope test; `intent_none[]` are paths of a kind whose `scripts_intent` or `assets_intent` is `none` (an absent or free-text intent detects). A path in these lists is no new file and no `stats` count, so step 6's report counts each of the three lists from this file, where it shows Category D: a brief scoped wrongly shows as many paths out of scope. A new file Category A lists too stays a new file: Category A lists every changed in-scope file, a genuine script included.

**Write the category JSON** to `{run_dir}/categories.json`, where §2.2 and §3 read it beside the helper files: the two flags, `degraded_mode` and `update_mode` (`normal` or `degraded`, as init.md and load-baseline.md §4 bound it). Category C stays in the files its steps wrote, which §2.2, §3 and step 5's `apply` take as `--category-c` and `--ccc-pairs`:

```bash
cat > "{run_dir}/categories.json" <<'SKF_JSON'
{"degraded_mode": <bool>, "update_mode": "{update_mode}"}
SKF_JSON
```

#### 2.2 — Major-Version Scope Reconciliation (Post-Detection)

**Purpose:** the safety net when no audit drift report named the restructure.

**Trigger computation:** skip §2.2 in degraded mode (there is no map). Otherwise invoke the helper with the files §3 reads, plus the provenance map:

```bash
uv run {buildChangeManifestHelper} deletion-ratio \
    --provenance-map "{provenance_map_path}" \
    --category-a "{run_dir}/category-a.json" \
    [--category-b-diff "{run_dir}/category-b-diff.json"] \
    [--category-c "{run_dir}/category-c.json"] \
    [--ccc-pairs "{run_dir}/ccc-pairs.json"] \
    --input "{run_dir}/categories.json"
```

Pass `--category-b-diff`, `--category-c` and `--ccc-pairs` when Category B, Category C and the CCC check wrote them.

If `skip_reason` is non-null OR `should_trigger` is false, skip the prompt and continue to §3. If `should_trigger` is true, present the prompt below.

**Prompt:**

```
**Major-version scope shift detected**

Deleted exports:        {deleted_export_count} of {total_provenance_exports} ({percent}%)
Deleted files:          {deleted_file_count}
Added files (in scope): {added_in_scope_count}
Renamed/moved exports:  {renamed_or_moved_count}

The upstream surface appears to have been substantially replaced. The brief's
`scope.include` patterns may no longer reflect the real public API.

[C] Continue — proceed with re-extraction; the deletion is intentional
[B] Brief    — halt and re-run skf-brief-skill to refine scope first
[A] Audit    — halt and run skf-audit-skill to map the new surface, then re-run update-skill
```

**GATE [default: C]**: in headless mode (`{headless_mode}` is true), auto-select `[C] Continue`, append the record `scope_reconciliation_post: {trigger: "deletion-ratio", ratio: X, decision: "headless-continue"}` to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `scope_reconciliation_post` (step 5 §4 lists it in the evidence report), and surface the warning in step 6's report. A non-interactive run must not silently halt, but the user must be able to see the signal post-hoc. **Also record the decision**, from `{project-root}`:

```bash
uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate": "detect-changes.deletion-ratio", "default_action": "C", "taken_action": "C", "reason": "headless: deletion-ratio threshold exceeded but no user to halt", "evidence": {"deletion_ratio": <ratio>, "deleted_export_count": <N>, "total_provenance_exports": <T>}}
SKF_JSON
```

**Apply decision:**

- **[C] Continue:** unless the headless branch above appended its record, append `scope_reconciliation_post: {trigger: "deletion-ratio", ratio: X, decision: "continue"}` to `{run_dir}/evidence-records.jsonl` the same way, and proceed to §3.
- **[B] Brief:** HALT with status `halted-for-brief-refinement` (halt procedure: `phase: "detect-changes:deletion-ratio"`, `reason: "the user chose to refine the brief's scope: {deleted_export_count} of {total_provenance_exports} exports deleted"`). Display: `"Halting update-skill. Re-run skf-brief-skill to refine scope for {skill_name}, then re-run skf-update-skill."` The change manifest is discarded: no partial writes.
- **[A] Audit:** HALT with status `halted-for-audit` (halt procedure: `phase: "detect-changes:deletion-ratio"`, `reason: "the user chose to audit the new surface first"`). Display: `"Halting update-skill. Run skf-audit-skill against {skill_name} to map the new surface: its drift report will feed reconcile-scope.md §1c on the next update-skill run."` The change manifest is discarded.

### 3. Build Change Manifest

Hand the helper files and the category JSON to the helper, which takes Category A from the classify output, maps the diff onto Category B, and takes each Category C pair out of the lists it was found in:

```bash
uv run {buildChangeManifestHelper} build \
    [--category-a "{run_dir}/category-a.json"] \
    [--category-b-diff "{run_dir}/category-b-diff.json"] \
    [--category-c "{run_dir}/category-c.json"] \
    [--ccc-pairs "{run_dir}/ccc-pairs.json"] \
    [--file-compare "{run_dir}/category-d-compare.json" --provenance-map "{provenance_map_path}"] \
    [--new-files "{run_dir}/new-files.json"] \
    --input "{run_dir}/categories.json" \
    > "{run_dir}/change-manifest.json"
```

Pass each helper file its category wrote. On exit 1 or no JSON: HALT with status `blocked` (halt procedure: `phase: "detect-changes:change-manifest"`, its stderr as `reason`).

`{run_dir}/change-manifest.json` is the change manifest: step 3, step 6 and step 5's `apply` read it there, so it survives a compacted context.

### 4. Check for No-Change Shortcut

**If zero changes detected across all categories** (`no_changes` is true in `{run_dir}/change-manifest.json`; for a docs-only skill, when every hashed document matched):

"**No changes detected.** Source code matches provenance map exactly.

The skill `{skill_name}` is current — no update needed.

**Skipping to report step...**"

→ Skip steps 3-5, immediately load {noChangeReportFile} with "no changes" status. A `--detect-only` or `--dry-run` run takes this route too and stays read-only there: report.md §1 prints its line with no result file and never runs `{onCompleteCommand}`.

### 5. Display Change Summary and Route

Display one line from the change manifest: "**Detected:** {modified} modified, {added} added, {deleted} deleted and {moved} moved or renamed files; {total_export_changes} exports affected." The report (step 6) shows the full counts.

For a docs-only skill, show instead the documents that changed (`changed_urls`) and the ones that could not be fetched.

This step auto-proceeds — no user choices. Once the change manifest is fully built, load and fully read the next file, then execute it, per the branch that applies:

- **`detect_only_mode == true`** → display "**Detect-only mode: skipping re-extract, merge and write.** Loading report..." and load `{noChangeReportFile}` (report.md), which emits status `detect-only`. Do not load `{nextStepFile}`.
- **No changes detected** (section 4) → load `{noChangeReportFile}` (report.md), which emits status `no-changes`.
- **Otherwise** → display "**Proceeding to re-extraction of {affected_file_count} changes...**" and load `{nextStepFile}` (re-extract.md) to begin re-extraction.
