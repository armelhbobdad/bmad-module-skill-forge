---
name: 'step-01-load-brief'
description: 'Load skill-brief.yaml, validate structure, resolve source code location, load forge tier'
nextStepFile: './step-02-ecosystem-check.md'
forgeTierFile: '{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml'
preferencesFile: '{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml'
---

# Step 1: Load Brief

## STEP GOAL:

To load and validate the skill-brief.yaml compilation config, resolve the source code location, and load the forge tier from sidecar to determine available capabilities for the compilation pipeline.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine performing initialization
- ✅ This is an autonomous init step — no user interaction needed
- ✅ Load data, validate structure, resolve paths, determine capabilities

### Step-Specific Rules:

- 🎯 Focus ONLY on loading brief, resolving source, and determining tier
- 🚫 FORBIDDEN to begin extraction or compilation — that's steps 03-05
- 🚫 FORBIDDEN to write any output files — this step only loads and validates
- 💬 Report initialization status clearly

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 All loaded data remains in context for subsequent steps
- 📖 Validate brief structure before proceeding
- 🚫 Halt with actionable error if prerequisites are missing

## CONTEXT BOUNDARIES:

- Available: User's skill name or brief path from Ferris menu invocation
- Focus: Loading inputs and determining capabilities
- Limits: Do NOT begin any extraction or compilation work
- Dependencies: forge-tier.yaml must exist (from setup-forge workflow)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Forge Tier

Load `{forgeTierFile}` completely.

**If file does not exist:**
Halt with: "Forge halted: No forge configuration found. Run [SF] Setup Forge first to detect tools and set your tier."

**If file exists:**
Extract and report:
- `tier`: Quick, Forge, or Deep
- `tools`: which tools are available (gh, ast-grep, qmd)

**Apply tier override:** Read `{preferencesFile}`. If `tier_override` is set and is a valid tier value (Quick, Forge, or Deep), use it instead of the detected tier.

### 2. Discover Skill Brief

**If user provided a specific brief path or skill name:**
- Search `{project-root}/forge-data/{skill-name}/skill-brief.yaml`
- If found, load it completely

**If user invoked with --batch flag:**
- Search specified directory for all `skill-brief.yaml` files
- List discovered briefs with skill names
- Store list for batch loop processing
- For this run, load the FIRST brief (batch loops back for remaining)

**If no brief found:**
Halt with: "No skill brief found. Run [BS] Brief Skill to create one, or use [QS] Quick Skill for brief-less generation."

### 3. Validate Brief Structure

Check that the loaded skill-brief.yaml contains required fields:

**Required fields:**
- `name` — skill identifier (kebab-case)
- `version` — source version to compile against
- `source_repo` — GitHub owner/repo or local path (**optional when `source_type: "docs-only"`**)
- `language` — primary source language
- `scope` — what to extract (e.g., "all public exports", specific modules)

**Optional fields:**
- `source_type` — `"source"` (default) or `"docs-only"` (external documentation only)
- `doc_urls` — array of `{url, label}` documentation URLs (required when `source_type: "docs-only"`)
- `source_branch` — branch to use (default: main/master)
- `source_authority` — official/community/internal (default: community; forced to `community` for docs-only)
- `include_patterns` — file glob patterns to include
- `exclude_patterns` — file glob patterns to exclude
- `description` — human description of the skill

**Docs-only validation:** When `source_type: "docs-only"`, `source_repo` is not required but `doc_urls` must have at least one entry. `source_authority` is forced to `community`.

**If required fields missing:**
Halt with specific error: "Brief validation failed: missing required field `{field}`. Update your skill-brief.yaml and re-run."

### 4. Resolve Source Code Location

**If source_repo is a GitHub URL or owner/repo format:**
- Verify repository exists via `gh_bridge.list_tree(owner, repo, branch)`
- If branch not specified, detect default branch
- Store resolved: owner, repo, branch, file tree

**If source_repo is a local path:**
- Verify path exists and contains source files
- Store resolved: local path, file listing

**If source cannot be resolved:**
Halt with: "Source not found: `{source_repo}`. Verify the repository exists and is accessible."

### 5. Report Initialization

Display initialization summary:

"**Forge initialized.**

**Skill:** {name} v{version}
**Source:** {source_repo} @ {branch}
**Language:** {language}
**Scope:** {scope}
**Tier:** {tier} — {tier_description}
**Tools:** {available_tools_list}

Proceeding to ecosystem check..."

Where tier_description follows positive capability framing:
- Quick: "Source reading and spec validation"
- Forge: "AST-backed structural extraction"
- Deep: "Full intelligence — structural + contextual + temporal"

### 6. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After initialization is complete and all data is loaded, immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed initialization step with no user choices
- Proceed directly to next step after successful initialization
- If any prerequisite check fails, HALT with actionable error — do NOT proceed

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN forge-tier.yaml is loaded, skill-brief.yaml is validated, and source code location is resolved will you proceed to load `{nextStepFile}` for ecosystem check.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Forge tier loaded from sidecar with tool availability
- Skill brief loaded and all required fields validated
- Source code location resolved and accessible
- Initialization summary displayed with tier and capabilities
- Auto-proceeded to step-02

### ❌ SYSTEM FAILURE:

- Proceeding without forge-tier.yaml (missing prerequisite)
- Proceeding with invalid or incomplete brief
- Not resolving source code location before proceeding
- Beginning extraction or compilation work in this step
- Not displaying initialization summary

**Master Rule:** This step ONLY loads and validates. It does NOT extract, compile, or write files.
