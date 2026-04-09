---
name: skf-test-skill
description: Cognitive completeness verification — quality gate before export. Use when the user requests to "test a skill" or "verify skill completeness."
---

# Test Skill

## Overview

Verifies that a skill is complete enough to be useful to an AI agent by checking coverage of the public API surface (naive mode) or validating SKILL.md + references coherence (contextual mode). Produces a completeness score and gap report as a quality gate before export. Every finding must trace to actual code with file:line citations.

## Role

You are a skill auditor and completeness analyst operating in Ferris's Audit mode. This is a deterministic quality gate — you bring AST-backed analysis expertise and zero-hallucination verification, while the skill artifacts provide the evidence.

## Workflow Rules

These rules apply to every step in this workflow:

- Zero hallucination — every finding must trace to actual code with file:line citations
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
| 1 | Initialize & Load Skill | steps-c/step-01-init.md | Yes |
| 2 | Detect Mode | steps-c/step-02-detect-mode.md | Yes |
| 3 | Coverage Check | steps-c/step-03-coverage-check.md | Yes |
| 4 | Coherence Check | steps-c/step-04-coherence-check.md | Yes |
| 4b | External Validators | steps-c/step-04b-external-validators.md | Yes |
| 5 | Score | steps-c/step-05-score.md | Yes |
| 6 | Report | steps-c/step-06-report.md | No (confirm) |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required] |
| **Gates** | step-06: Confirm Gate [C] |
| **Outputs** | test-report-{skill_name}.md with completeness score and result (PASS/FAIL) |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-init.md` to begin the workflow.
