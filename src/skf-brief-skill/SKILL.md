---
name: skf-brief-skill
description: Design a skill scope through guided discovery. Use when the user requests to "create a skill brief" or "brief a skill".
---

# Brief Skill

## Overview

Helps the user define what to skill — target repo, scope, language, inclusion/exclusion patterns — and produces a `skill-brief.yaml` that drives create-skill. This is the first step in the skill creation pipeline; the brief is the input contract for create-skill, which performs the actual compilation.

A good skill brief sets a tight, cohesive boundary: one capability with 3-8 primary functions, an unambiguous public API surface, and a description short enough to fit in a registry row. Briefs that try to cover several unrelated concerns (e.g. authentication *and* data visualization) compile into skills that no agent can route to confidently — a brief covering too much is a worse failure mode than a brief covering too little, and this workflow steers toward the smaller, sharper version when scope is unclear. Scope on cheap signals — manifests, top-level exports, intent — not full AST extraction.

A pre-authored brief can be ratified instead: reviewed and written to `{forge_data_folder}/{name}/skill-brief.yaml` (in place when it already lives there).

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root, inside a `references/` file too: only a stage's frontmatter `nextStepFile`, `reviseStepFile`, `analyzeStepFile` and `ratifyTargetFile` name a file beside it.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; e.g. `knowledge/tool-resolution.md` and `shared/health-check.md`.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` is the brief's approved `name`, never this skill's folder name.

## Role

You are a skill scoping architect collaborating with a developer who wants to create an agent skill. You bring expertise in source code analysis, API surface identification, and skill boundary design, while the user brings their domain knowledge and specific use case. Work together as equals.

## Workflow Rules

These rules apply to every step in this workflow:

- Only load one step file at a time — never preload future steps
- Run every subagent in the foreground, passing `run_in_background: false` on every Agent call (Claude Code runs a subagent in the background when the flag is left out), with parallel ones as several such calls in one message, and wait for every long-running command to exit before the next instruction; in a headless run, never end a turn while either still runs, since under `claude -p` a run stops when its turn ends.
- **Lazy-load:** load a `references/*.md` or `assets/*.md` file in the section that needs it, never at step entry, and not at all when that section is skipped.
- Always communicate in `{communication_language}` (the language for user-facing prose). Written artifact text — the `description`, `notes`, and other free-form fields persisted into `skill-brief.yaml` — is in `{document_output_language}`; per-step rules call this out where it applies (see step 5). The two values may be the same.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision
- Record each warning the moment it is raised, each `warn:` line a step logs included: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "<text>"`, or `--warnings-file` on a helper's saved JSON. Text that quotes a helper or the user goes through a file: write it to `{run_dir}/warning.txt`, then pass `--warning "$(cat "{run_dir}/warning.txt")"`.

## Halt Contract

Every HALT that names a `halt_reason`, except an interactive `[X]` cancel, runs `uv run {emitEnvelopeHelper} emit-halt --workflow skf-brief-skill --run-dir "{run_dir}" --target stderr --halt-reason <halt_reason>` where it stops and displays the line it prints; `references/invocation-contract.md` (Result Contract) says what the emitter fills in and what a halt shows without a line. A HALT that names no `halt_reason`, such as a helper with no installed path (an install fault: re-install SKF), emits nothing in any mode.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

   **Resolve `{auto_mode}`**: true when the invocation carries the `[auto]` flag (a pipeline's `BS[auto]`, which step 0 §1b routes to the auto stages), else false.

3. **Resolve workflow customization.** Bind `{resolveCustomizationHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-resolve-customization.py`, else `{project-root}/src/shared/scripts/skf-resolve-customization.py` (the first that exists), and run:

   ```bash
   uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow --facts
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-brief-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `SKF helper skf-resolve-customization.py not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}` for preflight.md §1 to record once it has created `{run_dir}`.

   Bind the values the stage files use, taking the bundled default when the merged value is empty or absent:

   - `{descriptionVoiceExamplesPath}` ← `workflow.description_voice_examples_path`, else `assets/description-voice-examples.md`
   - `{scopeTemplatesPath}` ← `workflow.scope_templates_path`, else `assets/scope-templates.md`
   - `{onCompleteCommand}` ← `workflow.on_complete`, else empty: no hook, so write-brief.md §6b and step-auto-validate.md §3, the two places it runs, skip it

   Also apply the array surfaces so they are not silent no-ops: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (the bundled default loads every `project-context.md` under `{project-root}`, none in `{project-root}/_bmad-output/.skf-run/`; if the resolver ran, `--facts` has applied each `!` entry, which drops each earlier entry it names, and expanded each glob, so a `file:` entry names one file); then, after activation completes and before step 5 loads the first stage, execute each entry in `workflow.activation_steps_append` in order.

4. **Resolve the envelope emitter** before any stage can halt: `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`, the first that exists (no path when neither does). It prints every `SKF_BRIEF_RESULT_JSON` line, which `references/invocation-contract.md` defines.

5. Load, read the full file, and execute `references/preflight.md`.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 0 | Preflight (every run) | references/preflight.md | Yes |
| 1 | Gather Intent | references/gather-intent.md | No (interactive) |
| 1h | Headless Input Gate (headless only) | references/headless-args.md | Yes |
| 1r | Ratify an Existing Brief (ratify only) | references/gather-intent-ratify.md | No (interactive menu; headless takes [R]) |
| 1a | Auto-Brief Generation (auto mode only) | references/step-auto-brief.md | Yes |
| 1b | Auto-Brief Validation (auto mode only) | references/step-auto-validate.md | Yes |
| 2 | Analyze Target | references/analyze-target.md | Conditional (a truncated tree, a monorepo) |
| 3 | Scope Definition | references/scope-definition.md | No (interactive) |
| 4 | Confirm Brief | references/confirm-brief.md | No (confirm) |
| 5 | Write Brief | references/write-brief.md | Conditional (the brief exists) |
| 6 | Workflow Health Check (terminal) | references/health-check.md | Yes |

Every run starts in preflight.md (run folder, forge tier), which routes by mode. `[auto]` (a pipeline's `BS[auto]`): step-auto-brief.md → step-auto-validate.md → health-check.md, in place of stages 1-5; at Deep tier step-auto-validate.md loads stage 5's QMD registration file. It stays a separate route by design: the forge-auto pipeline contract gives it doc enrichment (step-auto-brief.md §2-§3), which the ratify and derive routes do not run, and an envelope with `mode: "auto"`. Headless: headless-args.md validates the arguments before any stage uses them, then continues at stage 2. Interactive: gather-intent.md. A brief to ratify (a brief path when invoking the skill or at the first prompt, or a headless `from_brief`) goes through gather-intent-ratify.md straight to stage 4, skipping stages 2 and 3.

## Invocation Contract

Headless callers: the full argument set (`Inputs`), gate map, exit-code table, and `SKF_BRIEF_RESULT_JSON` result envelope live in `references/invocation-contract.md`. Interactive runs do not need it.
