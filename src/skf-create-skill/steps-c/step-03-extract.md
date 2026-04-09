---
nextStepFile: './step-03b-fetch-temporal.md'
componentExtractionStepFile: './step-03d-component-extraction.md'
extractionPatternsData: 'references/extraction-patterns.md'
extractionPatternsTracingData: 'references/extraction-patterns-tracing.md'
tierDegradationRulesData: 'references/tier-degradation-rules.md'
sourceResolutionData: 'references/source-resolution-protocols.md'
---

# Step 3: Extract

## STEP GOAL:

To extract all public exports, function signatures, type definitions, and co-import patterns from the source code using tier-appropriate tools, building a complete extraction inventory with confidence-tiered provenance citations.

## Rules

- Focus only on extracting exports, signatures, types from source code — do not compile SKILL.md
- Do not write any output files — extraction stays in context
- Every extracted item must have a provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Extraction Patterns

Load `{extractionPatternsData}` completely. Identify the strategy for the current forge tier.

### 2. Apply Scope Filters

From the brief, apply scope and pattern filters:

- `scope` — determines what to extract (e.g., "all public exports", specific modules)
- `include_patterns` — file globs to include (if specified)
- `exclude_patterns` — file globs to exclude (if specified)

Build the filtered file list from the source tree resolved in step-01. Record the result: "**Filtered file count: {N} files in scope**" — this count is the input to the AST Extraction Protocol decision tree in the extraction patterns data file.

### 2a. Resolve Source Access

Load `{sourceResolutionData}` completely. Follow the **Remote Source Resolution** protocol for Forge/Deep tiers (workspace or ephemeral clone, cleanup), the **Source Commit Capture** protocol for all tiers, and the **Version Reconciliation** protocol for all tiers. This ensures source code is accessible regardless of which extraction path is taken below (standard, component-library, or docs-only).

**Deferred CCC Discovery (Forge+ and Deep — remote sources only):**

If ALL of these conditions are true:
- `tools.ccc` is true in forge-tier.yaml
- `{ccc_discovery}` is empty (step-02b deferred because source was remote)
- `remote_clone_path` is set (source resolution succeeded for a remote URL)
- Tier is Forge+ or Deep

Then run CCC indexing and discovery on the resolved clone (workspace or ephemeral):

1. **Check existing index:** If `{remote_clone_path}/.cocoindex_code/` already exists (workspace repo with a persisted CCC index), skip steps 2-3 and proceed directly to step 4 using `ccc search --refresh` instead of plain `ccc search`. The `--refresh` flag tells CCC to re-index if files have changed since the last index, then search. This is the fast path for workspace repos that have been indexed before.

2. **Initialize index (first time only):** Run `cd {remote_clone_path} && ccc init`. If init fails, set `{ccc_discovery: []}` and continue — this is not an error.

   **Apply standard exclusions:** After `ccc init`, apply generic build/dependency exclusions to `{remote_clone_path}/.cocoindex_code/settings.yml`. These are standard artifact patterns, NOT SKF-specific paths (the workspace checkout is a source repo, not an SKF project):

   ```
   node_modules/, dist/, build/, .git/, vendor/, __pycache__/, .cache/, .next/, .nuxt/, target/, out/, .venv/, .tox/
   ```

   Read `settings.yml`, append any patterns not already present to the `exclude_patterns` array, write back.

   **Note:** Brief-specific `include_patterns` and `exclude_patterns` are NOT written to `settings.yml`. The CCC index is general-purpose — it indexes everything (minus standard artifacts). Brief-specific filtering happens at search result time, not index time. This allows a single workspace CCC index to serve multiple briefs with different scope filters.

3. **Index the clone:** Run `cd {remote_clone_path} && ccc index` with an extended timeout or in background mode. Indexing can take several minutes on large codebases (1000+ files). Use `ccc status` to verify completion — check that `Chunks` and `Files` counts are non-zero. If indexing fails, set `{ccc_discovery: []}` and continue — this is not an error.

4. **Construct semantic query:** Build from brief data: `"{brief.name} {brief.scope}"`. Truncate to 80 characters — keep the full skill name and trim `brief.scope` from the end. If `brief.scope` is very short (< 10 chars), append terms from `brief.description` to fill the remaining space.

5. **Execute search:** Run `ccc_bridge.search(query, remote_clone_path, top_k=20)`:
   - **If existing index was found (step 1):** Use `cd {remote_clone_path} && ccc search --refresh --limit 20 "{query}"` — this re-indexes if files changed, then searches.
   - **Otherwise:** Use `cd {remote_clone_path} && ccc search --limit 20 "{query}"` after indexing in step 3.
   - **Tool resolution:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or CLI. Note: `ccc search` operates on the index in the current working directory. See `knowledge/tool-resolution.md`.

6. **Store results:** If search succeeds, store as `{ccc_discovery: [{file, score, snippet}]}`. Display: "**CCC semantic discovery: {N} relevant regions identified across {M} unique files.**"

   If `remote_clone_type == "workspace"` and an existing index was reused, append: "(reused workspace index)"

7. **On failure:** Set `{ccc_discovery: []}`. Display: "CCC discovery unavailable — proceeding with standard extraction." Do NOT halt.

**CCC Discovery Integration (Forge+ and Deep with ccc only):**

If `{ccc_discovery}` is in context and non-empty (populated by step-02b or deferred discovery above):
- Sort the filtered file list by CCC relevance score: files appearing in `{ccc_discovery}` results move to the front of the extraction queue, sorted by their relevance score descending
- Files NOT in CCC results remain in the queue after ranked files — they are not excluded, only deprioritized
- Display: "**CCC discovery: {N} files pre-ranked by semantic relevance** — extraction will prioritize these first."

If `{ccc_discovery}` is empty or not in context: proceed with existing file ordering (no change to current behavior).

### 2b. Component Library Delegation

**If `scope.type: "component-library"` in the brief:**

"**Component library detected.** Delegating to specialized extraction strategy for registry-first, props-focused extraction."

Load and execute `{componentExtractionStepFile}` completely. When that step completes, it returns control here. Resume at section 5 (Build Extraction Inventory) with the enriched extraction data and `component_catalog[]` from the component extraction step.

**Otherwise:** Continue with standard extraction below.

### 3. Check for Docs-Only Mode

**If `source_type: "docs-only"` in the brief data:**

"**Docs-only mode:** No source code to extract. Documentation content will be fetched from `doc_urls` in step-03c."

Build an empty extraction inventory with zero exports. Set `extraction_mode: "docs-only"` in context. Auto-proceed through Gate 2 (section 6) — display the empty inventory and note that T3 content will be produced by the doc-fetcher step.

**If `source_type: "source"` (default):** Continue with extraction below.

### 4. Execute Tier-Dependent Extraction

Source resolution, version reconciliation, and CCC discovery were completed in section 2a. Proceed with the tier-specific extraction strategy below.

**Quick Tier (No AST tools):**

1. Use `gh_bridge.list_tree(owner, repo, branch)` to map source structure (if remote)
2. Identify entry points: index files, main exports, public modules
3. Use `gh_bridge.read_file(owner, repo, path)` to read each entry point
4. Extract from source text: exported function names, parameter lists, return types
5. Infer types from JSDoc, docstrings, type annotations
6. Confidence: All results T1-low — `[SRC:{file}:L{line}]`

**Tool resolution for gh_bridge:** Use `gh api repos/{owner}/{repo}/git/trees/{branch}?recursive=1` for list_tree, `gh api repos/{owner}/{repo}/contents/{path}` for read_file. If source is local, use direct file listing/reading instead. See `knowledge/tool-resolution.md`.

**Forge/Forge+/Deep Tier (AST available):**

⚠️ **CRITICAL:** Before executing AST extraction, load the **AST Extraction Protocol** section from `{extractionPatternsData}`. Follow the decision tree based on the file count from step-01's file tree. This determines whether to use the MCP tool, scoped YAML rules, or CLI streaming. Never use `ast-grep --json` (without `=stream`) — it loads the entire result set into memory and will fail on large codebases. Always use the explicit `run` subcommand with streaming: `ast-grep run -p '{pattern}' --json=stream`.

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

Use the entry point as the authoritative source for `metadata.json`'s `exports[]` array.

**If entry point is missing or unreadable:** Skip validation with a warning.

### 4c. Detect and Inventory Scripts/Assets

**Default resolution:** If `scripts_intent` is absent from the brief, treat as `"detect"` (auto-detection). If `assets_intent` is absent, treat as `"detect"`. Only an explicit `"none"` value disables detection.

**If `scripts_intent` is `"none"` AND `assets_intent` is `"none"`:** Skip this section entirely. **If only one is `"none"`:** Skip that category only, proceed with the other.

After export extraction, scan the source for scripts and assets using the detection patterns in `{extractionPatternsTracingData}`:

1. Scan source tree for directories/files matching detection heuristics (scripts/, bin/, tools/, cli/ for scripts; assets/, templates/, schemas/, configs/, examples/ for assets)
2. For each candidate: verify existence, check size (flag >500 lines), exclude binaries, compute SHA-256 hash
3. Extract purpose from header comments, shebang, README references, or schema fields. Record: file_path, purpose, source_path, language/type, content_hash, confidence (T1-low)

Add results to `scripts_inventory[]` and `assets_inventory[]` alongside the existing export inventory.

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
- `top_exports[]` — sorted list of the top 10-20 public API function names by prominence (import frequency or documentation position). This named field is consumed by step-03b for targeted temporal fetching and cache fingerprinting.

**Script/asset counts (when detected):**
- `scripts_found`: count of scripts detected
- `assets_found`: count of assets detected

**Co-import patterns (Forge/Deep only):**
- Libraries commonly imported alongside extracted exports
- Integration point suggestions

### 6. Present Extraction Summary (Gate 2)

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

