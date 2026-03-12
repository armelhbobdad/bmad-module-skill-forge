---
name: 'step-01-init'
description: 'Initialize stack skill workflow by loading forge tier and validating prerequisites'

nextStepFile: './step-02-detect-manifests.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
---

# Step 1: Initialize

## STEP GOAL:

Load forge tier configuration, validate prerequisites, and prepare the stack skill workflow for execution.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a dependency analyst and integration architect operating in Ferris Architect mode
- ✅ Execute with prescriptive precision — every finding must trace to actual code
- ✅ Speed-first approach with zero hallucination

### Step-Specific Rules:

- 🎯 Focus ONLY on loading configuration and validating prerequisites
- 🚫 FORBIDDEN to start detecting manifests or analyzing dependencies
- 🚫 No A/P menu — this is an auto-proceed init step

## EXECUTION PROTOCOLS:

- 🎯 Load forge tier and validate tools
- 💾 Store tier, tools, and optional inputs as workflow state
- 📖 Auto-proceed to next step after successful initialization
- 🚫 HALT with actionable error if prerequisites missing

## CONTEXT BOUNDARIES:

- This is the first step — no prior workflow state exists
- Requires setup-forge to have been completed (forge-tier.yaml)
- User may provide optional explicit dependency list or scope overrides
- No dependencies on brief-skill or create-skill outputs

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Forge Tier Configuration

Load `{forgeTierFile}` from the Ferris sidecar.

**If forge-tier.yaml does not exist:**

"**Cannot proceed.** The setup-forge workflow has not been run for this project.

**Required:** Run `setup-forge` first to detect available tools and determine your forge tier.

**Halting workflow.**"

STOP — do not proceed.

**If forge-tier.yaml exists:**

Extract:
- `forge_tier` — Quick, Forge, or Deep
- `available_tools` — list of detected tools (gh_bridge, ast_bridge, qmd_bridge, skill-check)
- `project_root` — project root path

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, or Deep), use it instead of the detected tier.

### 2. Validate Available Tools

**Required for all tiers:**
- File I/O capability (read project files)

**Tier-dependent tools:**
- **Quick:** gh_bridge (source reading) — graceful degradation to local file reading if unavailable
- **Forge:** ast_bridge (ast-grep structural analysis) — required for Forge tier
- **Deep:** qmd_bridge (QMD temporal enrichment) — required for Deep tier

Report tool availability. If a tier-required tool is missing, downgrade tier and note:

"**Tier adjusted:** {original_tier} → {adjusted_tier} — {missing_tool} unavailable."

### 3. Accept Optional Inputs

Check if the user provided:

**Explicit dependency list:**
- If provided, store as `explicit_deps` and skip auto-detection in step 02
- Format: comma-separated library names or a file path

**Scope overrides:**
- If provided, store as `scope_overrides` for use in step 03
- Format: `library_name: include|exclude`

If no optional inputs provided, auto-detection will be used.

### 4. Display Initialization Summary

"**Stack Skill Forge initialized.**

**Project:** {project_name}
**Forge Tier:** {tier_description}
- Quick: Source reading and import counting
- Forge: + AST-backed structural analysis
- Deep: + Temporal integration evolution

**Available Tools:** {tool_list}
**Input Mode:** {auto-detect | explicit dependency list}

**Proceeding to manifest detection...**"

### 5. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Forge tier loaded and validated
- Tool availability confirmed with tier adjustment if needed
- Optional inputs accepted and stored
- Initialization summary displayed with positive capability framing
- Auto-proceeded to step 02

### ❌ SYSTEM FAILURE:

- Proceeding without forge-tier.yaml
- Not reporting tier adjustments when tools missing
- Starting manifest detection in this step
- Displaying A/P menu (this is auto-proceed)

**Master Rule:** This step validates prerequisites and initializes state. No analysis, no detection, no extraction.
