---
name: skf-setup
description: Initialize forge environment, detect tools, and set capability tier (Quick/Forge/Forge+/Deep). Use when the user requests to "set up the forge" or "initialize the forge".
---

# Setup Forge

## Overview

Detects the available tools, sets the capability tier (Quick/Forge/Forge+/Deep) and writes the forge configuration to `{sidecar_path}/`. With `ccc` it also keeps `.cocoindex_code/settings.yml` and the semantic-search index current, and it reconciles the QMD and CCC index registries.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `references/` holds the workflow stages (chained by frontmatter `nextStepFile`), the invocation contract and `tier-rules.md`, the tier table `report.md` passes to the emitter's banner.
- Shared Python helpers do the deterministic work, with no prose fallback: each step's frontmatter `*ProbeOrder` array lists a helper's installed path (`{project-root}/_bmad/skf/shared/scripts/<name>`) then its dev path (`{project-root}/src/shared/scripts/<name>`). Run the first that exists; if none does, halt through the On Activation halt contract with phase `step <N>:helper-missing`.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a system executor: run each step in sequence, write the configuration files, and report at completion.

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

`references/invocation-contract.md` holds the flags, gate, outputs, `SKF_SETUP_RESULT_JSON` contract and failure modes for pipeline authors; no run loads it.

## On Activation

> **Halt contract.** Every halt in this workflow that names a phase, below and in the step files, follows this contract; the step 4 tier-miss halt names none and displays its `tier_failure` envelope instead. When `{quiet_mode}` is true, run `<runner> <helper> emit-blocked --phase '<phase>' --reason '<reason>' --path "<path>"` (`<path>` written with `/`; no `--path` for a halt without one): `<helper>` is `skf-emit-result-envelope.py`, at its installed path, else its dev path (Conventions), and `<runner>` is `uv run` in the step files. The halts in this list can fire before `uv` is proven present, so for them try the runners `uv run`, `python3`, `python` and `py -3` in that order and stop at the first that exits 0 and prints a line starting `SKF_SETUP_RESULT_JSON:` (the helper is stdlib-only). Display that line verbatim, nothing else. If neither path exists, or no runner exits 0 and prints that line, display the reason alone as that one line. Interactive runs display the reason as their diagnostic and emit no envelope. Text from the user or a helper never goes into the single-quoted `--reason`: write `<message>` there and pass the text on stdin with `--stderr-from -` and a quoted `<<'SKF_TEXT'` heredoc, one per runner tried, for the emitter to fold to one line and escape. Once item 6 binds `{customization_resolver_unavailable}` to a reason, every halt also passes `--customization-resolver-unavailable "<reason>"`, escaping each `\`, `"`, `$` and backtick in it with a backslash. `--headless` and `--quiet` are known at every halt, `headless_mode` from `preferences.yaml` only after item 5.

1. **Parse invocation flags first**, so every halt below knows whether to emit: `{headless_mode}` (true on `--headless` / `-H`, and when `{pipeline_mode}` is true), `{quiet_mode}` (true on `--quiet`, the alias of `--headless`, and whenever `{headless_mode}` is true), `{require_tier}` and `{orphan_action}` (each flag's raw value exactly as given, after `=` or a space; an empty string when nothing, or another flag, follows it; null only when the flag is absent), `{ccc_skip_index}` (true on `--ccc-skip-index`, false otherwise). `{pipeline_mode}` is not a flag: it is true only when the forger invokes setup as one step of a pipeline and passes it, and false otherwise, including every direct `/skf-setup` run. Step 1's detector rejects a `{require_tier}` that names no tier. When `{orphan_action}` is non-null and neither `keep` nor `remove`, halt with phase `on-activation:orphan-action-invalid`, no `path`, and reason `Setup cannot proceed: --orphan-action takes keep or remove, not <message>. Re-run with --orphan-action=keep or --orphan-action=remove.`, where `<message>` is the value as given, or `an empty value` when there is none, passed as the halt contract says.

2. **Check for the config.** If `{project-root}/_bmad/skf/config.yaml` does not exist, halt with phase `on-activation:config-missing`, `path` `{project-root}/_bmad/skf/config.yaml`, and reason `Setup cannot proceed: the SKF config file was not found. SKF is not installed in this project: from the project root, run npx bmad-module-skill-forge install (or npx bmad-method install and add SKF), then re-run /skf-setup.`

3. **Probe `uv` runtime.** Run `uv --version`. If `uv` is missing, halt with phase `on-activation:uv-missing`, no `path`, and reason `Setup cannot proceed: uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/ and re-run /skf-setup.`

4. **Load config and preferences.** `<preflight>` is `skf-preflight.py`, at its installed path, else its dev path (neither: halt with phase `on-activation:helper-missing`, `path` the installed one, reason `Setup cannot proceed: skf-preflight.py was not found. Reinstall SKF, then re-run /skf-setup.`). Run `uv run "<preflight>" "{project-root}" --allow-missing-sidecar`, which parses config.yaml and `preferences.yaml` into one JSON object:

   - `status` `ok`: bind `{project_name}`, `{user_name}`, `{communication_language}` and `{document_output_language}` from `config`, each folder from its absolute path (`{output_folder}`, `{skills_output_folder}`, `{forge_data_folder}` and `{sidecar_path}` from `config.<name>_resolved`), and `{tier_override}` from `sidecar.preferences.tier_override` (null when absent). With `sidecar.preferences_error`, go on with the defaults and, unless `{quiet_mode}` is true, display that error in one line.
   - `code` `CONFIG_MISSING`: the item 2 halt. Any other `hard-halt`, or no JSON `status`: halt with phase `on-activation:config-malformed`, `path` `{project-root}/_bmad/skf/config.yaml`, and reason `Setup cannot proceed: <message>`: its `error` without the leading `Cannot initialize. ` (else the first line the call printed), passed as the halt contract says, never preflight's whole JSON.

5. **Reconcile `{headless_mode}`**: OR it with `derived.headless_mode` (`headless_mode: true` in `preferences.yaml`). Then, if `{headless_mode}` is true, set `{quiet_mode}` to true.

6. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-setup.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. Bind `{customization_resolver_unavailable}` ← that reason (null when the resolver ran), which `references/report.md` and every later halt hand to the emitter; print the warning only when `{quiet_mode}` is false.

   Apply the resolved values, with no narration of your own when `{quiet_mode}` is true: run each `workflow.activation_steps_prepend` entry now; treat each `workflow.persistent_facts` entry as standing context (a `file:` entry loads its file or glob contents); bind `{onCompleteCommand}` ← `workflow.on_complete` (empty: no hook) for `references/report.md` §5; then run each `workflow.activation_steps_append` entry, before the first stage.

7. Execute `references/detect-and-tier.md`.
