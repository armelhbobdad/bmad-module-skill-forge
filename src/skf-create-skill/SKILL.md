---
name: skf-create-skill
description: "Parses a skill-brief.yaml and source code to compile a verified SKILL.md with frontmatter, provenance map, and progressive disclosure references. Supports --batch for multiple briefs. Use when the user requests to 'create a skill', 'compile a skill', 'build a skill', 'generate a skill', or 'write a skill from a brief'."
---

# Create Skill

## Overview

Compiles a verified agent skill from a skill-brief.yaml and source code, producing an agentskills.io-compliant SKILL.md with provenance map, evidence report, and progressive disclosure references. Steps adapt behavior based on forge tier (Quick/Forge/Forge+/Deep). Zero hallucination tolerance: every instruction in the output must trace to source code with a confidence tier citation.

## Workflow Rules

These rules apply to every step in this workflow:

- Never include content in SKILL.md that cannot be cited to source code
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Load Brief | steps-c/step-01-load-brief.md | Yes |
| 2 | Ecosystem Check | steps-c/step-02-ecosystem-check.md | Conditional |
| 2b | CCC Discover | steps-c/sub/step-02b-ccc-discover.md | Yes |
| 3 | Extract | steps-c/step-03-extract.md | No (confirm) |
| 3b | Fetch Temporal | steps-c/sub/step-03b-fetch-temporal.md | Yes |
| 3c | Fetch Docs | steps-c/sub/step-03c-fetch-docs.md | Yes |
| 3d | Component Extraction | steps-c/step-03d-component-extraction.md | Conditional |
| 4 | Enrich | steps-c/step-04-enrich.md | Yes |
| 5 | Compile | steps-c/step-05-compile.md | Yes |
| 6 | Validate | steps-c/step-06-validate.md | Conditional |
| 7 | Generate Artifacts | steps-c/step-07-generate-artifacts.md | Yes |
| 8 | Report | steps-c/step-08-report.md | Yes |
| 9 | Workflow Health Check | steps-c/step-09-health-check.md | Yes |

*Sub-steps under `steps-c/sub/` are conditional branches (CCC discovery, temporal/doc enrichment) kept out of the top-level step count so main-line steps 1–9 drive the workflow. Step 3d (Component Extraction) stays top-level as an alternative main step that replaces the standard extraction path when `scope.type: "component-library"`.*

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | brief_path (path to skill-brief.yaml) [required], --batch [optional] |
| **Gates** | step-02: Choice Gate [P] (if match) | step-03: Review Gate [C] |
| **Outputs** | SKILL.md, context-snippet.md, metadata.json, provenance-map.json, evidence-report.md, references/ |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `output_folder`, `user_name`, `communication_language`, `document_output_language`, `sidecar_path`, `skills_output_folder`, `forge_data_folder`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-load-brief.md` to begin the workflow.
