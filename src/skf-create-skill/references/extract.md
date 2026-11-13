---
nextStepFile: 'fetch-temporal.md'
componentExtractionStepFile: 'component-extraction.md'
extractionPatternsTracingData: 'references/extraction-patterns-tracing.md'
tierDegradationRulesData: 'references/tier-degradation-rules.md'
sourceResolutionData: 'references/source-resolution-protocols.md'
authoritativeFilesProtocol: 'references/authoritative-files-protocol.md'
cccIndexCheckData: 'references/ccc-index-check.md'
entryPointsByHandData: 'references/entry-points-by-hand.md'
remoteSourceAccessData: 'references/remote-source-access.md'
detectScriptsAssetsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-scripts-assets.py'
  - '{project-root}/src/shared/scripts/skf-detect-scripts-assets.py'
resolveAuthoritativeFilesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-authoritative-files.py'
  - '{project-root}/src/shared/scripts/skf-resolve-authoritative-files.py'
cccGitHygieneProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-ccc-git-hygiene.py'
  - '{project-root}/src/shared/scripts/skf-ccc-git-hygiene.py'
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
mergeCccExclusionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-merge-ccc-exclusions.py'
  - '{project-root}/src/shared/scripts/skf-merge-ccc-exclusions.py'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
scanManifestsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-scan-manifests.py'
  - '{project-root}/src/shared/scripts/skf-scan-manifests.py'
countImportsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-count-imports.py'
  - '{project-root}/src/shared/scripts/skf-count-imports.py'
pairIntersectProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-pair-intersect.py'
  - '{project-root}/src/shared/scripts/skf-pair-intersect.py'
extractionPatternsDataProbeOrder:
  - '{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md'
  - '{project-root}/src/skf-create-skill/references/extraction-patterns.md'
extractionInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extraction-inventory.py'
  - '{project-root}/src/shared/scripts/skf-extraction-inventory.py'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
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
- Write only beside the staging folder (the recipe runner's JSON and the co-import counts, §4, the detector's JSON, §4c, and the extraction inventory, §2a and §5), and the brief only through §2b's protocol
- Every extracted item must have a provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`
- A HARD HALT, once step 3 §2a has bound `{source_tree}`, first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` (resolved from `{sourceTreeProbeOrder}`) and goes on whatever it prints, and emits through `{emitEnvelopeHelper}`, resolved from `{emitEnvelopeProbeOrder}` when it is not bound: it stages `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "summary": {"halt_reason": "<halt_reason>", "evidence_report": null}}`, plus `"path"` when the HALT names a file or folder, as `{run_dir}/halt.json`, runs `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`, displays the line it prints (the halt message alone when no path resolves) and stops with the HALT's exit code. After its envelope, under `--batch` it ends only this brief: return to `references/batch-mode.md` §3, even when the halt reads as the end of the run.

## MANDATORY SEQUENCE

### 1. Load Extraction Patterns

Resolve `{extractionPatternsData}` ← first existing path in `{extractionPatternsDataProbeOrder}` and load it up to its `## Running the Recipes Without the Runner` heading, for the current tier's strategy and the AST Extraction Protocol: the rest (the decision tree, the CLI streaming template and the recipes) serves only a run without the recipe runner, and the protocol's **When the Runner Cannot Run** section sends such a run there. If neither path exists, **HARD HALT** (exit code 3, `helper-missing`, phase `extract`): "Cannot extract: extraction-patterns.md is missing. Re-install SKF, then re-run create-skill."

### 2. Apply Scope Filters

From the brief, apply scope and pattern filters:

- `scope.type`: what to extract (`full-library`, `specific-modules`, `public-api`, `component-library`, `reference-app` or `docs-only`). A `reference-app` brief documents a whole app's wiring patterns rather than public exports: it triggers the overrides in `references/assembly-reference-app.md`, which replace "Key API Summary" with a "Pattern Surface" section and make `stats.exports_documented` count patterns.
- `scope.include` — file globs to include
- `scope.exclude` — file globs to exclude

At Forge tier and above the recipe runner (§4) applies these globs to the source tree itself: its `files_in_scope_list` and `files_without_recipes_list` are the filtered file list, and `files_in_scope` its count. Where a step reads the list without the runner (at Quick tier, for a `component-library` brief (§2c), and in a §4 branch that extracts without the runner), resolve `{extractPublicApiHelper}` as §4 does and build it from the source tree resolved in step 1 by step 1 of `{entryPointsByHandData}`. When a call of that file fails as its step 4 says, **HARD HALT** (exit code 4, `write-failed`, phase `extract`, or exit code 3, `helper-missing`, when no path resolves): "Cannot list or count the public API: {its `error:` line}. Fix the brief, or re-install SKF, then re-run create-skill."

### 2a. Resolve Source Access

**Start clean:** first, for every brief, docs-only included, set `{source_tree}`, `{workspace_clone}` and `{remote_clone_path}` to null and `{resolved-source-path}` to `{source_root}` (null for a docs-only brief), so that in a `--batch` run one brief's source never carries into the next. Bind `{extraction_inventory}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.inventory.json`, `{detected_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.detected.json`, `{extraction_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.extraction.json`, `{co_imports_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.co-imports.json`, `{components_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.components.json` and `{read_by_eye_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.read-by-eye.json`, and run `rm -f "{extraction_inventory}" "{detected_json}" "{extraction_json}" "{co_imports_json}" "{components_json}" "{read_by_eye_json}" "{project-root}/_bmad-output/.skf-stage/{skill-name}.language-guide.json"`: the run record below, §4 (or step 3d), §4c, §5 and step 3c write this run's, so §5 never seeds from an earlier run's runner JSON, counts or components and step 5 never reads an earlier run's Language Guide.

**If `source_type: "docs-only"`:** skip the rest of §2a but **Record the run** below, with every source field `null` and `version` the brief's `target_version`, else its `version`: there is no source to resolve. Then proceed directly to §2c (component library delegation, which is itself skipped for docs-only) and then §3 (Check for Docs-Only Mode). Tag resolution, reading the source into a tree, source-commit capture, version reconciliation, and deferred CCC discovery all require a source tree and have nothing to do in docs-only mode.

Load `{sourceResolutionData}` completely. It says which brief field picks the ref and how to choose between several matching tags, and it holds the tag warnings, the Local Source Warning, Source Commit Capture and Version Reconciliation.

**Local source, or a Quick-tier remote source:** nothing to resolve. Apply the Local Source Warning to a local path. A Quick-tier remote source is read through `gh_bridge` in §4, and its `source_ref` is `HEAD`.

**Remote source at Forge, Forge+ or Deep tier:** load `{remoteSourceAccessData}` and follow its **Read the Source Into a Private Tree** section: it reads the source into the private tree `{source_tree}` names, which step 7 and every HALT after this close, and binds `{source_root}`, `{resolved-source-path}` and `{remote_clone_path}`.

Then run Source Commit Capture and Version Reconciliation from `{sourceResolutionData}` on `{source_root}`.

**Record the run** in the extraction inventory, so steps 5 and 8 read this run's source and run folder from disk, not from what context still holds: resolve `{extractionInventoryHelper}` ← first existing path in `{extractionInventoryProbeOrder}` (halt as §5 does when neither exists) and, from `{project-root}`, create the folder the inventory sits in (on a project's first run nothing has created it, and the helper creates none), start the inventory with `init`, then set its `run`. Pass the `--mode` §3 or §5 passes (`docs-only` for a docs-only brief, `component-library` for a component library, else `source`). Fill each `<...>` from the bindings above: `source_ref`, `source_commit`, `tag_resolution` (the object `resolve` printed, unquoted, in place of the `null`), `{source_tree}`, `{resolved-source-path}` and `version`, the working version Version Reconciliation set; write `null`, unquoted, for one that is null or unavailable. §3's and §5's `init` keep this `run` when they start the inventory again. When a call fails twice, halt as §5 says.

```bash
mkdir -p "{project-root}/_bmad-output/.skf-stage"
uv run {extractionInventoryHelper} init --inventory "{extraction_inventory}" --skill "{name}" --mode {source|docs-only|component-library} --tier "{tier}"
uv run {extractionInventoryHelper} set --inventory "{extraction_inventory}" <<'SKF_INVENTORY'
{"run": {"run_dir": "{run_dir}", "source_ref": "<source_ref>", "source_commit": "<source_commit>", "tag_resolution": null, "source_tree": "<source_tree>", "resolved_source_path": "<resolved-source-path>", "version": "<version>"}}
SKF_INVENTORY
```

**Deferred CCC Discovery:** for a remote source at Forge+ or Deep tier, follow the **Deferred CCC Discovery** section of `{remoteSourceAccessData}` (load the file again when it has left context): once the run is recorded, it indexes SKF's workspace clone and searches it.

**CCC Discovery Integration (Forge+ and Deep with ccc only):**

If `{ccc_discovery}` is in context and non-empty (populated by step 2b or deferred discovery above), §4 and §4b read the files they read one at a time in its order, as the CCC Pre-Ranking Strategy in `{extractionPatternsData}` says. Display: "**CCC discovery: {N} files ranked by semantic relevance.** Files read one at a time follow this order."

If `{ccc_discovery}` is empty or not in context: proceed with existing file ordering (no change to current behavior).

### 2b. Discovered Authoritative Files Protocol

**Runs after §2a, not before it.** The scan walks a local tree, so it waits for §2a to resolve one: `{source_root}` now names the local source itself, or the private tree §2a read a remote source into, which no other run can move.

**Start clean:** set `authoritative_files_scan` to null and `promoted_docs[]` to empty before either skip below, so that in a `--batch` run one brief's scan never carries into the next.

**Skip this section entirely if `source_type: "docs-only"`:** there is no source tree to scan.

**Remote source guard:** if `source_root` is still a remote URL after §2a, there is no local tree to walk, and the helper refuses a source root that is not a directory. That happens for a Quick-tier remote source, which §2a never clones, and for a remote source §2a could not read into a tree, which it falls back to reading like Quick tier. Skip the scan and continue to §2c: record `authoritative_files_scan: {not_scanned: "remote source not cloned"}` for the evidence report and display "**Authoritative files scan skipped:** `{source_repo}` was not cloned in this run, so authoritative AI documentation files (`llms.txt`, `AGENTS.md` and the like) outside the brief's scope were not looked for. A run with a local tree (a local checkout, or a remote source cloned at Forge tier or higher) scans them."

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

It writes `extraction_mode: "docs-only"` with no export and no `top_exports`, keeping the `run` §2a recorded: steps 3b and 4 skip their per-export work on it, and step 3c merges its T3 items into it. When it fails twice, halt as §5 says. Auto-proceed through Gate 2 (section 6): display the empty inventory and note that the doc-fetcher step produces the T3 content.

**If `source_type: "source"` (default):** Continue with extraction below.

### 4. Execute Tier-Dependent Extraction

Source resolution, version reconciliation, and CCC discovery were completed in section 2a. Run the Strategy for the current tier from `{extractionPatternsData}` (loaded in §1): source reading at Quick tier (and for a remote source §2a could not read into a tree), and at Forge, Forge+ and Deep the **AST Extraction Protocol** there, whose recipe runner reads `{source_root}` itself. A branch that extracts without the runner (source reading, or the protocol's fallback) reads the §2 filtered file list: build it first, from `{source_root}`, when §2 did not. Label each export by the tool that produced it, as that file's Confidence sections say.

**The recipe runner (Forge, Forge+ and Deep):** resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}`; it writes `{extraction_json}` (bound in §2a, beside the staging folder step 5 creates, never inside the skill). From `{project-root}`, create that folder (the runner creates no folder) and remove the JSON an earlier run left there, then call the runner with the longest timeout your shell tool takes, since a large tree takes minutes:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-stage"
rm -f "{extraction_json}"
uv run {extractPublicApiHelper} --mode full \
    --source-root "{source_root}" \
    --brief "{brief_path}" \
    --tier "{tier}" \
    -o "{extraction_json}"
```

`{brief_path}` is the `skill-brief.yaml` step 1 loaded: the runner takes its `scope.include`, `scope.exclude`, `scope.tier_a_include`, `scope.type` and `language` from it, and the head cap from `--tier`. A JSON at `{extraction_json}` after the call is this call's: read it, in parts when it is large, and act on its `status` and fields as the protocol's **Recipe Runner** section says, never on the exit code. Each export it returns is T1 as it stands, its `source_line`, `citation`, `ast_recipe`, `ast_node_type`, `signature`, `params` and `return_type` included: read a signature from the source, at its `source_line`, only for a function whose `params` is null, and read by eye (T1-low) only what the runner leaves. When no path resolves, or a case the protocol's **When the Runner Cannot Run** lists applies, such as no JSON at `{extraction_json}` after the call or an empty `scope.languages` (no recipe reads the brief's language), follow that section. When that section warns that the runner failed (no JSON, and a stderr line that holds `error:`), send the warning with §5's `add --field warnings` for §6 and the evidence report.

**When `truncated` is true,** a recipe matched more exports than its head cap keeps, and the matches past the cap are missing: a public name among them comes back as an extraction gap (§4b), read by eye, and the others are left out. Warn, and keep the warning for §6 and the evidence report: "**Extraction hit the head cap:** {each `recipes[]` id whose `truncated` is true} matched more than {head_cap} exports, so some exports were read by eye or left out. Narrow `scope.include` in the brief until no recipe reaches the cap."

**Co-import counts (Forge tier and above, AST tools or not):** resolve `{scanManifestsHelper}`, `{countImportsHelper}` and `{pairIntersectHelper}` ← first existing path in `{scanManifestsProbeOrder}`, `{countImportsProbeOrder}` and `{pairIntersectProbeOrder}`. From `{project-root}`, count the files of `{source_root}` that import each runtime dependency its manifests declare, matched on module boundaries (`react-dom` is not `react`), with one `--exclude` for each glob of the brief's `scope.exclude` (none when it lists none), so the files the brief leaves out, such as an `examples/` app, are not counted:

```bash
uv run {scanManifestsHelper} scan "{source_root}" | uv run {countImportsHelper} count "{source_root}" --deps - --threshold 2 [--exclude "<glob>"]... > "{co_imports_json}"
```

Each `dependencies[]` entry of `{co_imports_json}` has its `file_count`, its `files` (each with the line that imports it) and `above_threshold` (2 or more files), which §5's `co_imports` reads. When the files that import two of them together would help an integration point suggestion, `uv run {pairIntersectHelper} intersect --counts "{co_imports_json}" --only "{a},{b}"` lists them. When `{scanManifestsHelper}` or `{countImportsHelper}` does not resolve, or the call exits non-zero (a `{source_root}` that is no local folder included), run `rm -f "{co_imports_json}"`, warn "Co-imports were not counted: {the first stderr line, or '`{the missing script}` is missing; re-install SKF'}." and send the warning with §5's `add --field warnings`: never count imports by hand.

**If AST tools are unavailable at Forge, Forge+ or Deep tier** (no ast-grep can run the recipes: see `{tierDegradationRulesData}` for full rules):

⚠️ **Warn the user explicitly:** "AST tools are unavailable, so extraction will use source reading (T1-low). Run [SF] Setup Forge to detect and configure AST tools for T1 confidence."

Degrade to Quick tier extraction. Note the degradation reason in context for the evidence report.

**For each file, handle failures gracefully:**

- If a file cannot be read: log warning, skip file, continue with remaining files
- If AST parsing fails on a file (the runner lists each one in `file_issues`): fall back to source reading for that file, continue
- If an ast-grep call fails or times out: when the protocol's second run is still incomplete, read by eye each file an `errors[]` item lists in `unread`, continue

**Re-export tracing (Forge tier and above):** the runner follows each entry point's re-exports to the file that defines each name. Follow the **Re-Export Tracing** protocol in `{extractionPatternsTracingData}` for what it could not follow: each `entry_points.unresolved` chain, and each `entry_point_diff.extraction_gaps` name with no `file`. Without the runner, check for unresolved public exports from entry points (`__init__.py`, `index.ts`, `lib.rs`) and follow the same protocol to resolve them to their definition files.

### 4b. Validate Exports Against Package Entry Point

After extraction, validate the collected exports against the package's actual public API surface.

**When the recipe runner extracted (§4: its JSON's `status` is `ok` or `incomplete`, and `scope.languages` is not empty),** its `entry_point_diff` is this check: do not read the entry points or diff the sets yourself. It read each package's entry points, traced each re-exported name to the file that defines it, and diffed those names with the recipe matches (`skf-extract-public-api.py --help` lists the entry points it reads):

- `public`: the package's public names, which `metadata.json`'s `exports[]` lists. In a language with no entry point, or only empty ones (`entry_points.by_language`), every export the recipes found is public.
- `other_definitions`: each other in-scope definition of a public name, at its `file` and `line`, such as a name two packages of a monorepo each define (its `public` row keeps one of them). No `extraction_gaps` or `outside_scope` row reads it, and `exports_public_api` never counts it; `effective_denominator` counts its name when its file is counted.
- `internal`: exports the recipes found that no entry point exports or makes reachable. §5's `init` marks each `internal: true` in the inventory, and step 5 keeps them out of `metadata.json`'s `exports[]`.
- `extraction_gaps`: names an entry point exports that no recipe found: read each by eye at its `file` and `line` (T1-low), or trace it (§4) when it has no `file`.
- `outside_scope`: names an entry point exports that are defined in files outside the brief's scope. Display each of the runner's `warnings` (one names each `package.json` `exports` subpath whose entry point is outside the files in scope) and list these names with them: widen `scope.include` before extraction, or this surface stays undocumented while `exports_public_api` still counts it, so `public_api_coverage` drops (only `effective_denominator`, for the curated-subset shapes, leaves it out).

**A `public-api` scope documents only the public surface.** Under the brief's `scope.type: public-api`, §5's `init` also marks each export of a language family whose `entry_points.by_language` status is `barrel` `public: true` or `public: false` by this diff, as update-skill's `records` marks an update's exports (`skf-extraction-inventory.py --help` gives the rule): an export is public when `public`, `other_definitions` or `extraction_gaps` names it at its file (by its own name or the `local` one), or when a `public` name with no `file` is its name. A `namespace` item (a submodule the package exports, or `export * as ns`) with a `members` list stands for its members, the names its module passes on, which users call as `pkg.sub.name`: each member is public at its file (by its name or its `local` one), and the module itself is not. Step 5 leaves each export marked `public: false` out of SKILL.md, `references/`, `metadata.json`'s `exports[]` and the provenance map, and one warning of the inventory names them, each with its file (the first ten, then how many more). An export §5's `add` sends later is marked by the same rule. When the diff cannot be read (no `entry_point_diff`, an incomplete run, one with `errors`, or a non-empty `entry_points.unresolved`), nothing is marked and every export is documented, with a warning that says why. Any other scope type, and a family with no barrel, marks nothing.

§5's `init` records its `counts` (`exports_public_api`, `exports_internal`, `effective_denominator` and `effective_denominator_basis`) and `arms` for step 5 §4. Files you read by eye because no recipe reads their language (`files_without_recipes_list`) are outside this diff and these counts: count their entry points' names by steps 2 to 4 of `{entryPointsByHandData}`, with `--extraction "{extraction_json}"` (its names join them, each once), and send the `counts` its call writes with §5's `set`.

**Otherwise** (Quick tier, extraction by source reading, a brief whose language no recipe reads included, or the protocol's fallback), find the entry points' public names and count them by steps 2 to 4 of `{entryPointsByHandData}`, and send the `counts` and `arms` its call writes with §5's `set`.

### 4c. Detect and Inventory Scripts/Assets

The brief's `scripts_intent` and `assets_intent` are each `"detect"` (also when absent), `"none"` or free text describing the files wanted. The detector takes only `detect` or `none`: pass `none` for `"none"`, else `detect`. Resolve `{detectScriptsAssetsHelper}` ← first existing path in `{detectScriptsAssetsProbeOrder}`; if neither exists, **HARD HALT** (exit code 3, `helper-missing`, phase `extract`): "Cannot detect scripts and assets: skf-detect-scripts-assets.py is missing. Re-install SKF, then re-run create-skill." The detector implements the heuristics of `{extractionPatternsTracingData}`, and `--brief` keeps it to the files the brief's `scope.include` and `scope.exclude` take, by the scope test update-skill uses for the same files. From `{project-root}`, write its JSON to `{detected_json}` (bound in §2a), which §5's `init` reads:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-stage"
uv run {detectScriptsAssetsHelper} detect "{source_root}" \
    --scripts-intent {detect|none} \
    --assets-intent {detect|none} \
    --brief "{brief_path}" \
    [--max-lines 500] > "{detected_json}"
```

It writes `scripts_inventory[]` and `assets_inventory[]` (each entry with `name`, `source_file`, `purpose`, `content_hash`, `confidence`, `lines` and `size_flag`), `scripts_skipped`, `assets_skipped` and `stats`.

**If it exits non-zero** (a `{source_root}` that is no local folder, as for a remote source read by eye, or a brief it cannot read): warn "Scripts and assets were not detected: {the first stderr line}", send the warning with §5's `add --field warnings` for §6 and the evidence report, and run §5's `init` without `--detected`: the inventories stay empty.

**Otherwise** §5's `init` takes every entry, unchanged and already `T1-low` with its `content_hash`, which is the inventory for a `"detect"` intent. For a free-text intent, choose the entries that match it and, after `init`, send them with §5's `set` as `{"intent_mapping": {"scripts": {"intent": "<the text>", "kept": [source_file, ...]}}}`, `"assets"` the same way: the helper keeps only those entries and records the others as the mapping's `left_out`, which §6 lists and step 5 writes into the evidence report. §6 surfaces each `size_flag: "oversized"` entry before bundling.

### 5. Build Extraction Inventory

`{extraction_inventory}` (bound in §2a, beside the staging folder, never inside the skill) is the run's extraction record: steps 3b to 7 read it, and steps 3c and 4 add to it, instead of a copy held in context. `{extractionInventoryHelper}` writes it, each call atomically: the runner's and the detector's records go in as those tools wrote them, and you send only what you produced. Resolve `{extractionInventoryHelper}` ← first existing path in `{extractionInventoryProbeOrder}`; if neither exists, **HARD HALT** (exit code 3, `helper-missing`, phase `extract`): "Cannot write the extraction inventory: skf-extraction-inventory.py is missing. Re-install SKF, then re-run create-skill." Run each call below from `{project-root}`.

**Start the inventory** with `init`, which replaces any file at `{extraction_inventory}`, keeping only the `run` §2a recorded there:

```bash
uv run {extractionInventoryHelper} init --inventory "{extraction_inventory}" --skill "{name}" --mode {source|component-library} --tier "{tier}" [--extraction "{extraction_json}"] [--detected "{detected_json}"]
```

Pass `--mode component-library` for a component library (§2c), else `source`. Pass `--extraction` when §4's runner, or step 3d's Phase 4 for a component library, left a JSON at `{extraction_json}`, and `--detected` when §4c's detector exited 0. From the runner's JSON, `init` writes each export as the runner recorded it (T1, `ast-grep`, with its `source_file`, `source_line`, `citation`, `ast_recipe`, `ast_node_type` and `export_type`), marked `internal: true` when §4b's `internal` lists it and, under a `public-api` scope, `public: true` or `public: false` by §4b's public surface; `files_scanned` (the runner's `files_in_scope`); its `aggregates`, `counts` and `arms`; `extraction_rules` (its `recipe_set`, the `recipes` ids, its `scope` and `ast_grep.version`), from which step 7 writes `extraction-rules.yaml`; and the runner warnings in `warnings`, one line each: the head-cap warning (§4), each `errors[]` item, each `file_issues[]` file, each extension `files_without_recipes` counts, and each of its `warnings`. From the detector's JSON it writes `scripts_inventory` and `assets_inventory`.

**Then send what you produced**, each call with its JSON payload on stdin, leaving out a call with nothing to send:

- **Signatures** (`patch`): for each function export whose `params` the runner left null (and each Props interface of a component library), the full signature, the parameters (each as `{"name", "type", "default", "optional"}`, as the runner records them) and the return type you read from the source at its `source_line`. It sets only those three fields, matches each entry on `export_name` and `source_file`, and lists in `unmatched` and `ambiguous` the entries it could not place: correct those and send them again. An export marked `public: false` needs no signature: it is not documented.
- **Exports read by eye** (`add --field exports`): each export §4 or §4b read by eye (an extraction gap, a `file_issues` file, a file an `errors[]` item lists in `unread`, a language no recipe reads, or every export when the runner did not run), with its `export_name`, `export_type`, `signature`, `params`, `return_type`, `source_file` (relative to `{source_root}`, with `/` separators, as the runner writes its files, so §4b's public surface can match it), `source_line` and `[SRC:...]` citation. The helper marks it `public` by §4b's public surface, as `init` marks the runner's, and labels it T1-low (`source-read`, with `ast_node_type` and `ast_recipe` null) unless the entry carries its own labels, as a `find_code` match of the protocol's fallback does (T1, `ast-grep`, the `kind` its recipe or pattern declares, and the pattern as its `ast_recipe`). A component library (§2c) sends here only the exports step 3d read by eye (Quick tier, a `file_issues` file, a file an `errors[]` item lists in `unread`, or the runner's fallback), with the `< "{read_by_eye_json}"` call below when step 3d wrote that file; it sends each Props interface's fields with `patch` as `params`, and its `component_catalog` and `component_stats` with the `< "{components_json}"` call below when step 3d wrote that file.
- **Warnings you raise** (`add --field warnings`): a list of strings, such as a degradation reason (§2a, §4), the runner's failure (§4), the detector's failure (§4c) or a file you could not read.
- **The rest** (`set`), in one JSON object: `top_exports`, the 10 to 20 public API function names by prominence (import frequency or documentation position), none marked `public: false`, which step 3b's targeted temporal fetch reads; `co_imports` (Forge tier and above), from `{co_imports_json}` when §4 left it, else `[]`: one `{"name", "file_count", "integration"}` per `dependencies[]` entry whose `above_threshold` is true, in the file's order, with `name` and `file_count` as written there and `integration` your one-line integration point suggestion, null when its files show none; `promoted_docs` and `authoritative_files_scan`, §2b's records; `intent_mapping` for a free-text intent (§4c); and, when the runner did not run, `files_scanned` (§2's filtered file count) and the `counts` and `arms` §4b recorded. `counts` and `arms` merge into what is there, so after the runner send only a count you changed.

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

A component library's two file-fed calls, each run before `summary` when step 3d wrote its file:

```bash
uv run {extractionInventoryHelper} add --inventory "{extraction_inventory}" --field exports < "{read_by_eye_json}"
uv run {extractionInventoryHelper} set --inventory "{extraction_inventory}" < "{components_json}"
```

A call that exits non-zero changes nothing: fix what its `message` names and run it again. An entry the inventory already holds is not added twice (`duplicates`), so a call run again is safe. When a call fails twice, **HARD HALT** (exit code 4, `write-failed`, phase `extract`), with `"path": "{extraction_inventory}"`: "Cannot write the extraction inventory `{extraction_inventory}`: {the helper's message}. Check permissions and disk space."

The summary's `counts` give §6 its numbers: `files_scanned`, `exports`, `not_public` (the exports marked `public: false`), `by_type`, `t1`, `t1_low`, `co_imports`, `scripts` and `assets`.

### 6. Present Extraction Summary (Gate 2)

**Docs-only note:** for `extraction_mode: "docs-only"`, display "Docs-only mode: extraction inventory is empty. Documentation content will be fetched from `doc_urls` in step 3c. Auto-proceeding." and auto-proceed past this gate.

**Zero-export sanity check (source mode):** If `extraction_mode != "docs-only"` AND the §5 summary counts no export the provenance map will hold (its `exports` is 0, or equals its `not_public`) AND the brief declares no `doc_urls` (step 3c applies this check to a brief whose every `doc_urls` fetch failed), the empty extraction is almost always an error, not a valid empty surface. Surface a distinct warning at the gate:

"**⚠️ Zero public exports extracted.** A source-type brief produced no documented surface and declares no `doc_urls`. This usually means a scope/branch/tag mismatch (wrong `target_version`, over-narrow `scope.include`) or a failed AST run: the compiled skill would document nothing. Verify the brief's source ref and scope before continuing. For a `public-api` brief, every export found may instead be off the public surface: the `Off the public surface` warning names them.

**[C] Continue anyway**: compile an empty surface (default)
**[R] Refine the brief**: stop here"

Under `{headless_mode}`, do not auto-pass silently: log `"headless: zero public exports extracted, likely a scope, branch or tag mismatch; continuing"`, stage `{"step": "extract", "gate": "zero-exports", "decision": "C", "rationale": "headless mode: zero exports, no human to confirm scope or ref"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"` (the Workflow Rules' record), and proceed. Step 8 reports a run whose sink holds this decision as `status: "partial"` with `summary.warning: "zero-exports"`, so a run that looks green but is not reaches a person or a pipeline.

Display the extraction findings for user confirmation, the numbers from the §5 summary's `counts` and the lists from `{extraction_inventory}`:

"**Extraction complete.**

**Files scanned:** {files_scanned}
**Exports found:** {exports} ({by_type, each as its count and `export_type`}){if not_public > 0: , {not_public} of them off the public surface and left out}
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

Otherwise halt after the §6 summary and wait for the user to continue (they may ask about the results first). When §6 showed the zero-export or the head-cap warning, also offer **[R] Refine the brief**: stop here. **GATE [default: continue]**: under `{headless_mode}`, auto-proceed, log "headless: auto-approve extraction summary", stage `{"step": "extract", "gate": "review-gate", "decision": "continue", "rationale": "headless mode: no person to review the extraction summary"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"` (the Workflow Rules' record). On continue, load `{nextStepFile}`, read it fully, then execute it.

**On [R]:** **HARD HALT** (exit code 6, `halted-for-brief-refinement`, phase `extract`): "**Halting create-skill:** {the warning that prompted the stop, one line}. Fix `scope.include` or `target_version` in the brief (or re-run `skf-brief-skill`), then re-run `skf-create-skill`."

