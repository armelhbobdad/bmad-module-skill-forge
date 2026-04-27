---
name: skf-setup
description: Initialize forge environment, detect tools, and set capability tier (Quick/Forge/Forge+/Deep). Use when the user requests to "set up" or "initialize the forge."
---

# Setup Forge

## Overview

Initializes the forge environment by detecting available tools, determining the capability tier (Quick/Forge/Forge+/Deep), and writing persistent configuration to `_bmad/_memory/forger-sidecar/`. When `ccc` (cocoindex-code) is available, also augments `.cocoindex_code/settings.yml` with SKF exclusion patterns and creates or refreshes the project's semantic-search index. On Deep tier, reconciles the QMD collection registry; whenever ccc is available, reconciles the CCC index registry as well. The workflow is autonomous with one optional gate — orphaned QMD collection removal in step 3 (Deep tier only; default action: Keep) — which auto-resolves to the default when `{headless_mode}` is true.

## Role

You are a system executor performing environment resolution. Run each step in sequence, write configuration files, and report results at completion.

## Workflow Rules

These rules apply to every step in this workflow:

- Autonomous with one optional gate (step 3 orphan-removal prompt; default: Keep) — all other steps auto-proceed with no user interaction until the final report
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Detect Tools & Set Tier | steps-c/step-01-detect-and-tier.md | Yes |
| 1b | CCC Index (only when ccc is available) | steps-c/step-01b-ccc-index.md | Yes |
| 2 | Write Config | steps-c/step-02-write-config.md | Yes |
| 3 | QMD + CCC Registry Hygiene | steps-c/step-03-auto-index.md | Yes |
| 4 | Report | steps-c/step-04-report.md | Yes |
| 5 | Workflow Health Check | steps-c/step-05-health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | (none) |
| **Gates** | One optional: orphaned QMD collection removal (step 3, Deep tier only; default: Keep) |
| **Outputs** | `forger-sidecar/forge-tier.yaml`, `forger-sidecar/preferences.yaml`, `{forge_data_folder}/`; when ccc is available, `.cocoindex_code/settings.yml` (exclusion patterns merged) and the project ccc index |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name` (from installer-generated config.yaml, not module.yaml), `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-detect-and-tier.md` to begin the workflow.
