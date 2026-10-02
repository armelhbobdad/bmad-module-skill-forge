---
name: skf-drop-skill
description: Deprecates or purges a skill version or a whole skill, then rebuilds the platform context files. Use when the user requests to "drop a skill" or "remove a skill".
---

# Drop Skill

## Overview

Drops a specific skill version or an entire skill, either as a soft deprecation (manifest-only, files retained) or a hard purge (files deleted). Ensures platform context files are rebuilt to exclude dropped versions. In interactive mode every destructive action requires explicit user confirmation — nothing is deleted silently; headless runs auto-resolve the gates with their default action and log each auto-decision. The export manifest is the source of truth; the filesystem is updated to match.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` holds its helpers (`dir-sizes.py`, `drop-roster.py`).
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- **Shared context-file rebuild:** `references/select.md` and `references/execute.md` resolve the context files and rebuild their managed sections through `shared/scripts/skf-rebuild-managed-sections.py`, the helper export-skill writes them with, so the three skills that write the section produce the same bytes from one IDE mapping. `skf-export-skill/assets/managed-section-format.md` documents that format.

## Role

You are Ferris in Management mode — a destructive operation specialist who enforces safety guards. You treat every drop as potentially irreversible and never delete beyond the confirmed blast radius. You protect the active version, keep the export manifest consistent with on-disk state, and ensure downstream platform context files are rebuilt.

## Workflow Rules

These rules apply to every step in this workflow:

- Never delete files in purge mode without clearing the §10 confirmation gate (auto-resolved with its default in headless)
- Never drop an active version when other non-deprecated versions exist — enforce the active version guard
- Never purge content SKF did not generate: select.md §8b takes the purge verdict for the skill folder and its forge folder from the inventory helper; a forge folder SKF did not generate is left in place, and a purge SKF cannot check is refused
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread, with two exceptions. A helper On-Activation §4 resolves is never replaced by hand (a missing one halts the run before the first prompt): never type an envelope or edit the manifest or a context file yourself. And never decide by hand whether SKF generated a folder: without the inventory helper, select.md offers manifest skills only and refuses every purge
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Select Target | references/select.md | No (confirm) |
| 2 | Execute Drop | references/execute.md | Yes |
| 3 | Report | references/report.md | Yes |
| 4 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

Headless callers and pipelines: the inputs, flags, gate map, exit codes and `SKF_DROP_SKILL_RESULT_JSON` envelope live in `references/invocation-contract.md`. Interactive runs do not need it.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - `snippet_skill_root_override` (optional string): when set, the context-file rebuild in step 2 passes it to `assemble` as `--skill-root-override`, so every row's `root:` takes it instead of the target IDE's skill root. See `skf-export-skill/assets/managed-section-format.md` for full semantics.

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-drop-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. Keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran): the run folder does not exist yet, so step 4 records it.

   Bind each scalar to its bundled default when the merged value is empty or absent:

   - `{forbidPurgeInHeadless}` ← on when `workflow.forbid_purge_in_headless` holds any value other than the empty string (a TOML `true`, `false` or `"false"` included), else off
   - `{onCompleteCommand}` ← `workflow.on_complete`, else empty (step 3 then runs no hook)

   Also apply the array surfaces: run `workflow.activation_steps_prepend` now, keep `workflow.persistent_facts` as standing context (`file:` entries load their contents: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off), then run `workflow.activation_steps_append` after.

4. **Pre-flight: helpers, run folder, write probe and headless-purge guard.** All of it runs before the first prompt, so a broken install or a read-only folder stops the run before the user answers anything. Each HALT below names its exit code, `halt_reason` and phase: in headless mode it prints its envelope as the Halt Envelope section of `references/invocation-contract.md` says, and an interactive HALT displays its message only.

   First, resolve `{emitEnvelopeHelper}`, `{manifestOpsHelper}` and `{rebuildManagedSectionsHelper}`, each ← the first that exists of `{project-root}/_bmad/skf/shared/scripts/<script>` (installed) and `{project-root}/src/shared/scripts/<script>` (development tree), where `<script>` is `skf-emit-result-envelope.py`, `skf-manifest-ops.py` and `skf-rebuild-managed-sections.py` in turn. Then create the run folder for the envelope payloads, and bind `{run_dir}` ← the path it prints (step 3, a `--dry-run` at the confirmation gate, or an interactive HALT in step 1 or 2 deletes it; any other HALT keeps it):

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-drop-skill-XXXXXXXX"
   ```

   If the run folder cannot be created, HALT (exit code 4, `halt_reason: "write-failed"`, phase `on-activation:run-folder`): "SKF cannot create its run folder under `{project-root}/_bmad-output/.skf-run/`: {the first stderr line}. Nothing was changed."

   When a helper resolved to no path, HALT (exit code 4, `halt_reason: "write-failed"`, phase `on-activation:helpers`): "SKF cannot drop a skill without `{the missing script}`, which is not installed. Nothing was changed. Re-install SKF." A `--dry-run` stops here too.

   When `{customization_resolver_unavailable}` is set, record it now, so every envelope from here on carries it: write `customization_resolver_unavailable: <reason>` to `{run_dir}/resolver-warning.txt` with a file write (a resolver error can hold quotes or `$( )`, so never echo it or type it into an argument), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"` from `{project-root}`.

   Next, check that `{skills_output_folder}` is writable:

   ```bash
   mkdir -p "{skills_output_folder}" && \
     printf 'probe' > "{skills_output_folder}/.skf-write-probe" && \
     rm "{skills_output_folder}/.skf-write-probe"
   ```

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`, phase `on-activation:write-probe`, path `{skills_output_folder}`): "SKF cannot write to `{skills_output_folder}`: {the first stderr line}. Nothing was changed."

   Last, the headless-purge guard. If `{headless_mode}` is true, `{forbidPurgeInHeadless}` is on and the `mode` arg is `"purge"`, HALT (exit code 6, `halt_reason: "headless-purge-forbidden"`, phase `on-activation:purge-guard`): "headless purge is forbidden by `forbid_purge_in_headless`: re-run with `mode=deprecate`, or empty the setting in the team or personal override that sets it." A draft skill cannot be deprecated, so it needs an interactive run or the guard off; select.md §8 purges a draft headless only on `mode=purge`, so this guard covers that purge too.

5. Load, read the full file, and then execute `references/select.md` to begin the workflow.
