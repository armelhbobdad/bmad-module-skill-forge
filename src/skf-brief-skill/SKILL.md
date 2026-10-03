---
name: skf-brief-skill
description: Design a skill scope through guided discovery. Use when the user requests to "create a skill brief" or "brief a skill".
---

# Brief Skill

## Overview

Helps the user define what to skill — target repo, scope, language, inclusion/exclusion patterns — and produces a `skill-brief.yaml` that drives create-skill. This is the first step in the skill creation pipeline; the brief is the input contract for create-skill, which performs the actual compilation.

A good skill brief sets a tight, cohesive boundary: one capability with 3-8 primary functions, an unambiguous public API surface, and a description short enough to fit in a registry row. Briefs that try to cover several unrelated concerns (e.g. authentication *and* data visualization) compile into skills that no agent can route to confidently — a brief covering too much is a worse failure mode than a brief covering too little, and this workflow steers toward the smaller, sharper version when scope is unclear. Scope on cheap signals — manifests, top-level exports, intent — not full AST extraction.

**Ratify path.** A pre-authored `skill-brief.yaml` (typically from `skf-analyze-source`) can be *ratified*: reviewed and written to `{forge_data_folder}/{name}/skill-brief.yaml` (in place when it already lives there) instead of derived again. Interactively, pass its path at the first prompt; headlessly, pass `from_brief <path>`. `references/invocation-contract.md` states the full ratify contract.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; e.g. `knowledge/tool-resolution.md` and `shared/health-check.md`.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `assets/` holds the brief schema, the scope templates and the description voice examples.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a skill scoping architect collaborating with a developer who wants to create an agent skill. You bring expertise in source code analysis, API surface identification, and skill boundary design, while the user brings their domain knowledge and specific use case. Work together as equals.

## Workflow Rules

These rules apply to every step in this workflow:

- Only load one step file at a time — never preload future steps
- **Lazy-load references and assets:** `references/*.md` and `assets/*.md` files are loaded inside the section that needs them, not at step entry. If a section is skipped (e.g. `version-resolution.md` when `{extractPublicApiHelper}` already returned a version, `scope-templates.md` for the `docs-only` branch that bypasses §2c), do not load that file. Each unnecessary load costs context (~5-10 KB per reference) and biases the LLM toward consulting material the current path does not need.
- Always communicate in `{communication_language}` (the language for user-facing prose). Written artifact text — the `description`, `notes`, and other free-form fields persisted into `skill-brief.yaml` — is in `{document_output_language}`; per-step rules call this out where it applies (see step 5). The two values may be the same.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision
- Keep one list of the run's warnings, `workflow_warnings[]`, in the order they are raised: each `warn:` line a step logs, each entry of a helper's `warnings[]` that a step surfaces, and each degraded signal the run goes on past (a truncated tree listing, a failed doc detection or QMD step), one line of text each. A helper warning that is an object, such as the `{field, message}` entries skf-validate-brief-inputs.py and skf-validate-brief-schema.py return, goes in as one line, `<field>: <message>`: the emitter takes only strings, and one object in `warnings` makes it exit non-zero and print no line. The run's `SKF_BRIEF_RESULT_JSON` envelope carries the list as `warnings`, at the end of a successful run and at a halt

## Halt Contract

Every HALT that names a `halt_reason`, in any step file, emits the `SKF_BRIEF_RESULT_JSON` error envelope before it stops when `{headless_mode}` or `{auto_mode}` is true, through the emitter On Activation step 4 resolves:

```bash
uv run {emitBriefEnvelopeHelper} emit --target stderr <<'SKF_BRIEF_HALT'
{"status":"error","skill_name":"<skill name>","halt_reason":"<halt_reason>","mode":<"auto" or null>,"warnings":[<workflow_warnings[] as JSON strings>]}
SKF_BRIEF_HALT
```

Give the halt's own `halt_reason`: the helper derives `exit_code` from it. `skill_name` is the resolved skill name, or `unknown` while step 1 has not resolved one; `mode` is `"auto"` while `{auto_mode}` is true, else `null`; `warnings` holds `workflow_warnings[]` (`[]` when it is empty). The quoted heredoc hands the payload to the helper as written, so a quote inside a warning needs no shell escaping. Display the line the helper prints verbatim, then HALT. If `{emitBriefEnvelopeHelper}` has no path, or the helper exits non-zero or prints no line, display the halt message alone: a pipeline that sees no envelope line treats the run as not completed cleanly. An interactive run outside `[auto]` mode displays the halt message and emits nothing. A HALT that names no `halt_reason`, such as a helper with no installed path (an install fault: re-install SKF), emits nothing in any mode.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

   **Resolve `{auto_mode}`**: true when the invocation carries the `[auto]` flag (a pipeline's `BS[auto]`, which step 1 §1b routes to the auto stages), else false.

3. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-brief-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case add `customization_resolver_unavailable: <reason>` to `workflow_warnings[]` as the run's first warning.

   Bind the values the stage files use, taking the bundled default when the merged value is empty or absent:

   - `{descriptionVoiceExamplesPath}` ← `workflow.description_voice_examples_path`, else `assets/description-voice-examples.md`
   - `{scopeTemplatesPath}` ← `workflow.scope_templates_path`, else `assets/scope-templates.md`
   - `{onCompleteCommand}` ← `workflow.on_complete`, else empty: no hook, so write-brief.md §6b and step-auto-validate.md §3, the two places it runs, skip it

   Also apply the array surfaces so they are not silent no-ops: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries are paths or globs whose contents load as facts, and the bundled default loads any `project-context.md` under `{project-root}`; an entry prefixed `!` loads nothing and drops each earlier entry it names); then, after activation completes and before step 5 loads the first stage, execute each entry in `workflow.activation_steps_append` in order.

4. **Resolve the envelope emitter** before any stage can halt: `{emitBriefEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-brief-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-brief-result-envelope.py`, the first that exists (no path when neither does). It prints every `SKF_BRIEF_RESULT_JSON` line of the run: a halt's through the Halt Contract above, the success line in write-brief.md §4b or step-auto-validate.md §3. `references/invocation-contract.md` defines the envelope.

5. Load, read the full file, and execute `references/gather-intent.md`.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
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

Every run starts in gather-intent.md, whose §1 (run folder, forge tier) serves every mode; its §1b routes by mode. `[auto]` (a pipeline's `BS[auto]`): step-auto-brief.md → step-auto-validate.md → health-check.md, in place of stages 2-5 except stage 5's §3b QMD registration, which step-auto-validate.md runs at Deep tier. It stays a separate route by design: the forge-auto pipeline contract gives it doc enrichment (step-auto-brief.md §2-§3), which the ratify and derive routes do not run, and an envelope with `mode: "auto"`. Headless: headless-args.md validates the arguments before any stage uses them, then continues at stage 2. Interactive: the rest of gather-intent.md. A brief to ratify (a brief path at the first prompt, or a headless `from_brief`) goes through gather-intent-ratify.md straight to stage 4, skipping stages 2 and 3.

## Invocation Contract

Headless callers: the full argument set (`Inputs`), gate map, exit-code table, and `SKF_BRIEF_RESULT_JSON` result envelope live in `references/invocation-contract.md`. Interactive runs do not need it.
