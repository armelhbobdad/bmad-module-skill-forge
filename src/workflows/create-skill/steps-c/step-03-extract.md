---
name: 'step-03-extract'
description: 'Tier-dependent source code extraction — AST or source reading for exports, signatures, and types'
nextStepFile: './step-03b-fetch-temporal.md'
extractionPatternsData: '../data/extraction-patterns.md'
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

- Available: brief_data, tier, source_location, file_tree from step-01; ecosystem_status from step-02
- Focus: Source code extraction and inventory building
- Limits: Do NOT compile, assemble, or write any output
- Dependencies: Source code must be accessible (resolved in step-01)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Extraction Patterns

Load `{extractionPatternsData}` completely. Identify the strategy for the current forge tier.

### 2. Apply Scope Filters

From the brief, apply scope and pattern filters:

- `scope` — determines what to extract (e.g., "all public exports", specific modules)
- `include_patterns` — file globs to include (if specified)
- `exclude_patterns` — file globs to exclude (if specified)

Build the filtered file list from the source tree resolved in step-01.

### 3. Check for Docs-Only Mode

**If `source_type: "docs-only"` in the brief data:**

"**Docs-only mode:** No source code to extract. Documentation content will be fetched from `doc_urls` in step-03c."

Build an empty extraction inventory with zero exports. Set `extraction_mode: "docs-only"` in context. Auto-proceed through Gate 2 (section 5) — display the empty inventory and note that T3 content will be produced by the doc-fetcher step.

**If `source_type: "source"` (default):** Continue with extraction below.

### 4. Execute Tier-Dependent Extraction

**Remote Source Resolution (Forge/Deep only):**

If `source_repo` is a local path: proceed with the tier-appropriate strategy as normal.

If `source_repo` is a remote URL (GitHub URL or owner/repo format) AND tier is Forge or Deep:

1. **Check `git` availability:** Verify `git` is functional (`git --version`). If `git` is not available, skip to the fallback warning below.

2. **Ephemeral shallow clone:** Clone the repository to a system temp path for AST access:

   ```
   temp_path = {system_temp}/skf-ephemeral-{skill-name}-{timestamp}/
   git clone --depth 1 --branch {branch} --single-branch --filter=blob:none {source_repo} {temp_path}
   ```

   **If `include_patterns` are NOT specified:**

   ```
   git clone --depth 1 --branch {branch} --single-branch --filter=blob:none {source_repo} {temp_path}
   ```

   **If `include_patterns` ARE specified**, use sparse-checkout to limit the clone scope:

   ```
   git clone --depth 1 --branch {branch} --single-branch --filter=blob:none --sparse {source_repo} {temp_path}
   ```

   **IMPORTANT:** `git sparse-checkout set` expects **directories**, not glob patterns. Convert `include_patterns` before passing them:

   **Classification rule:** A pattern is an **individual file** if it contains no glob characters (`*`, `?`, `[`) AND does not end with `/`. Everything else is a glob — strip it to its directory root (the path prefix before the first glob character or wildcard segment).

   - Strip glob suffixes to directory roots (e.g., `src/core/**/*.py` → `src/core`, `src/api/*.ts` → `src/api`)
   - Deduplicate the resulting directory list
   - Individual files (e.g., `pyproject.toml`, `src/utils/helpers.py`) are kept as-is

   **If only directory roots (no individual files):**

   ```
   git -C {temp_path} sparse-checkout set {converted_directory_roots}
   ```

   **If any individual files are present (or mixed):**

   ```
   git -C {temp_path} sparse-checkout set --skip-checks {converted_directory_roots} {individual_files}
   ```

   Example transformation:
   ```
   Brief include_patterns:        sparse-checkout args:
   src/core/**/*.py          →    src/core          (directory root)
   src/api/*.ts              →    src/api           (directory root)
   examples/**/*.py          →    examples          (directory root)
   pyproject.toml            →    pyproject.toml    (individual file, needs --skip-checks)
   src/utils/helpers.py      →    src/utils/helpers.py (individual file, needs --skip-checks)
   ```

   After checkout, apply the original glob `include_patterns` as file-level filters when building the extraction file list — sparse-checkout gets the right directories, glob filtering narrows to the exact files.

3. **If clone succeeds:** Update the working source path to `{temp_path}` for all subsequent AST operations in this step. Proceed with the **Forge/Deep Tier** extraction strategy below. Mark `ephemeral_clone_active = true` for cleanup.

4. **If clone fails (network error, auth failure, timeout):**

   ⚠️ **Warn the user explicitly:**

   "Ephemeral clone of `{source_repo}` failed: {error}. Degrading to source reading (T1-low) for this run. For T1 (AST-verified) confidence, clone the repository locally and update `source_repo` in your brief to the local path."

   Proceed with Quick tier extraction strategy below. Note the degradation reason in context for the evidence report.

**Ephemeral clone cleanup:** After extraction is complete for all files in scope (whether successful or partially failed), before presenting the Gate 2 summary (Section 6), if `ephemeral_clone_active`, delete the `{temp_path}` directory. Log: "Ephemeral source clone cleaned up." This ensures cleanup runs even if some extractions failed, as long as the step itself is still executing.

**Version Reconciliation (all tiers, source mode only):**

**If `source_type: "docs-only"`:** skip this subsection — no source files exist to reconcile.

After the source path is accessible (local path from step-01, or ephemeral clone from above), check whether the source contains a version identifier and reconcile it with `brief.version`. Look for the first matching version file in the resolved source path:

- Python: `pyproject.toml` (`[project] version`), `setup.py` (`version=`), `__version__` in `__init__.py`
- JavaScript/TypeScript: `package.json` (`"version"`)
- Rust: `Cargo.toml` (`[package] version`)
- Go: `go.mod` (module version if tagged)

**If a source version is found AND it differs from `brief.version`:**

⚠️ Warn the user: "Brief version ({brief.version}) differs from source version ({source_version}). Using source version ({source_version})."

Update the working version in context to the source version. Record the mismatch in context for the evidence report (step-08).

**If no version file is found or version cannot be extracted:** keep `brief.version` as-is. No warning needed.

**If source is remote and accessed via Quick tier (gh_bridge, no local files):** attempt to read the version file via `gh_bridge.read_file(owner, repo, "{version_file}")` for the primary version file of the detected language. If the read fails, keep `brief.version`.

**Quick Tier (No AST tools):**

1. Use `gh_bridge.list_tree(owner, repo, branch)` to map source structure (if remote)
2. Identify entry points: index files, main exports, public modules
3. Use `gh_bridge.read_file(owner, repo, path)` to read each entry point
4. Extract from source text: exported function names, parameter lists, return types
5. Infer types from JSDoc, docstrings, type annotations
6. Confidence: All results T1-low — `[SRC:{file}:L{line}]`

**Forge/Deep Tier (AST available):**

⚠️ **CRITICAL:** Before executing AST extraction, load the **AST Extraction Protocol** section from `{extractionPatternsData}`. Follow the decision tree based on the file count from step-01's file tree. This determines whether to use the MCP tool, scoped YAML rules, or CLI streaming. Never use `ast-grep --json` (without `=stream`) — it loads the entire result set into memory and will fail on large codebases.

1. Detect language from brief or file extensions
2. Follow the AST Extraction Protocol decision tree from `{extractionPatternsData}`:
   - ≤100 files: use `find_code()` MCP tool with `max_results` and `output_format="text"`
   - ≤500 files: use `find_code_by_rule()` MCP tool with scoped YAML rules
   - >500 files: use CLI `--json=stream` with line-by-line streaming Python
3. For each export: extract function name, full signature, parameter types, return type, line number
4. Use `ast_bridge.detect_co_imports(path, libraries[])` to find integration points
5. Build extraction rules YAML data for reproducibility
6. Confidence: All results T1 — `[AST:{file}:L{line}]`

**If AST tool is unavailable at Forge/Deep tier:**

⚠️ **Warn the user explicitly:** "AST tools are unavailable — extraction will use source reading (T1-low). Run [SF] Setup Forge to detect and configure AST tools for T1 confidence."

Degrade to Quick tier extraction. Note the degradation reason in context for the evidence report.

**For each file — handle failures gracefully:**

- If a file cannot be read: log warning, skip file, continue with remaining files
- If AST parsing fails on a file: fall back to source reading for that file, continue

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

**Top exports:**
{list top 10 exports with signatures}

{warnings if any files skipped or degraded}

Review the extraction summary above. Select an option to continue."

### 7. Present MENU OPTIONS

Display: "**Extraction Summary — Select an Option:** [C] Continue to compilation"

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting the extraction summary
- This is Gate 2 — user must confirm before compilation proceeds
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
