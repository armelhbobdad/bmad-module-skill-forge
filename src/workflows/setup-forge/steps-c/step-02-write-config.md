---
name: 'step-02-write-config'
description: 'Write forge-tier.yaml, create preferences.yaml defaults, ensure forge-data/ exists'

nextStepFile: './step-03-auto-index.md'
---

# Step 2: Write Configuration

## STEP GOAL:

Write the detected tool availability and calculated tier to forge-tier.yaml, create preferences.yaml with defaults if it does not exist, and ensure the forge-data/ directory is present.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 🎯 Execute all operations autonomously — no user interaction

### Role Reinforcement:

- ✅ You are a system executor writing configuration files
- ✅ File operations must be precise — correct paths, correct YAML structure
- ✅ Preserve user data (preferences.yaml) — never overwrite existing

### Step-Specific Rules:

- 🎯 Focus only on writing configuration files and creating directories
- 🚫 FORBIDDEN to re-detect tools — use results from step-01
- 🚫 FORBIDDEN to overwrite existing preferences.yaml
- 💬 File write failures ARE errors — report clearly if they occur

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Write files to the forger-sidecar directory
- 📖 Use context from step-01 (detected_tools, calculated_tier)
- 🚫 FORBIDDEN to proceed if forge-tier.yaml write fails

## CONTEXT BOUNDARIES:

- Available: {detected_tools}, {calculated_tier}, {previous_tier} from step-01
- Focus: file I/O operations only
- Limits: do not modify preferences.yaml if it exists
- Dependencies: step-01 must have completed with tool detection results

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Write forge-tier.yaml

Write to `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml`:

```yaml
# Ferris Sidecar: Forge Tier State
# Written by setup-forge workflow

# Tool availability (detected during [SF] Setup Forge)
tools:
  ast_grep: {true/false from detection}
  gh_cli: {true/false from detection}
  qmd: {true/false from detection}

# Capability tier (derived from tool availability)
# Quick = no tools | Forge = ast-grep | Deep = ast-grep + gh + qmd
tier: {calculated_tier}
tier_detected_at: {current ISO timestamp}

# QMD collection registry (populated by create-skill, consumed by audit/update-skill)
# Each entry tracks a QMD collection created during skill workflows
qmd_collections: []
```

**This file is ALWAYS overwritten** on every run — it reflects current tool state.

If the write fails, report the error and halt the workflow.

### 2. Handle preferences.yaml

Check if `{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml` exists:

**If it does NOT exist (first run):** Create with defaults:

```yaml
# Ferris Sidecar: User Preferences
# Created by setup-forge workflow on first run
# Edit this file to customize Ferris behavior

# Override detected tier (set to Quick, Forge, or Deep to force a tier)
tier_override: ~

# Skill generation defaults
default_source_authority: community
default_confidence_threshold: 0.7
```

**If it DOES exist:** Do not modify. Preserve entirely.

### 3. Ensure forge-data/ Directory

Check if `{project-root}/forge-data/` directory exists:

- If missing: create it
- If exists: skip silently

### 4. Auto-Proceed

"**Proceeding to auto-index check...**"

#### Menu Handling Logic:

- After all file operations complete successfully, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after configuration is written

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN forge-tier.yaml has been written successfully and preferences.yaml exists (created or pre-existing) will you load and read fully `{nextStepFile}` to execute the auto-index step.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- forge-tier.yaml written with accurate tool booleans, tier, timestamp, and empty qmd_collections registry
- preferences.yaml exists (created with defaults on first run, preserved on re-run)
- forge-data/ directory exists (created or pre-existing)
- Auto-proceeded to step-03

### ❌ SYSTEM FAILURE:

- forge-tier.yaml write fails and workflow continues
- preferences.yaml overwritten when it already existed
- Incorrect tool values written (not matching step-01 detection)
- Missing tier_detected_at timestamp
- Re-detecting tools instead of using step-01 results

**Master Rule:** forge-tier.yaml must be written accurately. preferences.yaml must never be overwritten. These are the foundation for all downstream workflows.
