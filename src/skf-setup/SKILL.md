---
name: skf-setup
description: Initialize forge environment, detect tools, and set capability tier (Quick/Forge/Forge+/Deep). Use when the user requests to "set up" or "initialize the forge."
---

# Setup Forge

## Overview

Initializes the forge environment by detecting available tools, determining the capability tier (Quick/Forge/Forge+/Deep), and writing persistent configuration to `{project-root}/_bmad/_memory/forger-sidecar/`. When `ccc` (cocoindex-code) is available, also augments `.cocoindex_code/settings.yml` with SKF exclusion patterns and creates or refreshes the project's semantic-search index. On Deep tier, reconciles the QMD collection registry; whenever ccc is available, reconciles the CCC index registry as well. The workflow is autonomous with one optional gate — orphaned QMD collection removal in step 3 (Deep tier only; default action: Keep) — which auto-resolves to the default when `{headless_mode}` is true.

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
| **Flags** | `--headless` / `-H` (skip prompts, auto-resolve gates to defaults); `--require-tier=<Quick\|Forge\|Forge+\|Deep>` (halt with failure if calculated tier does not satisfy the requirement) |
| **Gates** | One optional: orphaned QMD collection removal (step 3, Deep tier only; default: Keep) |
| **Outputs** | `forger-sidecar/forge-tier.yaml`, `forger-sidecar/preferences.yaml`, `{forge_data_folder}/`; when ccc is available, `.cocoindex_code/settings.yml` (exclusion patterns merged) and the project ccc index |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. step-04 emits a single-line `SKF_SETUP_RESULT_JSON: {…}` envelope after the human-readable banner so pipelines can parse the outcome without reading forge-tier.yaml. Schema documented in `steps-c/step-04-report.md` §4. |
| **Failure modes** | `--require-tier` not satisfied → step-04 prints a "REQUIRED TIER NOT MET" block, the JSON envelope sets `"require_tier_satisfied": false`, and the workflow halts before step-05. |
| **Exit codes** | The workflow runs as an LLM-driven sequence rather than a CLI process, so "exit code" describes the agent's terminal state for a calling pipeline that reads `SKF_SETUP_RESULT_JSON`. **0 — success** (no JSON `error` field, all writes completed, `require_tier_satisfied` is `true` or `null`). **1 — required-tier failure** (`require_tier_satisfied` is `false`; envelope still emitted with full state for diagnosis). **2 — write failure** (forge-tier.yaml or preferences.yaml could not be written; envelope `error` field names the path and reason). Pipelines should branch on the JSON `require_tier_satisfied` and `error` fields rather than process exit codes. |

## On Activation

1. **Probe `uv` runtime.** Run `uv --version`. Every step in this workflow invokes shared Python helpers via `uv run` (PEP 723 inline metadata is what auto-resolves `pyyaml` for the helpers that need it — see `docs/getting-started.md`). If `uv` is missing, halt now with a single cohesive diagnostic rather than letting five separate steps each fail with `uv: command not found`:

   "**Setup cannot proceed: `uv` is not installed.** SKF helpers depend on `uv` to auto-resolve their Python dependencies. Install it from <https://docs.astral.sh/uv/getting-started/installation/> and re-run `/skf-setup`. (See the Prerequisites section in <https://docs.astral.sh/uv/getting-started/installation/> or the SKF docs at `docs/getting-started.md` for details.)"

2. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name` (from installer-generated config.yaml, not module.yaml), `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

3. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

4. **Resolve `{require_tier}`**: parse `--require-tier=<value>` from the invocation arguments. Accept exactly `Quick`, `Forge`, `Forge+`, or `Deep` (case-sensitive). If absent or unparseable, leave as null (no tier requirement).

5. Load, read the full file, and then execute `./steps-c/step-01-detect-and-tier.md` to begin the workflow.
