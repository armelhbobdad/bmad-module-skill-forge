---
name: skf-setup
description: Initialize forge environment, detect tools, and set capability tier (Quick/Forge/Forge+/Deep). Use when the user requests to "set up" or "initialize the forge".
---

# Setup Forge

## Overview

Initializes the forge environment by detecting available tools, determining the capability tier (Quick/Forge/Forge+/Deep), and writing persistent configuration to `{project-root}/_bmad/_memory/forger-sidecar/`. When `ccc` (cocoindex-code) is available, also prepares `.cocoindex_code/settings.yml` (running `ccc init` when it is missing), keeps its SKF exclusion patterns in line with the configured folders, and creates or refreshes the project's semantic-search index. On Deep tier, reconciles the QMD collection registry; whenever ccc is available, reconciles the CCC index registry as well.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md — workflow stages chained via frontmatter `nextStepFile`, plus static reference docs.
- Deterministic work is delegated to shared Python helpers under `src/shared/scripts/` (installed as `_bmad/skf/shared/scripts/`). Each step's frontmatter declares a `*ProbeOrder` array for the helpers it needs: run the first path in the array that exists. If none exists, halt through the On Activation halt contract with phase `step <N>:helper-missing` — the script owns that logic, with no prose fallback.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a system executor performing environment resolution. Run each step in sequence, write configuration files, and report results at completion.

## Workflow Rules

- Only load one step file at a time — never preload future steps.
- Communicate in `{communication_language}`.
- If `{orphan_action}` is non-null, or `{headless_mode}` or `{quiet_mode}` is true, resolve the step 3 orphan-removal gate without prompting; step 3 records the decision for the envelope's `warnings`.
- When `{headless_mode}` or `{quiet_mode}` is true, the one line setup displays is the `SKF_SETUP_RESULT_JSON: {…}` envelope that step 4 builds, or the blocked envelope from a halt. In a standalone run that line is the run's final message, so it is all `claude -p` prints; step 4 holds its envelope until the health check has finished (or until the tier-miss halt) for that reason. Every display instruction in the step files carries this guard.
- When `{headless_mode}` or `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief.
- When `{pipeline_mode}` is true, the forger runs setup as one step of a pipeline: display the same envelope line, then return control to the forger, which keeps chaining. The final-message rule above is for a standalone run.

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
| **Flags** | `--headless` / `-H` (skip prompts, auto-resolve gates to defaults); `--require-tier=<Quick\|Forge\|Forge+\|Deep>` (halt with failure if calculated tier does not satisfy the requirement); `--orphan-action=<keep\|remove>` (resolve the orphan-removal gate non-interactively, even outside `--headless`); `--ccc-skip-index` (skip building the CCC index — settings.yml is still prepared and its SKF exclusions kept current; envelope `ccc_index.status` becomes `"skipped"` — the fast re-probe lane for an expert re-running only to refresh the detected tier without paying the full ccc re-index cost); `--quiet` (the same envelope-only output as `--headless`, for pipelines and expert re-runners: the step 4 envelope takes the place of the FORGE STATUS banner and the health-check output, and the step 3 orphan gate resolves to Keep instead of prompting) |
| **Gates** | One optional: orphaned QMD collection removal (step 3, Deep tier only; default: Keep, or whatever `--orphan-action` set; resolves without prompting under `--headless` or `--quiet`) |
| **Outputs** | `forger-sidecar/forge-tier.yaml`, `forger-sidecar/preferences.yaml`, `{forge_data_folder}/`; when ccc is available, `.cocoindex_code/settings.yml` (created by `ccc init` when missing; SKF exclusion patterns merged and stale ones removed), a `/.cocoindex_code/` line in `.gitignore` when `ccc init` adds one, and the project ccc index |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true; `--quiet` resolves the step 3 gate the same way. Under `--headless` or `--quiet`, a standalone run's final message, and so everything `claude -p` prints, is exactly one line: the single-line `SKF_SETUP_RESULT_JSON: {…}` envelope from step 4 (displayed once the health check has finished, or at the tier-miss halt), or a blocked envelope from a halt, or the bare halt reason when no envelope helper can run (see Failure modes). Setup displays no FORGE STATUS banner or health-check output, and no halt diagnostic beyond that one line; the health check still runs and saves any findings to the local improvement queue. Inside a forger pipeline (`{pipeline_mode}` true), setup displays the same line and returns control to the forger. Branch on the envelope's top-level `status` field: `success`, `tier_failure` (require-tier miss), or `blocked` (any pre-report halt — the `error.phase` names the cause). `skf-emit-result-envelope.py` derives `status` from the payload, so pipelines never compose it from `require_tier_satisfied` + `error`. Schema in `references/report.md` §4. |
| **Failure modes** | `--require-tier` not satisfied → status `tier_failure`, the envelope sets `"require_tier_satisfied": false`, and the workflow halts before step 5 (interactive runs also print a "REQUIRED TIER NOT MET" block). A write failure (forge-tier.yaml, preferences.yaml or the forge data folder could not be written) halts step 2 with a `blocked` envelope whose `error.phase` (`step 2:write-tools`, `step 2:init-prefs` or `step 2:forge-data-dir`) and `error` name the path and reason. The other halts (uv missing, config missing or malformed, a helper that no probe path resolves, a failed tool detection) end the same way under `--headless` or `--quiet`: `error.phase` names the halt and `error.reason` carries the diagnostic. The exception is a run where the envelope helper itself cannot run (SKF's scripts are not installed in the project, as in a directory that is not an SKF project, or an On Activation halt on a machine where none of `uv`, `python3`, `python` and `py -3` can run it): its one line is the bare halt reason with no envelope, and a pipeline treats a missing envelope as a failure. |

## On Activation

> **Halt contract.** Every halt in this workflow that names a phase, below and in the step files, follows this contract; the step 4 tier-miss halt names none and displays its `tier_failure` envelope instead. When `{headless_mode}` or `{quiet_mode}` is true, pipe `{"phase":"<phase>","reason":"<reason>","path":"<path>"}` to `<runner> <helper> emit-blocked`, where `<helper>` is the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` then `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`, and `<runner>` is `uv run` in the step files, which run after the `uv` probe below. The halts in this list can fire before `uv` is proven present, and many Windows installs have `python` or `py` but no working `python3`, so for them try the runners `uv run`, `python3`, `python` and `py -3` in that order and stop at the first that exits 0 and prints a line starting `SKF_SETUP_RESULT_JSON:`. Display the helper's stdout line verbatim, and display nothing else: the envelope's `error.reason` carries the diagnostic, and a pipeline observer that sees no envelope treats the run as not-completed-cleanly. If neither path exists, or no runner exits 0 and prints that line, display the reason alone as that one line. Interactive runs display the human diagnostic and emit no envelope. The reason is the one-line diagnostic with no `'` and no `\` in it (use a backtick for a quote and `/` for a backslash), because it travels inside a single-quoted shell payload; write `path` with `/` as well. The helper is stdlib-only (its script header declares no dependencies), so a plain Python interpreter runs `emit-blocked` even when `uv` itself is the thing that is missing. `--headless` and `--quiet` are known at every halt; headless that comes only from `preferences.yaml` is known from the `uv` probe onward.

1. **Parse invocation flags first** (so every halt below knows whether to emit an envelope): `{headless_mode}` (true on `--headless` / `-H`), `{require_tier}` (`--require-tier=<Quick|Forge|Forge+|Deep>`, case-sensitive; null if absent or unparseable), `{orphan_action}` (`--orphan-action=<keep|remove>`; null if absent), `{ccc_skip_index}` (true on `--ccc-skip-index`, false otherwise), `{quiet_mode}` (true on `--quiet`; item 3 also sets it under headless). `{pipeline_mode}` is not a flag: it is true only when the forger invokes setup as one step of a pipeline and passes it, and false otherwise, including every direct `/skf-setup` run.

2. **Load config** from `{project-root}/_bmad/skf/config.yaml` and resolve `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`. Both halts here use `path` `{project-root}/_bmad/skf/config.yaml`, and an interactive run displays the reason as its diagnostic:

   - The file does not exist: halt with phase `on-activation:config-missing` and reason `Setup cannot proceed: _bmad/skf/config.yaml was not found. SKF is not installed in this project: from the project root, run npx bmad-module-skill-forge install (or npx bmad-method install and add SKF), then re-run /skf-setup.`
   - The YAML is invalid: halt with phase `on-activation:config-malformed` and reason `Setup cannot proceed: _bmad/skf/config.yaml is not valid YAML: <first line of the parser error>`.

3. **Reconcile `{headless_mode}`** with `preferences.yaml`: OR the parsed flag with `headless_mode: true` from the YAML. Then, if `{headless_mode}` is true, set `{quiet_mode}` to true: setup's headless output is the same envelope-only output, and `shared/health-check.md` reads `{quiet_mode}` alone.

4. **Probe `uv` runtime.** Run `uv --version`. Every step invokes shared Python helpers via `uv run` (PEP 723 inline metadata auto-resolves `pyyaml`). If `uv` is missing, halt with phase `on-activation:uv-missing`, no `path`, and reason `Setup cannot proceed: uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/ and re-run /skf-setup.` An interactive run displays this diagnostic instead:

   "**Setup cannot proceed: `uv` is not installed.** SKF helpers depend on `uv` to auto-resolve their Python dependencies. Install it from <https://docs.astral.sh/uv/getting-started/installation/> and re-run `/skf-setup`."

5. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append): `{skill-root}/customize.toml` (bundled defaults), `_bmad/custom/<skill-name>.toml` under `{project-root}` (team overrides, committed), and `_bmad/custom/<skill-name>.user.toml` under `{project-root}` (personal overrides, gitignored). If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly.

   Apply the resolved values so the surface is not a silent no-op (when `{headless_mode}` or `{quiet_mode}` is true, add no narration of your own around these entries): execute each entry in `workflow.activation_steps_prepend` in order now (org-wide pre-flight checks such as auth, network, or compliance); treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries are paths or globs whose contents load as facts); stash `{onCompleteCommand}` ← `workflow.on_complete` (empty string = no-op) for `references/report.md` §5 to invoke at the terminal stage. After activation completes, execute each entry in `workflow.activation_steps_append` in order, before the first stage runs.

6. Execute `references/detect-and-tier.md`.
