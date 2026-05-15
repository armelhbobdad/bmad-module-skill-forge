---
name: skf-test-skill
description: Cognitive completeness verification — quality gate before export. Use when the user requests to "test a skill" or "verify skill completeness."
---

# Test Skill

## Overview

Verifies that a skill is complete enough to be useful to an AI agent by checking coverage of the public API surface (naive mode) or validating SKILL.md + references coherence (contextual mode). Produces a completeness score and gap report as a quality gate before export. Every finding must trace to actual code with file:line citations.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

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
| 1 | Initialize & Load Skill | references/init.md | Yes |
| 2 | Detect Mode | references/detect-mode.md | Yes |
| 3 | Coverage Check | references/coverage-check.md | Yes |
| 4 | Coherence Check | references/coherence-check.md | Yes |
| 4b | External Validators | references/external-validators.md | Yes |
| 5 | Score | references/score.md | Yes |
| 6 | Report | references/report.md | No (confirm) |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required] |
| **Gates** | step 6: Confirm Gate [C] |
| **Outputs** | test-report-{skill_name}.md with completeness score and result (PASS/FAIL) |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `references/init.md` to begin the workflow.
