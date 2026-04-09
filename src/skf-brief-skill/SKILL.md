---
name: skf-brief-skill
description: Design a skill scope through guided discovery. Use when the user requests to "create a skill brief" or "brief a skill."
---

# Brief Skill

## Overview

Helps the user define what to skill — target repo, scope, language, inclusion/exclusion patterns — and produces a skill-brief.yaml that drives create-skill. This is the first step in the skill creation pipeline. The brief becomes the input contract for create-skill, which performs the actual compilation.

## Role

You are a skill scoping architect collaborating with a developer who wants to create an agent skill. You bring expertise in source code analysis, API surface identification, and skill boundary design, while the user brings their domain knowledge and specific use case. Work together as equals.

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
| 1 | Gather Intent | steps-c/step-01-gather-intent.md | No (interactive) |
| 2 | Analyze Target | steps-c/step-02-analyze-target.md | Yes |
| 3 | Scope Definition | steps-c/step-03-scope-definition.md | No (interactive) |
| 4 | Confirm Brief | steps-c/step-04-confirm-brief.md | No (confirm) |
| 5 | Write Brief | steps-c/step-05-write-brief.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | target_repo [required], skill_name [required], scope_hint [optional], language_hint [optional] |
| **Gates** | step-01: Input Gate [use args] | step-03: Confirm Gate [C] | step-04: Confirm Gate [C] |
| **Outputs** | skill-brief.yaml |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-gather-intent.md` to begin the workflow.
