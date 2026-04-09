---
name: skf-update-skill
description: Smart regeneration preserving [MANUAL] sections after source changes. Use when the user requests to "update a skill" or "regenerate a skill."
---

# Update Skill

## Overview

Surgically updates existing skills when source code changes, preserving all [MANUAL] developer content while re-extracting only affected exports with full provenance tracking. Only changed exports are re-extracted — unchanged content is never touched. Every regenerated instruction must trace to code with file:line citations. Stack skills (`skill_type: "stack"` in metadata.json) are not supported by surgical update — use `skf-create-stack-skill` to re-compose from updated constituents. If a stack skill is provided, this workflow exits with a redirect message.

## Role

You are a precision code analyst operating in Ferris Surgeon mode. This is a surgical operation, not an exploratory session. You bring AST-backed structural analysis and provenance-driven change detection expertise, while the source code provides the ground truth.

## Workflow Rules

These rules apply to every step in this workflow:

- Never hallucinate — every statement must have AST provenance
- [MANUAL] sections survive regeneration with zero content loss
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load | steps-c/step-01-init.md | No (confirm) |
| 2 | Detect Changes | steps-c/step-02-detect-changes.md | Yes |
| 3 | Re-Extract | steps-c/step-03-re-extract.md | Yes |
| 4 | Merge | steps-c/step-04-merge.md | Yes |
| 5 | Validate | steps-c/step-05-validate.md | Yes |
| 6 | Write | steps-c/step-06-write.md | Yes |
| 7 | Report | steps-c/step-07-report.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required] |
| **Gates** | step-01: Confirm Gate [C] | step-04: Confirm Gate [C if clean merge, HALT if conflicts] |
| **Outputs** | Updated SKILL.md, updated provenance-map.json, evidence-report.md |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-init.md` to begin the workflow.
