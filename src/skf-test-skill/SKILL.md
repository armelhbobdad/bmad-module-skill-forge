---
name: skf-test-skill
description: Cognitive completeness verification — quality gate before export. Use when the user requests to "test a skill" or "verify skill completeness."
---

# Test Skill

## Overview

Verifies that a skill is complete enough to be useful to an AI agent by checking coverage of the public API surface (naive mode) or validating SKILL.md + references coherence (contextual mode). Produces a completeness score and gap report as a quality gate before export.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root, inside a `references/` file too: only a stage's frontmatter `nextStepFile` and `blockedStepFile` name a file beside it.
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
- Run every subagent in the foreground, passing `run_in_background: false` on every Agent call (Claude Code runs a subagent in the background when the flag is left out), with parallel ones as several such calls in one message, and wait for every long-running command to exit before the next instruction; in a headless run, never end a turn while either still runs, since under `claude -p` a run stops when its turn ends.
- Update `stepsCompleted` in output file frontmatter before loading next step
- Always communicate in `{communication_language}`
- No stage waits for an answer in headless mode: the one question, the skill name, halts `input-missing` there
- Every HARD HALT names its `halt_reason` and phase and carries exit code 1 (`exit_code` in its envelope); in headless mode it prints its envelope through the shared emitter, as each stage's **Halt envelope** paragraph shows
- Once `references/init.md` §6a has taken the run lock, every HALT after it first releases the lock, whatever the release prints (it never removes another run's lock): from `{project-root}`, run `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"`.
- From `references/init.md` §6a until report.md §7 releases it, renew the run lock each time a subagent dispatch returns (once for parallel calls sent in one message) or, without subagents, the main thread finishes the work a step gives a subagent, each time the main thread finishes reading a source file by eye (once for files read in one message), as each stage from detect-mode.md to report.md starts, before its first numbered section, and, with the `--stale-after 180` command below, right before each subagent dispatch (once for parallel calls sent in one message; before report.md §4b.2 spawns its discovery subagents, say) or, without subagents, before the main thread starts the work a step gives a subagent, since the lock goes stale 60 minutes after it was taken or last renewed: from `{project-root}`, run `uv run {runLockHelper} acquire --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"`. A renewal right before a dispatch or that work runs `uv run {runLockHelper} acquire --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}" --stale-after 180` instead, since nothing can renew the lock while one dispatch runs: the helper keeps that window in the lock, so no other run takes it over for 180 minutes, and the next renewal that passes no `--stale-after` sets it back to 60. Exit 3 (another run took the lock over) HALTs `another-run-active` with "**Another test-skill run took over the run lock for {skill_name}.** This run wrote no result files. {message}", the helper's `message`, and exit 1 or 2, or no JSON, HALTs `helper-failed` with its stderr message, each at phase `<step>:run-lock` (`coverage-check:run-lock`, say).
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

1. **Check the runtime, then load the config.** Every helper this workflow runs, the preflight included, runs through `uv run`, so first confirm that `uv` is on `$PATH` (`command -v uv`). If it is missing, HALT (`halt_reason: "runtime-missing"`, phase `on-activation:runtime`): "**test-skill needs `uv`, which is not on your PATH.** Install it (<https://docs.astral.sh/uv/getting-started/installation/>; it is a documented runtime prerequisite, see <https://armelhbobdad.github.io/bmad-module-skill-forge/getting-started/#prerequisites-full-reference>), then re-run." Nothing is written.

   Then bind `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` (the first that exists; init.md §0 binds the same path again), and load the config: `{preflightHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-preflight.py`, else `{project-root}/src/shared/scripts/skf-preflight.py` (the first that exists). Run it once:

   ```bash
   uv run {preflightHelper} "{project-root}" --allow-missing-sidecar
   ```

   It parses `{project-root}/_bmad/skf/config.yaml` and `{sidecar_path}/preferences.yaml` into one JSON object: bind `project_name`, `user_name`, `communication_language` and `document_output_language` from its `config`, and `skills_output_folder`, `forge_data_folder` and `sidecar_path` from `config.<name>_resolved`, each folder's absolute path. With `sidecar.preferences_error` (a `preferences.yaml` that is there but does not load), display that error in one line and go on with the defaults. If neither path exists, HALT (`halt_reason: "helper-missing"`, phase `on-activation:config`); if the call exits non-zero or prints no JSON, HALT (`halt_reason: "helper-failed"`, phase `on-activation:config`). Either displays "**test-skill cannot load its config.** {its `error` and `code`, such as `CONFIG_MISSING`, else its first stderr line, else: `skf-preflight.py` is missing, so re-install SKF.}" Nothing is written.

   **Halt envelope.** Step 2 has not resolved `{headless_mode}` yet, so under `--headless` or `-H` each HALT of this step first prints its envelope. No run folder exists yet, and the config halt's message quotes preflight's error, which names an absolute path, so the halt passes its fields as options and the message on stdin in a quoted heredoc, never typed into JSON:

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-test-skill --target stderr --phase '<phase>' --halt-reason '<halt_reason>' --reason - <<'SKF_REASON'
   <the halt message>
   SKF_REASON
   ```

   The emitter needs only the standard library, so when `uv` is the missing tool, bind `{emitEnvelopeHelper}` as above first, and the command runs with `python3` in place of `uv run`. Display the line it prints as the run's last line, then stop. With no emitter path, or when the emitter exits non-zero or prints no line, display the halt message alone.

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if step 1's preflight gave `derived.headless_mode` true (`headless_mode: true` in `{sidecar_path}/preferences.yaml`). Default: false.

3. **Resolve workflow customization.** Bind `{resolveCustomizationHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-resolve-customization.py`, else `{project-root}/src/shared/scripts/skf-resolve-customization.py` (the first that exists), and run:

   ```bash
   uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-test-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `SKF helper skf-resolve-customization.py not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}`: report.md §4c hands it to the result as a warning.

   Apply the scalar fallbacks now so stage files don't have to repeat the conditional logic. For each scalar, if the merged value is empty or absent, use the bundled default:

   - `{testReportTemplatePath}` ← `workflow.test_report_template_path` if non-empty, else `templates/test-report-template.md`
   - `{defaultThreshold}` ← `workflow.default_threshold` if non-empty/non-null, else `80`. init.md §1b resolves the precedence (CLI, then per-pipeline default, then this scalar) once and writes `threshold` and `thresholdSource` into the report frontmatter, which score.md §1 reads.
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string (the post-finalization hook in `references/report.md` is then a no-op).

   Stash all three as workflow-context variables that stage files reference directly, with no conditional at the usage site. The scoring rules, the Gap Severity table and the output formats are not overridable: scripts own the scoring and the hard gate reads the table, so a house-style copy could change what blocks export.

   **Apply the array surfaces** (not silent no-ops): run `workflow.activation_steps_prepend` in order now; treat each `workflow.persistent_facts` entry as standing context for the run (`file:`-prefixed entries load their file/glob contents as facts: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off); then run `workflow.activation_steps_append` after activation.

4. Load, read the full file, and then execute `references/init.md` to begin the workflow.
