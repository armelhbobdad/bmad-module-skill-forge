---
name: skf-brief-skill
description: Design a skill scope through guided discovery. Use when the user requests to "create a skill brief" or "brief a skill".
---

# Brief Skill

## Overview

Helps the user define what to skill — target repo, scope, language, inclusion/exclusion patterns — and produces a `skill-brief.yaml` that drives create-skill. This is the first step in the skill creation pipeline; the brief is the input contract for create-skill, which performs the actual compilation.

A good skill brief sets a tight, cohesive boundary: one capability with 3-8 primary functions, an unambiguous public API surface, and a description short enough to fit in a registry row. Briefs that try to cover several unrelated concerns (e.g. authentication *and* data visualization) compile into skills that no agent can route to confidently — a brief covering too much is a worse failure mode than a brief covering too little, and this workflow steers toward the smaller, sharper version when scope is unclear.

Brief-skill is split from create-skill so the scoping conversation runs *once*, on cheap signals (manifests, top-level exports, intent), without paying for AST extraction. Compilation is expensive; scoping decisions are cheap to revise. Keeping them in separate workflows lets a user iterate on the brief, share it for review, and re-run create-skill against the same brief whenever the upstream version moves.

**Ratify path.** When the user already has a `skill-brief.yaml` produced by another workflow — typically `skf-analyze-source`'s `generate-briefs` step, where one analyze pass emits several recommended briefs — the brief can be *ratified* (reviewed and rewritten without re-deriving its fields) instead of authored from scratch. **Interactively:** invoke `/skf-brief-skill` with a path to that brief at the first prompt — gather-intent §3.1a loads the YAML, hydrates the brief context, and jumps straight to step 4 (confirm-brief) where the standard review/edit cycle still applies before step 5 writes. **Headlessly:** pass `from_brief <path>` — the step 1 §8 GATE runs the same schema validation and hydration and writes through the canonical writer (overwriting in place), enabling a fully headless analyze → brief → create pipeline that preserves the upstream-authored scope. Either path skips re-deriving fields the upstream draft already supplies and saves the 5-10 minutes a full re-run of intent + analyze + scope would cost.

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

   Stash all three as workflow-context variables. Stage files reference `{descriptionVoiceExamplesPath}` / `{scopeTemplatesPath}` / `{briefSchemaPath}` directly — no conditional at the usage site. Empty-string overrides cleanly fall through to the bundled default; non-empty values let orgs swap in house-style copies without forking the skill.

4. Load, read the full file, and execute `references/gather-intent.md`.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Gather Intent | references/gather-intent.md | No (interactive) |
| 2 | Analyze Target | references/analyze-target.md | Yes |
| 3 | Scope Definition | references/scope-definition.md | No (interactive) |
| 4 | Confirm Brief | references/confirm-brief.md | No (confirm) |
| 5 | Write Brief | references/write-brief.md | Yes |
| 6 | Workflow Health Check (terminal) | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `target_repo` [required], `skill_name` [required], `scope_hint` [optional], `language_hint` [optional], `target_version` [optional], `source_authority` [optional: official/community/internal, default community], `source_type` [optional: source/docs-only, default source], `doc_urls` [optional: list of `url[,label]` for source_type=docs-only or supplemental], `scope_type` [optional: full-library/specific-modules/public-api/component-library/reference-app/docs-only], `include` [optional: comma-separated globs], `exclude` [optional: comma-separated globs], `scripts_intent` [optional: detect/none/free-text, default detect], `assets_intent` [optional: detect/none/free-text, default detect], `intent` [optional: free-text used to derive description], `force` [optional: overwrite existing brief without prompting], `from_brief` [optional: path to a pre-authored `skill-brief.yaml` to *ratify* — when supplied it is the source of truth, `target_repo`/`skill_name` become optional/derived-from-brief, and the run mirrors the interactive §3.1a ratify path: schema-validate, skip analyze-target/scope-definition, write through the canonical writer in place] |
| **Gates** | step 1: Input Gate [use args] | step 3: Confirm Gate [C] | step 4: Confirm Gate [C] |
| **Outputs** | `skill-brief.yaml` at `{forge_data_folder}/{skill-name}/skill-brief.yaml`; final `SKF_BRIEF_RESULT_JSON` line on stdout when `{headless_mode}` is true |
| **Headless** | All gates auto-resolve with heuristic-driven or default action when `{headless_mode}` is true; pre-supplied inputs consumed at the gates that would otherwise prompt; absent `source_authority` and `scope_type` are resolved by signal-driven detection (see `references/headless-args.md`); existing briefs are preserved unless `--force` was supplied (HALT with `overwrite-cancelled` otherwise); supplying `from_brief <path>` instead routes the step 1 GATE to a ratify path that schema-validates the pre-authored brief, skips analyze-target/scope-definition, and writes through the canonical writer (overwriting in place, no `--force` needed) rather than deriving a new brief |
| **Transient-failure retry** | This workflow does **not** auto-retry network or subprocess failures. A failed `gh` fetch (analyze-target.md §1, portfolio-similarity-check.md), QMD probe, or extraction script is logged and surfaced in the final result envelope as a warning, but the workflow continues with whatever signal it has. Headless pipelines that want retry semantics should wrap the invocation at their orchestrator level (e.g. CI re-runner on non-zero exit). Rationale: brief-skill is read-mostly with one terminal write (the YAML at step 5); a partial-signal retry has more failure modes than just re-running the whole workflow, which is cheap. |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                  |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success              | step 6 (terminal)                                                                         |
| 2    | input-missing / input-invalid | step 1 GATE — required headless arg absent (`target_repo`, `skill_name`, or `doc_urls` when `source_type=docs-only`) → `input-missing`; enum violation, malformed semver, non-kebab `skill_name`, or step 5 brief-context schema validation failure → `input-invalid` |
| 3    | resolution-failure   | step 1 §1 (`forge-tier.yaml` missing); step 2 §1 (target inaccessible / `gh auth` fails) |
| 4    | write-failure        | step 1 §1 pre-flight write probe (data folder unwritable: read-only mount, disk full, permissions denied); step 5 §4 (write to `{forge_data_folder}/{skill-name}/skill-brief.yaml` failed) |
| 5    | overwrite-cancelled  | step 5 §2 (existing brief, `force` not supplied)                                          |
| 6    | user-cancelled       | any interactive menu in step 1/03/04 (user selected `[X]` Cancel and exit)                |

## Result Contract (Headless)

When `{headless_mode}` is true, step 5 emits a single-line JSON envelope on **stdout** before chaining to step 6, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_BRIEF_RESULT_JSON: {"status":"success|error","brief_path":"…|null","skill_name":"…","version":"…|null","language":"…|null","scope_type":"…|null","exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path, `"error"` on any HALT. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"forge-tier-missing"`, `"target-inaccessible"`, `"gh-auth-failed"`, `"write-failed"`, `"overwrite-cancelled"`, `"user-cancelled"`. `exit_code` matches the table above.
