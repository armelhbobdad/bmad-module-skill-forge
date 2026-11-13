---
name: skf-setup
description: Initialize forge environment, detect tools, and set capability tier (Quick/Forge/Forge+/Deep). Use when the user requests to "set up the forge" or "initialize the forge".
---

# Setup Forge

## Overview

Detects the available tools, sets the capability tier (Quick/Forge/Forge+/Deep) and writes the forge configuration to `{sidecar_path}/`. With `ccc` it also keeps `.cocoindex_code/settings.yml` and the semantic-search index current, and it reconciles the QMD and CCC index registries.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root, inside a `references/` file too: only a stage's frontmatter `nextStepFile` names a file beside it.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `references/` holds the workflow stages (chained by frontmatter `nextStepFile`), the invocation contract, `halt-contract.md`, which a halt that names a phase loads, and `tier-rules.md`, the tier table `report.md` passes to the emitter's banner.
- Shared Python helpers do the deterministic work, with no prose fallback: each step's frontmatter `*ProbeOrder` array lists a helper's installed path (`{project-root}/_bmad/skf/shared/scripts/<name>`) then its dev path (`{project-root}/src/shared/scripts/<name>`). On Activation item 4 resolves them all and halts (`on-activation:helper-missing`) on any helper with neither path.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a system executor: run each step in sequence, write the configuration files, and report at completion.

## Workflow Rules

- Only load one step file at a time — never preload future steps.
- Run every subagent in the foreground, passing `run_in_background: false` on every Agent call (Claude Code runs a subagent in the background when the flag is left out), with parallel ones as several such calls in one message, and wait for every long-running command to exit before the next instruction; in a headless run, never end a turn while either still runs, since under `claude -p` a run stops when its turn ends.
- Communicate in `{communication_language}`.
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
| 5 | Workflow Health Check (only when `{quiet_mode}` is false) | references/health-check.md |

## Invocation Contract

`references/invocation-contract.md` holds the flags, gate, outputs, `SKF_SETUP_RESULT_JSON` contract and failure modes for pipeline authors; no run loads it.

## On Activation

On any halt that names a phase, load `references/halt-contract.md` and follow it.

1. **Parse invocation flags first**, so every halt below knows whether to emit. `<parser>` is `skf-setup-args.py` at its installed path, else its dev path (Conventions); run it on the invocation's arguments exactly as given (keep the heredoc, empty, when there are none):

   ```bash
   for r in "uv run" python3 python "py -3"; do
     out=$($r "<parser>" <<'SKF_ARGS'
   <the arguments>
   SKF_ARGS
   ) && case "$out" in "{"*) printf '%s\n' "$out"; break ;; esac
   done
   ```

   Bind `{headless_mode}`, `{quiet_mode}`, `{require_tier}`, `{orphan_action}` and `{ccc_skip_index}` from the object it prints (`headless`, `quiet`, `require_tier`, `orphan_action`, `ccc_skip_index`), and set both modes true when `{pipeline_mode}` is true. `{pipeline_mode}` is not a flag: it is true only when the forger invokes setup as one step of a pipeline and passes it, and false otherwise, including every direct `/skf-setup` run. Step 1's detector rejects a `{require_tier}` that names no tier. When the object has a `phase`, halt with phase `on-activation:orphan-action-invalid`, no `path`, and reason `<message>`, its `reason` passed as the halt contract says. When no runner prints an object, `{quiet_mode}` is true when the arguments hold `--headless`, `-H` or `--quiet`, or `{pipeline_mode}` is true.

2. **Check for the config.** If `{project-root}/_bmad/skf/config.yaml` does not exist, halt with phase `on-activation:config-missing`, `path` `{project-root}/_bmad/skf/config.yaml`, and reason `Setup cannot proceed: the SKF config file was not found. SKF is not installed in this project: from the project root, run npx bmad-module-skill-forge install (or npx bmad-method install and add SKF), then re-run /skf-setup.`

3. **Probe `uv` runtime.** Run `uv --version`. If `uv` is missing, halt with phase `on-activation:uv-missing`, no `path`, and reason `Setup cannot proceed: uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/ and re-run /skf-setup.` Once `uv` is present, if item 1's parser printed no object, halt with phase `on-activation:helper-missing`, `path` its installed path, reason `Setup cannot proceed: skf-setup-args.py could not read the flags. Reinstall SKF, then re-run /skf-setup.`

4. **Load config and preferences.** `<preflight>` is `skf-preflight.py`, at its installed path, else its dev path (neither: halt with phase `on-activation:helper-missing`, `path` the installed one, reason `Setup cannot proceed: skf-preflight.py was not found. Reinstall SKF, then re-run /skf-setup.`). Run `uv run "<preflight>" "{project-root}" --allow-missing-sidecar --helpers "{skill-root}"`, which parses config.yaml and `preferences.yaml` into one JSON object and resolves the `*ProbeOrder` arrays of every step file into its `helpers` map:

   - `status` `ok`: bind `{project_name}`, `{user_name}`, `{communication_language}` and `{document_output_language}` from `config`, each folder from its absolute path (`{output_folder}`, `{skills_output_folder}`, `{forge_data_folder}` and `{sidecar_path}` from `config.<name>_resolved`), and `{tier_override}` from `sidecar.preferences.tier_override` (null when absent). Bind `{detectToolsHelper}`, `{mergeCccExclusionsHelper}`, `{forgeTierRwHelper}`, `{qmdClassifyHelper}`, `{emitEnvelopeHelper}` and `{resolveCustomizationHelper}` from `helpers.<stem>`, the name without `Helper` (`helpers.detectTools` for `{detectToolsHelper}`): the step files run these, and their own `*ProbeOrder` arrays are only a backstop. With `sidecar.preferences_error`, go on with the defaults and, unless `{quiet_mode}` is true, display that error in one line.
   - `code` starting `HELPERS_` (a helper of some step is missing, or a step's probe order cannot be read): halt with phase `on-activation:helper-missing`, `path` `{project-root}/_bmad/skf/shared/scripts`, and reason `Setup cannot proceed: <message>`: its `error` without the leading `Cannot initialize. `, which names every missing helper or the file whose probe order cannot be read, passed as the halt contract says. No step file loads.
   - `code` `CONFIG_MISSING`: the item 2 halt. Any other `hard-halt`, or no JSON `status`: halt with phase `on-activation:config-malformed`, `path` `{project-root}/_bmad/skf/config.yaml`, and reason `Setup cannot proceed: <message>`: its `error` without the leading `Cannot initialize. ` (else the first line the call printed), passed as the halt contract says, never preflight's whole JSON.

5. **Reconcile `{headless_mode}`**: OR it with `derived.headless_mode` (`headless_mode: true` in `preferences.yaml`), which resolves the gates only: `{quiet_mode}` stays as item 1 set it.

5b. **Create the run folder.** Run:

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-setup-XXXXXXXX"
   ```

   Bind `{run_dir}` ← the path it prints. If the folder cannot be created, halt with phase `on-activation:run-folder`, `path` `{project-root}/_bmad-output/.skf-run`, and reason `Setup cannot proceed: the run folder could not be created: <message>`, where `<message>` is the command's first stderr line. Item 3 proved `uv` and item 4 bound the helper, so this halt runs its own pipe, not the loop: with no run folder to hold that stderr, a quiet run repeats the command with its stderr piped to the emitter, which fills `<message>`; a repeat that succeeds removes the folder it made, and its reason then ends `(no error message)`:

   ```bash
   { mkdir -p "{project-root}/_bmad-output/.skf-run" && rmdir "$(mktemp -d "{project-root}/_bmad-output/.skf-run/skf-setup-XXXXXXXX")"; } 2>&1 >/dev/null | uv run {emitEnvelopeHelper} emit-blocked --phase "on-activation:run-folder" --path "{project-root}/_bmad-output/.skf-run" --reason "Setup cannot proceed: the run folder could not be created: <message>" --stderr-from -
   ```

6. **Resolve workflow customization.** With `{resolveCustomizationHelper}` bound in item 4, run:

   ```bash
   uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow --facts 2> "{run_dir}/resolver.err"
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-setup.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero or prints no JSON, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. The resolver's stderr is in `{run_dir}/resolver.err`, so read `<reason>` from that file (`(no error message)` when it is empty); when it exits 0 and prints no JSON, first write that fixed reason into the file (`printf '%s\n' '<the fixed reason>' > "{run_dir}/resolver.err"`), so the file holds the reason whenever `{customization_resolver_unavailable}` is bound. Bind `{customization_resolver_unavailable}` ← that reason (null when the resolver ran); `references/report.md` and every later halt then pass `--customization-resolver-unavailable-from "{run_dir}/resolver.err"` to the emitter; print the warning only when `{quiet_mode}` is false.

   Apply the resolved values, with no narration of your own when `{quiet_mode}` is true: run each `workflow.activation_steps_prepend` entry now; treat each `workflow.persistent_facts` entry as standing context (if the resolver ran, `--facts` has applied each `!` entry, which drops each earlier entry it names, and expanded each glob, so a `file:` entry names one file); bind `{onCompleteCommand}` ← `workflow.on_complete` (empty: no hook) for `references/report.md` §5; then run each `workflow.activation_steps_append` entry, before item 7 executes `references/detect-and-tier.md`.

7. Execute `references/detect-and-tier.md`.
