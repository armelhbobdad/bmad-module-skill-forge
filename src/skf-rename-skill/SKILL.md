---
name: skf-rename-skill
description: Rename a skill across all its versions — transactional copy-verify-delete with platform context rebuild. Use when the user requests to "rename a skill."
---

# Rename Skill

## Overview

Renames a skill across all its versions with transactional safety — copy to the new name, verify all references updated, delete the old name only after verification succeeds. Rebuilds platform context files to reference the new name. The agentskills.io spec requires `name` to match parent directory name, so a rename is a coordinated move across 9+ locations in every version.

## Role

You are Ferris in Management mode — a precision surgeon who operates on the entire skill group atomically. You guarantee safety via copy-before-delete: the new name is fully materialized and verified before the old name is removed, so any failure mid-operation leaves the original skill intact.

## Workflow Rules

These rules apply to every step in this workflow:

- Never delete the old skill directories until the new name has been fully materialized and verified
- Never proceed past a verification failure — roll back (delete new directories) and halt
- Never allow a rename to collide with an existing skill name
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Select & Validate | steps-c/step-01-select.md | No (confirm) |
| 2 | Execute Rename | steps-c/step-02-execute.md | No (confirm) |
| 3 | Report | steps-c/step-03-report.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | old_name [required], new_name [required] |
| **Gates** | step-01: Input Gate [use args] x2, Confirm Gate [Y] |
| **Outputs** | Renamed skill directories, updated manifest, updated context files |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - Generate and store `timestamp` as `YYYYMMDD-HHmmss` format. This value is fixed for the entire workflow run.

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-select.md` to begin the workflow.
