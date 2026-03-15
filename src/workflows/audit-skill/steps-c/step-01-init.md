---
name: 'step-01-init'
description: 'Load existing skill, provenance map, and detect forge tier for drift analysis'

nextStepFile: './step-02-re-index.md'
outputFile: '{forge_data_folder}/{skill_name}/drift-report-{timestamp}.md'
templateFile: '../data/drift-report-template.md'
---

# Step 1: Initialize Audit

## STEP GOAL:

Load the existing skill artifacts, provenance map, and forge tier configuration to establish the baseline for drift detection. Create the drift report document and present a baseline summary for user confirmation before proceeding with analysis.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor operating in Ferris Audit mode
- ✅ Every finding must trace to actual code with file:line citations
- ✅ You enforce the zero-hallucination principle: structural truth over semantic guessing
- ✅ You bring AST analysis expertise, the source code provides ground truth

### Step-Specific Rules:

- 🎯 Focus only on loading skill artifacts and establishing the baseline
- 🚫 FORBIDDEN to perform any diff or analysis — that happens in later steps
- 🚫 FORBIDDEN to proceed if skill path is invalid or SKILL.md not found
- 💬 Present baseline summary clearly so user can confirm before analysis begins

## EXECUTION PROTOCOLS:

- 🎯 Discover and load all required input artifacts
- 💾 Create drift report from {templateFile} with populated frontmatter
- 📖 Track loaded artifacts in report frontmatter
- 🚫 Do not proceed to analysis without user confirmation at the gate

## CONTEXT BOUNDARIES:

- Available: User-provided skill path, SKF module config variables
- Focus: Loading and validating all inputs needed for drift analysis
- Limits: Do not analyze or compare — only load and baseline
- Dependencies: setup-forge must be completed (forge-tier.yaml exists), skill must have been created by create-skill (provenance-map.json exists for source-based skills)
- Docs-only limitation: If `metadata.json` indicates `source_type: "docs-only"` or `confidence_tier: "Quick"` with all T3 citations, inform user: "**This is a docs-only skill.** Drift detection compares against upstream documentation, not source code. Re-run `@Ferris US` to re-fetch documentation URLs and detect content changes." Audit-skill's structural diff is not applicable to docs-only skills — recommend update-skill instead.

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Get Skill Path

"**Audit Skill — Drift Detection**

Which skill would you like to audit? Please provide the skill name or path."

**If user provides skill name (not full path):**
- Resolve to `{skills_output_folder}/{skill_name}/`

**If user provides full path:**
- Use as provided

**Validate:** Check that `SKILL.md` exists at the resolved path.
- If missing → "Skill not found at `{resolved_path}`. Check the path and try again."
- If found → Continue

### 2. Load Forge Tier

Load `{sidecar_path}/forge-tier.yaml` to detect available tools.

**If file missing:**
- "Setup-forge has not been run. Cannot determine tool availability. Run `[SF] Setup Forge` first."
- HALT workflow

**If found:**
- Extract tier level: Quick / Forge / Deep
- Extract available tools: gh_bridge, ast_bridge, qmd_bridge

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, or Deep), use it instead of the detected tier.

### 3. Load Skill Artifacts

Load the following from the skill directory:

**Required:**
- `SKILL.md` — The skill document to audit
- `metadata.json` — Skill metadata (version, created date, export count)

**Extract from metadata.json:**
- `name`, `version`, `generation_date`, `confidence_tier` used during creation
- `source_root` — Resolved source code path used during extraction

### 4. Load Provenance Map

Search for provenance map at `{forge_data_folder}/{skill_name}/provenance-map.json`

**If found:**
- Load and extract: export list, file mappings, extraction timestamps, confidence tiers
- Record provenance map age (days since last extraction)

**If missing:**
- "No provenance map found for `{skill_name}`. This skill may not have been created by create-skill."
- "**Degraded mode available:** I can perform text-based comparison without provenance data. Findings will have T1-low confidence."
- "**[D]egraded mode** — proceed with text-diff only"
- "**[X]** — abort audit"
- Wait for user selection. If D, set `degraded_mode: true`. If X, halt workflow.

### 5. Resolve Source Path

**If provenance map loaded:**
- Use `source_root` from provenance map as source code path
- Verify source path still exists and is accessible

**If degraded mode:**
- Ask user: "Please provide the path to the current source code."

**Validate:** Confirm source directory exists and contains expected files.

### 6. Create Drift Report

Create `{outputFile}` from `{templateFile}`:

- Populate frontmatter: skill_name, skill_path, source_path, forge_tier, date, user_name
- Set `stepsCompleted: ['step-01-init']`
- Fill Audit Summary skeleton with loaded baseline data

### 7. Present Baseline Summary (User Gate)

"**Audit Baseline Loaded**

| Field | Value |
|-------|-------|
| **Skill** | {skill_name} v{version} |
| **Created** | {generation_date} |
| **Source** | {source_path} |
| **Forge Tier** | {current_tier} (created at {original_tier}) |
| **Provenance Age** | {days} days since last extraction |
| **Export Count** | {count} exports in provenance map |
| **Mode** | {normal / degraded} |

**Analysis plan based on tier:**
- {Quick: text-diff comparison (T1-low confidence)}
- {Forge: AST structural comparison (T1 confidence)}
- {Deep: AST structural + QMD semantic comparison (T1 + T2 confidence)}

**Ready to begin drift analysis?**"

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Analysis"

#### Menu Handling Logic:

- IF C: Save baseline to {outputFile}, update frontmatter stepsCompleted, then load, read entire file, then execute {nextStepFile}
- IF Any other: help user, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and the drift report has been created with baseline data populated, will you then load and read fully `{nextStepFile}` to execute and begin source re-indexing.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Skill artifacts loaded (SKILL.md, metadata.json)
- Forge tier detected from sidecar (and override applied if set in preferences.yaml)
- Provenance map loaded (or degraded mode confirmed)
- Source path resolved and validated
- Drift report created from template with populated frontmatter
- Baseline summary presented to user
- User confirmed via [C] Continue

### ❌ SYSTEM FAILURE:

- Proceeding without valid skill path
- Not loading provenance map or offering degraded mode
- Not detecting forge tier
- Performing analysis in this step (analysis is Steps 02-05)
- Proceeding without user confirmation at the gate
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
