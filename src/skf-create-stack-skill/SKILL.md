---
name: skf-create-stack-skill
description: Consolidated project stack skill with integration patterns — code-mode (analyzes manifests) or compose-mode (synthesizes from existing skills + architecture doc). Use when the user requests to "create a stack skill", "forge a stack", or "stack this project".
---

# Create Stack Skill

## Overview

Produces a consolidated stack skill documenting how libraries connect. **Code-mode** analyzes dependency manifests and co-import patterns from actual source code. **Compose-mode** synthesizes from pre-generated individual skills and architecture documents when no codebase exists yet. Every finding must trace to actual code with file:line citations; in compose-mode, inferred integrations are permitted but must be labeled `[inferred from shared domain]`.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a dependency analyst and integration architect. You bring expertise in dependency analysis, cross-library integration patterns, and compositional architecture, while the user brings their project knowledge and scope preferences.

## Workflow Rules

These rules apply to every step in this workflow:

- Zero hallucination — all extracted content must trace to actual source code (compose-mode inferences must be labeled)
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision
- Warnings use a single accumulator — see `## Workflow state contract` below for shape and surfacing.

## Workflow state contract

Every step that emits a warning ("log a warning", "record in workflow state for the evidence report", "Warning: ...", etc.) appends a structured entry to a single in-memory list named `workflow_warnings[]`. Each entry has the shape `{step: "step-NN", severity: "info|warn|error", code: "<short-slug>", message: "<human text>", context: {<optional fields>}}`. Step 7 surfaces these in `evidence-report.md`; step 8 may add validation findings; step 9 §5 reads the accumulated list and renders the user-facing "Warnings" section. There is exactly one accumulator for the whole workflow — do not invent per-step channels.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Mode Detection | references/init.md | No (confirm) |
| 2 | Detect Manifests | references/detect-manifests.md | Yes |
| 3 | Rank & Confirm Libraries | references/rank-and-confirm.md | No (confirm) |
| 4 | Parallel Extract | references/parallel-extract.md | Yes |
| 5 | Detect Integrations | references/detect-integrations.md | Yes |
| 6 | Compile Stack | references/compile-stack.md | No (review) |
| 7 | Generate Output | references/generate-output.md | Yes |
| 8 | Validate | references/validate.md | Yes |
| 9 | Report | references/report.md | Yes |
| 10 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | project_path [required], mode (code/compose) [auto-detected] |
| **Gates** | step 3: Confirm Gate [C] | step 6: Review Gate [C] |
| **Outputs** | SKILL.md (stack), context-snippet.md, metadata.json |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                  |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success              | step 10 (terminal handoff to shared health-check)                                          |
| 2    | input-missing / input-invalid | step 1 §0 (`config.yaml` missing or malformed); step 2 §2 headless cannot proceed without manifests (S2); step 4 §3 all extractions failed (B7); step 5 §2 feasibility-report `schemaVersion` mismatch; compose-mode-rules `schemaVersion` mismatch |
| 3    | resolution-failure   | step 1 §1 (`forge-tier.yaml` missing); step 2 §0 compose-mode skill resolution corruption (manifest + symlink both fail); step 2 §0 compose-mode zero qualifying skills (S1/S3) |
| 4    | write-failure        | step 7 §1 stage-dir / commit-dir failure; step 7 §1 group-dir collision when an existing non-stack skill occupies the target path |
| 5    | overwrite-cancelled  | step 7 collision when the user declines to replace an existing stack package |
| 6    | user-cancelled       | any interactive menu in step 3 / step 6 (user selected `[X]` Cancel and exit) |

## Result Contract (Headless)

When `{headless_mode}` is true, step 9 emits a single-line JSON envelope on **stdout** before chaining to step 10, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_STACK_RESULT_JSON: {"status":"success|error","skill_package":"…|null","skill_name":"…","stack_libraries":["…"],"mode":"code|compose","exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path, `"error"` on any HALT. `skill_package` is the absolute path to the committed stack-skill directory (or `null` on error before commit). `skill_name` is the stack skill's published name (e.g. `{project_name}-stack`). `stack_libraries` is the array of library names included in the stack (constituent skill names in compose-mode, dependency names in code-mode). `mode` is `"code"` or `"compose"` per the run's resolved mode. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"forge-tier-missing"`, `"config-missing"`, `"no-manifests"`, `"all-extractions-failed"`, `"schema-version-mismatch"`, `"resolution-failure"`, `"write-failure"`, `"overwrite-cancelled"`, `"user-cancelled"`. `exit_code` matches the table above.

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
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append):

   - `{skill-root}/customize.toml` — bundled defaults
   - `_bmad/custom/<skill-name>.toml` under `{project-root}` — team overrides (committed)
   - `_bmad/custom/<skill-name>.user.toml` under `{project-root}` — personal overrides (gitignored)

   If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly — the bundled defaults are an empty string for each path scalar.

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each of the four scalars, if the merged value is empty or absent, use the bundled default:

   - `{stackSkillTemplatePath}` ← `workflow.stack_skill_template_path` if non-empty, else `assets/stack-skill-template.md`
   - `{integrationPatternsPath}` ← `workflow.integration_patterns_path` if non-empty, else `references/integration-patterns.md`
   - `{manifestPatternsPath}` ← `workflow.manifest_patterns_path` if non-empty, else `references/manifest-patterns.md`
   - `{composeModeRulesPath}` ← `workflow.compose_mode_rules_path` if non-empty, else `references/compose-mode-rules.md`

   Stash all four as workflow-context variables. Stage files reference `{stackSkillTemplatePath}` / `{integrationPatternsPath}` / `{manifestPatternsPath}` / `{composeModeRulesPath}` directly — no conditional at the usage site. Empty-string overrides cleanly fall through to the bundled default; non-empty values let orgs swap in house-style copies without forking the skill.

4. Load, read the full file, and then execute `references/init.md` to begin the workflow.
