---
name: skf-setup
description: Initialize forge environment, detect tools, and set capability tier (Quick/Forge/Forge+/Deep). Use when the user requests to "set up" or "initialize the forge".
---

# Setup Forge

## Overview

Initializes the forge environment by detecting available tools, determining the capability tier (Quick/Forge/Forge+/Deep), and writing persistent configuration to `{project-root}/_bmad/_memory/forger-sidecar/`. When `ccc` (cocoindex-code) is available, also augments `.cocoindex_code/settings.yml` with SKF exclusion patterns and creates or refreshes the project's semantic-search index. On Deep tier, reconciles the QMD collection registry; whenever ccc is available, reconciles the CCC index registry as well.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md — workflow stages chained via frontmatter `nextStepFile`, plus static reference docs.
- Deterministic work is delegated to shared Python helpers under `src/shared/scripts/` (installed as `_bmad/skf/shared/scripts/`). Each step's frontmatter declares a `*ProbeOrder` array for the helpers it needs: run the first path in the array that exists, and halt if none resolve — the script owns that logic, with no prose fallback.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a system executor performing environment resolution. Run each step in sequence, write configuration files, and report results at completion.

## Workflow Rules

- Only load one step file at a time — never preload future steps.
- Communicate in `{communication_language}`.
- If `{headless_mode}` is true, or if `{orphan_action}` is non-null, auto-resolve the step 3 orphan-removal gate non-interactively and log the decision.

## Stages

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
| **Flags** | `--headless` / `-H` (skip prompts, auto-resolve gates to defaults); `--require-tier=<Quick\|Forge\|Forge+\|Deep>` (halt with failure if calculated tier does not satisfy the requirement); `--orphan-action=<keep\|remove>` (resolve the orphan-removal gate non-interactively, even outside `--headless`); `--ccc-skip-index` (skip CCC indexing; envelope `ccc_index.status` becomes `"skipped"` — the fast re-probe lane for an expert re-running only to refresh the detected tier without paying the full ccc re-index cost); `--quiet` (suppress the human-readable FORGE STATUS banner — pipelines and expert re-runners get the envelope only) |
| **Gates** | One optional: orphaned QMD collection removal (step 3, Deep tier only; default: Keep, or whatever `--orphan-action` set) |
| **Outputs** | `forger-sidecar/forge-tier.yaml`, `forger-sidecar/preferences.yaml`, `{forge_data_folder}/`; when ccc is available, `.cocoindex_code/settings.yml` (exclusion patterns merged) and the project ccc index |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Under `--headless` or `--quiet`, step 4 emits a single-line `SKF_SETUP_RESULT_JSON: {…}` envelope as the only stdout line — the FORGE STATUS banner is suppressed. Branch on the envelope's top-level `status` field: `success`, `tier_failure` (require-tier miss), or `blocked` (any pre-report halt — the `error.phase` names the cause). `skf-emit-result-envelope.py` derives `status` from the payload, so pipelines never compose it from `require_tier_satisfied` + `error`. Schema in `references/report.md` §4. |
| **Failure modes** | `--require-tier` not satisfied → status `tier_failure`, the envelope sets `"require_tier_satisfied": false`, and the workflow halts before step 5 (interactive runs also print a "REQUIRED TIER NOT MET" block). A write failure (forge-tier.yaml or preferences.yaml could not be written) halts step 2 with a `blocked` envelope whose `error.phase` (`step 2:write-tools` or `step 2:init-prefs`) and `error` name the path and reason. |

## On Activation

> **Halt contract for headless/quiet runs.** Any halt below must first emit a blocked envelope when `{headless_mode}` or `{quiet_mode}` is true, before printing the human diagnostic — a pipeline observer that sees no envelope treats the run as not-completed-cleanly. Pipe `{"phase":"<phase>","reason":"<reason>","path":"<path>"}` to `python3 <helper> emit-blocked` where `<helper>` is the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` then `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. The `emit-blocked` subcommand declares zero dependencies (no `uv`, no `pyyaml`), so it works even when `uv` itself is the thing that's missing.

1. **Parse invocation flags first** (so every halt below knows whether to emit an envelope): `{headless_mode}` (true on `--headless` / `-H`), `{require_tier}` (`--require-tier=<Quick|Forge|Forge+|Deep>`, case-sensitive; null if absent or unparseable), `{orphan_action}` (`--orphan-action=<keep|remove>`; null if absent), `{ccc_skip_index}` (true on `--ccc-skip-index`), `{quiet_mode}` (true on `--quiet`).

2. **Probe `uv` runtime.** Run `uv --version`. Every step invokes shared Python helpers via `uv run` (PEP 723 inline metadata auto-resolves `pyyaml`). If `uv` is missing, halt with phase `on-activation:uv-missing` and the human diagnostic:

   "**Setup cannot proceed: `uv` is not installed.** SKF helpers depend on `uv` to auto-resolve their Python dependencies. Install it from <https://docs.astral.sh/uv/getting-started/installation/> and re-run `/skf-setup`."

3. **Load config** from `{project-root}/_bmad/skf/config.yaml` and resolve `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`. Halt with phase `on-activation:config-missing` if the file does not exist, or `on-activation:config-malformed` if the YAML is invalid, with the matching human diagnostic.

4. **Reconcile `{headless_mode}`** with `preferences.yaml`: OR the parsed flag with `headless_mode: true` from the YAML.

5. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append): `{skill-root}/customize.toml` (bundled defaults), `_bmad/custom/<skill-name>.toml` under `{project-root}` (team overrides, committed), and `_bmad/custom/<skill-name>.user.toml` under `{project-root}` (personal overrides, gitignored). If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly.

   Apply the resolved values so the surface is not a silent no-op: execute each entry in `workflow.activation_steps_prepend` in order now (org-wide pre-flight checks such as auth, network, or compliance); treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries are paths or globs whose contents load as facts); stash `{onCompleteCommand}` ← `workflow.on_complete` (empty string = no-op) for `references/report.md` §5 to invoke at the terminal stage. After activation completes, execute each entry in `workflow.activation_steps_append` in order, before the first stage runs.

6. Execute `references/detect-and-tier.md`.
