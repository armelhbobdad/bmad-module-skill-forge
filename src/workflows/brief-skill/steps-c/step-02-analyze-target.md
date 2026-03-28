---
name: 'step-02-analyze-target'
description: 'Analyze target repository structure, detect language, and list modules and exports'

nextStepFile: './step-03-scope-definition.md'
---

# Step 2: Analyze Target

## STEP GOAL:

To analyze the target repository by resolving its location, reading its structure, detecting the primary language, and listing top-level modules and exports — providing the user with a factual foundation for scoping decisions.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread

### Role Reinforcement:

- ✅ You are a source code analyst in Ferris Architect mode
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Report ONLY what is found — zero hallucination tolerance
- ✅ You bring structural analysis expertise, user brings their domain understanding

### Step-Specific Rules:

- 🎯 Focus only on analysis — do not define scope yet (that's step 03)
- 🚫 FORBIDDEN to make scoping decisions or recommendations in this step
- 🚫 FORBIDDEN to hallucinate or guess about repository contents
- 💬 Approach: Prescriptive — exact analysis instructions, factual reporting
- 📋 Report everything found; let the user interpret for scoping

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Analysis results are accumulated conversationally for use in step 03
- 📖 This step is autonomous — minimal user interaction required
- 🚫 FORBIDDEN to proceed if target is inaccessible — halt with actionable error

## CONTEXT BOUNDARIES:

- Available context: Target repo (URL or path), user intent, skill name, forge tier — all from step 01
- Focus: Structural analysis of the repository
- Limits: Do not read file contents deeply — only structure, exports, and metadata
- Dependencies: Confirmed target repository from step 01

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Resolve Target Location

**For GitHub URLs:**
- Use `gh api repos/{owner}/{repo}` to verify the repository exists
- Use `gh api repos/{owner}/{repo}/git/trees/HEAD?recursive=1` to get the file tree

**Truncation detection:** After receiving the tree response, check the `truncated` field in the JSON output. If `truncated: true`:
- Display: "Note: GitHub API returned a truncated tree response ({count} items). Full analysis may require a local clone."
- Record in analysis summary: "Tree listing is partial — some files may not appear in the analysis."
- For very large repos (>1000 files in tree response): suggest local clone for complete analysis.

- If inaccessible: **HALT** — "**Error:** Cannot access repository at {url}. Please verify the URL is correct and you have access. If private, ensure `gh auth` is configured."

**For local paths:**
- Verify the directory exists
- List the directory tree
- If path doesn't exist: **HALT** — "**Error:** Directory not found at {path}. Please verify the path is correct."

Display: "**Resolving target...**"

### 2. Read Repository Structure

List the top-level directory structure:

"**Repository Structure:**
```
{repo-name}/
├── {top-level files}
├── {top-level directories}/
│   └── ...
└── ...
```
**Total:** {file count} files, {directory count} directories"

### 3. Detect Primary Language

Examine file extensions and configuration files to detect the primary language:

**Detection signals (check in order):**
1. `package.json` → JavaScript/TypeScript
2. `tsconfig.json` → TypeScript
3. `Cargo.toml` → Rust
4. `pyproject.toml` or `setup.py` or `setup.cfg` → Python
5. `go.mod` → Go
6. `pom.xml` or `build.gradle` → Java
7. `*.csproj` or `*.sln` → C#
8. `Gemfile` → Ruby
9. File extension frequency analysis as fallback

"**Detected language:** {language}
**Confidence:** {high/medium/low}
**Detection source:** {what config file or pattern confirmed it}"

If confidence is low or ambiguous: flag for user override in step 03.

### 4. List Top-Level Modules and Exports

Based on detected language, identify public API surface:

**For JavaScript/TypeScript:**
- Check `package.json` for `main`, `exports`, `module` fields
- Look for `index.ts`/`index.js` in `src/`
- List directories under `src/` as potential modules

**For Python:**
- Check `__init__.py` files for public exports
- List top-level packages under the source directory

**For Rust:**
- Check `lib.rs` for `pub mod` declarations
- List modules from `src/` directory

**For other languages:**
- List top-level source directories as potential modules
- Note any obvious entry points

"**Top-Level Modules/Directories:**
{numbered list of modules with brief description of each}

**Detected Exports/Entry Points:**
{numbered list of public-facing items found}"

**Semantic Signals (Forge+ and Deep with ccc only):**

**Remote source guard:** If the target source was resolved via GitHub API (remote URL, not a local file path), skip this CCC subsection — CCC requires a local source index and cannot operate on remote-only sources. Note: "CCC semantic discovery skipped — target is remote. CCC discovery will run automatically during create-skill after the source is cloned."

If `tools.ccc` is true in forge-tier.yaml, supplement the module listing with a semantic discovery pass:

**CCC Semantic Discovery:**
- **Claude Code:** Use `/ccc search "{repo_name} public API exports modules" {source_path}`
- **Cursor:** Use `ccc` MCP server `search` tool with query `"{repo_name} public API exports modules"` and path `{source_path}`
- **CLI fallback:** `ccc search "{repo_name} public API exports modules" --path {source_path} --limit 10`

See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md) for full bridge-to-tool mapping.

If results are returned, display:

"**Semantic Signals (ccc):**
{numbered list of file:snippet pairs from CCC results — top 5 most relevant}"

This supplements — never replaces — the explicit module list above. CCC may surface non-obvious entry points (dynamically constructed exports, re-export chains) that static directory analysis misses.

If CCC is unavailable or returns no results: skip this subsection silently.

### 4b. Detect Source Version

Attempt to auto-detect the source version using the rules from the skill-brief-schema.md Version Detection section:

**For Python:** Check `pyproject.toml` `[project] version` (static) → if `dynamic = ["version"]`, check `__init__.py` for `__version__` → `_version.py` if exists → `setup.py` `version=` → `git describe --tags --abbrev=0`
**For JavaScript/TypeScript:** Check `package.json` `"version"` field
**For Rust:** Check `Cargo.toml` `[package] version` (static) → if `version = { workspace = true }`, resolve from workspace root `Cargo.toml` → `git describe --tags --abbrev=0`
**For Go:** Check `go.mod` or `git describe --tags --abbrev=0`

**For GitHub repos:** Use `gh api repos/{owner}/{repo}/contents/{file}` to read version files (decode base64 content).
**For local repos:** Read the file directly.

Display: "**Detected version:** {version or 'Not detected — will default to 1.0.0'}"

If detection fails or returns a non-semver value: note that version will default to `"1.0.0"` and the user can override in step 04.

### 5. Report Analysis Summary

Present the complete analysis:

"**Analysis Complete**

---

**Target:** {repo URL or path}
**Language:** {detected language} ({confidence})
**Structure:** {file count} files across {directory count} directories

**Key Modules ({count}):**
{bulleted list of modules}

**Public Exports/Entry Points ({count}):**
{bulleted list of exports}

**Notable Files:**
- README: {found/not found}
- Tests: {found/not found — location}
- Docs: {found/not found — location}
- Config: {list of config files found}
- Version: {detected version or "Not detected — defaulting to 1.0.0"}

---

{If language confidence is low:}
**Note:** Language detection confidence is low. You'll be able to override this in the next step.

Moving to scope definition where you'll choose what to include and exclude."

### 6. Auto-Proceed to Scope Definition

Display: "**Proceeding to scope definition...**

Review the analysis above. If anything looks wrong, let me know now — otherwise I'll proceed to scope definition."

Pause briefly for user input. If the user provides corrections or asks questions, address them and re-present any updated analysis findings. Then proceed.

#### Menu Handling Logic:

- After analysis report is presented to user and any corrections addressed, load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is a soft auto-proceed step — present the pause prompt, wait briefly for user input
- If user provides corrections: address them, then proceed
- If no user input after a brief pause: proceed directly to step 03

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the analysis is complete and the summary has been presented to the user will you load and read fully `./step-03-scope-definition.md` to begin scope definition.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Target repository resolved and accessible
- Repository structure listed clearly
- Primary language detected with confidence level
- Top-level modules and exports identified
- Source version detected (or default noted)
- Analysis summary presented factually
- Auto-proceeded to scope definition (with pause for corrections)

### ❌ SYSTEM FAILURE:

- Hallucinating or guessing about repository contents
- Making scoping recommendations (too early — that's step 03)
- Proceeding when target is inaccessible (must halt with error)
- Not detecting or reporting the primary language
- Skipping the analysis summary

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
