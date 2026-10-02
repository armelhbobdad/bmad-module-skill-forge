---
name: skf-test-skill
description: Cognitive completeness verification — quality gate before export. Use when the user requests to "test a skill" or "verify skill completeness."
---

# Test Skill

## Overview

Verifies that a skill is complete enough to be useful to an AI agent by checking coverage of the public API surface (naive mode) or validating SKILL.md + references coherence (contextual mode). Produces a completeness score and gap report as a quality gate before export.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; e.g. `shared/references/output-contract-schema.md` and `shared/health-check.md`.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one. The coherence and migration rules cite `skf-create-skill/assets/skill-sections.md` and `skf-create-stack-skill/references/compose-mode-rules.md`.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` holds deterministic helpers, `assets/` the output section formats and `templates/` the test report template.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a skill auditor and completeness analyst operating in Ferris's Audit mode. This is a deterministic quality gate — you bring AST-backed analysis expertise and zero-hallucination verification, while the skill artifacts provide the evidence.

## Workflow Rules

These rules apply to every step in this workflow:

- Zero hallucination — every finding must trace to actual code with file:line citations
- Only load one step file at a time — never preload future steps
- Update `stepsCompleted` in output file frontmatter before loading next step
- Always communicate in `{communication_language}`
- No stage waits for an answer in headless mode: the one question, the skill name, halts `input-missing` there
- Every HARD HALT names its `halt_reason` and phase and carries exit code 1 (`exit_code` in its envelope); in headless mode it prints its envelope through the shared emitter, as each stage's **Halt envelope** paragraph shows
- Once `references/init.md` §6a has taken the run lock, every HALT after it first releases the lock, whatever the release prints (it never removes another run's lock): from `{project-root}`, run `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"`.
- The report is `{report_file}`: init.md §6c creates it as `.skf-test-report-{skill_name}-{run_id}.md`, and it takes its public name `test-report-{skill_name}-{run_id}.md` only once report.md §4c's checks pass, a blocked run's included, so a halted run never leaves a partial report where export-skill and update-skill look. The steps read the verdict inputs (`threshold`, `toolingStatus`, `workspaceDrift`, `testResult`) from its frontmatter, never from memory
- Run state (the scripts' files, the emitter's payloads) lives in `{run_dir}`: report.md §7 deletes it, a HALT keeps it

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load Skill | references/init.md | Yes |
| 2 | Detect Mode | references/detect-mode.md | Yes |
| 3 | Coverage Check | references/coverage-check.md | Yes |
| 4 | Coherence Check | references/coherence-check.md | Yes |
| 4b | External Validators | references/external-validators.md | Yes |
| 4c | Hard Gate | references/step-hard-gate.md | Yes |
| 5 | Score | references/score.md | Yes |
| 6 | Report | references/report.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

Headless callers: the full argument set (`Inputs`), the outputs, the exit codes and the `SKF_TEST_RESULT_JSON` result envelope live in `references/invocation-contract.md`. Interactive runs do not need it.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-test-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}`: report.md §4c hands it to the result as a warning.

   Apply the scalar fallbacks now so stage files don't have to repeat the conditional logic. For each scalar, if the merged value is empty or absent, use the bundled default:

   - `{testReportTemplatePath}` ← `workflow.test_report_template_path` if non-empty, else `templates/test-report-template.md`
   - `{defaultThreshold}` ← `workflow.default_threshold` if non-empty/non-null, else `80`. init.md §1b resolves the precedence (CLI, then per-pipeline default, then this scalar) once and writes `threshold` and `thresholdSource` into the report frontmatter, which score.md §1 reads.
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string (the post-finalization hook in `references/report.md` is then a no-op).

   Stash all three as workflow-context variables that stage files reference directly, with no conditional at the usage site. The scoring rules, the Gap Severity table and the output formats are not overridable: scripts own the scoring and the hard gate reads the table, so a house-style copy could change what blocks export.

   **Apply the array surfaces** (not silent no-ops): run `workflow.activation_steps_prepend` in order now; treat each `workflow.persistent_facts` entry as standing context for the run (`file:`-prefixed entries load their file/glob contents as facts: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off); then run `workflow.activation_steps_append` after activation.

4. Load, read the full file, and then execute `references/init.md` to begin the workflow.
