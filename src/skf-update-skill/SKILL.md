---
name: skf-update-skill
description: Smart regeneration preserving [MANUAL] sections after source changes. Use when the user requests to "update a skill" or "regenerate a skill."
---

# Update Skill

## Overview

Surgically updates existing skills when source code changes, preserving all [MANUAL] developer content while re-extracting only affected exports with full provenance tracking; unchanged content is never touched, and each regenerated instruction cites code by file:line. Stack skills (`skill_type: "stack"` in metadata.json) are not updated here: this workflow redirects them to `skf-create-stack-skill`, which re-composes them from updated constituents.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; stage files reference `knowledge/version-paths.md` and `knowledge/tool-resolution.md`, and the terminal step chains to `shared/health-check.md`.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `references/` holds the workflow stages, chained by each file's frontmatter `nextStepFile` (init.md §8 loads `gap-driven.md` through `gapDrivenStepFile` instead when `update_mode` is `gap-driven`), the [MANUAL] rules file merge.md loads, and the invocation contract; `scripts/` holds this skill's own helper.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Cross-skill data coupling:** stages load shared assets from `skf-create-skill`, so create and update extract alike: `re-extract.md` pulls `extraction-patterns.md`, `extraction-patterns-tracing.md` and `tier-degradation-rules.md` from `skf-create-skill/references/`, `detect-changes.md` pulls `extraction-patterns.md`, and `gap-driven.md` pulls `extraction-patterns.md` and `tier-degradation-rules.md`; `init.md` §6c reads the version files the Version Reconciliation section of `skf-create-skill/references/source-resolution-protocols.md` lists, and `skf-source-tree.py` (init.md §6b) computes a remote skill's clone path with its workspace rule; `write.md` reads `skill-sections.md` from `skf-create-skill/assets/`, and `extraction-patterns.md` and, for §2's by-hand public API count, `entry-points-by-hand.md` from `skf-create-skill/references/`.

## Role

You are a precision code analyst operating in Ferris Surgeon mode. This is a surgical operation, not an exploratory session. You bring AST-backed structural analysis and provenance-driven change detection expertise, while the source code provides the ground truth.

## Workflow Rules

These rules apply to every step in this workflow:

- Never hallucinate — every statement must have AST provenance
- [MANUAL] sections survive regeneration with zero content loss
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision
- Every HALT, ABORT or other exit before step 7 runs the **Halt procedure** of the step file it fires in: one `{runStateHelper}` `halt` call that undoes this run's writes, removes the private source tree, releases the run lock and, headless, prints the halt's line. A halt never falls through to step 6.
- While `{source_tree}` is bound, a step that finds `{source_root}` missing HALTs with status `blocked` (`error.phase` `<step>:source-tree-missing`) instead of reading its files as deleted.
- **Run log.** Warnings and gate decisions live in the run folder, never only in context: a step records each warning the moment it raises it, and each gate its decision, with the `record` call that step names.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load | references/init.md | No (confirm) |
| 2 | Detect Changes | references/detect-changes.md | Conditional (§1b, §1c and §2.2 ask when triggered) |
| 2g | Gap-Driven Repair (only when `update_mode` is gap-driven: in place of steps 2 and 3) | references/gap-driven.md | Conditional (§1 rule R1 asks [D]/[R] when a gap's remediation names removal) |
| 3 | Re-Extract | references/re-extract.md | Yes |
| 4 | Merge | references/merge.md | Conditional ([C] after resolved [MANUAL] conflicts) |
| 5 | Write | references/write.md | Yes |
| 6 | Report | references/report.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

Headless callers: the inputs, flags, gate map, outputs and the `SKF_UPDATE_RESULT_JSON` line live in `references/invocation-contract.md`. Interactive runs do not need it.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false. Bind `{requested_skill}` ← the skill name or folder path the invocation passes (its argument that is neither a flag nor a flag's value), else empty: `references/init.md` §1 takes it as the skill without asking.

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
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-update-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. Record the warning in the run log at once: write `customization_resolver_unavailable: <reason>` to `{run_dir}/resolver-warning.txt` with a file write (a resolver error can hold quotes or `$( )`, so never echo it or type it into an argument), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"` from `{project-root}`.

   Apply the resolved values so no surface is a silent no-op: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (entries prefixed `file:` are paths or globs whose contents load as facts: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off); resolve `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string, and stash it in workflow context (`references/report.md` §5b runs it after a finished run's result files, never in `--detect-only`, `--dry-run` or a halt; empty = no-op). After activation completes, execute each entry in `workflow.activation_steps_append` in order before `init.md` runs.

5. Load, read the full file, and then execute `references/init.md` to begin the workflow.
