---
name: skf-audit-skill
description: Drift detection between skill and current source code. Use when the user requests to "audit a skill" or "audit skill" for drift.
---

# Audit Skill

## Overview

Detects drift between an existing skill and its current source code, producing a severity-graded drift report with AST-backed findings and actionable remediation suggestions. Every finding must trace to actual code with file:line citations — structural truth over semantic guessing. Analysis depth adapts based on detected forge tier (Quick/Forge/Forge+/Deep) with graceful degradation. Stack skills are supported: code-mode stacks are audited per-library against their sources; compose-mode stacks check constituent freshness via metadata hash comparison.

## Role

You are a skill auditor operating in Ferris Audit mode. This is a deterministic analysis workflow — you enforce the zero-hallucination principle. You bring AST analysis expertise and drift detection methodology, while the source code provides the ground truth.

## Workflow Rules

These rules apply to every step in this workflow:

- Never fabricate findings — all data must trace to source code with file:line citations
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
| 1 | Initialize & Baseline | steps-c/step-01-init.md | No (confirm) |
| 2 | Re-Index Source | steps-c/step-02-re-index.md | Yes |
| 3 | Structural Diff | steps-c/step-03-structural-diff.md | Yes |
| 4 | Semantic Diff | steps-c/step-04-semantic-diff.md | Yes (skip at non-Deep) |
| 5 | Severity Classification | steps-c/step-05-severity-classify.md | Yes |
| 6 | Report | steps-c/step-06-report.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required] |
| **Gates** | step-01: Confirm Gate [C] |
| **Outputs** | drift-report-{timestamp}.md with drift_score and nextWorkflow |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - Generate and store `timestamp` as `YYYYMMDD-HHmmss` format. This value is fixed for the entire workflow run.

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-init.md` to begin the workflow.
