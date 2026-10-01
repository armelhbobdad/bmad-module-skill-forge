---
name: skf-update-skill
description: Smart regeneration preserving [MANUAL] sections after source changes. Use when the user requests to "update a skill" or "regenerate a skill."
---

# Update Skill

## Overview

Surgically updates existing skills when source code changes, preserving all [MANUAL] developer content while re-extracting only affected exports with full provenance tracking; unchanged content is never touched, and each regenerated instruction cites code by file:line. Stack skills (`skill_type: "stack"` in metadata.json) are not updated here: this workflow redirects them to `skf-create-stack-skill`, which re-composes them from updated constituents.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root — stage files reference `knowledge/version-paths.md` and `knowledge/tool-resolution.md`, and the terminal step chains to `shared/health-check.md`.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Cross-skill data coupling:** stages load shared assets from `skf-create-skill`, so create and update extract alike: `re-extract.md` pulls `extraction-patterns.md`, `extraction-patterns-tracing.md` and `tier-degradation-rules.md` from `skf-create-skill/references/`; `init.md` §6c reads the version files the Version Reconciliation section of `skf-create-skill/references/source-resolution-protocols.md` lists, and `skf-source-tree.py` (init.md §6b) computes a remote skill's clone path with its workspace rule; `write.md` reads `skill-sections.md` from `skf-create-skill/assets/`. These files must be installed, with semantics stable across both skills.

## Role

You are a precision code analyst operating in Ferris Surgeon mode. This is a surgical operation, not an exploratory session. You bring AST-backed structural analysis and provenance-driven change detection expertise, while the source code provides the ground truth.

## Workflow Rules

These rules apply to every step in this workflow:

- Never hallucinate — every statement must have AST provenance
- [MANUAL] sections survive regeneration with zero content loss
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision
- Every HALT, ABORT or other exit before step 8 runs the **Halt procedure** of the step file it fires in: one `{runStateHelper}` `halt` call that undoes this run's writes, removes the private source tree, releases the run lock and, headless, prints the halt's line. A halt never falls through to step 7.
- While `{source_tree}` is bound, a step that finds `{source_root}` missing HALTs with status `blocked` (`error.phase` `<step>:source-tree-missing`) instead of reading its files as deleted.
- **Run log.** Warnings and gate decisions live in the run folder, never only in context: record a warning at once with `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "<text>"` from `{project-root}`, and each gate's decision with `record --decision`.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load | references/init.md | No (confirm) |
| 2 | Detect Changes | references/detect-changes.md | Yes |
| 3 | Re-Extract | references/re-extract.md | Yes |
| 4 | Merge | references/merge.md | Yes |
| 5 | Validate | references/validate.md | Yes |
| 6 | Write | references/write.md | Yes |
| 7 | Report | references/report.md | Yes |
| 8 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required]: the skill's name or folder path, as the argument. With none, an interactive run offers the skills SKF generated, and a headless run halts `blocked` (`error.phase` `init:skill-name`, `error.reason` starting `input-missing`) |
| **Flags** | `--headless` / `-H`; `--from-test-report` (gap-driven mode); `--target-ref <ref>`; `--allow-workspace-drift` (gap-driven only: update-skill takes nothing from HEAD, and a gap that needs the pinned tree, a rescope included, halts `halted-for-workspace-drift` before merge); `--allow-degraded`; `--detect-only` (status `detect-only`); `--dry-run` (status `dry-run`, writes nothing in any mode; a re-extract halt such as `halted-for-remediation-path` or `halted-for-workspace-drift` still stops it). init.md §1 describes each; `--detect-only` wins over `--dry-run`. |
| **Gates** | step 1: Confirm Gate [C]; init.md §4b's [G]/[S] test-report offer, interactive only (headless warns `unconsumed-test-report`) | step 4: Confirm Gate [C if clean merge, HALT if conflicts] |
| **Outputs** | A new version folder `{skill_group}/{new_version}/` and its forge folder, beside the unchanged previous version (a gap-driven repair writes the current version in place), and a finished run's `update-skill-result-{YYYYMMDD-HHmmss}.json` and `update-skill-result-latest.json` in that version's forge folder (a run that found no change: the current one's). `--detect-only` and `--dry-run` write none of these, nor the skill brief. Run state goes to a run folder under `{project-root}/_bmad-output/.skf-run/` that step 8 removes; a halt keeps it |
| **Concurrency** | A second real update of the same skill halts `halted-for-concurrent-run` while the first holds its run lock (init.md §1b); `--detect-only` and `--dry-run` take no lock. A remote skill is read from a private tree, and no mode writes to the shared workspace clone before write.md §6b. |
| **Headless** | Every gate auto-resolves with its default action. One `SKF_UPDATE_RESULT_JSON` line (report.md §5b), at step 7 or at a HALT, printed by the shared emitter and checked against `shared/scripts/schemas/skf-update-result-envelope.v1.json`. Pipelines branch on `skf_update.status`: `success`, `no-changes`, `detect-only` and `dry-run` are successful exits. |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false. Bind `{requested_skill}` ← the skill name or folder path the invocation passes (its argument that is neither a flag nor a flag's value), else empty: `references/init.md` §1 takes it as the skill without asking.

3. **Resolve the shared helpers and create the run folder**, before anything can halt. Resolve `{emitEnvelopeHelper}` ← the first that exists of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`.
   Resolve `{runStateHelper}` ← the first that exists of `{project-root}/_bmad/skf/shared/scripts/skf-update-run-state.py` and `{project-root}/src/shared/scripts/skf-update-run-state.py`. Then, from `{project-root}`, run:

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-update-skill-XXXXXXXX"
   ```

   Bind `{run_dir}` ← the path it prints and `{run_id}` ← its folder name less `skf-update-skill-`.

   If a helper is missing or the folder cannot be created, HALT: display "**SKF cannot start this update:** {the missing helper (re-install SKF), or the command's first stderr line}. Nothing was changed." Headless, when the emitter resolved, print the halt's line with no run folder, from `{project-root}`:

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-update-skill <<'SKF_JSON'
   {"status": "blocked", "phase": "on-activation:run-folder", "path": "{project-root}/_bmad-output/.skf-run", "reason": "<which helper is missing, or that stderr line>", "skill_name": "unknown", "version": "unknown", "previous_version": "unknown", "update_mode": "normal"}
   SKF_JSON
   ```

4. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   This merges the three layers per `bmad-customize` rules (scalars override, arrays append): `{skill-root}/customize.toml` (bundled defaults), `_bmad/custom/<skill-name>.toml` under `{project-root}` (team overrides), and `_bmad/custom/<skill-name>.user.toml` under `{project-root}` (personal overrides). If the script is missing or fails, read `{skill-root}/customize.toml` directly and add `customization_resolver_unavailable: <the reason>` to `warnings[]`.

   Apply the resolved values so no surface is a silent no-op: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (entries prefixed `file:` are paths or globs whose contents load as facts: the bundled default loads any `project-context.md` under `{project-root}`); resolve `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string, and stash it in workflow context (`references/report.md` §5b runs it after a finished run's result files, never in `--detect-only`, `--dry-run` or a halt; empty = no-op). After activation completes, execute each entry in `workflow.activation_steps_append` in order before `init.md` runs.

5. Load, read the full file, and then execute `references/init.md` to begin the workflow.
