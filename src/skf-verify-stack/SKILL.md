---
name: skf-verify-stack
description: Pre-code stack feasibility verification against architecture and PRD documents. Use when the user requests to "verify a tech stack" or "verify stack."
---

# Verify Stack

## Overview

Cross-references generated skills against architecture and PRD documents to produce a feasibility report with evidence-backed integration verdicts, coverage analysis, and requirements mapping. Read-only: it reads skills and input documents and writes only the feasibility report, its result files and a scratch run folder (see Workflow Rules).

**Schema contract:** This skill is the producer of the SKF shared feasibility report schema — every report conforms to it.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; e.g. `shared/references/output-contract-schema.md` and `shared/health-check.md`.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.

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
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision; a gate that picks its default for the user (step 1's offer of the newest earlier report) also records that decision in the run sink the moment it decides
- Every helper a stage runs (a `scripts/` file, or a shared helper from the stage's probe order) is required: if the probe order resolves to no path, or the helper cannot start, HALT (exit code 3, `halt_reason: "resolution-failure"`) at the stage's phase, through the stage's halt envelope. Never recompute a helper's result by hand: the main-thread rule above covers subagent work, not helpers.
- Every HARD HALT names its exit code, `halt_reason` and phase, and in headless mode prints its envelope through the shared emitter, with the command each stage file shows (`references/exit-codes.md` describes the envelope).
- Stages 1 to 5 write only the timestamped report `{outputFile}`, and each write that fails halts (exit code 4, `halt_reason: "write-failed"`). Step 6 copies the report to `{outputFileLatest}` only after it passes the feasibility-report check, so a run that halts before then leaves the previous finished copy, the one consumers read, in place.
- Run state lives in `{run_dir}`, not in context; step 6 deletes it, a HALT keeps it.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load Inputs | references/init.md | No (confirm) |
| 2 | Coverage Analysis | references/coverage.md | Yes |
| 3 | Integration Verification | references/integrations.md | Yes |
| 4 | Requirements Mapping | references/requirements.md | Yes |
| 5 | Synthesize Verdict | references/synthesize.md | Yes |
| 6 | Report | references/report.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | architecture_doc_path [required], prd_path [optional], previous_report_path [optional] |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--architecture-doc <path>` (skip step 1 prompt for the required input); `--prd <path>` (skip step 1 prompt for the optional PRD); `--previous-report <path>` (skip step 1 prompt for delta comparison) |
| **Gates** | step 1 Input Gate (use args), including the offer to compare against the newest earlier report (headless default: use it). No later stage waits for input: a run with 0% coverage or only Blocked pairs prints one warning and continues, so its report still carries the recommendations. |
| **Outputs** | `feasibility-report-{project_slug}-{timestamp}.md` and its `feasibility-report-{project_slug}-latest.md` copy (not a symlink), written by step 6 once the finished report passes the feasibility-report check, both per the SKF shared feasibility report schema (`{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md`; `{project-root}/src/shared/references/feasibility-report-schema.md` in a dev checkout), with integration verdicts, coverage analysis, recommendations, and evidence sources; plus `verify-stack-result-{YYYYMMDD-HHmmss}.json` and `verify-stack-result-latest.json` in `{forge_data_folder}` |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Per-flag args (`--architecture-doc`, `--prd`, `--previous-report`) consumed at the gates that would otherwise prompt. |
| **Exit codes** | See `references/exit-codes.md` |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 prints one `SKF_VERIFY_STACK_RESULT_JSON: {...}` line on **stdout** and every HARD HALT one on **stderr**, built by the shared emitter: `references/exit-codes.md` gives its fields, the `halt_reason` values and the halt command.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Fix the run-scoped variables** so no stage derives them again:
   - `timestamp` ← UTC `YYYYMMDD-HHmmss` captured at activation time
   - `project_slug` is bound by init.md before its §1, from the shared feasibility-report helper, which holds the one slug rule the consumers of this report also apply; never slugify `project_name` by hand
   - The two combine in init.md §4 into `{outputFile}` and `{outputFileLatest}` per the stage frontmatter template, and stay fixed for the whole run, so every later reference to either file resolves to the same path.
   - `run_dir` ← `{project-root}/_bmad-output/.skf-run/skf-verify-stack-{timestamp}`, the run folder init.md creates first

3. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

   **Bind the inputs** in every mode: `{architecture_doc_path}` ← the `--architecture-doc` value, `{prd_path}` ← `--prd` and `{previous_report_path}` ← `--previous-report`, each null when its flag is absent. init.md §1 asks only for those still null.

4. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-verify-stack.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran) for init.md to record once it has created `{run_dir}`.

   Apply the path-scalar fallback now so stage files don't repeat it: `{reportTemplatePath}` ← `workflow.report_template_path` if non-empty, else `assets/feasibility-report-template.md`. An empty or absent value falls through to that default, and init.md §4 loads the variable as it is. Bind `{outputFolderPath}` ← `{forge_data_folder}`, always (no setting moves it): the report and its `-latest` copy go where create-stack-skill and refine-architecture look for them, and step 1 finds the earlier reports there.

   The same merge resolves `workflow.on_complete` (default empty = no-op); report.md §5 executes it, if non-empty, at the terminal stage.

   Also apply the array surfaces so they are not silent no-ops: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries load their file/glob contents as facts: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off); then execute each entry in `workflow.activation_steps_append` after activation completes.

5. **Pre-flight: the emitter.** Before the first prompt, resolve `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` (the first that exists). If neither exists, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `on-activation:emitter` and display only: "Verify Stack cannot run without `skf-emit-result-envelope.py`, which is not installed. Re-install SKF."

6. Load, read the full file, and then execute `references/init.md` to begin the workflow.
