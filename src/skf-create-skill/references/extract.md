---
nextStepFile: 'sub/fetch-temporal.md'
componentExtractionStepFile: 'component-extraction.md'
extractionPatternsTracingData: 'references/extraction-patterns-tracing.md'
tierDegradationRulesData: 'references/tier-degradation-rules.md'
sourceResolutionData: 'references/source-resolution-protocols.md'
authoritativeFilesProtocol: 'references/authoritative-files-protocol.md'
cccIndexCheckData: 'references/ccc-index-check.md'
# Probe installed SKF module path first, src/ dev-checkout fallback. At first
# use below, resolve `{atomicWriteHelper}` to the first existing path; HALT if
# neither candidate exists — losing atomic-write guarantees is not an option.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# Resolve `{detectScriptsAssetsHelper}` to the first existing path; HALT if
# neither candidate exists. §4c relies on the helper for deterministic
# script/asset detection (file walk, SHA-256 hashing, header-comment purpose
# extraction); falling back to prose-driven detection would lose hash stability.
detectScriptsAssetsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-scripts-assets.py'
  - '{project-root}/src/shared/scripts/skf-detect-scripts-assets.py'
# Resolve `{resolveAuthoritativeFilesHelper}` to the first existing path;
# HALT if neither exists. §2a uses it to scan the source tree for
# authoritative AI documentation files, classify each against scope
# filters + amendments, and load previews + content hashes — all five
# deterministic phases in one call. Falling back to prose-driven file
# walking + glob matching + hashing would let the LLM drift on the
# heuristic list and miss auth-doc files at deeper directory depths.
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
# Resolve `{sourceTreeHelper}` to the first existing path. §2b reads a remote
# source at Forge tier or above through it, into a private tree at one
# commit, and step 7 and every HALT after §2b remove that tree with it. If
# neither path exists, §2b degrades that source to source reading.
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
# Resolve `{mergeCccExclusionsHelper}` to the first existing path. §2b's
# deferred ccc discovery prepares the workspace clone's settings.yml with it;
# if neither path exists, that discovery is skipped.
mergeCccExclusionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-merge-ccc-exclusions.py'
  - '{project-root}/src/shared/scripts/skf-merge-ccc-exclusions.py'
# Resolve `{extractPublicApiHelper}` to the first existing path. §4 runs it
# in --mode full: it is the recipe runner of the AST Extraction Protocol in
# `{extractionPatternsData}`. If neither path exists, §4 follows the
# protocol's fallback.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
# Resolve `{extractionPatternsData}` to the first existing path; HALT if
# neither exists. Steps 5 and 6 bind it the same way.
extractionPatternsDataProbeOrder:
  - '{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md'
  - '{project-root}/src/skf-create-skill/references/extraction-patterns.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Extract

## STEP GOAL:

To extract all public exports, function signatures, type definitions, and co-import patterns from the source code using tier-appropriate tools, building a complete extraction inventory with confidence-tiered provenance citations.

## Rules

- Focus only on extracting exports, signatures, types from source code — do not compile SKILL.md
- Do not write any output files: extraction stays in context, apart from the JSON the recipe runner writes beside the staging folder (§4)
- Every extracted item must have a provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`

## MANDATORY SEQUENCE

### 1. Load Extraction Patterns

Resolve `{extractionPatternsData}` ← first existing path in `{extractionPatternsDataProbeOrder}` and load it completely. Identify the strategy for the current forge tier.

### 2. Apply Scope Filters

From the brief, apply scope and pattern filters:

- `scope.type` — determines what to extract (e.g., `full-library`, `specific-modules`, `public-api`, `component-library`, `reference-app`, `docs-only`). Use `reference-app` when the source is a whole app and the skill's value is wiring patterns rather than public exports (embedded-sidecar reference apps, CLI-demo repos, integration-pattern demonstrators). `reference-app` triggers the compile-assembly overrides in `assets/compile-assembly-rules.md` that replace "Key API Summary" with a "Pattern Surface" section and make `stats.exports_documented` semantics pattern-oriented. Do not pick `full-library` for reference apps — downstream assembly will remap wiring onto export slots, producing fuzzy counts and an awkward SKILL.md.
- `scope.include` — file globs to include
- `scope.exclude` — file globs to exclude

At Forge tier and above the recipe runner (§4) applies these globs to the source tree itself, and its `files_in_scope` is the filtered file count. Build the filtered file list by hand only where a step reads it: at Quick tier, for a `component-library` brief (§2c), and in a §4 branch that extracts without the runner. Build it from the source tree resolved in step 1 (for a remote source at Forge tier or above, §2b builds it again from the tree it reads), matching the globs by the **Files in scope** rule of the Recipe Runner section in `{extractionPatternsData}`, and record the result: "**Filtered file count: {N} files in scope**".

Sections 2b and 2a follow in that order: §2b resolves the source to a local tree, and §2a scans that tree for authoritative files.

### 2b. Resolve Source Access

**Start clean:** first, for every brief, docs-only included, set `{source_tree}`, `{workspace_clone}` and `{remote_clone_path}` to null and `{resolved-source-path}` to `{source_root}` (null for a docs-only brief), so that in a `--batch` run one brief's source never carries into the next.

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

Load `{authoritativeFilesProtocol}` and execute it. The full protocol (heuristic scan list, helper invocation, classification dispatch, prompt flow, P/S/U decision-apply, summary, provenance-map handoff, downstream consumption) lives there.

Briefly: scan the source tree for authoritative AI documentation files (`llms.txt`, `AGENTS.md`, `.cursorrules`, etc.) that the brief's scope filters may have excluded. The `{resolveAuthoritativeFilesHelper}` helper does the deterministic work (walk, scope diff, amendment reconcile, preview load, hashing); the LLM applies the resulting `unresolved[]` prompt loop. Promoted decisions are persisted to the brief immediately so re-runs replay deterministically.

### 2c. Component Library Delegation

**Skip this section if `source_type` is `"docs-only"` — docs-only skills do not use component extraction.**

**If `scope.type: "component-library"` in the brief:**

"**Component library detected.** Delegating to specialized extraction strategy for registry-first, props-focused extraction."

Load and execute `{componentExtractionStepFile}` completely. When that step completes, it returns control here. Resume at section 5 (Build Extraction Inventory) with the enriched extraction data and `component_catalog[]` from the component extraction step.

**Otherwise:** Continue with standard extraction below.

### 3. Check for Docs-Only Mode

**If `source_type: "docs-only"` in the brief data:**

"**Docs-only mode:** No source code to extract. Documentation content will be fetched from `doc_urls` in step 3c."

Build an empty extraction inventory with zero exports. **Set `top_exports = []` explicitly in context** — downstream steps (notably §3b targeted searches and step 4 enrichment fan-out) must see an empty list rather than an undefined/missing field so they can short-circuit deterministically. Set `extraction_mode: "docs-only"` in context. Auto-proceed through Gate 2 (section 6) — display the empty inventory and note that T3 content will be produced by the doc-fetcher step.

**If `source_type: "source"` (default):** Continue with extraction below.

### 4. Execute Tier-Dependent Extraction

Source resolution, version reconciliation, and CCC discovery were completed in section 2b. Run the Strategy for the current tier from `{extractionPatternsData}` (loaded in §1): source reading at Quick tier (and for a remote source §2b could not read into a tree), and at Forge, Forge+ and Deep the **AST Extraction Protocol** there, whose recipe runner reads `{source_root}` itself. A branch that extracts without the runner (source reading, or the protocol's fallback) reads the §2 filtered file list: build it first, from `{source_root}`, when §2 did not. Label each export by the tool that produced it, as that file's Confidence sections say.

**The recipe runner (Forge, Forge+ and Deep):** resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}` and bind `{extraction_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.extraction.json` (beside the staging folder step 5 creates, never inside the skill). From `{project-root}`, create that folder (the runner creates no folder) and remove the JSON an earlier run left there, then call the runner with the longest timeout your shell tool takes, since a large tree takes minutes:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-stage"
rm -f "{extraction_json}"
uv run {extractPublicApiHelper} --mode full \
    --source-root "{source_root}" \
    --brief "{brief_path}" \
    --tier "{tier}" \
    -o "{extraction_json}"
```

`{brief_path}` is the `skill-brief.yaml` step 1 loaded: the runner takes its `scope.include`, `scope.exclude`, `scope.tier_a_include`, `scope.type` and `language` from it, and the head cap from `--tier`. A JSON at `{extraction_json}` after the call is this call's: read it, in parts when it is large, and act on its `status` and fields as the protocol's **Recipe Runner** section says, never on the exit code. Each export it returns is T1 as it stands (its `source_line`, `citation`, `ast_recipe` and `ast_node_type` included), so read from the source only each export's full signature, parameter types and return type, at its `source_line`, and read by eye (T1-low) only what the runner leaves. When no path resolves, or a case the protocol's **When the Runner Cannot Run** lists applies, such as no JSON at `{extraction_json}` after the call or an empty `scope.languages` (no recipe reads the brief's language), follow that section.

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
- `internal`: exports the recipes found that no entry point exports or makes reachable: mark them internal and keep them out of `metadata.json`'s `exports[]`.
- `extraction_gaps`: names an entry point exports that no recipe found: read each by eye at its `file` and `line` (T1-low), or trace it (§4) when it has no `file`.
- `outside_scope`: names an entry point exports that are defined in files outside the brief's scope. Display each of the runner's `warnings` (one names each `package.json` `exports` subpath whose entry point is outside the files in scope) and list these names with them: widen `scope.include` before extraction, or this surface stays undocumented while `exports_public_api` still counts it, so `public_api_coverage` drops (only `effective_denominator`, for the curated-subset shapes, leaves it out).

Record its `counts` (`exports_public_api`, `exports_internal`, `effective_denominator` and `effective_denominator_basis`) and `arms` for step 5 §4. Files you read by eye because no recipe reads their language (`files_without_recipes`) are outside this diff and these counts: read their entry points as **Otherwise** says and add their names to the counts.

**Otherwise** (Quick tier, extraction by source reading, a brief whose language no recipe reads included, or the protocol's fallback), read the entry points yourself (when the runner's JSON has `status: no-ast-grep`, its `entry_points.files` lists them, and record its `arms` for step 5 §4) and compare them with the extracted exports, then count `exports_public_api` (the entry points' public names) and `exports_internal` (every other non-underscore export) for step 5 §4:

- **Python:** Read `{source_root}/__init__.py` — extract imports to build the public export list. Compare against AST results:
  - In AST but not entry point → mark as internal (exclude from `metadata.json` exports)
  - In entry point but not AST → flag as extraction gap (trace via re-export protocol)
- **TypeScript/JS:** Read `index.ts`/`index.js` — same comparison logic.
- **Rust:** Read `lib.rs` — extract `pub use` items. Same logic. **Go:** Scan for exported (capitalized) identifiers.

**Multi-entry packages (`exports` map / declaration-file entry points).** A single per-language entry-point read misses public surface that a package ships through its `package.json` `exports` map — especially committed `.d.ts` / `.d.mts` declaration files that resolve **outside** the conventional source dir (e.g. a monorepo package whose `./macro` subpath maps to `macro/index.d.mts`, listed in `files[]` but not under `src/`). When the in-scope package declares an `exports` map:

- Resolve each `exports` subpath to its target file and treat that file — and any committed `.d.ts` / `.d.mts` declaration it resolves to — as an authoritative public entry point, reading it the same way as the primary barrel above even when it lives outside `src/`.
- If a resolved `exports` subpath target falls **outside** the brief's `scope.include` globs, surface a note: `"warn: public entry point {path} (exports subpath '{subpath}') resolves outside scope.include: widen scope.include before extraction, or this surface stays undocumented while exports_public_api still counts it, so public_api_coverage drops (only effective_denominator, for the curated-subset shapes, leaves it out)."` Widening `scope.include` here keeps the documented surface aligned with the `effective_denominator` that compile.md §4 derives from those same globs, without mid-run scope surgery.

Use the entry point as the authoritative source for `metadata.json`'s `exports[]` array.

**If entry point is missing or unreadable:** Skip validation with a warning.

### 4c. Detect and Inventory Scripts/Assets

**Default resolution:** If `scripts_intent` is absent from the brief, treat as `"detect"` (auto-detection). If `assets_intent` is absent, treat as `"detect"`. Only an explicit `"none"` value disables detection.

Invoke the deterministic detector — it implements the heuristics from `{extractionPatternsTracingData}` (directory conventions, shebang signals, `package.json` `bin` entry-points, asset filename patterns, binary-extension exclusion, generated-path pruning) so this stage doesn't re-derive them per-run:

```bash
uv run {detectScriptsAssetsHelper} detect <source-root> \
    --scripts-intent <scripts_intent> \
    --assets-intent <assets_intent> \
    [--scope-include "<glob1>,<glob2>,..."] \
    [--max-lines 500]
```

The helper emits JSON on stdout:

```json
{
  "scripts_inventory": [ {name, source_file, purpose, language, content_hash, confidence, lines, size_flag}, ... ],
  "assets_inventory":  [ {name, source_file, purpose, type,     content_hash, confidence, lines, size_flag}, ... ],
  "scripts_skipped": <bool>,
  "assets_skipped":  <bool>,
  "stats": { "scripts_found": N, "assets_found": M, "files_scanned": K }
}
```

Merge `scripts_inventory[]` and `assets_inventory[]` into the running extraction inventory verbatim — entries already carry `confidence: "T1-low"` and `content_hash` (sha256:...). Records with `size_flag: "oversized"` should be surfaced in §6 (Extraction Summary) so the user can confirm before bundling. If both `scripts_skipped` and `assets_skipped` are true, the helper performs no walk and §4c is effectively a no-op.

### 5. Build Extraction Inventory

Compile all extracted data into a structured inventory:

**Per-export entry:**
- Function/type name
- Full signature with types
- Parameters (name, type, required/optional)
- Return type
- Source file and line number
- Provenance citation (`[AST:...]` or `[SRC:...]`)
- Confidence tier: T1 for an export an ast-grep rule matched, T1-low for an export read by eye
- `extraction_method`: the tool that produced the entry, `ast-grep` or `source-read`
- `ast_node_type`: the `kind` the matching recipe or pattern declares, or `null` for an export read by eye
- `ast_recipe`: the recipe that matched it (its `id` in `{extractionPatternsData}`, or the pattern of a `find_code` call), or `null` for an export read by eye. validate.md §7a reads it to repair a node kind ast-grep does not know

An export the recipe runner returned takes its name, `source_file`, `source_line`, `citation`, `ast_recipe`, `ast_node_type` and `export_type` from the runner's record unchanged.

**Aggregate counts:** when the runner ran, take them from its JSON and add the exports read by eye; otherwise count the inventory:
- Total files scanned: the runner's `files_in_scope` (else §2's filtered file count)
- Total exports found: `aggregates.exports`, plus the exports read by eye
- Exports by type (functions, types/interfaces, constants): `aggregates.by_type`, plus the exports read by eye
- Confidence breakdown: T1 is `aggregates.t1`, the runner's exports; T1-low counts the exports read by eye
- `top_exports[]` — sorted list of the top 10-20 public API function names by prominence (import frequency or documentation position). This named field is consumed by step 3b for targeted temporal fetching and cache fingerprinting.

**Runner warnings (when it ran):** keep for §6 and the evidence report the head-cap warning when `truncated` is true (§4), each `errors[]` item ("ast-grep did not finish on {files} files from `{first_file}` ({detail}): exports in them may be missing"), each `file_issues[]` file read by eye, each extension `files_without_recipes` counts ("{N} `{ext}` files in scope are in a language no recipe reads"), and each entry of its `warnings`.

**Extraction rules (for step 7's `extraction-rules.yaml`):** the runner's `recipe_set`, the `recipes[]` ids it ran, its `scope` and `ast_grep.version`.

**Script/asset counts (when detected):**
- `scripts_found`: count of scripts detected
- `assets_found`: count of assets detected

**Co-import patterns (Forge/Deep only):**
- Libraries commonly imported alongside extracted exports
- Integration point suggestions

### 6. Present Extraction Summary (Gate 2)

**Docs-only note:** If `docs_only_mode` is active (`extraction_mode: "docs-only"`), display a brief note explaining that T3 content will be added by the doc-fetcher step (step 3c), then auto-proceed past this gate. Example: "Docs-only mode: extraction inventory is empty. Documentation content will be fetched from `doc_urls` in step 3c. Auto-proceeding."

**Zero-export sanity check (source mode):** If `extraction_mode != "docs-only"` AND `export_count == 0` AND the brief declares no `doc_urls`, an empty extraction is almost always an error — a wrong branch/tag, an over-narrow `scope.include`, or a failed AST run — not a valid empty surface. Do not let this sail through to a green report. Surface a distinct warning at the gate:

"**⚠️ Zero public exports extracted.** A source-type brief produced no documented surface and declares no `doc_urls`. This usually means a scope/branch/tag mismatch (wrong `target_version`, over-narrow `scope.include`) or a failed AST run — the compiled skill would document nothing. Verify the brief's source ref and scope before continuing.

**[C] Continue anyway** — compile an empty surface (default)"

Under `{headless_mode}`, do not auto-pass silently: set `status: "partial"` and `summary.warning: "zero-exports"` on the result contract (carried to step 8's record), log `"headless: zero public exports extracted — likely scope/branch/tag mismatch, continuing"`, append a `headless_decisions[]` entry `{step: "extract", gate: "zero-exports", decision: "C", rationale: "headless mode — zero exports, no human to confirm scope/ref", timestamp: {ISO}}` and, the moment it lands, append the same object as a JSON line to the durable audit sink `{sidecar_path}/auto-decisions.jsonl` (the on-landing append established at step 1 §3), and proceed. The distinct warning string surfaces the worst kind of failure (looks green, isn't) where a human or automator can act on it.

Display the extraction findings for user confirmation:

"**Extraction complete.**

**Files scanned:** {file_count}
**Exports found:** {export_count} ({function_count} functions, {type_count} types, {constant_count} constants)
**Confidence:** {t1_count} T1 (AST-verified), {t1_low_count} T1-low (source reading)
**Tier used:** {tier}
**Co-import patterns:** {pattern_count} detected
{if scripts_found > 0: **Scripts detected:** {scripts_found}}
{if assets_found > 0: **Assets detected:** {assets_found}}

**Top exports:**
{list top 10 exports with signatures}

{warnings: the runner warnings §5 kept, and any file skipped or degraded}

Review the extraction summary above, then confirm to continue."

### 7. Gate 2 — Confirm Extraction

Docs-only mode (`extraction_mode: "docs-only"`) needs no confirmation — auto-proceed to `{nextStepFile}`.

Otherwise this is a confirmation gate: halt after the §6 summary and wait for the user to continue (they may ask about the results first). **GATE [default: continue]** — under `{headless_mode}`, auto-proceed and log "headless: auto-approve extraction summary". On continue, load `{nextStepFile}`, read it fully, then execute it.

