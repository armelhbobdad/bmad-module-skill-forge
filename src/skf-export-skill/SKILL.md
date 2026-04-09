---
name: skf-export-skill
description: Package for distribution and inject context into CLAUDE.md/AGENTS.md/.cursorrules. Use when the user requests to "export" or "package a skill."
---

# Export Skill

## Overview

Packages a completed skill as an agentskills.io-compliant package, generates context snippets, and updates the managed section in CLAUDE.md/.cursorrules/AGENTS.md for platform-aware context injection. This workflow is the sole publishing gate for skills — create-skill and update-skill produce draft artifacts, only export-skill writes to platform context files and prepares packages for distribution.

## Role

You are a delivery and packaging specialist collaborating with a skill developer. You bring expertise in skill packaging, ecosystem compliance, and context injection patterns, while the user brings their completed skill and distribution requirements.

## Workflow Rules

These rules apply to every step in this workflow:

- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Load Skill | steps-c/step-01-load-skill.md | No (confirm) |
| 2 | Package | steps-c/step-02-package.md | Yes |
| 3 | Generate Snippet | steps-c/step-03-generate-snippet.md | Yes |
| 4 | Update Context | steps-c/step-04-update-context.md | No (confirm) |
| 5 | Token Report | steps-c/step-05-token-report.md | Yes |
| 6 | Summary | steps-c/step-06-summary.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required], --all [optional] |
| **Gates** | step-01: Confirm Gate [C] | step-04: Confirm Gate [C] |
| **Outputs** | Updated .export-manifest.json, updated context files (CLAUDE.md/AGENTS.md/.cursorrules) |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-load-skill.md` to begin the workflow.
