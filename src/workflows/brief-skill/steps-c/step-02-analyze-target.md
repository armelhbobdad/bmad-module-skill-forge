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

If `tools.ccc` is true in forge-tier.yaml, supplement the module listing with a semantic discovery pass:

Run `ccc_bridge.search("{repo_name} public API exports modules", source_path, top_k=10)` — **Tool resolution:** `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `ccc search` CLI. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md).

If results are returned, display:

"**Semantic Signals (ccc):**
{numbered list of file:snippet pairs from CCC results — top 5 most relevant}"

This supplements — never replaces — the explicit module list above. CCC may surface non-obvious entry points (dynamically constructed exports, re-export chains) that static directory analysis misses.

If CCC is unavailable or returns no results: skip this subsection silently.

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

---

{If language confidence is low:}
**Note:** Language detection confidence is low. You'll be able to override this in the next step.

Moving to scope definition where you'll choose what to include and exclude."

### 6. Auto-Proceed to Scope Definition

Display: "**Proceeding to scope definition...**"

#### Menu Handling Logic:

- After analysis report is presented to user, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step — analysis is factual reporting with no user choices
- Proceed directly to step 03 after presenting the analysis summary

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the analysis is complete and the summary has been presented to the user will you load and read fully `./step-03-scope-definition.md` to begin scope definition.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Target repository resolved and accessible
- Repository structure listed clearly
- Primary language detected with confidence level
- Top-level modules and exports identified
- Analysis summary presented factually
- Auto-proceeded to scope definition

### ❌ SYSTEM FAILURE:

- Hallucinating or guessing about repository contents
- Making scoping recommendations (too early — that's step 03)
- Proceeding when target is inaccessible (must halt with error)
- Not detecting or reporting the primary language
- Skipping the analysis summary

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
