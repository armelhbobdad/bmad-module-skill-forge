---
name: skf-analyze-source
description: Discover what to skill in a large repo and produce recommended skill briefs. Use when the user requests to "analyze source for skills" or "discover skill opportunities."
---

# Analyze Source

## Overview

Analyzes a large repo or multi-service project to identify discrete skillable units, map exports and integration points, and produce recommended skill-brief.yaml files as the primary entry point for brownfield onboarding. The analysis must be thorough enough to produce actionable briefs, but scoped enough to avoid overwhelming the user with false positives. Exports come from the ast-grep recipe runner at every forge tier (read by eye where ast-grep is missing or the language has no recipe).

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; e.g. `shared/health-check.md`, which the terminal step chains to.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `assets/` holds the brief schema and `templates/` the analysis report skeleton.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a source code analyst and decomposition architect collaborating with a developer onboarding an existing project, pairing your codebase-analysis and skill-scoping expertise with their domain knowledge.

## Workflow Rules

These rules apply to every step in this workflow:

- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`; the text persisted into `skill-brief.yaml` (each recommendation's `description` and `scope.notes`) is written in `{document_output_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action, and record each one in the run sink as the gate says

## Stages

| # | Step | File | Auto-proceed | Condition |
|---|------|------|--------------|-----------|
| 1 | Initialize | references/init.md | Yes | Always |
| 1a | Auto-Scope | references/step-auto-scope.md | Conditional (the coexistence gate) | `[auto]` mode only: bypasses steps 2–6; owns pin resolution, coexistence detection, and the docs-only short-circuit |
| 1b | Continue (session resume) | references/continue.md | Yes | An unfinished report of the same target and inputs (init section 1) |
| 2 | Scan Project | references/scan-project.md | No (confirm) | Interactive mode only |
| 3 | Identify Units | references/identify-units.md | No (confirm) | Interactive mode only |
| 4 | Map & Detect | references/map-and-detect.md | No (confirm) | Interactive mode only |
| 5 | Recommend | references/recommend.md | No (confirm) | Interactive mode only |
| 6 | Generate Briefs | references/generate-briefs.md | No (confirm) | Interactive mode only |
| 7 | Workflow Health Check | references/health-check.md | Yes | Always |

**Auto mode path:** With `[auto]` present, init routes directly to step 1a, which loads a branch file only when its branch fires: `references/step-auto-scope-coexistence.md` (a skill already matches), `references/step-auto-scope-split.md` (a monorepo splits into N briefs) and `references/step-auto-scope-corpora.md` (a whole-language reference), and routes docs-only targets to `references/auto-docs-only.md`.

**[D] Discover Additional Source** (steps 4 and 5) loads `references/discover-additional-source.md`. Step 2 and [D] make each project path's scan root by `references/scan-root.md` (steps 3 and 4 make one again when a resumed session no longer finds it), and step 4 and [D] map each unit's exports by `references/map-unit-exports.md`.

**Shape detection reference:** `references/step-shape-detect.md` — loaded by step 1a as a reference doc (not a chained step).

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | project_path [required], intent_hint, scope_hint, target_ref or target_refs [optional]. `project_path` is a GitHub repo URL or a local path, or in `[auto]` mode a documentation URL (routed docs-only). An interactive run reads them from the invocation and asks at most one opening question. |
| **Headless inputs** | `--project-path <path>` (comma-separated for several), `--scope-hint <text>` (folders or packages to focus on or skip, `[auto]` included), `--intent-hint <text>` (the goal: ranks the step 5 recommendations; an interactive run also defers the units outside it before step 4, restorable, a headless run never; `[auto]` keeps a merged repo's facets it names), `--target-ref <ref>` (a tag or branch for every project path, written into every brief; not `[auto]`, which pins with `--pin`), `--target-refs <path:ref,...>` (one ref per path, written into each unit's brief; not with `--target-ref`, and not `[auto]`), `--pin <version>` (`[auto]` only: a tag or branch; absent, the latest release tag; a step-by-step analysis an `[auto]` run falls back to keeps its pin) |
| **Headless flag** | `--headless` / `-H` flips every confirm gate to auto-proceed |
| **Auto flag** | `[auto]` bracket modifier — activates auto-scope mode (step 1a; see **Auto mode path** above). Pipelines pass this as `AN[auto]`. Requires `--project-path`. |
| **Gates** | one per step: steps 2 to 4 [C] (step 4 also takes composite merges, default accept); step 5 [C] after the decisions (default: confirm every card, flag every stack skill candidate); step 6 [Y] (write briefs). Headless takes each default and records it in `headless_decisions`. Auto mode: only the step 1a coexistence gate (default [A]longside) |
| **Outputs** | analysis-report.md, skill-brief.yaml files (one per recommended unit) and the run's result files, written by every run that ends, zero confirmed units included; final `SKF_ANALYZE_RESULT_JSON` line on stdout when `{headless_mode}` is true. In auto mode, the envelope includes `"mode":"auto"`. |
| **Exit codes** | Envelope, emitter, result files, `halt_reason` enum and exit codes: `references/headless-contract.md` |

## On Activation

1. **Resolve the envelope helper.** `{emitEnvelopeHelper}` ← the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. If neither path exists, HARD HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `on-activation:helpers`) and display only: "`skf-emit-result-envelope.py` is missing. Nothing was changed. Re-install SKF." In headless mode every other HARD HALT prints its envelope on stderr through the emitter: with the first command below once step 5 has created `{run_dir}`, before that with the second, the payload on one line. `references/headless-contract.md` (Halt Envelope) gives the payload rules, and each step file restates them in its opening.

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --target stderr <<'SKF_ANALYZE_HALT'
   {"phase": "on-activation:config", "reason": "<the halt message>", "halt_reason": "input-missing", "mode": "interactive"}
   SKF_ANALYZE_HALT
   ```

2. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `forge_data_folder`, `skills_output_folder`, `sidecar_path`
   - If the config cannot be loaded, HARD HALT (exit code 2, `halt_reason: "input-missing"`, phase `on-activation:config`): "SKF cannot load `{project-root}/_bmad/skf/config.yaml`: the workflow has no forge context to run against. Run setup first." When `--headless` or `-H` was passed, print its envelope with the second command above.

3. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

4. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-analyze-source.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran) for step 5 to record in the run sink.

   Then bind, so stage files use the variable with no conditional at the usage site:

   - `{analysisReportTemplatePath}` ← `workflow.analysis_report_template_path` (the bundled `templates/analysis-report-template.md` when an override leaves it empty)
   - `{onCompleteCommand}` ← `workflow.on_complete` (empty: no hook)

   Run `workflow.activation_steps_prepend` now, and treat `workflow.persistent_facts` as standing context for the run (`file:`-prefixed entries load their file/glob contents as facts: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off).

5. **Create the run folder.** It holds what the run stages for its helpers (the tree listing, each brief's context, the subagents' unit records, the halt and result payloads) and the sink of its auto-decisions:

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-analyze-source-XXXXXXXX"
   ```

   Bind `{run_dir}` ← the path it prints. The step that ends the run deletes it once the envelope is out; a HARD HALT keeps it. If it cannot be created, HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `on-activation:run-folder`, path `{project-root}/_bmad-output/.skf-run`): "SKF cannot create its run folder under `{project-root}/_bmad-output/.skf-run/`: {the first stderr line}. Nothing was changed." Its envelope goes through the second command of step 1, its payload with `"customization_resolver_unavailable": "<reason>"` added when step 4 kept one. Once the folder exists and `{customization_resolver_unavailable}` is set, record the reason in the run sink: write `customization_resolver_unavailable: {customization_resolver_unavailable}` to `{run_dir}/resolver-warning.txt` with a file write, never `echo` (the reason can hold quotes or `$( )`), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"`.

6. Run `workflow.activation_steps_append`, then load, read the full file, and execute `references/init.md` to begin the workflow.
