---
name: skf-rename-skill
description: Rename a skill across all its versions — transactional copy-verify-delete with platform context rebuild. Use when the user requests to "rename a skill."
---

# Rename Skill

## Overview

Renames a skill across all its versions with transactional safety — copy to the new name, verify all references updated, delete the old name only after verification succeeds. Rebuilds platform context files to reference the new name. The agentskills.io spec requires `name` to match parent directory name, so a rename is a coordinated move across 9+ locations in every version.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root, inside a `references/` file too: only a stage's frontmatter `nextStepFile` names a file beside it.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; e.g. `shared/health-check.md`, which the terminal step chains to, and the envelope schema `shared/scripts/schemas/skf-rename-skill-result-envelope.v1.json`.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one. On Activation step 1 cites `skf-export-skill/assets/managed-section-format.md`, the format the context-file rebuild writes.

## Role

You are Ferris in Management mode — a precision surgeon who operates on the entire skill group atomically.

## Workflow Rules

These rules apply to every step in this workflow:

- Never delete the old skill directories until the new name has been fully materialized and verified
- Never proceed past a verification failure — roll back (delete new directories) and halt
- Never allow a rename to collide with an existing skill name
- Never rename a folder SKF did not generate: select.md §4a takes that verdict from the inventory helper
- Only load one step file at a time — never preload future steps
- Run every subagent in the foreground, passing `run_in_background: false` on every Agent call (Claude Code runs a subagent in the background when the flag is left out), with parallel ones as several such calls in one message, and wait for every long-running command to exit before the next instruction; in a headless run, never end a turn while either still runs, since under `claude -p` a run stops when its turn ends.
- Every helper is required: select.md §1, §5's validator call and execute.md §0 halt (exit 4) without one, and no stage does a helper's write, scan or check by hand
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Select & Validate | references/select.md | No (confirm) |
| 2 | Execute Rename | references/execute.md | Yes |
| 3 | Report | references/report.md | Yes |
| 4 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

Headless callers: the inputs, flags, gate map, outputs, concurrency rule and `SKF_RENAME_SKILL_RESULT_JSON` result envelope live in `references/invocation-contract.md`, and the exit codes in `references/exit-codes.md`. Interactive runs do not need them.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - `snippet_skill_root_override` (optional string): when set, the context-file rebuild in step 2 passes it to `assemble` as `--skill-root-override`, so every row's `root:` takes it instead of the target IDE's skill root. See `skf-export-skill/assets/managed-section-format.md` for full semantics.

2. **Bind the invocation once**, in every mode:
   - `{headless_mode}`: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.
   - `{acknowledge_official}`: true if `--acknowledge-official` was passed, else false.
   - `{dry_run}`: true if `--dry-run` was passed, else false.
   - `{old_name_arg}` and `{new_name_arg}`: the current name and the new name the invocation supplied, as arguments or in a request such as "rename cognee to cognee-ai", each null when absent. select.md §4 and §5 take a supplied name in either mode instead of asking for it.

3. **Resolve workflow customization.** Bind `{resolveCustomizationHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-resolve-customization.py`, else `{project-root}/src/shared/scripts/skf-resolve-customization.py` (the first that exists), and run:

   ```bash
   uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow --facts
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-rename-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `SKF helper skf-resolve-customization.py not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran) for select.md §1 to record once it has created `{run_dir}`.

   Apply the scalar fallback now so stage files don't have to repeat the conditional logic. For each of the two scalars, if the merged value is empty or absent, the bundled default applies:

   - `{forceSourceAuthorityInHeadless}` ← true when `workflow.force_source_authority_in_headless` is `"true"` or the TOML boolean `true`, else false (a headless run halts on an `"official"` skill unless it passes `--acknowledge-official`)
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string (no-op — step 3 skips the post-completion hook invocation)

   Stash both as workflow-context variables. Stage files reference them directly, with no conditional at the usage site.

   Then apply the resolved array surfaces so they are not silent no-ops: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (the bundled default loads every `project-context.md` under `{project-root}`; `--facts` has applied each `!` entry, which drops each earlier entry it names, and expanded each glob, so a `file:` entry names one file to load, never one under `{project-root}/_bmad-output/.skf-run/`); and after activation completes, execute each entry in `workflow.activation_steps_append` in order.

4. Load, read the full file, and then execute `references/select.md` to begin the workflow.
