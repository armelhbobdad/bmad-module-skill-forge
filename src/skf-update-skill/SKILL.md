---
name: skf-update-skill
description: Smart regeneration preserving [MANUAL] sections after source changes. Use when the user requests to "update a skill" or "regenerate a skill."
---

# Update Skill

## Overview

Surgically updates existing skills when source code changes, preserving all [MANUAL] developer content while re-extracting only affected exports with full provenance tracking. Only changed exports are re-extracted — unchanged content is never touched. Every regenerated instruction must trace to code with file:line citations. Stack skills (`skill_type: "stack"` in metadata.json) are not supported by surgical update — use `skf-create-stack-skill` to re-compose from updated constituents. If a stack skill is provided, this workflow exits with a redirect message.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Cross-skill data coupling:** stages in this workflow load four shared assets from `skf-create-skill` to keep extraction semantics aligned between create and update — `re-extract.md` pulls `extraction-patterns.md`, `extraction-patterns-tracing.md`, and `tier-degradation-rules.md` from `skf-create-skill/references/`; `remote-source-resolution.md` references `source-resolution-protocols.md`; `write.md` reads `skill-sections.md` from `skf-create-skill/assets/`. Update-skill assumes these files are present at install time and that their semantics are stable across the two skills' versions.

## Role

You are a precision code analyst operating in Ferris Surgeon mode. This is a surgical operation, not an exploratory session. You bring AST-backed structural analysis and provenance-driven change detection expertise, while the source code provides the ground truth.

## Workflow Rules

These rules apply to every step in this workflow:

- Never hallucinate — every statement must have AST provenance
- [MANUAL] sections survive regeneration with zero content loss
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load | references/init.md | No (confirm) |
| 2 | Detect Changes | references/detect-changes.md | Yes |
| 3 | Re-Extract | references/re-extract.md | Yes |
| 4 | Merge | references/merge.md | Yes |
| 5 | Validate | references/validate.md | Yes |
| 6 | Write | references/write.md | Yes |
| 7 | Report | references/report.md | Yes |
| 8 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required] |
| **Gates** | step 1: Confirm Gate [C] | step 4: Confirm Gate [C if clean merge, HALT if conflicts] |
| **Outputs** | Updated SKILL.md, updated provenance-map.json, evidence-report.md |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `references/init.md` to begin the workflow.
