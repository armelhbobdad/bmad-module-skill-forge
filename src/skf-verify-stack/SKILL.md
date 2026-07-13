---
name: skf-verify-stack
description: Pre-code stack feasibility verification against architecture and PRD documents. Use when the user requests to "verify a tech stack" or "verify stack."
---

# Verify Stack

## Overview

Cross-references generated skills against architecture and PRD documents to produce a feasibility report with evidence-backed integration verdicts, coverage analysis, and requirements mapping. Read-only: it reads skills and input documents and writes only the feasibility report (see Workflow Rules).

**Schema contract:** This skill is the producer of the SKF shared feasibility report schema — every report conforms to it.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a stack feasibility analyst and integration verifier operating in Ferris Audit mode. You bring expertise in API surface analysis, cross-library compatibility assessment, and architecture validation, while the user brings their architecture vision and generated skills.

## Workflow Rules

These rules apply to every step in this workflow:

- Read-only — never modify skills, architecture docs, or PRD files
- Every verdict must cite evidence from the generated skills
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load Inputs | references/init.md | No (confirm) |
| 2 | Coverage Analysis | references/coverage.md | Yes |
| 3 | Integration Verification | references/integrations.md | Yes |
| 4 | Requirements Mapping | references/requirements.md | Yes |
| 5 | Synthesize Verdict | references/synthesize.md | Yes |
| 6 | Report | references/report.md | No (confirm) |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | architecture_doc_path [required], prd_path [optional], previous_report_path [optional] |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--architecture-doc <path>` (skip step 1 prompt for the required input); `--prd <path>` (skip step 1 prompt for the optional PRD); `--previous-report <path>` (skip step 1 prompt for delta comparison) |
| **Gates** | step 1 Input Gate (use args); step 6 Report Menu ([R] review / [X] exit, headless default X). Steps 2-3 also hold elective vacuous-analysis guards (0% coverage, all-Blocked) that only fire in degenerate cases; every guard auto-resolves to Continue in headless. |
| **Outputs** | `feasibility-report-{projectSlug}-{timestamp}.md` and `feasibility-report-{projectSlug}-latest.md` (copy, not symlink) per the SKF shared feasibility report schema (`_bmad/skf/shared/references/feasibility-report-schema.md`; `src/shared/references/…` in a dev checkout) — with integration verdicts, coverage analysis, recommendations, and evidence sources; plus `verify-stack-result-{timestamp}.json` and `verify-stack-result-latest.json` |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Per-flag args (`--architecture-doc`, `--prd`, `--previous-report`) consumed at the gates that would otherwise prompt. |
| **Exit codes** | See `references/exit-codes.md` |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 emits a single-line JSON envelope on **stdout** before chaining to step 7, and every headless hard halt emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_VERIFY_STACK_RESULT_JSON: {"status":"success|error","report_path":"…|null","report_latest_path":"…|null","overall_verdict":"…|null","coverage_percentage":0,"recommendation_count":0,"exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path, `"error"` on any halt. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"skills-folder-missing"`, `"insufficient-skills"`, `"forge-folder-unconfigured"`, `"resolution-failure"`, `"previous-report-collision"`, `"inventory-unreliable"`, `"schema-violation"`, `"write-failed"`, `"user-cancelled"`. `exit_code` matches `references/exit-codes.md` (the `analysis-halted` / exit-8 gates are interactive-only, so they never reach this envelope). `overall_verdict` uses the schema tokens (`FEASIBLE`/`CONDITIONALLY_FEASIBLE`/`NOT_FEASIBLE`).

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Compute run-scoped variables** (same place as config so every stage can reference them without re-derivation):
   - `project_slug` ← slugify `project_name` (lowercase, hyphens only, no unicode, no whitespace)
   - `timestamp` ← UTC `YYYYMMDD-HHmmss` captured at activation time
   - These two combine in init.md §4 into `{outputFile}` per the stage frontmatter template, but the values themselves are fixed for the entire workflow run — every later reference to `{outputFile}` resolves consistently.

3. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

4. **Resolve workflow customization.** Run:

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

   - `{reportTemplatePath}` ← `workflow.report_template_path` if non-empty, else `assets/feasibility-report-template.md`
   - `{integrationRulesPath}` ← `workflow.integration_rules_path` if non-empty, else `references/integration-verification-rules.md`
   - `{coveragePatternsPath}` ← `workflow.coverage_patterns_path` if non-empty, else `references/coverage-patterns.md`
   - `{outputFolderPath}` ← `workflow.output_folder_path` if non-empty, else `{forge_data_folder}`

   Stash all four as workflow-context variables. Stage files reference them directly — no conditional at the usage site. Empty-string overrides cleanly fall through to the bundled default.

   The same merge resolves `workflow.on_complete` (default empty = no-op); report.md §5 executes it, if non-empty, at the terminal stage.

   Also apply the array surfaces so they are not silent no-ops: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries load their file/glob contents as facts — the bundled default glob is `{project-root}/**/project-context.md`); then execute each entry in `workflow.activation_steps_append` after activation completes.

5. **Pre-flight write probe.** Verify `{outputFolderPath}` is writable. A read-only mount, full disk, or permissions-denied path otherwise only surfaces at init.md §4 atomic write — by then the user has already gone through the input prompts:

   ```bash
   mkdir -p "{outputFolderPath}" && \
     printf 'probe' > "{outputFolderPath}/.skf-write-probe" && \
     rm "{outputFolderPath}/.skf-write-probe"
   ```

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`). In headless mode, emit the error envelope per **Result Contract (Headless)** with `report_path: null`, `report_latest_path: null`, `overall_verdict: null`.

6. Load, read the full file, and then execute `references/init.md` to begin the workflow.
