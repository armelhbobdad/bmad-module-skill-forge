---
name: skf-create-stack-skill
description: Consolidated project stack skill with integration patterns — code-mode (analyzes manifests) or compose-mode (synthesizes from existing skills + architecture doc). Use when the user requests to "create a stack skill", "forge a stack", or "stack this project".
---

# Create Stack Skill

## Overview

Produces a consolidated stack skill documenting how libraries connect. **Code-mode** analyzes dependency manifests and co-import patterns from actual source code. **Compose-mode** synthesizes from pre-generated individual skills and architecture documents when no codebase exists yet. Every finding must trace to its source with file:line citations.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root, inside a `references/` file too: only a stage's frontmatter `nextStepFile` and `composeNextStepFile` name a file beside it.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; e.g. `knowledge/tool-resolution.md`, `knowledge/version-paths.md` and `shared/references/feasibility-report-schema.md`.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a dependency analyst and integration architect; the user brings their project knowledge and scope preferences.

## Workflow Rules

These rules apply to every step in this workflow:

- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread, with two exceptions: never decide by hand whether SKF generated a folder (the ownership check), and never work out by hand what a shared helper computes where its step names a `helper-missing` HALT: that helper resolving to no path stops the run with exit 3 `helper-missing` (`references/invocation-contract.md` lists every such halt). Where a step says what to do without its helper (an advisory check, a default value), do as it says
- Run every subagent in the foreground, passing `run_in_background: false` on every Agent call (Claude Code runs a subagent in the background when the flag is left out), with parallel ones as several such calls in one message, and wait for every long-running command to exit before the next instruction; in a headless run, never end a turn while either still runs, since under `claude -p` a run stops when its turn ends.
- Never write into a skill folder SKF did not generate: step 1 runs the inventory's write check before any prior metadata is read, step 7 again before staging
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action, and record each auto-decision in the run sink the moment the gate takes it, with the `record --decision` command the gate shows
- Every HARD HALT names its exit code, `halt_reason` and phase, and prints its envelope through the shared emitter with the command its step file shows (the `init:emitter` halt, with no emitter, only displays its message); never type an `SKF_STACK_RESULT_JSON` line

## Workflow state contract

Every step that emits a warning appends an entry to `workflow_warnings[]`, the one accumulator for the whole workflow, and records it in the run sink at once, as the step shows. An entry has the shape `{step: "step-NN", severity: "info|warn|error", code: "<short-slug>", message: "<human text>", context: {<optional fields>}}`, its `context` fields folded into the message. The sink, `{run_dir}/warnings.jsonl`, is the list: step 7 §8b lists it in `evidence-report.md`, step 9 §1 renders it, and the result envelope carries it.

**Resume only at the review gate:** the run's state lives in `{run_dir}`, the run folder step 1 creates under `{project-root}/_bmad-output/.skf-run/`, a step 1 binding lost to compaction is re-read from its `run.json`, and an interrupted run starts again from step 1 unless step 1 resumes an interactive one at step 6's review gate.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Mode Detection | references/init.md | Conditional |
| 2 | Detect Manifests | references/detect-manifests.md; compose: references/compose-skills.md | Conditional (no manifest found) |
| 3 | Rank & Confirm Libraries | references/rank-and-confirm.md; compose: references/compose-scope.md first | No (confirm) |
| 4 | Parallel Extract | references/parallel-extract.md; compose: references/compose-extract.md | Yes |
| 5 | Detect Integrations | references/detect-integrations.md; compose: references/compose-pairs.md first | Yes |
| 6 | Compile Stack | references/compile-stack.md | No (review) |
| 7 | Generate Output | references/generate-output.md | Yes |
| 8 | Validate | references/validate.md | Yes |
| 9 | Report | references/report.md | Yes |
| 10 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

`references/invocation-contract.md` holds the inputs, gates and outputs, the exit code and `halt_reason` of every HARD HALT, and the `SKF_STACK_RESULT_JSON` result envelope.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`** by the first rule that applies: `false` when `--headless=false` or `--no-headless` was passed, whatever the preferences say; `true` when `--headless` or `-H` was passed without `=false`; otherwise `headless_mode` from `{sidecar_path}/preferences.yaml` (`true` or `false`); otherwise `false`.

3. **Resolve workflow customization.** Bind `{resolveCustomizationHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-resolve-customization.py`, else `{project-root}/src/shared/scripts/skf-resolve-customization.py` (the first that exists), and run:

   ```bash
   uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow --facts
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-create-stack-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `SKF helper skf-resolve-customization.py not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran): `references/init.md` records it as the run's first warning once its pre-flight has created `{run_dir}`.

   Bind these three as workflow-context variables, taking the default when the merged value is empty or absent:

   - `{stackSkillTemplatePath}` ← `workflow.stack_skill_template_path`, else `assets/stack-skill-template.md` (the SKILL.md, snippet and reference-file structures, less the lines `skf-render-stack-metadata.py` writes; never `assets/metadata-contract.md`)
   - `{integrationPatternsPath}` ← `workflow.integration_patterns_path`, else `references/integration-patterns.md`
   - `{onCompleteCommand}` ← `workflow.on_complete`, else empty (`references/report.md` §2c then runs no hook)

   Run `workflow.activation_steps_prepend` now and keep `workflow.persistent_facts` as standing context (the bundled default loads every `project-context.md` under `{project-root}`, none in `{project-root}/_bmad-output/.skf-run/`; if the resolver ran, `--facts` has applied each `!` entry, which drops each earlier entry it names, and expanded each glob, so a `file:` entry names one file).

4. Run each entry in `workflow.activation_steps_append` in order, then load, read the full file, and execute `references/init.md` to begin the workflow.
