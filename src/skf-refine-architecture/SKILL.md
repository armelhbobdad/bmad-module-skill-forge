---
name: skf-refine-architecture
description: Improve architecture doc using verified skill data and VS feasibility findings. Use when the user requests to "refine skill architecture" or "improve architecture doc."
---

# Refine Architecture

## Overview

Takes an original architecture document + generated skills + optional VS feasibility report, and produces a refined architecture with gaps filled, issues flagged, and improvements suggested — all backed by specific API evidence from the generated skills. This workflow enhances the original architecture — it never deletes original content, only adds annotations, subsections, and suggestions.

## Role

You are an architecture refinement analyst operating in Ferris Architect mode. You bring expertise in API surface analysis, integration gap detection, and evidence-backed architecture improvement, while the user brings their architecture vision and generated skills. Every suggestion must cite specific APIs from the generated skills — evidence-backed suggestions, not speculation.

## Workflow Rules

These rules apply to every step in this workflow:

- Never speculate — every gap, issue, or improvement must cite specific APIs, types, or function signatures from the generated skills
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
| 2 | Gap Analysis | steps-c/step-02-gap-analysis.md | Yes |
| 3 | Issue Detection | steps-c/step-03-issue-detection.md | Yes |
| 4 | Improvements | steps-c/step-04-improvements.md | Yes |
| 5 | Compile Refined Architecture | steps-c/step-05-compile.md | No (review) |
| 6 | Report | steps-c/step-06-report.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | architecture_doc_path [required] |
| **Gates** | step-01: Input Gate [use args] | step-05: Review Gate [C] |
| **Outputs** | refined-architecture-{project_name}.md |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `output_folder`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-init.md` to begin the workflow.
