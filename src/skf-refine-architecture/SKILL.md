---
name: skf-refine-architecture
description: Improve architecture doc using verified skill data and VS feasibility findings. Use when the user requests to "refine skill architecture" or "improve architecture doc."
---

# Refine Architecture

## Overview

Takes an original architecture document + generated skills + optional VS feasibility report, and produces a refined architecture with gaps filled, issues flagged, and improvements suggested, all backed by specific API evidence from the generated skills. This workflow enhances the original architecture: it never deletes original content, only adds annotations, subsections, and suggestions, each between `<!-- RA:BEGIN ... -->` and `<!-- RA:END -->` marker lines. Run again on a refined document, it sets its own earlier annotations aside and writes one current set in their place.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are an architecture refinement analyst operating in Ferris Architect mode. You bring expertise in API surface analysis, integration gap detection, and evidence-backed architecture improvement, while the user brings their architecture vision and generated skills. Every suggestion must cite specific APIs from the generated skills — evidence-backed suggestions, not speculation.

## Workflow Rules

These rules apply to every step in this workflow:

- Never speculate — every gap, issue, or improvement must cite specific APIs, types, or function signatures from the generated skills
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision; a gate that picks its default for the user also records that decision in the run sink the moment it decides
- Every HARD HALT names its exit code, `halt_reason` and phase, and in headless mode prints its envelope through the shared emitter, with the command each stage file shows (`references/exit-codes.md` describes the envelope)
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
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--architecture-doc <path>` (skip step 1 prompt for the required input); `--vs-report-path <path>` (skip step 1 prompt for the optional VS report; `--vs-report-path none` refines without a report and skips the search for one); `--scope-skills <names>` (comma-separated in-scope skill names; overrides scope derivation in gap analysis, so step 2 asks no scope confirmation) |
| **Gates** | step 1: Input Gate [use args] | step 2: Scope Confirm Gate [C] continue / [X] cancel (only when a derived scope leaves skills out or keeps an ambiguous one) | step 5: Review Gate [R] review each refinement / [C] approve and replace the refined document / [X] cancel |
| **Outputs** | `refined-architecture-{arch_project_name}.md` at `{outputFolderPath}` (`{arch_project_name}` = the architecture doc's frontmatter `project_name`, else config `project_name`, resolved in init.md), promoted from a draft only when the step 5 review approves it; an earlier file of that name is first renamed to `refined-architecture-{arch_project_name}-{timestamp}.md`. Plus `refine-architecture-result-{YYYYMMDD-HHmmss}.json` (UTC, named by the emitter) and `refine-architecture-result-latest.json`, and `.ra-dismissed-{arch_project_name}.json` beside them once a review that drops a finding is approved (a later run on the refined document leaves it out) |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Per-flag args (`--architecture-doc`, `--vs-report-path`, `--scope-skills`) consumed at the gates that would otherwise prompt: `--scope-skills` skips the step 2 scope confirmation, and without `--vs-report-path` step 1 uses the [VS] report it finds for the project, while `--vs-report-path none` uses none. |
| **Exit codes** | See `references/exit-codes.md` |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 prints one `SKF_REFINE_ARCHITECTURE_RESULT_JSON: {...}` line on **stdout** when it writes the result contract, and every HARD HALT one on **stderr**, built by the shared emitter: `references/exit-codes.md` gives its fields, the `halt_reason` values and the halt command each stage file shows.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `output_folder`, `sidecar_path`

2. **Compute run-scoped variables:**
   - `timestamp` ← the output of `date -u +%Y%m%d-%H%M%S`, run once now and fixed for the run: it names the run folder and, when step 5 promotes the draft, the timestamped name an earlier refined document is renamed to. The result files take their names from the emitter's clock.
   - `run_dir` ← `{project-root}/_bmad-output/.skf-run/skf-refine-architecture-{timestamp}`, the run folder §5 creates: it holds the analysis copy of the architecture document, the insertion plan, the draft build's record, the halt and result payloads, and the run sink of auto-decisions and warnings

3. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

4. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append):

   - `{skill-root}/customize.toml` — bundled defaults
   - `_bmad/custom/<skill-name>.toml` under `{project-root}` — team overrides (committed)
   - `_bmad/custom/<skill-name>.user.toml` under `{project-root}` — personal overrides (gitignored)

   If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly — the bundled defaults are an empty string for each path scalar.

   Apply the path-scalar fallback now. For each scalar, if the merged value is empty or absent, use the bundled default:

   - `{refinementRulesPath}` ← `workflow.refinement_rules_path` if non-empty, else `references/refinement-rules.md` (house style only: the file's first section names what a copy can change)
   - `{outputFolderPath}` ← `workflow.output_folder_path` if non-empty, else `{output_folder}`
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty (no-op — report.md skips the hook invocation entirely)

   Also apply the array surfaces (not silent no-ops): run `workflow.activation_steps_prepend` now, treat `workflow.persistent_facts` as standing context for the run (`file:`-prefixed entries load their file/glob contents as facts), then run `workflow.activation_steps_append` once §5's pre-flight has passed, before §6 loads the first stage.

5. **Pre-flight: the emitter, config, write probe and run folder.** Resolve the emitter first, so every halt below can print its envelope. Then assert both output paths are configured before probing writability: order matters, since an empty path makes `mkdir -p ""` fail, which would misreport a *missing config* (exit 3) as a *write failure* (exit 4) and collapse the distinction the Result Contract draws.

   **The emitter.** Resolve `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` (the first that exists). If neither exists, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `on-activation:emitter` and display only: "Refine Architecture cannot run without `skf-emit-result-envelope.py`, which is not installed. Re-install SKF."

   Every other HALT in this section comes before the run folder exists, so in headless mode it passes its payload to the emitter on stdin:

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-refine-architecture --target stderr <<'SKF_RA_HALT'
   {"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}
   SKF_RA_HALT
   ```

   **Config-completeness (exit 3).** If `{outputFolderPath}` is empty: HALT (exit code 3, `halt_reason: "output-folder-unconfigured"`) at phase `on-activation:config`: "`output_folder` is not configured in config.yaml. Add an `output_folder` path and re-run [RA]." If `{forge_data_folder}` is empty: HALT (exit code 3, `halt_reason: "forge-folder-unconfigured"`) at phase `on-activation:config`: "`forge_data_folder` is not configured in config.yaml. Add a `forge_data_folder` path and re-run [RA]."

   **Write probe (exit 4).** With both paths now non-empty, verify each is writable — a read-only mount, full disk, or permissions-denied path otherwise only surfaces at init.md §3c's RA state file write, by which point the user has already gone through input prompts:

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

   If the command fails, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation:run-folder`: "Cannot create the run folder `{run_dir}`: {the first stderr line}."

6. Load, read the full file, and then execute `references/init.md` to begin the workflow.
