---
nextStepFile: './step-03-auto-index.md'
---

# Step 2: Write Configuration

## STEP GOAL:

Write the detected tool availability and calculated tier to forge-tier.yaml, create preferences.yaml with defaults if it does not exist, and ensure the forge-data/ directory is present.

## Rules

- Focus only on writing configuration files and creating directories
- Do not re-detect tools — use results from step-01
- Do not overwrite existing preferences.yaml
- File write failures are errors — report clearly

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Write forge-tier.yaml

Write to `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml`:

```yaml
# Ferris Sidecar: Forge Tier State
# Written by setup workflow

# Tool availability (detected during [SF] Setup Forge)
tools:
  ast_grep: {true/false from detection}
  gh_cli: {true/false from detection}
  qmd: {true/false from detection}
  ccc: {true/false from detection}
  ccc_daemon: {ccc_daemon from step-01 if available: "healthy"|"stopped"|"error", or ~}
  security_scan: {true/false — true when SNYK_TOKEN is set}

# Capability tier (derived from tool availability)
# Quick = no tools | Forge = + ast-grep | Forge+ = + ast-grep + ccc | Deep = + ast-grep + gh + QMD
tier: {calculated_tier}
tier_detected_at: {current ISO timestamp}

# CCC semantic index state (managed by setup step-01b and extraction workflows)
ccc_index:
  indexed_path: {ccc_indexed_path from step-01b, or ~}
  last_indexed: {ccc_last_indexed from step-01b, or ~}
  status: {ccc_index_result from step-01b: "fresh"|"created"|"none"|"failed"}
  staleness_threshold_hours: 24
  file_count: {ccc_file_count from step-01b, or ~}
  exclude_patterns: {ccc_exclude_patterns from step-01b, or []}

# CCC index registry (tracks which source paths have been indexed for skill workflows)
# PRESERVE existing entries on re-runs — see Note below
ccc_index_registry: {preserved from existing forge-tier.yaml, or [] if first run}

# QMD collection registry (populated by create-skill, consumed by audit/update-skill)
# PRESERVE existing entries on re-runs — see Note below
qmd_collections: {preserved from existing forge-tier.yaml, or [] if first run}
```

**Note on re-runs:** The `qmd_collections`, `ccc_index_registry` arrays, and `staleness_threshold_hours` value must be preserved across re-runs. Before overwriting forge-tier.yaml, read these existing values and re-inject them into the new write. These values are populated by create-skill workflows or customized by users and must not be reset. Note: `exclude_patterns` is NOT preserved — it is always written fresh from `{ccc_exclude_patterns}` computed by step-01b.

**This file is ALWAYS overwritten** on every run — it reflects current tool state.

If the write fails, report the error and halt the workflow.

### 2. Handle preferences.yaml

Check if `{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml` exists:

**If it does NOT exist (first run):** Create with defaults:

```yaml
# Ferris Sidecar: User Preferences
# Created by setup workflow on first run
# Edit this file to customize Ferris behavior

# Override detected tier (set to Quick, Forge, Forge+, or Deep to force a tier)
tier_override: ~

# Passive context injection (set to false to skip snippet generation and CLAUDE.md updates during export)
passive_context: true

# Headless mode (set to true to skip confirmation gates in all workflows)
headless_mode: false

# Compact greeting (set to true to skip the full capabilities table on session start)
compact_greeting: false

# Reserved for future use — these fields are not yet consumed by any workflow step
# output_language: ~
# skill_format_version: ~
# citation_style: ~
# confidence_display: ~
```

**If it DOES exist:** Do not modify. Preserve entirely.

### 3. Ensure forge-data/ Directory

Check if `{forge_data_folder}` directory exists:

- If missing: create it
- If exists: skip silently

### 4. Auto-Proceed

"**Proceeding to QMD collection hygiene...**"

#### Menu Handling Logic:

- After all file operations complete successfully, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after configuration is written

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN forge-tier.yaml has been written successfully and preferences.yaml exists (created or pre-existing) will you load and read fully `{nextStepFile}` to execute the QMD hygiene step.

