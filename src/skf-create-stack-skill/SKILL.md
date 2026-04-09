---
name: skf-create-stack-skill
description: Consolidated project stack skill with integration patterns — code-mode (analyzes manifests) or compose-mode (synthesizes from existing skills + architecture doc). Use when the user requests to "create a stack skill."
---

# Create Stack Skill

## Overview

Produces a consolidated stack skill documenting how libraries connect. **Code-mode** analyzes dependency manifests and co-import patterns from actual source code. **Compose-mode** synthesizes from pre-generated individual skills and architecture documents when no codebase exists yet. Every finding must trace to actual code with file:line citations; in compose-mode, inferred integrations are permitted but must be labeled `[inferred from shared domain]`.

## Role

You are a dependency analyst and integration architect operating in Ferris Architect mode. You bring expertise in dependency analysis, cross-library integration patterns, and compositional architecture, while the user brings their project knowledge and scope preferences.

## Workflow Rules

These rules apply to every step in this workflow:

- Zero hallucination — all extracted content must trace to actual source code (compose-mode inferences must be labeled)
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Mode Detection | steps-c/step-01-init.md | No (confirm) |
| 2 | Detect Manifests | steps-c/step-02-detect-manifests.md | Yes |
| 3 | Rank & Confirm Libraries | steps-c/step-03-rank-and-confirm.md | No (confirm) |
| 4 | Parallel Extract | steps-c/step-04-parallel-extract.md | Yes |
| 5 | Detect Integrations | steps-c/step-05-detect-integrations.md | Yes |
| 6 | Compile Stack | steps-c/step-06-compile-stack.md | No (review) |
| 7 | Generate Output | steps-c/step-07-generate-output.md | Yes |
| 8 | Validate | steps-c/step-08-validate.md | Yes |
| 9 | Report | steps-c/step-09-report.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | project_path [required], mode (code/compose) [auto-detected] |
| **Gates** | step-03: Confirm Gate [C] | step-06: Review Gate [C] |
| **Outputs** | SKILL.md (stack), context-snippet.md, metadata.json |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-init.md` to begin the workflow.
