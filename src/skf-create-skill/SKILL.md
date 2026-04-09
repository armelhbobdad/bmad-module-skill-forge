---
name: skf-create-skill
description: Compile a skill from a brief. Supports --batch for multiple briefs. Use when the user requests to "create a skill" or "compile a skill."
---

# Create Skill

## Overview

Compiles a verified agent skill from a skill-brief.yaml and source code, producing an agentskills.io-compliant SKILL.md with provenance map, evidence report, and progressive disclosure references. The workflow is mostly autonomous with three interaction points — after ecosystem check (if match found), after source extraction (to confirm findings), and after content quality review (when tessl produces suggestions). Steps adapt behavior based on forge tier (Quick/Forge/Forge+/Deep). Zero hallucination tolerance: every instruction in the output must trace to source code with a confidence tier citation.

## Role

You are operating in Ferris Architect mode — a skill compilation engine performing structural extraction and assembly. Apply zero hallucination tolerance: uncitable content is excluded, not guessed.

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
| 2b | CCC Discover | steps-c/step-02b-ccc-discover.md | Yes |
| 3 | Extract | steps-c/step-03-extract.md | No (confirm) |
| 3b | Fetch Temporal | steps-c/step-03b-fetch-temporal.md | Yes |
| 3c | Fetch Docs | steps-c/step-03c-fetch-docs.md | Yes |
| 3d | Component Extraction | steps-c/step-03d-component-extraction.md | Conditional |
| 4 | Enrich | steps-c/step-04-enrich.md | Yes |
| 5 | Compile | steps-c/step-05-compile.md | Yes |
| 6 | Validate | steps-c/step-06-validate.md | Conditional |
| 7 | Generate Artifacts | steps-c/step-07-generate-artifacts.md | Yes |
| 8 | Report | steps-c/step-08-report.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | brief_path (path to skill-brief.yaml) [required], --batch [optional] |
| **Gates** | step-02: Choice Gate [P] (if match) | step-03: Review Gate [C] |
| **Outputs** | SKILL.md, context-snippet.md, metadata.json, provenance-map.json, evidence-report.md, references/ |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `sidecar_path`, `skills_output_folder`, `forge_data_folder`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-load-brief.md` to begin the workflow.
