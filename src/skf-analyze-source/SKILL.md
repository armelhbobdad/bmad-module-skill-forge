---
name: skf-analyze-source
description: Discover what to skill in a large repo and produce recommended skill briefs. Use when the user requests to "analyze source for skills" or "discover skill opportunities."
---

# Analyze Source

## Overview

Analyzes a large repo or multi-service project to identify discrete skillable units, map exports and integration points, and produce recommended skill-brief.yaml files as the primary entry point for brownfield onboarding. The analysis must be thorough enough to produce actionable briefs, but scoped enough to avoid overwhelming the user with false positives. Scanning depth adapts to forge tier — Quick (file structure), Forge (AST), Forge+ (AST + CCC semantic pre-ranking), Deep (AST+QMD).

## Role

You are a source code analyst and decomposition architect collaborating with a developer onboarding an existing project. You bring expertise in codebase analysis, service boundary detection, and skill scoping, while the user brings their domain knowledge. Work together as equals.

## Workflow Rules

These rules apply to every step in this workflow:

- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- Update `stepsCompleted` in output file frontmatter before loading next step
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize | steps-c/step-01-init.md | Yes |
| 1b | Continue (session resume) | steps-c/step-01b-continue.md | Yes |
| 2 | Scan Project | steps-c/step-02-scan-project.md | No (confirm) |
| 3 | Identify Units | steps-c/step-03-identify-units.md | No (confirm) |
| 4 | Map & Detect | steps-c/step-04-map-and-detect.md | Yes |
| 5 | Recommend | steps-c/step-05-recommend.md | No (confirm) |
| 6 | Generate Briefs | steps-c/step-06-generate-briefs.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | project_path [required], scope_hint [optional] |
| **Gates** | step-02: Confirm Gate [C] | step-03: Confirm Gate [C] | step-05: Confirm Gate [C] |
| **Outputs** | analysis-report.md, skill-brief.yaml files (one per recommended unit) |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `forge_data_folder`, `skills_output_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-init.md` to begin the workflow.
