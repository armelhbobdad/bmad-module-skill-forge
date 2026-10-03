---
name: skf-export-skill
description: Exports an SKF skill, validating its package, writing its context snippet and updating the managed section in CLAUDE.md, AGENTS.md or .cursorrules. Use when the user requests to "export a skill" or "package a skill."
---

# Export Skill

## Overview

Checks a completed skill against the agentskills.io export gate, writes its context snippet and updates the managed section in CLAUDE.md, AGENTS.md or .cursorrules. It is the sole publishing gate: create-skill and update-skill produce drafts, and only export writes the context files and records the skill in `.export-manifest.json`.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; for example `knowledge/version-paths.md` and `shared/health-check.md`.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `references/` holds the workflow stages, chained by frontmatter `nextStepFile`; the files a stage loads when it needs them (`load-skill.md` loads `multi-skill-mode.md` and `preflight-snippet-root-probe.md`, `update-context.md` loads `orphan-context-detection.md`, `orphan-row-detection.md` and `manifest-rebuild.md`); and the headless contract (`invocation-contract.md`, `result-envelope.md`). `assets/` holds the snippet and managed-section templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Cross-skill data coupling:** export-skill, drop-skill and rename-skill write the managed section only through `shared/scripts/skf-rebuild-managed-sections.py`, in the format `assets/managed-section-format.md` documents, and change `.export-manifest.json` only through `shared/scripts/skf-manifest-ops.py` (v2 schema in `references/manifest-rebuild.md`). A change to either contract changes all three skills.

## Role

You are Ferris in Delivery mode, a packaging specialist: you check a developer's completed skill against the ecosystem rules and inject it into the context files it targets.

## Workflow Rules

- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and record each auto-decision in the run sink (`references/result-envelope.md`)
- Every HALT names its exit code, `halt_reason` and phase; in headless mode it first emits its envelope as `references/result-envelope.md` states
- **Snippet timing:** step 3 only stages each `context-snippet.md` outside the project; step 4 §9c copies it into the skill package after its [C] gate, as step 4's last write. A cancel, a dry run or a halt before §9c leaves every snippet, and a carried gotchas line's one `[CARRIED]` cycle, as it was.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Load Skill | references/load-skill.md | No (confirm) |
| 2 | Package | references/package.md | Yes |
| 3 | Generate Snippet | references/generate-snippet.md | Yes |
| 4 | Update Context | references/update-context.md | No (confirm) |
| 5 | Token Report | references/token-report.md | Yes |
| 6 | Summary | references/summary.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

Headless callers and pipelines: the inputs, flags, gates, outputs and exit codes are in `references/invocation-contract.md`, and the `SKF_EXPORT_RESULT_JSON` envelope in `references/result-envelope.md`. Interactive runs do not need them.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - `snippet_skill_root_override` (optional): the `root:` prefix of every snippet and managed-section row in place of the IDE skill folder, for an authoring repo that keeps its skills in one folder such as `skills/`; step 1's snippet-root option (d) sets it for one run without changing `config.yaml`.

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-export-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. Keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran): a headless run records it once step 4 creates its run folder, and an interactive run only prints it.

   Bind each scalar to its bundled default when the merged value is empty or absent:

   - `{snippetFormatPath}` ← `workflow.snippet_format_path`, else `assets/snippet-format.md`
   - `{onCompleteCommand}` ← `workflow.on_complete`, else empty (step 6 then runs no hook)

   Then apply the array surfaces: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries are paths or globs whose contents load as facts: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off); then, after activation completes and before the first stage runs, execute each entry in `workflow.activation_steps_append` in order.

4. **Resolve the helpers and create the run folder.** Resolve each helper to the first of its two paths that exists, the installed module first, all in parallel:

   - `{emitEnvelopeHelper}` ← the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` (every envelope, result file and headless record).
   - `{manifestOpsHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py`, else `{project-root}/src/shared/scripts/skf-manifest-ops.py` (steps 1, 3 and 4).
   - `{skillInventoryHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py`, else `{project-root}/src/shared/scripts/skf-skill-inventory.py` (step 1).
   - `{rebuildManagedSectionsHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py`, else `{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py` (steps 1 and 4).
   - `{validateOutputHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-validate-output.py`, else `{project-root}/src/shared/scripts/skf-validate-output.py` (steps 1 and 2).
   - `{countTokensHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-count-tokens.py`, else `{project-root}/src/shared/scripts/skf-count-tokens.py` (steps 3 and 5).

   No step has a fallback for them, so check them all here, before any prompt or write. If one has no existing path, HALT (exit code 4, `halt_reason: "context-rebuild-failed"`) at phase `on-activation §4`: "`{the missing helper's file name}` is missing. Nothing was changed. Re-install SKF."

   When `{headless_mode}` is true, create the run folder, whose sink holds the headless auto-decisions:

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-export-skill-XXXXXXXX"
   ```

   Bind `{run_dir}` ← the path it prints. Step 6 deletes it once the run's envelope is built; a HARD HALT leaves it in place. If it cannot be created, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation §4`. When `{customization_resolver_unavailable}` is set, record it there: write `customization_resolver_unavailable: <reason>` to `{run_dir}/resolver-warning.txt` with a file write (a resolver error can hold quotes or `$( )`, so never echo it or type it into an argument), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"` from `{project-root}`.

5. **Pre-flight write check.** Verify `{skills_output_folder}` is writable, so a read-only mount, a full disk or a denied path stops the run before the user confirms a batch. Without `--dry-run`, probe it with a write:

   ```bash
   mkdir -p "{skills_output_folder}" && \
     printf 'probe' > "{skills_output_folder}/.skf-write-probe" && \
     rm "{skills_output_folder}/.skf-write-probe"
   ```

   With `--dry-run`, check without writing: `test -w "{skills_output_folder}"` when the folder exists; when it does not, skip the check, since step 1 then finds no skill to export.

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation §5`.

6. Load, read the full file, and then execute `references/load-skill.md` to begin the workflow.
