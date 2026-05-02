---
name: skf-brief-skill
description: Design a skill scope through guided discovery. Use when the user requests to "create a skill brief" or "brief a skill."
---

# Brief Skill

## Overview

Helps the user define what to skill — target repo, scope, language, inclusion/exclusion patterns — and produces a `skill-brief.yaml` that drives create-skill. This is the first step in the skill creation pipeline; the brief is the input contract for create-skill, which performs the actual compilation.

A good skill brief sets a tight, cohesive boundary: one capability with 3-8 primary functions, an unambiguous public API surface, and a description short enough to fit in a registry row. Briefs that try to cover several unrelated concerns (e.g. authentication *and* data visualization) compile into skills that no agent can route to confidently — a brief covering too much is a worse failure mode than a brief covering too little, and this workflow steers toward the smaller, sharper version when scope is unclear.

Brief-skill is split from create-skill so the scoping conversation runs *once*, on cheap signals (manifests, top-level exports, intent), without paying for AST extraction. Compilation is expensive; scoping decisions are cheap to revise. Keeping them in separate workflows lets a user iterate on the brief, share it for review, and re-run create-skill against the same brief whenever the upstream version moves.

## Role

You are a skill scoping architect collaborating with a developer who wants to create an agent skill. You bring expertise in source code analysis, API surface identification, and skill boundary design, while the user brings their domain knowledge and specific use case. Work together as equals.

## Workflow Rules

These rules apply to every step in this workflow:

- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- **Lazy-load references and assets:** `references/*.md` and `assets/*.md` files are loaded inside the section that needs them, not at step entry. If a section is skipped (e.g. `version-resolution.md` when `{extractPublicApiScript}` already returned a version, `scope-templates.md` for the `docs-only` branch that bypasses §2c), do not load that file. Each unnecessary load costs context (~5-10 KB per reference) and biases the LLM toward consulting material the current path does not need.
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Gather Intent | steps-c/step-01-gather-intent.md | No (interactive) |
| 2 | Analyze Target | steps-c/step-02-analyze-target.md | Yes |
| 3 | Scope Definition | steps-c/step-03-scope-definition.md | No (interactive) |
| 4 | Confirm Brief | steps-c/step-04-confirm-brief.md | No (confirm) |
| 5 | Write Brief | steps-c/step-05-write-brief.md | Yes |
| 6 | Workflow Health Check (terminal — chains to `shared/health-check.md`) | steps-c/step-06-health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `target_repo` [required], `skill_name` [required], `scope_hint` [optional], `language_hint` [optional], `target_version` [optional], `source_authority` [optional: official/community/internal, default community], `source_type` [optional: source/docs-only, default source], `doc_urls` [optional: list of `url[,label]` for source_type=docs-only or supplemental], `scope_type` [optional: full-library/specific-modules/public-api/component-library/reference-app/docs-only], `include` [optional: comma-separated globs], `exclude` [optional: comma-separated globs], `scripts_intent` [optional: detect/none/free-text, default detect], `assets_intent` [optional: detect/none/free-text, default detect], `intent` [optional: free-text used to derive description], `force` [optional: overwrite existing brief without prompting] |
| **Gates** | step-01: Input Gate [use args] | step-03: Confirm Gate [C] | step-04: Confirm Gate [C] |
| **Outputs** | `skill-brief.yaml` at `{forge_data_folder}/{skill-name}/skill-brief.yaml`; final `SKF_BRIEF_RESULT_JSON` line on stdout when `{headless_mode}` is true |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true; pre-supplied inputs consumed at the gates that would otherwise prompt; existing briefs are preserved unless `--force` was supplied (HALT with `overwrite-cancelled` otherwise) |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                  |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success              | step-06 (terminal)                                                                         |
| 2    | input-missing        | step-01 GATE — required headless arg absent (`target_repo`, `skill_name`)                  |
| 3    | resolution-failure   | step-01 §1 (`forge-tier.yaml` missing); step-02 §1 (target inaccessible / `gh auth` fails) |
| 4    | write-failure        | step-05 §4 (write to `{forge_data_folder}/{skill-name}/skill-brief.yaml` failed)           |
| 5    | overwrite-cancelled  | step-05 §2 (existing brief, `force` not supplied)                                          |

## Result Contract (Headless)

When `{headless_mode}` is true, step-05 emits a single-line JSON envelope on **stdout** before chaining to step-06, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_BRIEF_RESULT_JSON: {"status":"success|error","brief_path":"…|null","skill_name":"…","version":"…|null","language":"…|null","scope_type":"…|null","exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path, `"error"` on any HALT. `halt_reason` is one of: `null` (success), `"input-missing"`, `"forge-tier-missing"`, `"target-inaccessible"`, `"gh-auth-failed"`, `"write-failed"`, `"overwrite-cancelled"`. `exit_code` matches the table above.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-gather-intent.md` to begin the workflow.
