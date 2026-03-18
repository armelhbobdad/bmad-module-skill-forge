---
name: 'step-01-init'
description: 'Initialize analysis workflow — load config, detect continuation, accept project path, check existing skills, create report'

nextStepFile: './step-02-scan-project.md'
continueFile: './step-01b-continue.md'
outputFile: '{output_folder}/analyze-source-report-{project_name}.md'
templateFile: '../templates/analysis-report-template.md'
---

# Step 1: Initialize Analysis

## STEP GOAL:

To initialize the analyze-source workflow by loading configuration, detecting continuation state, accepting the target project path, checking for existing skills, and creating the analysis report document.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread

### Role Reinforcement:

- ✅ You are a source code analyst and decomposition architect (Ferris Architect mode)
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Prescriptive precision — zero-hallucination, only report what is found
- ✅ File:line citation tracing for all claims

### Step-Specific Rules:

- 🎯 Focus only on initialization — do NOT begin scanning or analysis
- 🚫 FORBIDDEN to analyze source code in this step
- 💬 Collect project path and scope hints from user
- 📋 Verify prerequisites before proceeding

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Create output document from template when initialization complete
- 📖 Update output frontmatter with initialization data
- 🚫 FORBIDDEN to proceed without valid project path and forge-tier.yaml

## CONTEXT BOUNDARIES:

- Available: SKF module config (loaded by workflow.md), forge_data_folder, skills_output_folder, forge_tier
- Focus: Setup and validation only — no analysis
- Limits: Do not read source files beyond checking prerequisites
- Dependencies: setup-forge must have been run (forge-tier.yaml must exist)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Check for Existing Report (Continuation Detection)

Look for {outputFile}.

**IF the file exists AND has `stepsCompleted` with entries:**
- "**Found an existing analysis report. Resuming previous session...**"
- Load, read entirely, then execute {continueFile}
- **STOP HERE** — do not continue this sequence

**IF the file does not exist OR stepsCompleted is empty:**
- Continue to section 2

### 2. Verify Prerequisites

**Check forge-tier.yaml:**
- Look for `{sidecar_path}/forge-tier.yaml`
- **IF missing:** HARD HALT — "**Cannot proceed.** forge-tier.yaml not found at `{sidecar_path}/forge-tier.yaml`. Please run the setup-forge workflow first to configure your forge tier (Quick/Forge/Deep)."
- **IF found:** Read and note the forge tier value

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, or Deep), use it instead of the detected tier.

"**Forge tier detected:** {tier} — analysis depth will be calibrated accordingly."

### 3. Collect Project Path

"**Welcome to Analyze Source — the SKF decomposition engine.**

I'll analyze your project to identify discrete skillable units and produce skill-brief.yaml files for each recommended unit.

**Please provide the project root path(s) to analyze:**

This can be:
- A single root directory of a repo or multi-service project
- Multiple paths or URLs (comma-separated) for multi-repo analysis (e.g., integration/stack skills)

Examples:
- `/path/to/project`
- `owner/repo, owner/repo2`
- `/path/to/project, https://github.com/owner/repo2`"

Wait for user input.

**Validate the path(s):**
- For each provided path/URL: check that it exists (local) or is accessible (remote)
- **IF any invalid:** "Path `{path}` doesn't appear to be valid. Please correct it."
- Store as `project_paths[]` array in report frontmatter (single path stored as 1-element array for consistency)

### 4. Collect Optional Scope Hints

"**Optional: Do you have scope hints to narrow the analysis?**

For example:
- Specific packages to focus on (e.g., `packages/auth`, `services/api`)
- Directories to exclude (e.g., `vendor/`, `node_modules/`, `dist/`)

Enter scope hints, or press Enter to analyze the entire project."

Wait for user input. Document any hints provided.

### 5. Check for Existing Skills

Scan `{forge_data_folder}/` for existing `skill-brief.yaml` files.

**IF existing skills found:**
"**Existing skills detected:**
{list each existing skill name and path}

These units will be flagged as 'already skilled' during analysis. If source changes are detected, I'll recommend running update-skill instead of generating new briefs."

**IF no existing skills found:**
"**No existing skills found.** All identified units will be treated as new."

### 6. Create Analysis Report

Create {outputFile} from {templateFile}.

**Populate frontmatter:**
```yaml
stepsCompleted: ['step-01-init']
lastStep: 'step-01-init'
lastContinued: ''
date: '{current_date}'
user_name: '{user_name}'
project_name: '{project_name}'
project_paths: ['{provided_project_path}']
forge_tier: '{detected_tier}'
existing_skills: [{list of existing skill names}]
confirmed_units: []
stack_skill_candidates: []
nextWorkflow: ''
```

"**Initialization complete.**

**Project:** {project_path}
**Forge Tier:** {forge_tier}
**Existing Skills:** {count}
**Scope Hints:** {hints or 'None — full project analysis'}

**Proceeding to project scan...**"

### 7. Proceed to Next Step

Display: "**Proceeding to project scan...**"

#### Menu Handling Logic:

- After initialization is complete and report is created, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed initialization step with no user choices at this point
- Proceed directly to next step after setup

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the output report has been created with populated frontmatter (project_paths, forge_tier, existing_skills) will you load and read fully {nextStepFile} to execute and begin the project scan.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Continuation detection performed correctly
- forge-tier.yaml verified present and tier noted
- Valid project path collected from user
- Optional scope hints collected
- Existing skills scanned and documented
- Analysis report created from template with populated frontmatter
- Auto-proceeded to step 02

### ❌ SYSTEM FAILURE:

- Skipping forge-tier.yaml check
- Accepting an invalid project path
- Not checking for existing skills
- Not creating the output report before proceeding
- Beginning source analysis in this step
- Hardcoded paths instead of using frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
