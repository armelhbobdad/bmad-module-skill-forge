---
name: skf-refine-architecture
description: Refines an architecture document against generated skills and a Verify Stack report. Use when the user requests to "refine the architecture against generated skills" or "refine an architecture doc with a VS report."
---

# Refine Architecture

## Overview

Produces a refined architecture document: gaps filled, issues flagged and improvements suggested from the generated skills and an optional VS feasibility report. It never deletes original content, only adds annotations, subsections and suggestions between `<!-- RA:BEGIN ... -->` and `<!-- RA:END -->` marker lines; run again on a refined document, it sets its earlier annotations aside and writes one current set.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are an architecture refinement analyst in Ferris Architect mode; the user brings the architecture vision and the generated skills.

## Workflow Rules

These rules apply to every step in this workflow:

- Never speculate — every gap, issue, or improvement must cite specific APIs, types, or function signatures from the generated skills
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action; a gate that picks its default records that decision in the run sink the moment it decides
- Every HARD HALT names its exit code, `halt_reason` and phase, and in headless mode prints the envelope the Result Contract below describes
- Run state lives in `{run_dir}`, not in context; step 6 deletes it when the run finishes, a HALT keeps it

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load Inputs | references/init.md | No (input gate) |
| 2 | Gap Analysis | references/gap-analysis.md | Conditional (confirm a derived scope) |
| 3 | Issue Detection | references/issue-detection.md | Yes |
| 4 | Improvements | references/improvements.md | Yes |
| 5 | Compile Refined Architecture | references/compile.md | No (review) |
| 6 | Report | references/report.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | architecture_doc_path [required], vs_report_path [optional] |
| **Flags** | `--headless` / `-H`; `--architecture-doc <path>` and `--vs-report-path <path>` answer the step 1 prompts (`--vs-report-path none` refines without a report and skips the search for one); `--scope-skills <names>` (comma-separated skill names that replace the derived scope, so step 2 asks no scope confirmation) |
| **Gates** | step 1: Input Gate [use args] | step 2: Scope Confirm Gate [C] continue / [X] cancel (only when a derived scope drops skills or keeps an ambiguous one) | step 5: Review Gate [R] review each refinement / [C] approve and replace the refined document / [X] cancel |
| **Outputs** | `refined-architecture-{arch_project_name}.md` at `{outputFolderPath}` (the document's frontmatter `project_name`, else config's), promoted from a draft once the step 5 review approves it; an earlier one is first renamed to `refined-architecture-{arch_project_name}-{timestamp}.md`. Also `refine-architecture-result-{YYYYMMDD-HHmmss}.json`, its `-latest.json` copy and, once an approved review drops a finding, `.ra-dismissed-{arch_project_name}.json` |
| **Headless** | Every gate takes its default when `{headless_mode}` is true: `--scope-skills` skips the step 2 scope confirmation, and without `--vs-report-path` step 1 uses the [VS] report it finds. |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 prints one `SKF_REFINE_ARCHITECTURE_RESULT_JSON: {...}` line on **stdout**, and every HARD HALT one on **stderr**, built by the shared emitter: `references/exit-codes.md` gives its fields, the `halt_reason` values and the halt command.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `output_folder`, `sidecar_path`

2. **Compute run-scoped variables:**
   - `timestamp` ← the output of `date -u +%Y%m%d-%H%M%S`, run once now: it names the run folder and the copy an earlier refined document is renamed to.
   - `run_dir` ← `{project-root}/_bmad-output/.skf-run/skf-refine-architecture-{timestamp}`, the run folder §5 creates

3. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

4. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-refine-architecture.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}` for §5 to record.

   Bind each path scalar, taking the bundled default when the merged value is empty or absent:

   - `{refinementRulesPath}` ← `workflow.refinement_rules_path` if non-empty, else `references/refinement-rules.md` (house style only: the file's first section names what a copy can change)
   - `{outputFolderPath}` ← `workflow.output_folder_path` if non-empty, else `{output_folder}`
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty

   Then run `workflow.activation_steps_prepend` now, treat `workflow.persistent_facts` as standing context for the run (`file:`-prefixed entries load their file/glob contents as facts: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off), then run `workflow.activation_steps_append` once §5's pre-flight has passed, before §6 loads the first stage.

5. **Pre-flight: the emitter, config, write probe and run folder.** In that order, so every halt can print its envelope and an empty path halts as missing config (exit 3), not as a write failure.

   **The emitter.** Resolve `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` (the first that exists). If neither exists, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `on-activation:emitter` and display only: "Refine Architecture cannot run without `skf-emit-result-envelope.py`, which is not installed. Re-install SKF."

   The halts below come before the run folder, so in headless mode each passes its payload on stdin, with `"customization_resolver_unavailable": "<reason>"` added when step 4 kept one:

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-refine-architecture --target stderr <<'SKF_RA_HALT'
   {"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}
   SKF_RA_HALT
   ```

   **Config-completeness (exit 3).** If `{outputFolderPath}` is empty: HALT (exit code 3, `halt_reason: "output-folder-unconfigured"`) at phase `on-activation:config`: "Set `output_folder` in config.yaml, then re-run [RA]." If `{forge_data_folder}` is empty: HALT (exit code 3, `halt_reason: "forge-folder-unconfigured"`) at phase `on-activation:config`: "Set `forge_data_folder` in config.yaml, then re-run [RA]."

   **Write probe (exit 4).** Check that both paths are writable before any prompt:

   ```bash
   for dir in "{outputFolderPath}" "{forge_data_folder}"; do
     mkdir -p "$dir" && \
       printf 'probe' > "$dir/.skf-write-probe" && \
       rm "$dir/.skf-write-probe"
   done
   ```

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation:write-probe`, with `"path"` set to the folder that failed.

   **Run folder (exit 4).** Create the run folder:

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"
   ```

   If the command fails, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation:run-folder`: "Cannot create the run folder `{run_dir}`: {the first stderr line}." Once it exists and `{customization_resolver_unavailable}` is set, record the reason in the run sink: write `customization_resolver_unavailable: {customization_resolver_unavailable}` to `{run_dir}/resolver-warning.txt` with a file write, never `echo`, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"`.

6. Load, read the full file, and then execute `references/init.md` to begin the workflow.
