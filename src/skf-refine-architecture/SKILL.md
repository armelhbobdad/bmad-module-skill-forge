---
name: skf-refine-architecture
description: Improve architecture doc using verified skill data and VS feasibility findings. Use when the user requests to "refine skill architecture" or "improve architecture doc."
---

# Refine Architecture

## Overview

Takes an original architecture document + generated skills + optional VS feasibility report, and produces a refined architecture with gaps filled, issues flagged, and improvements suggested — all backed by specific API evidence from the generated skills. This workflow enhances the original architecture — it never deletes original content, only adds annotations, subsections, and suggestions.

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
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load Inputs | references/init.md | No (confirm) |
| 2 | Gap Analysis | references/gap-analysis.md | Yes |
| 3 | Issue Detection | references/issue-detection.md | Yes |
| 4 | Improvements | references/improvements.md | Yes |
| 5 | Compile Refined Architecture | references/compile.md | No (review) |
| 6 | Report | references/report.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | architecture_doc_path [required], vs_report_path [optional] |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--architecture-doc <path>` (skip step 1 prompt for the required input); `--vs-report-path <path>` (skip step 1 prompt for the optional VS report); `--scope-skills <names>` (comma-separated in-scope skill names; overrides scope derivation in gap analysis) |
| **Gates** | step 1: Input Gate [use args] | step 5: Review Gate [C] |
| **Outputs** | `refined-architecture-{project_name}.md` at `{outputFolderPath}`, plus `refine-architecture-result-{timestamp}.json` and `refine-architecture-result-latest.json` |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Per-flag args (`--architecture-doc`, `--vs-report-path`) consumed at the gates that would otherwise prompt. |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                    |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 7 (terminal)                                                                           |
| 2    | input-missing / input-invalid | step 1 §1 (headless missing `architecture-doc` arg, or invalid path) → `input-missing`; non-existent file → `input-invalid` |
| 3    | resolution-failure   | step 1 §3 (`output_folder` or `forge_data_folder` unconfigured) |
| 4    | write-failure        | On-Activation §3 pre-flight write probe; step 1 §3c (RA state file write failed); step 5 §6 (refined-architecture write failed); step 6 §3 (result-contract write failed) |
| 5    | state-conflict       | step 1 §3 (no skills found — refinement requires ≥1 skill) |
| 6    | user-cancelled       | step 1 §1 prompt cancelled; any prompt that accepted `cancel`/`exit`/`:q`; step 5 review gate `[X]` |
| 7    | inventory-unreliable | step 1 §2 (>20% skill-inventory warnings exceed budget) |
| 8    | recovery-failed      | step 5 §1 (durability state insufficient to reconstruct Step 02-04 findings); step 6 §1 (`## Refinement Summary` absent from the compiled document) |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 emits a single-line JSON envelope on **stdout** before chaining to step 7, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_REFINE_ARCHITECTURE_RESULT_JSON: {"status":"success|error","refined_path":"…|null","gap_count":0,"issue_count":0,"improvement_count":0,"exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path, `"error"` on any HALT. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"insufficient-skills"`, `"output-folder-unconfigured"`, `"forge-folder-unconfigured"`, `"inventory-unreliable"`, `"write-failed"`, `"recovery-failed"`, `"user-cancelled"`. `exit_code` matches the table above.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `output_folder`, `sidecar_path`

2. **Compute run-scoped variables:**
   - `timestamp` ← UTC `YYYYMMDD-HHmmss` captured at activation time. Fixed for the entire workflow run; report.md reuses this when writing the result contract.

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

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each scalar, if the merged value is empty or absent, use the bundled default:

   - `{refinementRulesPath}` ← `workflow.refinement_rules_path` if non-empty, else `references/refinement-rules.md`
   - `{outputFolderPath}` ← `workflow.output_folder_path` if non-empty, else `{output_folder}`

   Stash both as workflow-context variables. Stage files reference them directly — no conditional at the usage site.

5. **Pre-flight write probe.** Verify both `{outputFolderPath}` and `{forge_data_folder}` are writable. A read-only mount, full disk, or permissions-denied path otherwise only surfaces at init.md §3c's RA state file write — by then the user has already gone through input prompts:

   ```bash
   for dir in "{outputFolderPath}" "{forge_data_folder}"; do
     mkdir -p "$dir" && \
       printf 'probe' > "$dir/.skf-write-probe" && \
       rm "$dir/.skf-write-probe"
   done
   ```

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`). In headless mode, emit the error envelope per **Result Contract (Headless)** with `refined_path: null`.

6. Load, read the full file, and then execute `references/init.md` to begin the workflow.
