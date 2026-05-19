---
nextStepFile: 'scan-project.md'
continueFile: 'continue.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
templateFile: 'templates/analysis-report-template.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Analysis

## STEP GOAL:

To initialize the analyze-source workflow by loading configuration, detecting continuation state, accepting the target project path, checking for existing skills, and creating the analysis report document.

## Rules

- Focus only on initialization — do not begin scanning or analysis
- Collect project path and scope hints from user
- Verify prerequisites before proceeding

## MANDATORY SEQUENCE

### 1. Check for Existing Report (Continuation Detection)

Look for {outputFile}.

**IF the file exists AND has `stepsCompleted` with entries:**
- The report filename is keyed to `{project_name}` (the forge workspace), not the analyzed target — so a report from a *different* target can collide here. Before resuming, establish the requested target and compare it to the existing report:
  - Determine the requested target now: if `--project-path <path>` was passed at invocation, set `project_paths[]` from it (comma-split if multiple); otherwise collect the path(s) using the section-3 "Collect Project Path" prompt and store as `project_paths[]`. (Section 3 must NOT re-prompt when `project_paths[]` is already populated here.)
  - Read the existing report's frontmatter `project_paths`.
  - **IF the existing report's `project_paths` matches the requested target:** "**Found an existing analysis report. Resuming previous session...**" — Load, read entirely, then execute {continueFile}. **STOP HERE** — do not continue this sequence.
  - **ELSE (different target — stale collision):** the existing report belongs to another analysis. Archive it by renaming to `{forge_data_folder}/analyze-source-report-{project_name}-<UTC-timestamp>.md`, announce "**Existing report belongs to a different target — archived as <name>; starting a fresh analysis.**", then continue to section 2 (skip re-collecting the path in section 3 — it is already set).

**IF the file does not exist OR stepsCompleted is empty:**
- Continue to section 2

### 2. Verify Prerequisites

**Check forge-tier.yaml:**
- Look for `{sidecar_path}/forge-tier.yaml`
- **IF missing:** HARD HALT — "**Cannot proceed.** forge-tier.yaml not found at `{sidecar_path}/forge-tier.yaml`. Please run the setup workflow first to configure your forge tier (Quick/Forge/Forge+/Deep)."
- **IF found:** Read and note the forge tier value

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

"**Forge tier detected:** {tier} — analysis depth will be calibrated accordingly."

### 3. Collect Project Path

**Headless flag consumption:** If `project_paths[]` is already populated (e.g. collected by the section-1 stale-collision guard) OR `--project-path <path>` was passed at invocation, set/keep `project_paths[]` (comma-split the flag value if multiple paths were supplied), skip the prompt below, and proceed to validation. Otherwise prompt as today.

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

**Collect intent hint** (drives recommendation ranking in Step 5):

**Headless flag consumption:** If `--intent-hint <text>` was passed at invocation, set workflow-context `intent_hint` directly from the flag value, skip the prompt below, and proceed. If `{headless_mode}` is true and no `--intent-hint` was supplied, set `intent_hint = ""` (empty) and proceed without prompting.

"**Optional: What are you hoping to get out of this analysis?**

For example:
- Skills for a specific domain (e.g., 'authentication and authorization')
- Target consumer agents (e.g., 'skills our backend team's AI assistants will call')
- Constraints (e.g., 'we only want stable public APIs, no internal modules')

Type details, or press Enter to skip."

Wait for user input. Store as workflow-context `intent_hint` (empty string if skipped).

### 4. Collect Optional Scope Hints

**Headless flag consumption:** If `--scope-hint <text>` was passed at invocation, set workflow-context `scope_hint` directly from the flag value, skip the prompt below, and proceed. If `{headless_mode}` is true and no `--scope-hint` was supplied, set `scope_hint = ""` (empty) and proceed without prompting.

"**Optional: Do you have scope hints to narrow the analysis?**

For example:
- Specific packages to focus on (e.g., `packages/auth`, `services/api`)
- Directories to exclude (e.g., `vendor/`, `node_modules/`, `dist/`)

Enter scope hints, or press Enter to analyze the entire project."

Wait for user input. Document any hints provided.

### 5. Check for Existing Skills

Scan `{forge_data_folder}/*/skill-brief.yaml` (one level deep — each skill has its own subdirectory) for existing skill briefs.

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
stepsCompleted: ['init']
lastStep: 'init'
lastContinued: ''
date: '{current_date}'
user_name: '{user_name}'
project_name: '{project_name}'
project_paths: ['{provided_project_path}']
forge_tier: '{detected_tier}'
existing_skills: [{list of existing skill names}]
intent_hint: '{intent_hint or empty string}'
scope_hint: '{scope_hint or empty string}'
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

