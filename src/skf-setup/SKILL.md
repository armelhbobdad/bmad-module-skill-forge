---
name: skf-setup
description: Initialize forge environment, detect tools, and set capability tier (Quick/Forge/Forge+/Deep). Use when the user requests to "set up" or "initialize the forge".
---

# Setup Forge

## Overview

Initializes the forge environment by detecting available tools, determining the capability tier (Quick/Forge/Forge+/Deep), and writing persistent configuration to `{project-root}/_bmad/_memory/forger-sidecar/`. When `ccc` (cocoindex-code) is available, also augments `.cocoindex_code/settings.yml` with SKF exclusion patterns and creates or refreshes the project's semantic-search index. On Deep tier, reconciles the QMD collection registry; whenever ccc is available, reconciles the CCC index registry as well. The workflow is autonomous with one optional gate — orphaned QMD collection removal in step 3 (Deep tier only; default action: Keep) — which auto-resolves non-interactively when `{headless_mode}` is true or when `--orphan-action=<keep|remove>` is passed.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a system executor performing environment resolution. Run each step in sequence, write configuration files, and report results at completion.

## Workflow Rules

- One optional gate (step 3 orphan-removal prompt; default: Keep). Every other step auto-proceeds.
- Only load one step file at a time — never preload future steps.
- Communicate in `{communication_language}`.
- If `{headless_mode}` is true, or if `{orphan_action}` is non-null, auto-resolve the gate non-interactively and log the decision.

## Stages

All stages auto-proceed except the optional orphan-removal gate in step 3.

| # | Step | File |
|---|------|------|
| 1 | Detect Tools & Set Tier | references/detect-and-tier.md |
| 1b | CCC Index (only when ccc is available) | references/ccc-index.md |
| 2 | Write Config | references/write-config.md |
| 3 | QMD + CCC Registry Hygiene | references/auto-index.md |
| 4 | Report | references/report.md |
| 5 | Workflow Health Check | references/health-check.md |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | (none) |
| **Flags** | `--headless` / `-H` (skip prompts, auto-resolve gates to defaults); `--require-tier=<Quick\|Forge\|Forge+\|Deep>` (halt with failure if calculated tier does not satisfy the requirement); `--orphan-action=<keep\|remove>` (resolve the orphan-removal gate non-interactively, even outside `--headless`); `--ccc-skip-index` (skip CCC indexing; envelope `ccc_index.status` becomes `"skipped"`); `--quiet` (suppress the human-readable FORGE STATUS banner — pipelines and expert re-runners get the envelope only) |
| **Gates** | One optional: orphaned QMD collection removal (step 3, Deep tier only; default: Keep, or whatever `--orphan-action` set) |
| **Outputs** | `forger-sidecar/forge-tier.yaml`, `forger-sidecar/preferences.yaml`, `{forge_data_folder}/`; when ccc is available, `.cocoindex_code/settings.yml` (exclusion patterns merged) and the project ccc index |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Under `--headless` or `--quiet`, step 4 emits a single-line `SKF_SETUP_RESULT_JSON: {…}` envelope as the only stdout line — the FORGE STATUS banner is suppressed. Branch on the envelope's top-level `status` field (one of `success`, `tier_failure`, `write_failure`, `blocked`) — `skf-emit-result-envelope.py` derives it from the payload, so pipelines never compose it from `require_tier_satisfied` + `error`. Schema in `references/report.md` §4. |
| **Failure modes** | `--require-tier` not satisfied → status becomes `tier_failure`, the envelope sets `"require_tier_satisfied": false`, and the workflow halts before step 5 (interactive runs also print a "REQUIRED TIER NOT MET" block). |
| **Exit codes** | The workflow runs as an LLM-driven sequence rather than a CLI process, so "exit code" describes the agent's terminal state for a calling pipeline that reads `SKF_SETUP_RESULT_JSON`. **0 — success** (no JSON `error` field, all writes completed, `require_tier_satisfied` is `true` or `null`). **1 — required-tier failure** (`require_tier_satisfied` is `false`; envelope still emitted with full state for diagnosis). **2 — write failure** (forge-tier.yaml or preferences.yaml could not be written; envelope `error` field names the path and reason). Pipelines should branch on the JSON `require_tier_satisfied` and `error` fields rather than process exit codes. |

## On Activation

> **Halt contract for headless/quiet runs.** Any halt below MUST first emit a blocked envelope when `{headless_mode}` or `{quiet_mode}` is true, before printing the human diagnostic. Pipe `{"phase":"<phase>","reason":"<reason>","path":"<path>"}` to `python3 <helper> emit-blocked` where `<helper>` is the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` then `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. The `emit-blocked` subcommand declares zero dependencies (no `uv`, no `pyyaml`), so it works even when `uv` itself is the thing that's missing.

1. **Parse invocation flags FIRST** (so every halt below knows whether to emit an envelope): `{headless_mode}` (true on `--headless` / `-H`), `{require_tier}` (`--require-tier=<Quick|Forge|Forge+|Deep>`, case-sensitive; null if absent or unparseable), `{orphan_action}` (`--orphan-action=<keep|remove>`; null if absent), `{ccc_skip_index}` (true on `--ccc-skip-index`), `{quiet_mode}` (true on `--quiet`).

2. **Probe `uv` runtime.** Run `uv --version`. Every step invokes shared Python helpers via `uv run` (PEP 723 inline metadata auto-resolves `pyyaml`). If `uv` is missing, halt with phase `on-activation:uv-missing` and the human diagnostic:

   "**Setup cannot proceed: `uv` is not installed.** SKF helpers depend on `uv` to auto-resolve their Python dependencies. Install it from <https://docs.astral.sh/uv/getting-started/installation/> and re-run `/skf-setup`."

3. **Load config** from `{project-root}/_bmad/skf/config.yaml` and resolve `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`. Halt with phase `on-activation:config-missing` if the file does not exist, or `on-activation:config-malformed` if the YAML is invalid, with the matching human diagnostic.

4. **Reconcile `{headless_mode}`** with `preferences.yaml`: OR the parsed flag with `headless_mode: true` from the YAML.

5. Execute `references/detect-and-tier.md`.
