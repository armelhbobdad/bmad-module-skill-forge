---
nextStepFile: 'merge.md'
extractionPatternsData: 'skf-create-skill/references/extraction-patterns.md'
extractionPatternsTracingData: 'skf-create-skill/references/extraction-patterns-tracing.md'
tierDegradationRulesData: 'skf-create-skill/references/tier-degradation-rules.md'
# `{buildChangeManifestHelper}`: §4's `records`. HALT if neither exists.
buildChangeManifestProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-build-change-manifest.py'
  - '{project-root}/src/shared/scripts/skf-build-change-manifest.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Re-Extract Changed Exports

## STEP GOAL:

Perform tier-aware extraction on only the changed files identified in step 2, producing fresh export data with confidence tier labels (T1/T1-low/T2) that will be merged into the existing skill in step 4.

## Rules

- Focus only on extracting changed exports — do not merge or modify existing skill
- Only extract files in the change manifest: do not touch unchanged files
- For each changed file, launch a subprocess (Pattern 2) that reads its exports at the lines step 2 recorded (§1b); if unavailable, extract sequentially

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the halt helper SKILL.md On Activation resolved. This step writes nothing outside `{run_dir}`, so there is nothing to undo, `--dry-run` included.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "<normal or degraded>"}
SKF_JSON
```

Pass `--tree` when init.md §6b bound `{source_tree}`, `--lock` and `--owner` when init.md §1b bound `{lock_owner}` (the read-only modes take no lock), and `--emit` in `{headless_mode}`. It removes the private source tree, releases the run lock (never one another run holds) and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line through the shared emitter, which adds the decisions recorded so far, the `error` object and a warning for each step the helper could not finish (`source-tree-not-removed`, `run-lock-not-released`); it never stops on a result. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "re-extract:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 1. Check for Docs-Only Mode

**If `source_type: "docs-only"` in the original brief or metadata:**

"**Docs-only skill detected.** This skill was generated from external documentation, not source code. Re-extraction re-fetches the documents whose hash changed (step 2 §1) for their updated content."

- Re-fetch each URL in `changed_urls` of `{run_dir}/change-manifest.json` using whatever web fetching capability is available; leave every other document as it is
- Extract updated API information with T3 `[EXT:{url}]` citations
- Write the updated extraction inventory to `{run_dir}/reextract-records.json`, from which merge and step 5's `apply` work, as `{"mode": "docs-only", "changed_urls": [<the URLs re-fetched>], "exports": [{"name": "<export>", "type": "<kind>", "params": [<each parameter>], "return_type": "<type, or null>", "url": "<the URL it came from>"}]}`
- Skip sections 1b to 5 (source code extraction), then go straight to §6 (Route to Next Step), whose `dry_run_mode` branch holds for a docs-only skill too: a docs-only `--dry-run` never loads merge.md

**If `source_type: "source"` (default):** Continue with source extraction below.

### 1b. Determine Extraction Strategy by Tier

**Source access (every tier):** read every changed file from `{source_root}`. When `{source_tree_status}` is `ready` or `offline`, that is the tree init.md §6b prepared at `{target_commit}`, the commit step 2 compared, so detection, extraction, merge and write read one tree; otherwise it is the local source init.md §6 validated. Do not fetch changed files through the gh contents API, zread or deepwiki: the gh contents API serves the default branch unless given a ref, and the zread and deepwiki indexes may sit at another commit, so a citation read there would not point into the commit this update records. If `{source_tree_status}` is `ready` or `offline` and `{source_root}` no longer exists, HALT with status `blocked` per SKILL.md's source-tree rule (halt procedure: `phase: "re-extract:source-tree-missing"`, `path: "{source_root}"`, `reason: "source tree {source_root} disappeared mid-run"`). If one changed file cannot be read, limit its analysis to the provenance-map baseline (State 2: each baseline entry keeps its own confidence label from compilation-time data) and warn: "Could not read {path} from {source_root}. Its analysis is limited to the provenance-map baseline."

**What the workers read (every tier):** at each export's line the workers (§2) read what no tool records: its full signature (a function's, a type definition, a constant's value), a class's members and its JSDoc or docstring, and its parameter types and return type only where neither the runner nor `{run_dir}/export-details.json` records them.

**Quick tier (text pattern matching):** step 2 read every listed file by text pattern into `{run_dir}/export-details.json` (T1-low, with `extraction_method: source-read` and `ast_node_type: null`), and §4's helper seeds each record from it.

**Forge tier (AST structural extraction):**

- Step 2's Category B ran the recipe runner (`{extractPublicApiHelper}` `--mode full`, the recipes of the AST Extraction Protocol in `{extractionPatternsData}`) over every file to extract, `{run_dir}/extract-files.json`, and wrote `{run_dir}/extraction.json`: never run it again here. §4's helper takes each file's exports from its `exports[]`, each at the line of its name, never a decorator or `export` line above it: T1 (AST-verified structural truth) with `extraction_method: ast-grep` and the recipe's labels.
- Read by eye only what the recipes leave out: an export a file defines in a form Known Limitation #11 in `{extractionPatternsData}` lists, a file `file_issues[]` names (not UTF-8, or code the parser could not read, where a recipe can miss an export), a name `entry_point_diff.extraction_gaps[]` lists, a map entry `{run_dir}/baseline-gaps.json` lists (a module, an alias that renames, `__version__` or another underscore name the runner never reports, which its file still declares), and each file step 2 told the user it read by eye. Step 2 already read those of the modified and added files into `{run_dir}/export-details.json` (its entries with an `export_type`), and §4's helper takes them from there. An export read by eye is T1-low with `extraction_method: source-read` and `ast_node_type: null`.

**Tier degradation handling (Forge/Forge+/Deep):** If step 2's runner could run no ast-grep, or left files unread (step 2 told the user which), follow `{tierDegradationRulesData}` for fallback strategy and user notification requirements. Silent degradation is forbidden: the user must always know which files were read by eye instead of matched, and why.

**Deep tier (AST + QMD semantic enrichment):**
- Perform all Forge tier extractions, labeled by tool as at Forge tier
- Additionally: launch a subprocess that queries qmd_bridge for temporal context on changed exports, returning T2 evidence per export
- QMD provides: usage patterns, historical context, related documentation
- Confidence: structural entries labeled by tool (T1 for an ast-grep match, T1-low for an export read by eye), T2 for semantic enrichment

**Tool resolution:** `ast_bridge` → `{extractPublicApiHelper}` `--mode full` (step 2), which runs every recipe through the ast-grep CLI; `find_code` only as the fallback of Known Limitation #4, for a recipe that errors or finds nothing where a file clearly holds exports. `qmd_bridge` → QMD MCP tools (`mcp__plugin_qmd-plugin_qmd__search`, `vector_search`) or `qmd` CLI. See `knowledge/tool-resolution.md`.

### 2. Extract Changed Files

Step 2's Category A left every promoted or tracked document out of the files to extract (its §2.0): a document must not reach AST extraction, which would produce ghost entries; step 2's Category D and step 4's Priority 6/7 handle doc-type drift.

For each file `{run_dir}/extract-files.json` lists (step 2 wrote it: the MODIFIED and ADDED files and each MOVED file's new path), launch a subprocess that:

1. Loads the source file
2. Takes this file's exports from step 2's `{run_dir}/extraction.json` and `export-details.json` (§1b)
3. Reads at each export's line what §1b says no tool records
4. **Return contract.** Each worker returns ONLY this per-file patch, with no prose, no commentary and no markdown fences (the parent strips wrapping fences before parsing), and leaves out a field it has nothing for. Write each patch, as returned, to a file of its own in `{run_dir}/reextract-patches/`, which §4's helper merges into the records it seeds from step 2's files:

   ```json
   {"file_path": "...", "exports": [
     {"name": "...", "signature": "<the full signature>", "members": ["<a class's member>"], "docstring": "...",
      "params": ["<name: type>"], "return_type": "..."}
   ]}
   ```

**For DELETED files:** No extraction needed — deletions handled in merge step.

**For MOVED files:** Re-extract at new location to update file:line references.

**Re-export tracing (Forge/Deep only):** After extracting changed files, check if any public exports from the package entry point (`__init__.py`, `index.ts`, `lib.rs`) are unresolved — particularly when a changed file is part of a module re-export chain. Follow the **Re-Export Tracing** protocol in `{extractionPatternsTracingData}` to trace unresolved symbols to their actual definition files.

### 3. Deep Tier QMD Enrichment (Conditional)

**ONLY if forge_tier == Deep:**

Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`.

Find the collection entry matching the current skill: look for an entry where `skill_name` matches the skill being updated AND `type` is `"extraction"`.

**If a matching extraction collection is found:**
Launch a subprocess that loads qmd_bridge and for each changed export:
1. Queries the `{skill_name}-extraction` collection for semantic context related to the export
2. Searches for usage patterns, documentation references, temporal history
3. Returns T2 evidence per export (usage frequency, context snippets, related concepts), as patches §4 merges: write one `{"file_path", "exports": [{"name", "qmd_evidence"}]}` block per file to its own file in `{run_dir}/reextract-patches/`

**If no matching collection found in registry:**
Log: "No QMD extraction collection found for {skill_name}. T2 enrichment skipped. Re-run [CS] Create Skill to generate the collection."
Continue without T2 enrichment: extraction still produces its structural results, labeled by tool.

**If forge_tier != Deep:** Skip this section with notice: "QMD enrichment skipped (tier: {forge_tier})"

### 4. Compile Extraction Results

Resolve `{buildChangeManifestHelper}` ← first existing path in `{buildChangeManifestProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {buildChangeManifestHelper} records \
    [--extraction "{run_dir}/extraction.json"] \
    [--export-details "{run_dir}/export-details.json"] \
    --files-from "{run_dir}/extract-files.json" \
    [--patches "{run_dir}/reextract-patches"] \
    -o "{run_dir}/reextract-records.json"
```

Pass `--extraction` and `--export-details` when step 2 wrote them, and `--patches` when §2 or §3 wrote a patch. It seeds each export's record from step 2's files (name, type, signature, location, labels, return type and `params` in the provenance map's typed form), merges the patches, writes `{run_dir}/reextract-records.json`, where merge and step 5's `apply` read it, and prints `files_extracted`, `exports_extracted` and `confidence_breakdown` (T1, T1-low, T2): never type a record or count one by hand. Add each of its `warnings[]` to `warnings[]`. On exit 1 whose error names a patch file, rewrite that file once in the shape of §2's return contract and run `records` again. On a second exit 1, any other exit 1, no JSON, or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "re-extract:records"`, its stderr as `reason`).

### 5. Display Extraction Summary and Auto-Proceed

Display one line from §4's results: "**Re-extracted** {exports} exports from {files} files ({t1} T1, {t1_low} T1-low, {t2} T2)." The report (step 6) shows the confidence tier breakdown.

### 6. Route to Next Step

This step auto-proceeds — no user choices. Once all changed files are extracted and results compiled, load and fully read the next file, then execute it, per the branch that applies:

- **`dry_run_mode == true`** → display "**Dry-run mode: skipping merge and write.** Loading report..." and load `report.md` (NOT `{nextStepFile}`); it emits status `dry-run` describing what merge+write would have done. Every route out of this step comes here, the docs-only one (§1) included, so no artifact is modified on disk by this run.
- **Otherwise** → display "**Proceeding to merge...**" and load `{nextStepFile}` (merge.md) to begin the merge operation.

