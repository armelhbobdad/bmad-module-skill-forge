---
name: skf-verify-stack
description: Pre-code stack feasibility verification against architecture and PRD documents. Use when the user requests to "verify a tech stack" or "verify stack."
---

# Verify Stack

## Overview

Cross-references generated skills against architecture and PRD documents to produce a feasibility report with evidence-backed integration verdicts, coverage analysis, and requirements mapping. This is a read-only workflow — it never modifies skills or input documents, only reads and produces a feasibility report. Every verdict must cite specific APIs, types, or function signatures from the generated skills.

**Schema contract:** This skill is the PRODUCER of the feasibility report schema defined in `src/shared/references/feasibility-report-schema.md`. All report outputs emit `schemaVersion: "1.0"` in frontmatter, use only the defined verdict tokens (`Verified|Plausible|Risky|Blocked` per pair; `FEASIBLE|CONDITIONALLY_FEASIBLE|NOT_FEASIBLE` overall), follow the fixed section-heading order, and are written through `src/shared/scripts/skf-atomic-write.py write` to both the timestamped file and the stable `-latest.md` copy.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a stack feasibility analyst and integration verifier operating in Ferris Audit mode. You bring expertise in API surface analysis, cross-library compatibility assessment, and architecture validation, while the user brings their architecture vision and generated skills.

## Workflow Rules

These rules apply to every step in this workflow:

- Read-only — never modify skills, architecture docs, or PRD files
- Every verdict must cite evidence from the generated skills
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load Inputs | references/init.md | No (confirm) |
| 2 | Coverage Analysis | references/coverage.md | Yes |
| 3 | Integration Verification | references/integrations.md | Yes |
| 4 | Requirements Mapping | references/requirements.md | Yes |
| 5 | Synthesize Verdict | references/synthesize.md | Yes |
| 6 | Report | references/report.md | No (confirm) |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | architecture_doc_path [required], prd_path [optional], previous_report_path [optional] |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--architecture-doc <path>` (skip step 1 prompt for the required input); `--prd <path>` (skip step 1 prompt for the optional PRD); `--previous-report <path>` (skip step 1 prompt for delta comparison) |
| **Gates** | step 1: Input Gate [use args] | step 6: Confirm Gate [C] |
| **Outputs** | `feasibility-report-{projectSlug}-{timestamp}.md` and `feasibility-report-{projectSlug}-latest.md` (copy, not symlink) per `src/shared/references/feasibility-report-schema.md` — with integration verdicts, coverage analysis, recommendations, and evidence sources; plus `verify-stack-result-{timestamp}.json` and `verify-stack-result-latest.json` |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Per-flag args (`--architecture-doc`, `--prd`, `--previous-report`) consumed at the gates that would otherwise prompt. |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                    |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 7 (terminal)                                                                           |
| 2    | input-missing / input-invalid | step 1 §1 (headless missing `architecture-doc` arg, or invalid path) → `input-missing`; non-existent file → `input-invalid` |
| 3    | resolution-failure   | step 1 §2 (`{skills_output_folder}` does not exist or is empty); step 1 §3 (forge_data_folder unconfigured) |
| 4    | write-failure        | On-Activation §3 pre-flight write probe; step 1 §4 (atomic write of report skeleton failed); step 6 §4b (result-contract write failed) |
| 5    | state-conflict       | step 1 §3 (fewer than 2 valid skills found — stack requires ≥2); step 1 §1 (`previousReport` resolves to same inode as `{outputFile}`); step 6 §1 (report section order or schemaVersion mismatch — schema-violation) |
| 6    | user-cancelled       | step 1 §1 prompt cancelled; any prompt that accepted `cancel`/`exit`/`:q`; step 6 menu cancelled |
| 7    | inventory-unreliable | step 1 §2 (>20% subagent failures or enumerate-stack-skills warnings exceed budget) |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 emits a single-line JSON envelope on **stdout** before chaining to step 7, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_VERIFY_STACK_RESULT_JSON: {"status":"success|error","report_path":"…|null","report_latest_path":"…|null","overall_verdict":"…|null","coverage_percentage":0,"recommendation_count":0,"exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path, `"error"` on any HALT. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"skills-folder-missing"`, `"insufficient-skills"`, `"forge-folder-unconfigured"`, `"previous-report-collision"`, `"inventory-unreliable"`, `"schema-violation"`, `"write-failed"`, `"user-cancelled"`. `exit_code` matches the table above. `overall_verdict` uses the schema tokens (`FEASIBLE`/`CONDITIONALLY_FEASIBLE`/`NOT_FEASIBLE`).

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Compute run-scoped variables** (same place as config so every stage can reference them without re-derivation):
   - `project_slug` ← slugify `project_name` (lowercase, hyphens only, no unicode, no whitespace)
   - `timestamp` ← UTC `YYYYMMDD-HHmmss` captured at activation time
   - These two combine in init.md §4 into `{outputFile}` per the stage frontmatter template, but the values themselves are fixed for the entire workflow run — every later reference to `{outputFile}` resolves consistently. (Computing them here resolves an order-of-operations bug where the §1 §3 inode-collision check referenced `{outputFile}` before `{project_slug}` and `{timestamp}` were defined.)

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

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each of the four scalars, if the merged value is empty or absent, use the bundled default:

   - `{reportTemplatePath}` ← `workflow.report_template_path` if non-empty, else `assets/feasibility-report-template.md`
   - `{integrationRulesPath}` ← `workflow.integration_rules_path` if non-empty, else `references/integration-verification-rules.md`
   - `{coveragePatternsPath}` ← `workflow.coverage_patterns_path` if non-empty, else `references/coverage-patterns.md`
   - `{outputFolderPath}` ← `workflow.output_folder_path` if non-empty, else `{forge_data_folder}`

   Stash all four as workflow-context variables. Stage files reference them directly — no conditional at the usage site. Empty-string overrides cleanly fall through to the bundled default.

5. **Pre-flight write probe.** Verify `{outputFolderPath}` is writable. A read-only mount, full disk, or permissions-denied path otherwise only surfaces at init.md §4 atomic write — by then the user has already gone through the input prompts:

   ```bash
   mkdir -p "{outputFolderPath}" && \
     printf 'probe' > "{outputFolderPath}/.skf-write-probe" && \
     rm "{outputFolderPath}/.skf-write-probe"
   ```

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`). In headless mode, emit the error envelope per **Result Contract (Headless)** with `report_path: null`, `report_latest_path: null`, `overall_verdict: null`.

6. Load, read the full file, and then execute `references/init.md` to begin the workflow.
