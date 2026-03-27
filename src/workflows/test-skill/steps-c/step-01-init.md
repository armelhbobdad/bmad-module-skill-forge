---
name: 'step-01-init'
description: 'Discover skill, load forge tier state, validate inputs, create test report'

nextStepFile: './step-02-detect-mode.md'
outputFile: '{forge_data_folder}/{skill_name}/test-report-{skill_name}.md'
templateFile: '../templates/test-report-template.md'
sidecarFile: '{sidecar_path}/forge-tier.yaml'
skillsOutputFolder: '{skills_output_folder}'
---

# Step 1: Initialize Test

## STEP GOAL:

Discover and validate the target skill, load forge tier state to determine analysis depth, and create the test report document from template.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER proceed if required inputs are missing — halt with clear error
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor operating in Ferris's Audit mode
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Methodical, precise, evidence-based — zero hallucination
- ✅ Every finding must trace to actual artifacts

### Step-Specific Rules:

- 🎯 Focus only on input discovery and validation — do NOT begin analysis
- 🚫 FORBIDDEN to start coverage or coherence checks in this step
- 💬 Report what was found clearly and concisely
- 📋 Validate all required files exist before proceeding

## EXECUTION PROTOCOLS:

- 🎯 Discover skill path from user input or batch list
- 💾 Create output document from {templateFile}
- 📖 Load forge tier state from {sidecarFile}
- 🚫 FORBIDDEN to proceed if SKILL.md is missing

## CONTEXT BOUNDARIES:

- Available: User-provided skill path, SKF module config
- Focus: Input validation and tier detection only
- Limits: Do not analyze skill content — just confirm it exists and is loadable
- Dependencies: setup-forge must have run (forge-tier.yaml must exist)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Receive Skill Path

If skill path was provided as workflow argument, use it directly.

If no path provided, ask:

"**Which skill would you like to test?**

Provide the skill path or name. I'll search in `{skillsOutputFolder}`.

**Path or name:**"

### 2. Validate Skill Exists

Check that the skill directory contains required files:

**Required files:**
- `{skillsOutputFolder}/{skill_name}/SKILL.md` — the skill documentation
- `{skillsOutputFolder}/{skill_name}/metadata.json` — skill metadata

**If SKILL.md missing:**
"**Error: SKILL.md not found at `{skillsOutputFolder}/{skill_name}/SKILL.md`**

This skill has not been created yet. Run the **create-skill** workflow first."

HALT — do not proceed.

**If metadata.json missing:**
"**Warning:** metadata.json not found. Proceeding with limited metadata. Some checks may be skipped."

### 3. Validate Frontmatter Compliance

Before proceeding to content analysis, verify that SKILL.md has valid agentskills.io frontmatter. This catches compliance issues early, regardless of which workflow generated the skill.

**Check the following:**
- [ ] SKILL.md begins with `---` and has a closing `---` (frontmatter present)
- [ ] `name` field exists, non-empty, lowercase alphanumeric + hyphens, 1-64 chars
- [ ] `name` matches the skill directory name
- [ ] `description` field exists, non-empty, 1-1024 chars
- [ ] No unknown frontmatter fields (only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are permitted)

**If frontmatter is missing or invalid:**
"**Warning: SKILL.md frontmatter is non-compliant with agentskills.io specification.**

{list specific issues}

This skill will fail `npx skills add` and `npx skill-check check`. Consider fixing frontmatter before proceeding (run `npx skill-check check <skill-dir> --fix` to auto-fix deterministic issues)."

Log each issue as a pre-check finding. Continue with testing — frontmatter issues will be reported in the gap report alongside coverage/coherence findings.

### 4. Load Forge Tier State

Read `{sidecarFile}` to determine available analysis depth.

**If forge-tier.yaml exists:**
- Read `tier` value (Quick, Forge, Forge+, or Deep)
- Read tool availability flags (ast_grep, gh_cli, qmd)

**If forge-tier.yaml missing:**
"**Warning:** Forge tier not detected. Defaulting to **Quick** tier (structural checks only).

Run **setup-forge** to enable deeper analysis with AST-backed verification."

Default to Quick tier and continue.

### 4b. Apply Tier Override (if set)

Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), update `detected_tier` to the override value for use in subsequent steps and output documents.

### 5. Load Skill Metadata

Read `metadata.json` to extract:
- `name` — display name
- `skill_type` — single or stack (needed for mode detection)
- `source_path` — path to source code (if present)
- `generation_date` — when skill was generated
- `confidence_tier` — tier used during creation

If source path override was provided as optional input, use that instead.

### 6. Create Output Document

Create `{outputFile}` from `{templateFile}` with initial frontmatter:

```yaml
---
workflowType: 'test-skill'
skillName: '{skill_name}'
skillDir: '{skill_path}'
testMode: ''
forgeTier: '{detected_tier}'
testResult: ''
score: ''
threshold: ''
analysisConfidence: ''
testDate: '{current_date}'
stepsCompleted: ['step-01-init']
nextWorkflow: ''
---
```

### 7. Report Initialization Status

"**Test initialization complete.**

**Skill:** {skill_name}
**Path:** {skill_path}
**Type:** {skill_type}
**Forge Tier:** {detected_tier}
**Source:** {source_path}

**Proceeding to mode detection...**"

### 8. Auto-Proceed

Display: "**Proceeding to mode detection...**"

#### Menu Handling Logic:

- After initialization is complete, update {outputFile} frontmatter stepsCompleted, then immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed initialization step with no user choices
- Proceed directly to next step after setup

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all required files are validated, forge tier is loaded, output document is created, and initialization status is reported, will you then load and read fully `{nextStepFile}` to execute mode detection.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Skill path validated (SKILL.md exists)
- Forge tier state loaded (or gracefully defaulted to Quick), override applied if set in preferences.yaml
- Skill metadata extracted
- Output document created from template with initial frontmatter
- Initialization status reported clearly
- Auto-proceeded to step 02

### ❌ SYSTEM FAILURE:

- Proceeding without validating SKILL.md exists
- Not loading forge tier state
- Not creating output document before proceeding
- Starting analysis in this step (coverage/coherence belongs to later steps)
- Hardcoding paths instead of using frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
