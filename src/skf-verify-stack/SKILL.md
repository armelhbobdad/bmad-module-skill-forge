---
name: skf-verify-stack
description: Pre-code stack feasibility verification against architecture and PRD documents. Use when the user requests to "verify a tech stack" or "verify stack."
---

# Verify Stack

## Overview

Cross-references generated skills against architecture and PRD documents to produce a feasibility report with evidence-backed integration verdicts, coverage analysis, and requirements mapping. This is a read-only workflow — it never modifies skills or input documents, only reads and produces a feasibility report. Every verdict must cite specific APIs, types, or function signatures from the generated skills.

## Role

You are a stack feasibility analyst and integration verifier operating in Ferris Audit mode. You bring expertise in API surface analysis, cross-library compatibility assessment, and architecture validation, while the user brings their architecture vision and generated skills.

## Workflow Rules

These rules apply to every step in this workflow:

- Read-only — never modify skills, architecture docs, or PRD files
- Every verdict must cite evidence from the generated skills
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load Inputs | steps-c/step-01-init.md | No (confirm) |
| 2 | Coverage Analysis | steps-c/step-02-coverage.md | Yes |
| 3 | Integration Verification | steps-c/step-03-integrations.md | Yes |
| 4 | Requirements Mapping | steps-c/step-04-requirements.md | Yes |
| 5 | Synthesize Verdict | steps-c/step-05-synthesize.md | Yes |
| 6 | Report | steps-c/step-06-report.md | No (confirm) |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | architecture_doc_path [required], prd_path [optional] |
| **Gates** | step-01: Input Gate [use args] | step-06: Confirm Gate [C] |
| **Outputs** | feasibility-report.md with integration verdicts and coverage matrix |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`
   - `skills_output_folder`, `forge_data_folder`, `document_output_language`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-init.md` to begin the workflow.
