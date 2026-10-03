---
nextStepFile: 'sub/fetch-temporal.md'
componentExtractionStepFile: 'component-extraction.md'
extractionPatternsTracingData: 'references/extraction-patterns-tracing.md'
tierDegradationRulesData: 'references/tier-degradation-rules.md'
sourceResolutionData: 'references/source-resolution-protocols.md'
authoritativeFilesProtocol: 'references/authoritative-files-protocol.md'
cccIndexCheckData: 'references/ccc-index-check.md'
entryPointsByHandData: 'references/entry-points-by-hand.md'
# Each probe order lists the installed path first, then the src/ dev-checkout
# path; the first existing path wins. §4c: deterministic script and asset
# detection, with stable hashes.
detectScriptsAssetsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-scripts-assets.py'
  - '{project-root}/src/shared/scripts/skf-detect-scripts-assets.py'
# §2a: the authoritative-files scan, classification, previews and hashes in
# one call.
resolveAuthoritativeFilesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-authoritative-files.py'
  - '{project-root}/src/shared/scripts/skf-resolve-authoritative-files.py'
# Resolve `{cccGitHygieneHelper}` to the first existing path. It keeps ccc's
# index folders and SKF's workspace lock out of git, and undoes the
# `.gitignore` edit `ccc init` makes in a workspace clone. If neither path
# exists, skip the call and continue: it never gates the workflow.
cccGitHygieneProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-ccc-git-hygiene.py'
  - '{project-root}/src/shared/scripts/skf-ccc-git-hygiene.py'
# §2b reads a remote source into a private tree through it, and step 7 and
# every HALT after §2b remove the tree; without it §2b reads the source by
# eye.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
# §2b's deferred ccc discovery prepares the clone's settings.yml; skipped
# without it.
mergeCccExclusionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-merge-ccc-exclusions.py'
  - '{project-root}/src/shared/scripts/skf-merge-ccc-exclusions.py'
# §4's recipe runner (--mode full); without it §4 follows the protocol's
# fallback.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
# Steps 5 and 6 bind it the same way.
extractionPatternsDataProbeOrder:
  - '{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md'
  - '{project-root}/src/skf-create-skill/references/extraction-patterns.md'
# §3 and §5 write the inventory through it (`init`, `patch`, `add`, `set`);
# steps 3c and 4 append with its `add`, and step 7 writes the rules with it.
extractionInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extraction-inventory.py'
  - '{project-root}/src/shared/scripts/skf-extraction-inventory.py'
# §2a's protocol records each decision in the brief through its `amend`.
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
# HARD HALT helper (Rules).
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Extract

## STEP GOAL:

To extract all public exports, function signatures, type definitions, and co-import patterns from the source code using tier-appropriate tools, building a complete extraction inventory with confidence-tiered provenance citations.

## Rules

- Focus only on extracting exports, signatures, types from source code — do not compile SKILL.md
- Write only beside the staging folder (the recipe runner's JSON, §4, the detector's JSON, §4c, and the extraction inventory, §5), and the brief only through §2a's protocol
- Every extracted item must have a provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`
- A HARD HALT, once step 3 §2b has bound `{source_tree}`, first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` (resolved from `{sourceTreeProbeOrder}`) and goes on whatever it prints, and emits through `{emitEnvelopeHelper}`, resolved from `{emitEnvelopeProbeOrder}` when it is not bound. After its envelope, under `--batch` it ends only this brief: return to `references/batch-mode.md` §3, even when the halt reads as the end of the run.

## MANDATORY SEQUENCE

### 1. Load Extraction Patterns

Resolve `{extractionPatternsData}` ← first existing path in `{extractionPatternsDataProbeOrder}` and load it up to its `## Running the Recipes Without the Runner` heading, for the current tier's strategy and the AST Extraction Protocol: the rest (the decision tree, the CLI streaming template and the recipes) serves only a run without the recipe runner, and the protocol's **When the Runner Cannot Run** section sends such a run there. If neither path exists, **HARD HALT** (exit code 3, `helper-missing`, phase `extract`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot extract: extraction-patterns.md is missing. Re-install SKF, then re-run create-skill."

### 2. Apply Scope Filters

From the brief, apply scope and pattern filters:

- `scope.type`: what to extract (`full-library`, `specific-modules`, `public-api`, `component-library`, `reference-app` or `docs-only`). A `reference-app` brief documents a whole app's wiring patterns rather than public exports: it triggers the compile-assembly overrides in `assets/compile-assembly-rules.md`, which replace "Key API Summary" with a "Pattern Surface" section and make `stats.exports_documented` count patterns.
- `scope.include` — file globs to include
- `scope.exclude` — file globs to exclude

At Forge tier and above the recipe runner (§4) applies these globs to the source tree itself, and its `files_in_scope` is the filtered file count. Build the filtered file list by hand only where a step reads it: at Quick tier, for a `component-library` brief (§2c), and in a §4 branch that extracts without the runner. Build it from the source tree resolved in step 1 (for a remote source at Forge tier or above, §2b builds it again from the tree it reads), matching the globs by the **Files in scope** rule of the Recipe Runner section in `{extractionPatternsData}`, and record the result: "**Filtered file count: {N} files in scope**".

Sections 2b and 2a follow in that order: §2b resolves the source to a local tree, and §2a scans that tree for authoritative files.

### 2b. Resolve Source Access

**Start clean:** first, for every brief, docs-only included, set `{source_tree}`, `{workspace_clone}` and `{remote_clone_path}` to null and `{resolved-source-path}` to `{source_root}` (null for a docs-only brief), so that in a `--batch` run one brief's source never carries into the next. Bind `{extraction_inventory}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.inventory.json`, `{detected_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.detected.json` and `{extraction_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.extraction.json`, and run `rm -f "{extraction_inventory}" "{detected_json}" "{extraction_json}" "{project-root}/_bmad-output/.skf-stage/{skill-name}.language-guide.json"`: §4 (or step 3d), §4c, §5 and step 3c write this run's, so §5 never seeds from an earlier run's runner JSON and step 5 never reads an earlier run's Language Guide.

**If `source_type: "docs-only"`:** skip the rest of §2b: there is no source to resolve. Proceed directly to §2c (component library delegation, which is itself skipped for docs-only) and then §3 (Check for Docs-Only Mode). Tag resolution, reading the source into a tree, source-commit capture, version reconciliation, and deferred CCC discovery all require a source tree and have nothing to do in docs-only mode.

Load `{sourceResolutionData}` completely. It says which brief field picks the ref and how to choose between several matching tags, and it holds the tag warnings, the Local Source Warning, Source Commit Capture and Version Reconciliation.

**Local source, or a Quick-tier remote source:** nothing to resolve. Apply the Local Source Warning to a local path. A Quick-tier remote source is read through `gh_bridge` in §4, and its `source_ref` is `HEAD`.

**Remote source at Forge, Forge+ or Deep tier:** `{sourceTreeHelper}` reads the source into a private tree at one commit, which no other run can move, and in the same call moves SKF's workspace clone of the repository to that commit (`{sourceResolutionData}` "Remote Source Resolution"). Resolve `{sourceTreeHelper}` ← first existing path in `{sourceTreeProbeOrder}`; it stays bound for the rest of the run (step 7 and every HALT use it). Resolve `{cccGitHygieneHelper}` ← first existing path in `{cccGitHygieneProbeOrder}`. Bind `{tree_timeout}` to the seconds the helper may take, a little under the longest timeout your shell tool can be given, since a first fetch of a large repository is slow: `540` when it takes a 10-minute timeout, `100` when its longest is two minutes or you do not know it. Give the command that longest shell timeout: the helper stops itself within `--timeout` seconds and still prints its result. From `{project-root}`, run:

```bash
uv run {sourceTreeHelper} resolve \
    --source-repo "{source_repo}" \
    [--target-ref "{brief.target_ref}"] \
    [--version "{brief.target_version}" --name "{brief.name}"] \
    [--version "{brief.version}" --implicit] \
    --update-clone \
    [--hygiene-helper "{cccGitHygieneHelper}"] \
    --timeout "{tree_timeout}"
```

Pass `--target-ref` when the brief sets `target_ref`. Pass the first `--version` line when the brief sets `target_version`, else the second when it sets `version`, never both. Pass `--hygiene-helper` when `{cccGitHygieneHelper}` resolved.

Bind from its JSON `source_ref` ← `source_ref`, `source_commit` ← `source_commit`, `tag_resolution` ← `tag_resolution`, `{workspace_path}` ← `workspace_path`, `{workspace_clone}` ← `clone`, `{source_tree}` ← `tree`, `{source_resolve_status}` ← `status`, `{source_resolve_reason}` ← `reason`, `{source_resolve_message}` ← `message`, `{clone_status}` ← `clone_status` and `{clone_skip_reason}` ← `clone_skip_reason`, and display each entry of `warnings`.

Dispatch on `{source_resolve_status}`:

- **`ready`** (exit 0): bind `{source_root}` ← `{source_tree}`. Every later read of the source reads this tree: the §2 file list, the §2a scan, extraction, step 6's citation check and step 7's script and asset copies. Build the §2 filtered file list again from `{source_root}` when §2 builds one (a `component-library` brief), since step 1 listed the remote's default branch, which need not hold `source_commit`. Bind `{resolved-source-path}` ← `{workspace_clone}`, or ← `{source_repo}` when `{workspace_clone}` is null (the folder at `{workspace_path}` is not SKF's clone of the repository): it is the `source_root` metadata.json records (`{sourceResolutionData}` "Source Commit Capture"). When `{clone_status}` is `advanced` or `ok`, SKF's clone now holds `source_commit`: bind `{remote_clone_path}` ← `{workspace_clone}`, the folder the deferred ccc discovery below and step 7 §6b index. Otherwise leave it null and display "SKF's clone of `{source_repo}` at `{workspace_path}` was not moved ({clone_skip_reason}), so this run skips ccc discovery and the ccc index registration. Extraction reads this run's own tree." Then report the outcome of `tag_resolution` as `{sourceResolutionData}` "Tag Resolution" says.
- **`ambiguous`** (exit 0): several tags match, and nothing was read. Make the choice in `{sourceResolutionData}` "Several Matching Tags", run the command again with `--target-ref "{chosen tag}"` (`HEAD` for the default branch) in place of `--version`, `--name`, `--implicit` and any `--target-ref` from the brief, and dispatch on that result.
- **`skipped`** (exit 0): the helper does not read `{source_repo}` as a remote repository (`skip_reason` is `not-remote`), so treat it as a local source, above.
- **`unavailable`** (exit 3): no commit could be read, and no tree was left behind (`{source_resolve_reason}` is `invalid-ref`, `git-unavailable`, `upstream-unreachable`, `ref-not-found`, `fetch-failed`, `checkout-failed`, `tree-folder-failed` or `timed-out`). ⚠️ Warn the user explicitly: "Could not read `{source_repo}`: {source_resolve_message}. Degrading to source reading (T1-low) for this run. For T1 (AST-verified) confidence, clone the repository locally and update `source_repo` in your brief to the local path." Keep `{source_root}` the remote URL, bind `source_ref` ← `source_ref` when it is not null and `HEAD` otherwise, and extract with the Quick tier strategy in §4. Note the degradation reason in context for the evidence report.
- **No candidate resolves, or the command exits 1 or 2, or prints no JSON:** continue as for `unavailable`, with `{source_resolve_message}` = "skf-source-tree.py did not finish: {the first stderr line; 'the shell stopped it before it printed a result' when your shell tool's timeout ended it; or 'it is missing; re-install SKF'}". A later run removes a tree a stopped run left behind once it is seven days old.

Then run Source Commit Capture and Version Reconciliation from `{sourceResolutionData}` on `{source_root}`. This ensures source code is accessible regardless of which extraction path is taken below (standard, component-library, or docs-only).

**Deferred CCC Discovery (Forge+ and Deep, remote sources only):**

If ALL of these conditions are true:
- `tools.ccc` is true in forge-tier.yaml
- `{ccc_discovery}` is empty (step 2b deferred because source was remote)
- `{remote_clone_path}` is set (SKF's clone holds `source_commit`)
- Tier is Forge+ or Deep

Then index SKF's clone and search it. The clone persists across forges, so an index an earlier forge built there is brought up to date rather than rebuilt. ccc's results only rank files; extraction still reads `{source_root}`.

1. **Prepare the settings:** resolve `{mergeCccExclusionsHelper}` ← first existing path in `{mergeCccExclusionsProbeOrder}` and, from `{project-root}`, run `uv run {mergeCccExclusionsHelper} --clone-root "{remote_clone_path}"`. It runs `ccc init -f` in the clone when `.cocoindex_code/settings.yml` is missing, and appends the standard build and dependency exclusions the file lacks (`**/node_modules`, `**/dist`, `**/build`, `**/target` and the like), on a first run and on a reused index alike, keeping every entry already there. These are standard artifact patterns, not SKF paths: the clone is a source repository, not an SKF project. When `settings_yml_existed` is true and `patterns_added_list` is not empty, display: "Added {patterns_added} standard exclusions to the reused workspace index settings." When `settings_ready` is false, the command fails or no candidate resolves, set `{ccc_discovery: []}` and continue: this is not an error.

   **Note:** Brief-specific `include_patterns` and `exclude_patterns` are not written to `settings.yml`. The CCC index is general-purpose: it indexes everything (minus standard artifacts). Brief-specific filtering happens at search result time, not index time. This allows a single workspace CCC index to serve multiple briefs with different scope filters.

2. **Index the clone:** run `cd "{remote_clone_path}" && ccc index` in the foreground with an extended timeout. Indexing can take several minutes on large codebases (1000+ files); a reused index processes only what changed. Then load `{cccIndexCheckData}` and run it with `{ccc_root}` = `{remote_clone_path}` and `{ccc_settings_owner}` = `skf`. On **index unverified**, display "CCC index still building (index unverified), skipping the language check." and continue to step 3. When `ccc index` fails, or the check returns **degraded**, set `{ccc_discovery: []}` and continue: this is not an error.

3. **Construct semantic query:** Build from brief data: `"{brief.name} {brief.scope}"`. Truncate to 80 characters: keep the full skill name and trim `brief.scope` from the end. If `brief.scope` is very short (< 10 chars), append terms from `brief.description` to fill the remaining space.

4. **Execute search:** Run `ccc_bridge.search(query, remote_clone_path, top_k=20)` as `cd "{remote_clone_path}" && ccc search --limit 20 "{query}"`. Step 2 has just brought the index up to date, whether it was reused or new, so the search needs no refresh flag.
   - **Tool resolution:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or CLI. Note: `ccc search` operates on the index in the current working directory. See `knowledge/tool-resolution.md`.

5. **Store results:** If search succeeds, store as `{ccc_discovery: [{file, score, snippet}]}`. Display: "**CCC semantic discovery: {N} relevant regions identified across {M} unique files.**"

   If step 1 reported `settings_yml_existed` true (an earlier forge's index was reused), append: "(reused workspace index)"

6. **On failure:** Set `{ccc_discovery: []}`. Display: "CCC discovery unavailable, proceeding with standard extraction." Do not halt.

**Leave the workspace clone clean:** run `uv run {cccGitHygieneHelper} workspace --repo "{remote_clone_path}"` from `{project-root}` once this block is done with the clone: after step 5 or step 6, and also when step 1 or step 2 set `{ccc_discovery: []}`. Every `ccc init` or `ccc index` that creates `settings.yml` in a clone (the helper's `ccc init -f`, or a `ccc index` that initializes the clone itself) appends `# CocoIndex Code (ccc)` and `/.cocoindex_code/` to the clone's tracked `.gitignore`, and that change would make a later forge's move of the clone to another ref fail. The helper restores the `.gitignore` when those two lines are its only change (or deletes a `.gitignore` holding only them) and keeps the index folder out of git through the clone's `.git/info/exclude` instead. Resolve `{cccGitHygieneHelper}` from `{cccGitHygieneProbeOrder}` and read nothing from its output; if neither path exists or the command fails, continue: the next resolve repairs the clone before it moves it.

**CCC Discovery Integration (Forge+ and Deep with ccc only):**

If `{ccc_discovery}` is in context and non-empty (populated by step 2b or deferred discovery above), §4 and §4b read the files they read one at a time in its order, as the CCC Pre-Ranking Strategy in `{extractionPatternsData}` says. Display: "**CCC discovery: {N} files ranked by semantic relevance.** Files read one at a time follow this order."

If `{ccc_discovery}` is empty or not in context: proceed with existing file ordering (no change to current behavior).

### 2a. Discovered Authoritative Files Protocol

**Runs after §2b, not before it.** The scan walks a local tree, so it waits for §2b to resolve one: `{source_root}` now names the local source itself, or the private tree §2b read a remote source into, which no other run can move.

**Start clean:** set `authoritative_files_scan` to null and `promoted_docs[]` to empty before either skip below, so that in a `--batch` run one brief's scan never carries into the next.

**Skip this section entirely if `source_type: "docs-only"`:** there is no source tree to scan.

**Remote source guard:** if `source_root` is still a remote URL after §2b, there is no local tree to walk, and the helper refuses a source root that is not a directory. That happens for a Quick-tier remote source, which §2b never clones, and for a remote source §2b could not read into a tree, which it falls back to reading like Quick tier. Skip the scan and continue to §2c: record `authoritative_files_scan: {not_scanned: "remote source not cloned"}` for the evidence report and display "**Authoritative files scan skipped:** `{source_repo}` was not cloned in this run, so authoritative AI documentation files (`llms.txt`, `AGENTS.md` and the like) outside the brief's scope were not looked for. A run with a local tree (a local checkout, or a remote source cloned at Forge tier or higher) scans them."

Load `{authoritativeFilesProtocol}` and execute it: it scans the source tree for authoritative AI documentation files (`llms.txt`, `AGENTS.md`, `.cursorrules` and the like) the brief's scope filters left out, and records each decision in the brief at once, so re-runs replay it.

### 2c. Component Library Delegation

Skip this section for a `docs-only` brief. When `scope.type` is `"component-library"`, display "**Component library detected.** Delegating to specialized extraction strategy for registry-first, props-focused extraction.", load and execute `{componentExtractionStepFile}` completely, and when it returns control here resume at section 5 (Build Extraction Inventory) with its extraction data and `component_catalog[]`. Otherwise continue with standard extraction below.

### 3. Check for Docs-Only Mode

**If `source_type: "docs-only"` in the brief data:**

"**Docs-only mode:** No source code to extract. Documentation content will be fetched from `doc_urls` in step 3c."

Start the empty inventory with §5's `init` (resolve `{extractionInventoryHelper}` and halt as §5 says), from `{project-root}`:

```bash
uv run {extractionInventoryHelper} init --inventory "{extraction_inventory}" --skill "{name}" --mode docs-only --tier "{tier}"
```

It writes `extraction_mode: "docs-only"` with no export and no `top_exports`: steps 3b and 4 skip their per-export work on it, and step 3c merges its T3 items into it. When it fails twice, halt as §5 says. Auto-proceed through Gate 2 (section 6): display the empty inventory and note that the doc-fetcher step produces the T3 content.

**If `source_type: "source"` (default):** Continue with extraction below.

### 4. Execute Tier-Dependent Extraction

Source resolution, version reconciliation, and CCC discovery were completed in section 2b. Run the Strategy for the current tier from `{extractionPatternsData}` (loaded in §1): source reading at Quick tier (and for a remote source §2b could not read into a tree), and at Forge, Forge+ and Deep the **AST Extraction Protocol** there, whose recipe runner reads `{source_root}` itself. A branch that extracts without the runner (source reading, or the protocol's fallback) reads the §2 filtered file list: build it first, from `{source_root}`, when §2 did not. Label each export by the tool that produced it, as that file's Confidence sections say.

**The recipe runner (Forge, Forge+ and Deep):** resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}`; it writes `{extraction_json}` (bound in §2b, beside the staging folder step 5 creates, never inside the skill). From `{project-root}`, create that folder (the runner creates no folder) and remove the JSON an earlier run left there, then call the runner with the longest timeout your shell tool takes, since a large tree takes minutes:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-stage"
rm -f "{extraction_json}"
uv run {extractPublicApiHelper} --mode full \
    --source-root "{source_root}" \
    --brief "{brief_path}" \
    --tier "{tier}" \
    -o "{extraction_json}"
```

`{brief_path}` is the `skill-brief.yaml` step 1 loaded: the runner takes its `scope.include`, `scope.exclude`, `scope.tier_a_include`, `scope.type` and `language` from it, and the head cap from `--tier`. A JSON at `{extraction_json}` after the call is this call's: read it, in parts when it is large, and act on its `status` and fields as the protocol's **Recipe Runner** section says, never on the exit code. Each export it returns is T1 as it stands, its `source_line`, `citation`, `ast_recipe`, `ast_node_type`, `signature`, `params` and `return_type` included: read a signature from the source, at its `source_line`, only for a function whose `params` is null, and read by eye (T1-low) only what the runner leaves. When no path resolves, or a case the protocol's **When the Runner Cannot Run** lists applies, such as no JSON at `{extraction_json}` after the call or an empty `scope.languages` (no recipe reads the brief's language), follow that section.

**When `truncated` is true,** a recipe matched more exports than its head cap keeps, and the matches past the cap are missing: a public name among them comes back as an extraction gap (§4b), read by eye, and the others are left out. Warn, and keep the warning for §6 and the evidence report: "**Extraction hit the head cap:** {each `recipes[]` id whose `truncated` is true} matched more than {head_cap} exports, so some exports were read by eye or left out. Narrow `scope.include` in the brief until no recipe reaches the cap."

**Co-import detection (Forge tier and above):** use `ast_bridge.detect_co_imports(path, libraries[])` to find integration points: `find_code_by_rule` with a co-import YAML rule scoped to the libraries list, or `ast-grep scan -r {rule_file} --json=stream` (see `knowledge/tool-resolution.md`).

**If AST tools are unavailable at Forge, Forge+ or Deep tier** (no ast-grep can run the recipes: see `{tierDegradationRulesData}` for full rules):

⚠️ **Warn the user explicitly:** "AST tools are unavailable, so extraction will use source reading (T1-low). Run [SF] Setup Forge to detect and configure AST tools for T1 confidence."

Degrade to Quick tier extraction. Note the degradation reason in context for the evidence report.

**For each file, handle failures gracefully:**

- If a file cannot be read: log warning, skip file, continue with remaining files
- If AST parsing fails on a file (the runner lists each one in `file_issues`): fall back to source reading for that file, continue

**Re-export tracing (Forge tier and above):** the runner follows each entry point's re-exports to the file that defines each name. Follow the **Re-Export Tracing** protocol in `{extractionPatternsTracingData}` for what it could not follow: each `entry_points.unresolved` chain, and each `entry_point_diff.extraction_gaps` name with no `file`. Without the runner, check for unresolved public exports from entry points (`__init__.py`, `index.ts`, `lib.rs`) and follow the same protocol to resolve them to their definition files.

### 4b. Validate Exports Against Package Entry Point

After extraction, validate the collected exports against the package's actual public API surface.

**When the recipe runner extracted (§4: its JSON's `status` is `ok` or `incomplete`, and `scope.languages` is not empty),** its `entry_point_diff` is this check: do not read the entry points or diff the sets yourself. It read each package's entry points, traced each re-exported name to the file that defines it, and diffed those names with the recipe matches (`skf-extract-public-api.py --help` lists the entry points it reads):

- `public`: the package's public names, which `metadata.json`'s `exports[]` lists. In a language with no entry point, or only empty ones (`entry_points.by_language`), every export the recipes found is public.
- `internal`: exports the recipes found that no entry point exports or makes reachable. §5's `init` marks each `internal: true` in the inventory, and step 5 keeps them out of `metadata.json`'s `exports[]`.
- `extraction_gaps`: names an entry point exports that no recipe found: read each by eye at its `file` and `line` (T1-low), or trace it (§4) when it has no `file`.
- `outside_scope`: names an entry point exports that are defined in files outside the brief's scope. Display each of the runner's `warnings` (one names each `package.json` `exports` subpath whose entry point is outside the files in scope) and list these names with them: widen `scope.include` before extraction, or this surface stays undocumented while `exports_public_api` still counts it, so `public_api_coverage` drops (only `effective_denominator`, for the curated-subset shapes, leaves it out).

§5's `init` records its `counts` (`exports_public_api`, `exports_internal`, `effective_denominator` and `effective_denominator_basis`) and `arms` for step 5 §4. Files you read by eye because no recipe reads their language (`files_without_recipes`) are outside this diff and these counts: read their entry points as **Otherwise** says, add their names to the counts, and send the counts you changed with §5's `set`.

**Otherwise** (Quick tier, extraction by source reading, a brief whose language no recipe reads included, or the protocol's fallback), read the entry points yourself (when the runner's JSON has `status: no-ast-grep`, its `entry_points.files` lists them, and §5's `init` records its `arms` for step 5 §4): load `{entryPointsByHandData}`, which only this branch reads, compare and count as it says, and send the `counts` (and, without the runner's JSON, the `arms`) with §5's `set`.

### 4c. Detect and Inventory Scripts/Assets

The brief's `scripts_intent` and `assets_intent` are each `"detect"` (also when absent), `"none"` or free text describing the files wanted. The detector takes only `detect` or `none`: pass `none` for `"none"`, else `detect`. Resolve `{detectScriptsAssetsHelper}` ← first existing path in `{detectScriptsAssetsProbeOrder}`; if neither exists, **HARD HALT** (exit code 3, `helper-missing`, phase `extract`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot detect scripts and assets: skf-detect-scripts-assets.py is missing. Re-install SKF, then re-run create-skill." The detector implements the heuristics of `{extractionPatternsTracingData}`. From `{project-root}`, write its JSON to `{detected_json}` (bound in §2b), which §5's `init` reads:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-stage"
uv run {detectScriptsAssetsHelper} detect "{source_root}" \
    --scripts-intent {detect|none} \
    --assets-intent {detect|none} \
    [--scope-include "<glob1>,<glob2>,..."] \
    [--max-lines 500] > "{detected_json}"
```

It writes `scripts_inventory[]` and `assets_inventory[]` (each entry with `name`, `source_file`, `purpose`, `content_hash`, `confidence`, `lines` and `size_flag`), `scripts_skipped`, `assets_skipped` and `stats`.

**If it exits non-zero** (a `{source_root}` that is no local folder, as for a remote source read by eye): warn "Scripts and assets were not detected: {the first stderr line}", send the warning with §5's `add --field warnings` for §6 and the evidence report, and run §5's `init` without `--detected`: the inventories stay empty.

**Otherwise** §5's `init` takes every entry, unchanged and already `T1-low` with its `content_hash`, which is the inventory for a `"detect"` intent. For a free-text intent, choose the entries that match it and, after `init`, send them with §5's `set` as `{"intent_mapping": {"scripts": {"intent": "<the text>", "kept": [source_file, ...]}}}`, `"assets"` the same way: the helper keeps only those entries and records the others as the mapping's `left_out`, which §6 lists and step 5 writes into the evidence report. §6 surfaces each `size_flag: "oversized"` entry before bundling.

### 5. Build Extraction Inventory

`{extraction_inventory}` (bound in §2b, beside the staging folder, never inside the skill) is the run's extraction record: steps 3b to 7 read it, and steps 3c and 4 add to it, instead of a copy held in context. `{extractionInventoryHelper}` writes it, each call atomically: the runner's and the detector's records go in as those tools wrote them, and you send only what you produced. Resolve `{extractionInventoryHelper}` ← first existing path in `{extractionInventoryProbeOrder}`; if neither exists, **HARD HALT** (exit code 3, `helper-missing`, phase `extract`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot write the extraction inventory: skf-extraction-inventory.py is missing. Re-install SKF, then re-run create-skill." Run each call below from `{project-root}`.

**Start the inventory** with `init`, which replaces any file at `{extraction_inventory}`:

```bash
uv run {extractionInventoryHelper} init --inventory "{extraction_inventory}" --skill "{name}" --mode {source|component-library} --tier "{tier}" [--extraction "{extraction_json}"] [--detected "{detected_json}"]
```

Pass `--mode component-library` for a component library (§2c), else `source`. Pass `--extraction` when §4's runner, or step 3d's Phase 4 for a component library, left a JSON at `{extraction_json}`, and `--detected` when §4c's detector exited 0. From the runner's JSON, `init` writes each export as the runner recorded it (T1, `ast-grep`, with its `source_file`, `source_line`, `citation`, `ast_recipe`, `ast_node_type` and `export_type`), marked `internal: true` when §4b's `internal` lists it; `files_scanned` (the runner's `files_in_scope`); its `aggregates`, `counts` and `arms`; `extraction_rules` (its `recipe_set`, the `recipes` ids, its `scope` and `ast_grep.version`), from which step 7 writes `extraction-rules.yaml`; and the runner warnings in `warnings`, one line each: the head-cap warning (§4), each `errors[]` item, each `file_issues[]` file, each extension `files_without_recipes` counts, and each of its `warnings`. From the detector's JSON it writes `scripts_inventory` and `assets_inventory`.

**Then send what you produced**, each call with its JSON payload on stdin, leaving out a call with nothing to send:

- **Signatures** (`patch`): for each function export whose `params` the runner left null (and each Props interface of a component library), the full signature, the parameters (each as `{"name", "type", "default", "optional"}`, as the runner records them) and the return type you read from the source at its `source_line`. It sets only those three fields, matches each entry on `export_name` and `source_file`, and lists in `unmatched` and `ambiguous` the entries it could not place: correct those and send them again.
- **Exports read by eye** (`add --field exports`): each export §4 or §4b read by eye (an extraction gap, a `file_issues` file, a language no recipe reads, or every export when the runner did not run), with its `export_name`, `export_type`, `signature`, `params`, `return_type`, `source_file`, `source_line` and `[SRC:...]` citation. The helper labels it T1-low (`source-read`, with `ast_node_type` and `ast_recipe` null) unless the entry carries its own labels, as a `find_code` match of the protocol's fallback does (T1, `ast-grep`, the `kind` its recipe or pattern declares, and the pattern as its `ast_recipe`). A component library (§2c) sends here only the exports step 3d read by eye (Quick tier, a `file_issues` file, or the runner's fallback); it sends each Props interface's fields with `patch` as `params`, and `component_catalog` with `set`.
- **Warnings you raise** (`add --field warnings`): a list of strings, such as a degradation reason (§2b, §4), the detector's failure (§4c) or a file you could not read.
- **The rest** (`set`), in one JSON object: `top_exports`, the 10 to 20 public API function names by prominence (import frequency or documentation position), which step 3b's targeted temporal fetch reads; `co_imports` (Forge tier and above), the libraries commonly imported alongside the exports, with integration point suggestions; `promoted_docs` and `authoritative_files_scan`, §2a's records; `intent_mapping` for a free-text intent (§4c); a component library's `component_catalog`; and, when the runner did not run, `files_scanned` (§2's filtered file count) and the `counts` and `arms` §4b recorded. `counts` and `arms` merge into what is there, so after the runner send only a count you changed.

```bash
uv run {extractionInventoryHelper} patch --inventory "{extraction_inventory}" <<'SKF_INVENTORY'
[{"export_name": "...", "source_file": "...", "signature": "...", "params": [], "return_type": "..."}]
SKF_INVENTORY
uv run {extractionInventoryHelper} add --inventory "{extraction_inventory}" --field exports <<'SKF_INVENTORY'
[{"export_name": "...", "export_type": "...", "signature": "...", "params": [], "return_type": "...", "source_file": "...", "source_line": 0, "citation": "[SRC:...]"}]
SKF_INVENTORY
uv run {extractionInventoryHelper} add --inventory "{extraction_inventory}" --field warnings <<'SKF_INVENTORY'
["..."]
SKF_INVENTORY
uv run {extractionInventoryHelper} set --inventory "{extraction_inventory}" <<'SKF_INVENTORY'
{"top_exports": [], "co_imports": [], "promoted_docs": [], "authoritative_files_scan": null}
SKF_INVENTORY
uv run {extractionInventoryHelper} summary --inventory "{extraction_inventory}"
```

A call that exits non-zero changes nothing: fix what its `message` names and run it again. An entry the inventory already holds is not added twice (`duplicates`), so a call run again is safe. When a call fails twice, **HARD HALT** (exit code 4, `write-failed`, phase `extract`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`), with `"path": "{extraction_inventory}"`: "Cannot write the extraction inventory `{extraction_inventory}`: {the helper's message}. Check permissions and disk space."

The summary's `counts` give §6 its numbers: `files_scanned`, `exports`, `by_type`, `t1`, `t1_low`, `co_imports`, `scripts` and `assets`.

### 6. Present Extraction Summary (Gate 2)

**Docs-only note:** for `extraction_mode: "docs-only"`, display "Docs-only mode: extraction inventory is empty. Documentation content will be fetched from `doc_urls` in step 3c. Auto-proceeding." and auto-proceed past this gate.

**Zero-export sanity check (source mode):** If `extraction_mode != "docs-only"` AND the §5 summary counts no export (its `exports` is 0) AND the brief declares no `doc_urls` (step 3c applies this check to a brief whose every `doc_urls` fetch failed), the empty extraction is almost always an error, not a valid empty surface. Surface a distinct warning at the gate:

"**⚠️ Zero public exports extracted.** A source-type brief produced no documented surface and declares no `doc_urls`. This usually means a scope/branch/tag mismatch (wrong `target_version`, over-narrow `scope.include`) or a failed AST run — the compiled skill would document nothing. Verify the brief's source ref and scope before continuing.

**[C] Continue anyway**: compile an empty surface (default)
**[R] Refine the brief**: stop here"

Under `{headless_mode}`, do not auto-pass silently: log `"headless: zero public exports extracted, likely a scope, branch or tag mismatch; continuing"`, stage `{"step": "extract", "gate": "zero-exports", "decision": "C", "rationale": "headless mode: zero exports, no human to confirm scope or ref", "timestamp": "{ISO}"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"` (the Workflow Rules' record), and proceed. Step 8 reports a run whose sink holds this decision as `status: "partial"` with `summary.warning: "zero-exports"`, so a run that looks green but is not reaches a person or a pipeline.

Display the extraction findings for user confirmation, the numbers from the §5 summary's `counts` and the lists from `{extraction_inventory}`:

"**Extraction complete.**

**Files scanned:** {files_scanned}
**Exports found:** {exports} ({by_type, each as its count and `export_type`})
**Confidence:** {t1} T1 (AST-verified), {t1_low} T1-low (source reading)
**Tier used:** {tier}
**Co-import patterns:** {co_imports} detected
{if scripts > 0: **Scripts detected ({scripts}):** each kept entry as `{name}` (`{source_file}`): {purpose}, marked when `size_flag` is oversized}
{if assets > 0: **Assets detected ({assets}):** the same way}
{for a free-text intent: the files its `intent_mapping` left out}

**Top exports:**
{list top 10 exports with signatures}

{warnings: the inventory's `warnings`}

Review the extraction summary above, then confirm to continue."

### 7. Gate 2 — Confirm Extraction

Docs-only mode (`extraction_mode: "docs-only"`) needs no confirmation: auto-proceed to `{nextStepFile}`.

Otherwise halt after the §6 summary and wait for the user to continue (they may ask about the results first). When §6 showed the zero-export or the head-cap warning, also offer **[R] Refine the brief**: stop here. **GATE [default: continue]**: under `{headless_mode}`, auto-proceed, log "headless: auto-approve extraction summary", stage `{"step": "extract", "gate": "review-gate", "decision": "continue", "rationale": "headless mode: no person to review the extraction summary", "timestamp": "{ISO}"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"` (the Workflow Rules' record). On continue, load `{nextStepFile}`, read it fully, then execute it.

**On [R]:** **HARD HALT** (exit code 6, `halted-for-brief-refinement`, phase `extract`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "**Halting create-skill:** {the warning that prompted the stop, one line}. Fix `scope.include` or `target_version` in the brief (or re-run `skf-brief-skill`), then re-run `skf-create-skill`."

