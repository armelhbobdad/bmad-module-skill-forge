---
name: skf-create-stack-skill
description: Consolidated project stack skill with integration patterns — code-mode (analyzes manifests) or compose-mode (synthesizes from existing skills + architecture doc). Use when the user requests to "create a stack skill."
---

# Create Stack Skill

## Overview

Produces a consolidated stack skill documenting how libraries connect. **Code-mode** analyzes dependency manifests and co-import patterns from actual source code. **Compose-mode** synthesizes from pre-generated individual skills and architecture documents when no codebase exists yet. Every finding must trace to actual code with file:line citations; in compose-mode, inferred integrations are permitted but must be labeled `[inferred from shared domain]`.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

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
- **Workflow state contract — `workflow_warnings[]` accumulator (M4):** every step that emits a warning ("log a warning", "record in workflow state for the evidence report", "Warning: ...", etc.) MUST append a structured entry to a single in-memory list named `workflow_warnings[]`. Each entry has the shape `{step: "step-NN", severity: "info|warn|error", code: "<short-slug>", message: "<human text>", context: {<optional fields>}}`. Step-07 surfaces these in `evidence-report.md`; step 8 may add validation findings; step 9 §5 reads the accumulated list and renders the user-facing "Warnings" section. Do not invent a per-step warning channel — there is exactly one accumulator for the whole workflow.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Mode Detection | references/init.md | No (confirm) |
| 2 | Detect Manifests | references/detect-manifests.md | Yes |
| 3 | Rank & Confirm Libraries | references/rank-and-confirm.md | No (confirm) |
| 4 | Parallel Extract | references/parallel-extract.md | Yes |
| 5 | Detect Integrations | references/detect-integrations.md | Yes |
| 6 | Compile Stack | references/compile-stack.md | No (review) |
| 7 | Generate Output | references/generate-output.md | Yes |
| 8 | Validate | references/validate.md | Yes |
| 9 | Report | references/report.md | Yes |
| 10 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | project_path [required], mode (code/compose) [auto-detected] |
| **Gates** | step 3: Confirm Gate [C] | step 6: Review Gate [C] |
| **Outputs** | SKILL.md (stack), context-snippet.md, metadata.json |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`** with explicit precedence (B2):
   1. **Explicit disable wins.** If `--headless=false` or `--no-headless` was passed, `{headless_mode}` is `false` regardless of any preference.
   2. **Explicit enable next.** If `--headless` or `-H` was passed (without `=false`), `{headless_mode}` is `true`.
   3. **Preferences fallback.** Otherwise, read `headless_mode` from `{sidecar_path}/preferences.yaml` (`true` or `false`).
   4. **Default:** `false`.

3. Load, read the full file, and then execute `references/init.md` to begin the workflow.
