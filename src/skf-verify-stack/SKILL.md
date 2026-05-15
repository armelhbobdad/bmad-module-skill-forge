---
name: skf-verify-stack
description: Pre-code stack feasibility verification against architecture and PRD documents. Use when the user requests to "verify a tech stack" or "verify stack."
---

# Verify Stack

## Overview

Cross-references generated skills against architecture and PRD documents to produce a feasibility report with evidence-backed integration verdicts, coverage analysis, and requirements mapping. This is a read-only workflow — it never modifies skills or input documents, only reads and produces a feasibility report. Every verdict must cite specific APIs, types, or function signatures from the generated skills.

**Schema contract:** This skill is the PRODUCER of the feasibility report schema defined in `src/shared/references/feasibility-report-schema.md`. All report outputs emit `schemaVersion: "1.0"` in frontmatter, use only the defined verdict tokens (`Verified|Plausible|Risky|Blocked` per pair; `FEASIBLE|CONDITIONALLY_FEASIBLE|NOT_FEASIBLE` overall), follow the fixed section-heading order, and are written through `src/shared/scripts/skf-atomic-write.py write` to both the timestamped file and the stable `-latest.md` copy.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

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
| 1 | Initialize & Load Inputs | references/init.md | No (confirm) |
| 2 | Coverage Analysis | references/coverage.md | Yes |
| 3 | Integration Verification | references/integrations.md | Yes |
| 4 | Requirements Mapping | references/requirements.md | Yes |
| 5 | Synthesize Verdict | references/synthesize.md | Yes |
| 6 | Report | references/report.md | No (confirm) |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | architecture_doc_path [required], prd_path [optional] |
| **Gates** | step 1: Input Gate [use args] | step 6: Confirm Gate [C] |
| **Outputs** | `feasibility-report-{projectSlug}-{timestamp}.md` and `feasibility-report-{projectSlug}-latest.md` (copy, not symlink) per `src/shared/references/feasibility-report-schema.md` — with integration verdicts, coverage analysis, recommendations, and evidence sources |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`
   - `skills_output_folder`, `forge_data_folder`, `document_output_language`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `references/init.md` to begin the workflow.
