---
name: 'step-03-extract'
description: 'Tier-dependent source code extraction — AST or source reading for exports, signatures, and types'
nextStepFile: './step-03b-fetch-temporal.md'
componentExtractionStepFile: './step-03d-component-extraction.md'
extractionPatternsData: '../data/extraction-patterns.md'
extractionPatternsTracingData: '../data/extraction-patterns-tracing.md'
tierDegradationRulesData: '../data/tier-degradation-rules.md'
sourceResolutionData: '../data/source-resolution-protocols.md'
---

# Step 3: Extract

## STEP GOAL:

To extract all public exports, function signatures, type definitions, and co-import patterns from the source code using tier-appropriate tools, building a complete extraction inventory with confidence-tiered provenance citations.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine performing structural extraction
- ✅ Zero hallucination tolerance — every extracted item must trace to source code
- ✅ Confidence tier labeling is mandatory for every extraction result

### Step-Specific Rules:

- 🎯 Focus ONLY on extracting exports, signatures, types from source code
- 🚫 FORBIDDEN to compile SKILL.md content — that's step-05
- 🚫 FORBIDDEN to write any output files — extraction stays in context
- 🚫 FORBIDDEN to include content that cannot be cited to a source location
- ⚒️ Every extracted item MUST have a provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Build extraction inventory in context — do not write files
- 📖 Load extraction patterns data file for tier-specific strategy
- 🚫 If an export cannot be verified, exclude it — do not guess

## CONTEXT BOUNDARIES:

- Available: brief_data, tier, source_root, file_tree from step-01; ecosystem check outcome from step-02 (proceed/halt decision — no named variable stored)
- Focus: Source code extraction and inventory building
- Limits: Do NOT compile, assemble, or write any output
- Dependencies: Source code must be accessible (local repos resolved in step-01; remote repos cloned in section 2a)

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

Load `{sourceResolutionData}` completely. Follow the **Remote Source Resolution** protocol for Forge/Deep tiers (ephemeral clone, sparse-checkout, cleanup), the **Source Commit Capture** protocol for all tiers, and the **Version Reconciliation** protocol for all tiers. This ensures source code is accessible regardless of which extraction path is taken below (standard, component-library, or docs-only).

**Deferred CCC Discovery (Forge+ and Deep — remote sources only):**

If ALL of these conditions are true:
- `tools.ccc` is true in forge-tier.yaml
- `{ccc_discovery}` is empty (step-02b deferred because source was remote)
- `ephemeral_clone_active` is true (clone succeeded in source resolution above)
- Tier is Forge+ or Deep

Then run CCC indexing and discovery on the ephemeral clone:

1. **Index the clone:** Run `cd {temp_path} && ccc init` then `ccc index` with an extended timeout or in background mode — `ccc init` takes no positional arguments and initializes the index for the current working directory. Indexing can take several minutes on large codebases (1000+ files). Use `ccc status` to verify completion — check that `Chunks` and `Files` counts are non-zero. If init fails or indexing fails, set `{ccc_discovery: []}` and continue — this is not an error.

2. **Construct semantic query:** Build from brief data: `"{brief.name} {brief.scope}"`. Truncate to 80 characters — keep the full skill name and trim `brief.scope` from the end. If `brief.scope` is very short (< 10 chars), append terms from `brief.description` to fill the remaining space.

3. **Execute search:** Run `ccc_bridge.search(query, temp_path, top_k=20)`:
   - **Tool resolution:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `cd {temp_path} && ccc search --limit 20 "{query}"` (CLI). Note: `ccc search` operates on the index in the current working directory. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md).

4. **Store results:** If search succeeds, store as `{ccc_discovery: [{file, score, snippet}]}`. Display: "**CCC semantic discovery (post-clone): {N} relevant regions identified across {M} unique files.**"

5. **On failure:** Set `{ccc_discovery: []}`. Display: "CCC post-clone discovery unavailable — proceeding with standard extraction." Do NOT halt.

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

**Tool resolution for gh_bridge:** Use `gh api repos/{owner}/{repo}/git/trees/{branch}?recursive=1` for list_tree, `gh api repos/{owner}/{repo}/contents/{path}` for read_file. If source is local, use direct file listing/reading instead. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md).

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

**Tool resolution for ast_bridge:** Use ast-grep MCP tools (`mcp__ast-grep__find_code`, `mcp__ast-grep__find_code_by_rule`) as specified in the AST Extraction Protocol above, or `ast-grep` CLI. For `detect_co_imports`, use `find_code_by_rule` with a co-import YAML rule scoped to the libraries list. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md).

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

**If `scripts_intent: "none"` AND `assets_intent: "none"` in brief:** Skip this section.

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
- This is Gate 2 — user must confirm before compilation proceeds (except docs-only mode)
- User may ask questions about the extraction results before continuing

#### Menu Handling Logic:

- IF C: Confirm extraction inventory is complete. Immediately load, read entire file, then execute `{nextStepFile}`
- IF Any other comments or queries: answer questions about the extraction results, then redisplay the menu

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the extraction inventory is built with provenance citations and the user has confirmed the extraction summary will you proceed to load `{nextStepFile}` for temporal context fetching.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Extraction patterns loaded and tier-appropriate strategy applied
- Scope filters applied from brief
- All accessible source files in scope scanned
- Every extracted item has a provenance citation with confidence tier
- Extraction inventory built with aggregate counts
- Graceful degradation if AST tools unavailable
- Gate 2 summary presented with export counts and confidence breakdown
- User confirmed before proceeding

### ❌ SYSTEM FAILURE:

- Including exports without provenance citations
- Guessing or hallucinating function signatures not in source
- Not applying scope/include/exclude filters from the brief
- Halting on individual file read failures instead of skipping
- Not presenting Gate 2 summary for user confirmation
- Beginning compilation or SKILL.md assembly in this step
- Not reporting confidence tier breakdown

**Master Rule:** Zero hallucination — every extraction must trace to source code. Uncitable content is excluded, not guessed.
