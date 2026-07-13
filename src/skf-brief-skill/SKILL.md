---
name: skf-brief-skill
description: Design a skill scope through guided discovery. Use when the user requests to "create a skill brief" or "brief a skill".
---

# Brief Skill

## Overview

Helps the user define what to skill — target repo, scope, language, inclusion/exclusion patterns — and produces a `skill-brief.yaml` that drives create-skill. This is the first step in the skill creation pipeline; the brief is the input contract for create-skill, which performs the actual compilation.

A good skill brief sets a tight, cohesive boundary: one capability with 3-8 primary functions, an unambiguous public API surface, and a description short enough to fit in a registry row. Briefs that try to cover several unrelated concerns (e.g. authentication *and* data visualization) compile into skills that no agent can route to confidently — a brief covering too much is a worse failure mode than a brief covering too little, and this workflow steers toward the smaller, sharper version when scope is unclear. Scope on cheap signals — manifests, top-level exports, intent — not full AST extraction.

**Ratify path.** A pre-authored `skill-brief.yaml` (typically from `skf-analyze-source`'s `generate-briefs` step) can be *ratified* — reviewed and rewritten in place — instead of re-derived from scratch. Interactively, pass its path at the first prompt; headlessly, pass `from_brief <path>`. See the `from_brief` Inputs cell in `references/invocation-contract.md` for the full ratify contract.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
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

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append):

   - `{skill-root}/customize.toml` — bundled defaults
   - `_bmad/custom/<skill-name>.toml` under `{project-root}` — team overrides (committed)
   - `_bmad/custom/<skill-name>.user.toml` under `{project-root}` — personal overrides (gitignored)

   If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly — the bundled defaults are an empty string for each path scalar.

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each of the three scalars, if the merged value is empty or absent, use the bundled default:

   - `{descriptionVoiceExamplesPath}` ← `workflow.description_voice_examples_path` if non-empty, else `assets/description-voice-examples.md`
   - `{scopeTemplatesPath}` ← `workflow.scope_templates_path` if non-empty, else `assets/scope-templates.md`
   - `{briefSchemaPath}` ← `workflow.brief_schema_path` if non-empty, else `assets/skill-brief-schema.md`
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string (no-op — write-brief.md skips the hook invocation entirely)

   Stash all four as workflow-context variables. Stage files reference `{descriptionVoiceExamplesPath}` / `{scopeTemplatesPath}` / `{briefSchemaPath}` / `{onCompleteCommand}` directly — no conditional at the usage site. Empty-string overrides cleanly fall through to the bundled default; non-empty values let orgs swap in house-style copies (or wire in a pipeline hook) without forking the skill.

   Also apply the array surfaces so they are not silent no-ops: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries are paths or globs whose contents load as facts — the bundled default loads any `project-context.md` under `{project-root}`); then, after activation completes and before step 4 loads the first stage, execute each entry in `workflow.activation_steps_append` in order.

4. Load, read the full file, and execute `references/gather-intent.md`.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Gather Intent | references/gather-intent.md | No (interactive) |
| 1a | Auto-Brief Generation (auto mode only) | references/step-auto-brief.md | Yes |
| 1b | Auto-Brief Validation (auto mode only) | references/step-auto-validate.md | No (interactive gate — headless auto-approves) |
| 2 | Analyze Target | references/analyze-target.md | Yes |
| 3 | Scope Definition | references/scope-definition.md | No (interactive) |
| 4 | Confirm Brief | references/confirm-brief.md | No (confirm) |
| 5 | Write Brief | references/write-brief.md | Yes |
| 6 | Workflow Health Check (terminal) | references/health-check.md | Yes |

Stages 1a-1b are conditional — they replace stages 2-5 when BS is invoked with the `[auto]` flag via pipeline context. The routing decision is made in stage 1 (gather-intent.md §1b). In auto mode, the chain is: gather-intent.md §1 (forge tier) → §1b (auto check) → step-auto-brief.md → step-auto-validate.md → health-check.md (on [A]pprove or [E]dit) or → confirm-brief.md → write-brief.md → health-check.md (on [R]eject).

## Invocation Contract

Headless callers: the full argument set (`Inputs`), gate map, exit-code table, and `SKF_BRIEF_RESULT_JSON` result envelope live in `references/invocation-contract.md`. Interactive runs do not need it.
