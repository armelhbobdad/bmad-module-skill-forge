---
name: skf-setup
description: Initialize forge environment, detect tools, and set capability tier (Quick/Forge/Forge+/Deep). Use when the user requests to "set up the forge" or "initialize the forge".
---

# Setup Forge

## Overview

Initializes the forge environment: detects the available tools, sets the capability tier (Quick/Forge/Forge+/Deep) and writes the configuration to `{sidecar_path}/`. With `ccc` (cocoindex-code) it also keeps `.cocoindex_code/settings.yml` and the project's semantic-search index current, and it reconciles the QMD (Deep tier) and CCC index registries.

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
- If `{orphan_action}` is non-null or `{quiet_mode}` is true, resolve the step 3 orphan-removal gate without prompting; step 3 records the decision for the envelope's `warnings`.
- When `{quiet_mode}` is true, the one line setup displays is the `SKF_SETUP_RESULT_JSON: {…}` envelope that step 4 builds, or the blocked envelope from a halt. In a standalone run that line is the run's final message, so it is all `claude -p` prints (step 4 holds it until then).
- When `{quiet_mode}` is true, write no assistant text at all between tool calls: no status, progress or step-transition notes, however brief.
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

`references/invocation-contract.md` documents the flags, gate, outputs, `SKF_SETUP_RESULT_JSON` contract and failure modes for pipeline authors; no run loads it.

## On Activation

> **Halt contract.** Every halt in this workflow that names a phase, below and in the step files, follows this contract; the step 4 tier-miss halt names none and displays its `tier_failure` envelope instead. When `{quiet_mode}` is true, pipe `{"phase":"<phase>","reason":"<reason>","path":"<path>"}` to `<runner> <helper> emit-blocked`, where `<helper>` is the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` then `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`, and `<runner>` is `uv run` in the step files, which run after the `uv` probe below. The halts in this list can fire before `uv` is proven present, so for them try the runners `uv run`, `python3`, `python` and `py -3` in that order and stop at the first that exits 0 and prints a line starting `SKF_SETUP_RESULT_JSON:`. Display the helper's stdout line verbatim, and display nothing else: the envelope's `error.reason` carries the diagnostic. If neither path exists, or no runner exits 0 and prints that line, display the reason alone as that one line. Interactive runs display the reason as their diagnostic and emit no envelope. The reason is the one-line diagnostic with no `'`, `"` or `\` in it (a backtick for either quote, `/` for a backslash), because it travels as a JSON string inside a single-quoted shell payload; write `path` with `/` as well. The helper is stdlib-only, so a bare interpreter runs it without `uv`. `--headless` and `--quiet` are known at every halt, `headless_mode` from `preferences.yaml` only after item 5 (a `uv` helper reads that file).

1. **Parse invocation flags first** (so every halt below knows whether to emit an envelope): `{headless_mode}` (true on `--headless` / `-H`, and when `{pipeline_mode}` is true), `{quiet_mode}` (true on `--quiet`, the alias of `--headless`, and whenever `{headless_mode}` is true), `{require_tier}` and `{orphan_action}` (each flag's raw value exactly as given, after `=` or a space; an empty string when nothing, or another flag, follows it; null only when the flag is absent), `{ccc_skip_index}` (true on `--ccc-skip-index`, false otherwise). `{pipeline_mode}` is not a flag: it is true only when the forger invokes setup as one step of a pipeline and passes it, and false otherwise, including every direct `/skf-setup` run. Step 1's detector rejects a `{require_tier}` that names no tier. When `{orphan_action}` is non-null and neither `keep` nor `remove`, halt with phase `on-activation:orphan-action-invalid`, no `path`, and reason `Setup cannot proceed: --orphan-action takes keep or remove, not <value>. Re-run with --orphan-action=keep or --orphan-action=remove.`, where `<value>` is the value as given, or `an empty value` when there is none.

2. **Check for the config.** If `{project-root}/_bmad/skf/config.yaml` does not exist, halt with phase `on-activation:config-missing`, `path` `{project-root}/_bmad/skf/config.yaml`, and reason `Setup cannot proceed: _bmad/skf/config.yaml was not found. SKF is not installed in this project: from the project root, run npx bmad-module-skill-forge install (or npx bmad-method install and add SKF), then re-run /skf-setup.` This check runs no script: a project without the config usually has no SKF scripts either.

3. **Probe `uv` runtime.** Run `uv --version`. Every step invokes shared Python helpers via `uv run`. If `uv` is missing, halt with phase `on-activation:uv-missing`, no `path`, and reason `Setup cannot proceed: uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/ and re-run /skf-setup.`

4. **Load config and preferences.** `<preflight>` is the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-preflight.py` then `{project-root}/src/shared/scripts/skf-preflight.py` (neither: halt with phase `on-activation:helper-missing`, `path` the first, reason `Setup cannot proceed: skf-preflight.py was not found. Reinstall SKF, then re-run /skf-setup.`). Run `uv run "<preflight>" "{project-root}" --allow-missing-sidecar`, which parses config.yaml and `preferences.yaml` into one JSON object:

   - `status` `ok`: bind `{project_name}`, `{user_name}`, `{communication_language}` and `{document_output_language}` from `config`, each folder from its absolute path (`{output_folder}`, `{skills_output_folder}`, `{forge_data_folder}` and `{sidecar_path}` from `config.<name>_resolved`), and `{tier_override}` from `sidecar.preferences.tier_override` (null when absent). With `sidecar.preferences_error` (the file did not load), go on with its defaults and, unless `{quiet_mode}` is true, display that error in one line.
   - `code` `CONFIG_MISSING`: the item 2 halt. Any other `hard-halt`, or no JSON `status`: halt with phase `on-activation:config-malformed`, `path` `{project-root}/_bmad/skf/config.yaml`, and reason `Setup cannot proceed: <message>`: its `error` without the leading `Cannot initialize. ` (else the first line the call printed), sanitized per the halt contract.

5. **Reconcile `{headless_mode}`**: OR it with `derived.headless_mode` (`headless_mode: true` in `preferences.yaml`). Then, if `{headless_mode}` is true, set `{quiet_mode}` to true.

6. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append): `{skill-root}/customize.toml` (bundled defaults), `_bmad/custom/<skill-name>.toml` under `{project-root}` (team overrides, committed), and `_bmad/custom/<skill-name>.user.toml` under `{project-root}` (personal overrides, gitignored). If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly.

   Apply the resolved values so the surface is not a silent no-op (when `{quiet_mode}` is true, add no narration of your own around these entries): execute each entry in `workflow.activation_steps_prepend` in order now (org-wide pre-flight checks such as auth, network, or compliance); treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries are paths or globs whose contents load as facts); stash `{onCompleteCommand}` ← `workflow.on_complete` (empty string = no-op) for `references/report.md` §5 to carry out at the terminal stage. After activation completes, execute each entry in `workflow.activation_steps_append` in order, before the first stage runs.

7. Execute `references/detect-and-tier.md`.
