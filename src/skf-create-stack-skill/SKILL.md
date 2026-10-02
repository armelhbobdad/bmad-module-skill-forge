---
name: skf-create-stack-skill
description: Consolidated project stack skill with integration patterns — code-mode (analyzes manifests) or compose-mode (synthesizes from existing skills + architecture doc). Use when the user requests to "create a stack skill", "forge a stack", or "stack this project".
---

# Create Stack Skill

## Overview

Produces a consolidated stack skill documenting how libraries connect. **Code-mode** analyzes dependency manifests and co-import patterns from actual source code. **Compose-mode** synthesizes from pre-generated individual skills and architecture documents when no codebase exists yet. Every finding must trace to actual code with file:line citations; in compose-mode, inferred integrations are permitted but must be labeled `[inferred from shared domain]`.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root, inside a `references/` file too: only a stage's frontmatter `nextStepFile` names a file beside it.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; e.g. `knowledge/tool-resolution.md`, `knowledge/version-paths.md` and `shared/references/feasibility-report-schema.md`.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `assets/` holds the stack skill template, the metadata contract and the provenance map schema.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a dependency analyst and integration architect. You bring expertise in dependency analysis, cross-library integration patterns, and compositional architecture, while the user brings their project knowledge and scope preferences.

## Workflow Rules

These rules apply to every step in this workflow:

- Zero hallucination — all extracted content must trace to actual source code (compose-mode inferences must be labeled)
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread, with two exceptions: never decide by hand whether SKF generated a folder (the ownership check), and never work out by hand what a shared helper computes where its step names a `helper-missing` HALT: that helper resolving to no path stops the run with exit 3 `helper-missing` (`references/invocation-contract.md` lists every such halt). Where a step says what to do without its helper (an advisory check, a default value), do as it says
- Never write into a skill folder SKF did not generate — generate-output §1 runs the inventory's write check before any prior metadata is read and again before staging
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action, and record each auto-decision in the run sink the moment the gate takes it, with the `record --decision` command the gate shows
- Every HARD HALT names its exit code, `halt_reason` and phase, and prints its envelope through the shared emitter with the command its step file shows (the `init:emitter` halt, with no emitter, only displays its message); never type an `SKF_STACK_RESULT_JSON` line
- Warnings use a single accumulator: see `## Workflow state contract` below for shape and surfacing.

## Workflow state contract

Every step that emits a warning appends a structured entry to a single list named `workflow_warnings[]` (the one accumulator for the whole workflow). Each entry has the shape `{step: "step-NN", severity: "info|warn|error", code: "<short-slug>", message: "<human text>", context: {<optional fields>}}`. Appending one means recording it in the run sink at once, the `context` fields folded into the message. Write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, never an `echo`: a message can quote backticks or `$( )`, which a shell runs. Then run:

```bash
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"
```

The shell does not expand what the substitution prints, so the message reaches the sink as text.

The sink, `{run_dir}/warnings.jsonl`, is the list: step 7 §8b lists it in `evidence-report.md`, step 9 §1 renders it, and the result envelope carries it.

**Single-pass, no resume:** the run's state lives in `{run_dir}`, the run folder step 1 creates under `{project-root}/_bmad-output/.skf-run/` (the warnings and auto-decisions, step 3's import counts, step 4's extraction bundle and step 6's draft), and an interrupted run starts again from step 1.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Mode Detection | references/init.md | Conditional |
| 2 | Detect Manifests | references/detect-manifests.md | Conditional (no manifest found) |
| 3 | Rank & Confirm Libraries | references/rank-and-confirm.md | No (confirm) |
| 4 | Parallel Extract | references/parallel-extract.md | Yes |
| 5 | Detect Integrations | references/detect-integrations.md | Yes |
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

2. **Resolve `{headless_mode}`** with explicit precedence (B2):
   1. **Explicit disable wins.** If `--headless=false` or `--no-headless` was passed, `{headless_mode}` is `false` regardless of any preference.
   2. **Explicit enable next.** If `--headless` or `-H` was passed (without `=false`), `{headless_mode}` is `true`.
   3. **Preferences fallback.** Otherwise, read `headless_mode` from `{sidecar_path}/preferences.yaml` (`true` or `false`).
   4. **Default:** `false`.

3. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-create-stack-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran): `references/init.md` records it as the run's first warning once its pre-flight has created `{run_dir}`.

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each of the two scalars, if the merged value is empty or absent, use the bundled default:

   - `{stackSkillTemplatePath}` ← `workflow.stack_skill_template_path` if non-empty, else `assets/stack-skill-template.md` (the SKILL.md, snippet and reference-file structures; `assets/metadata-contract.md` holds the `metadata.json` contract, which no override replaces)
   - `{integrationPatternsPath}` ← `workflow.integration_patterns_path` if non-empty, else `references/integration-patterns.md`

   Also resolve `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string (no-op: `references/report.md` §2c then skips the hook).

   Stash both paths plus `{onCompleteCommand}` as workflow-context variables. Stage files reference `{stackSkillTemplatePath}` and `{integrationPatternsPath}` directly; empty-string overrides fall through to the bundled default.

   Also apply the array surfaces: run `workflow.activation_steps_prepend` now, keep `workflow.persistent_facts` as standing context (`file:` entries load their contents: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off), then run `workflow.activation_steps_append` after.

4. Load, read the full file, and then execute `references/init.md` to begin the workflow.
