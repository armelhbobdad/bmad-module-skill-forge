---
nextStepFile: 'sub/fetch-temporal.md'
componentExtractionStepFile: 'component-extraction.md'
extractionPatternsData: 'references/extraction-patterns.md'
extractionPatternsTracingData: 'references/extraction-patterns-tracing.md'
tierDegradationRulesData: 'references/tier-degradation-rules.md'
sourceResolutionData: 'references/source-resolution-protocols.md'
authoritativeFilesProtocol: 'references/authoritative-files-protocol.md'
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
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Extract

## STEP GOAL:

To extract all public exports, function signatures, type definitions, and co-import patterns from the source code using tier-appropriate tools, building a complete extraction inventory with confidence-tiered provenance citations.

## Rules

- Focus only on extracting exports, signatures, types from source code — do not compile SKILL.md
- Do not write any output files — extraction stays in context
- Every extracted item must have a provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`

## MANDATORY SEQUENCE

### 1. Load Extraction Patterns

Load `{extractionPatternsData}` completely. Identify the strategy for the current forge tier.

### 2. Apply Scope Filters

From the brief, apply scope and pattern filters:

- `scope.type` — determines what to extract (e.g., `full-library`, `specific-modules`, `public-api`, `component-library`, `reference-app`, `docs-only`). Use `reference-app` when the source is a whole app and the skill's value is wiring patterns rather than public exports (embedded-sidecar reference apps, CLI-demo repos, integration-pattern demonstrators). `reference-app` triggers the compile-assembly overrides in `{compileAssemblyRules}` that replace "Key API Summary" with a "Pattern Surface" section and make `stats.exports_documented` semantics pattern-oriented. Do NOT pick `full-library` for reference apps — downstream assembly will remap wiring onto export slots, producing fuzzy counts and an awkward SKILL.md.
- `scope.include` — file globs to include
- `scope.exclude` — file globs to exclude

Build the filtered file list from the source tree resolved in step 1. Record the result: "**Filtered file count: {N} files in scope**" — this count is the input to the AST Extraction Protocol decision tree in the extraction patterns data file.

### 2a. Discovered Authoritative Files Protocol

**Skip this section entirely if `source_type: "docs-only"`** — there is no source tree to scan.

Load `{authoritativeFilesProtocol}` and execute it. The full protocol (heuristic scan list, helper invocation, classification dispatch, prompt flow, P/S/U decision-apply, summary, provenance-map handoff, downstream consumption) lives there. This stub exists so the inline `### 2a` heading stays present in `extract.md`'s table of contents while keeping the body lean.

Briefly: scan the source tree for authoritative AI documentation files (`llms.txt`, `AGENTS.md`, `.cursorrules`, etc.) that the brief's scope filters may have excluded. The `{resolveAuthoritativeFilesHelper}` helper does the deterministic work (walk, scope diff, amendment reconcile, preview load, hashing); the LLM applies the resulting `unresolved[]` prompt loop. Promoted decisions are persisted to the brief immediately so re-runs replay deterministically.

### 2b. Resolve Source Access

**If `source_type: "docs-only"`:** skip §2b entirely — there is no source to resolve. Proceed directly to §2c (component library delegation, which is itself skipped for docs-only) and then §3 (Check for Docs-Only Mode). Tag resolution, remote/workspace cloning, source-commit capture, version reconciliation, and deferred CCC discovery all require a source tree and have nothing to do in docs-only mode.

Load `{sourceResolutionData}` completely. Follow these protocols in order:
1. **Tag Resolution** — run the explicit variant when `brief.target_version` is set, or the implicit variant when only `brief.version` is set (Forge/Deep remote sources only). This sets `source_ref` before any clone happens. Quick tier remote sources skip this.
2. **Remote Source Resolution** — workspace or ephemeral clone, cleanup (Forge/Deep tiers).
3. **Source Commit Capture** — all tiers.
4. **Version Reconciliation** — all tiers.

This ensures source code is accessible regardless of which extraction path is taken below (standard, component-library, or docs-only).

**Deferred CCC Discovery (Forge+ and Deep — remote sources only):**

If ALL of these conditions are true:
- `tools.ccc` is true in forge-tier.yaml
- `{ccc_discovery}` is empty (step 2b deferred because source was remote)
- `remote_clone_path` is set (source resolution succeeded for a remote URL)
- Tier is Forge+ or Deep

Then run CCC indexing and discovery on the resolved clone (workspace or ephemeral):

1. **Check existing index:** If `{remote_clone_path}/.cocoindex_code/` already exists (workspace repo with a persisted CCC index), skip steps 2-3 and proceed directly to step 4 using `ccc search --refresh` instead of plain `ccc search`. The `--refresh` flag tells CCC to re-index if files have changed since the last index, then search. This is the fast path for workspace repos that have been indexed before. **Note:** If `--refresh` is not supported by the installed ccc version, omit the flag — ccc will use the existing index.

2. **Initialize index (first time only):** Run `cd {remote_clone_path} && ccc init`. If init exits non-zero with `A parent directory has a project marker` — the common case when the clone is nested under a ccc-indexed project (e.g. a `.forge-sources/` checkout inside this repo) — re-run as `cd {remote_clone_path} && ccc init -f` to initialize at the subtree anyway (same handling as step 7 §6b). If init fails for any other reason, or the `-f` retry also fails, set `{ccc_discovery: []}` and continue — this is not an error.

   **Apply standard exclusions:** After `ccc init`, apply generic build/dependency exclusions to `{remote_clone_path}/.cocoindex_code/settings.yml`. These are standard artifact patterns, NOT SKF-specific paths (the workspace checkout is a source repo, not an SKF project):

   ```
   node_modules/, dist/, build/, .git/, vendor/, __pycache__/, .cache/, .next/, .nuxt/, target/, out/, .venv/, .tox/
   ```

   Read `settings.yml`, append any patterns not already present to the `exclude_patterns` array, write back. **Reuse check:** if an existing `.cocoindex_code/settings.yml` was already present (workspace hit), read its `exclude_patterns` first and diff against the standard-exclusion list above. If ANY standard entry is missing from the existing list, append only the missing entries (preserving any user-added patterns) AND force a re-index by running `ccc index --force` (or the equivalent rebuild flag). If every standard entry is already present, skip the write and skip the forced re-index — the existing index is valid. Record `ccc_exclusions_augmented: {count}` in context for the evidence report.

   **Note:** Brief-specific `include_patterns` and `exclude_patterns` are NOT written to `settings.yml`. The CCC index is general-purpose — it indexes everything (minus standard artifacts). Brief-specific filtering happens at search result time, not index time. This allows a single workspace CCC index to serve multiple briefs with different scope filters.

3. **Index the clone:** Run `cd {remote_clone_path} && ccc index` with an extended timeout or in background mode. Indexing can take several minutes on large codebases (1000+ files). Use `ccc status` to verify completion — check that `Chunks` and `Files` counts are non-zero. If indexing fails, set `{ccc_discovery: []}` and continue — this is not an error.

4. **Construct semantic query:** Build from brief data: `"{brief.name} {brief.scope}"`. Truncate to 80 characters — keep the full skill name and trim `brief.scope` from the end. If `brief.scope` is very short (< 10 chars), append terms from `brief.description` to fill the remaining space.

5. **Execute search:** Run `ccc_bridge.search(query, remote_clone_path, top_k=20)`:
   - **If existing index was found (step 1):** Use `cd {remote_clone_path} && ccc search --refresh --limit 20 "{query}"` — this re-indexes if files changed, then searches. If `--refresh` is not supported by the installed ccc version, omit the flag — ccc will use the existing index.
   - **Otherwise:** Use `cd {remote_clone_path} && ccc search --limit 20 "{query}"` after indexing in step 3.
   - **Tool resolution:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or CLI. Note: `ccc search` operates on the index in the current working directory. See `knowledge/tool-resolution.md`.

6. **Store results:** If search succeeds, store as `{ccc_discovery: [{file, score, snippet}]}`. Display: "**CCC semantic discovery: {N} relevant regions identified across {M} unique files.**"

   If `remote_clone_type == "workspace"` and an existing index was reused, append: "(reused workspace index)"

7. **On failure:** Set `{ccc_discovery: []}`. Display: "CCC discovery unavailable — proceeding with standard extraction." Do NOT halt.

**CCC Discovery Integration (Forge+ and Deep with ccc only):**

If `{ccc_discovery}` is in context and non-empty (populated by step 2b or deferred discovery above):
- Sort the filtered file list by CCC relevance score: files appearing in `{ccc_discovery}` results move to the front of the extraction queue, sorted by their relevance score descending
- Files NOT in CCC results remain in the queue after ranked files — they are not excluded, only deprioritized
- Display: "**CCC discovery: {N} files pre-ranked by semantic relevance** — extraction will prioritize these first."

If `{ccc_discovery}` is empty or not in context: proceed with existing file ordering (no change to current behavior).

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

Source resolution, version reconciliation, and CCC discovery were completed in section 2b. Proceed with the tier-specific extraction strategy below.

**Quick Tier (No AST tools):**

1. Use `gh_bridge.list_tree(owner, repo, branch)` to map source structure (if remote)
2. Identify entry points: index files, main exports, public modules
3. Use `gh_bridge.read_file(owner, repo, path)` to read each entry point
4. Extract from source text: exported function names, parameter lists, return types
5. Infer types from JSDoc, docstrings, type annotations
6. Confidence: All results T1-low — `[SRC:{file}:L{line}]`

**Tool resolution for gh_bridge:** Use `gh api repos/{owner}/{repo}/git/trees/{branch}?recursive=1` for list_tree, `gh api repos/{owner}/{repo}/contents/{path}` for read_file. If source is local, use direct file listing/reading instead. See `knowledge/tool-resolution.md`.

**Forge/Forge+/Deep Tier (AST available):**

⚠️ **CRITICAL:** Before executing AST extraction, load the **AST Extraction Protocol** section from `{extractionPatternsData}`. Follow the decision tree based on the file count from step 1's file tree. This determines whether to use the MCP tool, scoped YAML rules, or CLI streaming. Never use `ast-grep --json` (without `=stream`) — it loads the entire result set into memory and will fail on large codebases. Always use the explicit `run` subcommand with streaming: `ast-grep run -p '{pattern}' --json=stream`.

1. Detect language from brief or file extensions
2. Follow the AST Extraction Protocol decision tree from `{extractionPatternsData}`:
   - ≤100 files: use `find_code()` MCP tool with `max_results` and `output_format="text"`
   - ≤500 files: use `find_code_by_rule()` MCP tool with scoped YAML rules
   - >500 files: use CLI `--json=stream` with line-by-line streaming Python — **CRITICAL:** inject the brief's `scope.exclude` patterns into the Python filter's `EXCLUDES` list (use `[]` if absent) so excluded files are discarded before consuming `head -N` slots (see template in extraction patterns data)
3. For each export: extract function name, full signature, parameter types, return type, line number
4. Use `ast_bridge.detect_co_imports(path, libraries[])` to find integration points
5. Build extraction rules YAML data for reproducibility
6. Confidence: All results T1 — `[AST:{file}:L{line}]`

**Tool resolution for ast_bridge:** Use ast-grep MCP tools (`mcp__ast-grep__find_code`, `mcp__ast-grep__find_code_by_rule`) as specified in the AST Extraction Protocol above, or `ast-grep` CLI. For `detect_co_imports`, use `find_code_by_rule` with a co-import YAML rule scoped to the libraries list. See `knowledge/tool-resolution.md`.

**If AST tool is unavailable at Forge/Deep tier** (see `{tierDegradationRulesData}` for full rules):

⚠️ **Warn the user explicitly:** "AST tools are unavailable — extraction will use source reading (T1-low). Run [SF] Setup Forge to detect and configure AST tools for T1 confidence."

Degrade to Quick tier extraction. Note the degradation reason in context for the evidence report.

**For each file — handle failures gracefully:**

- If a file cannot be read: log warning, skip file, continue with remaining files
- If AST parsing fails on a file: fall back to source reading for that file, continue

**Re-export tracing (Forge/Deep only):** After the initial AST scan, check for unresolved public exports from entry points (`__init__.py`, `index.ts`, `lib.rs`). Follow the **Re-Export Tracing** protocol in `{extractionPatternsTracingData}` to resolve them to their definition files.

### 4b. Validate Exports Against Package Entry Point

After extraction, validate the collected exports against the package's actual public API surface:

- **Python:** Read `{source_root}/__init__.py` — extract imports to build the public export list. Compare against AST results:
  - In AST but not entry point → mark as internal (exclude from `metadata.json` exports)
  - In entry point but not AST → flag as extraction gap (trace via re-export protocol)
- **TypeScript/JS:** Read `index.ts`/`index.js` — same comparison logic.
- **Rust:** Read `lib.rs` — extract `pub use` items. Same logic. **Go:** Scan for exported (capitalized) identifiers.

**Multi-entry packages (`exports` map / declaration-file entry points).** A single per-language entry-point read misses public surface that a package ships through its `package.json` `exports` map — especially committed `.d.ts` / `.d.mts` declaration files that resolve **outside** the conventional source dir (e.g. a monorepo package whose `./macro` subpath maps to `macro/index.d.mts`, listed in `files[]` but not under `src/`). When the in-scope package declares an `exports` map:

- Resolve each `exports` subpath to its target file and treat that file — and any committed `.d.ts` / `.d.mts` declaration it resolves to — as an authoritative public entry point, reading it the same way as the primary barrel above even when it lives outside `src/`.
- If a resolved `exports` subpath target falls **outside** the brief's `scope.include` globs, surface a note: `"warn: public entry point {path} (exports subpath '{subpath}') resolves outside scope.include — widen scope.include before extraction, or this surface stays undocumented and excluded from the coverage denominator."` Widening `scope.include` here keeps the documented surface aligned with the `effective_denominator` that compile.md §4 derives from those same globs, without mid-run scope surgery.

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
- Confidence tier (T1 or T1-low)

**Aggregate counts:**
- Total files scanned
- Total exports found
- Exports by type (functions, types/interfaces, constants)
- Confidence breakdown (T1 count, T1-low count)
- `top_exports[]` — sorted list of the top 10-20 public API function names by prominence (import frequency or documentation position). This named field is consumed by step 3b for targeted temporal fetching and cache fingerprinting.

**Script/asset counts (when detected):**
- `scripts_found`: count of scripts detected
- `assets_found`: count of assets detected

**Co-import patterns (Forge/Deep only):**
- Libraries commonly imported alongside extracted exports
- Integration point suggestions

### 6. Present Extraction Summary (Gate 2)

**Docs-only note:** If `docs_only_mode` is active (`extraction_mode: "docs-only"`), display a brief note explaining that T3 content will be added by the doc-fetcher step (step 3c), then auto-proceed past this gate. Example: "Docs-only mode: extraction inventory is empty. Documentation content will be fetched from `doc_urls` in step 3c. Auto-proceeding."

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

{warnings if any files skipped or degraded}

Review the extraction summary above. Select an option to continue."

### 7. Present MENU OPTIONS

Display: "**Extraction Summary — Select an Option:** [C] Continue to compilation"

#### EXECUTION RULES:

- IF docs-only mode (`extraction_mode: "docs-only"`): Auto-proceed immediately to `{nextStepFile}` — no user interaction required
- OTHERWISE: ALWAYS halt and wait for user input after presenting the extraction summary
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-approve extraction summary"
- This is Gate 2 — user must confirm before compilation proceeds (except docs-only mode)
- User may ask questions about the extraction results before continuing

#### Menu Handling Logic:

- IF C: Confirm extraction inventory is complete. Immediately load, read entire file, then execute `{nextStepFile}`
- IF Any other comments or queries: answer questions about the extraction results, then redisplay the menu

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the extraction inventory is built with provenance citations and the user has confirmed the extraction summary will you proceed to load `{nextStepFile}` for temporal context fetching.

