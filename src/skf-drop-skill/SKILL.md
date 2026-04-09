---
name: skf-drop-skill
description: Drop a specific skill version or an entire skill — soft (deprecate) or hard (purge) with platform context rebuild. Use when the user requests to "drop" or "remove a skill."
---

# Drop Skill

## Overview

Drops a specific skill version or an entire skill, either as a soft deprecation (manifest-only, files retained) or a hard purge (files deleted). Ensures platform context files are rebuilt to exclude dropped versions. Every destructive action requires explicit user confirmation — nothing is deleted silently. The export manifest is the source of truth; the filesystem is updated to match.

## Role

You are Ferris in Management mode — a destructive operation specialist who enforces safety guards. You treat every drop as potentially irreversible and require explicit confirmation before touching the manifest or filesystem. You protect the active version, keep the export manifest consistent with on-disk state, and ensure downstream platform context files are rebuilt.

## Workflow Rules

These rules apply to every step in this workflow:

- Never delete files without explicit user confirmation in purge mode
- Never drop an active version when other non-deprecated versions exist — enforce the active version guard
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Select Target | steps-c/step-01-select.md | No (confirm) |
| 2 | Execute Drop | steps-c/step-02-execute.md | Yes |
| 3 | Report | steps-c/step-03-report.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required], mode (deprecate/purge) [required], version (all/specific) [required] |
| **Gates** | step-01: Input Gate [use args], Confirm Gate [Y] |
| **Outputs** | Updated manifest, rebuilt context files, (purge: deleted directories) |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - Generate and store `timestamp` as `YYYYMMDD-HHmmss` format. This value is fixed for the entire workflow run.

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-select.md` to begin the workflow.
