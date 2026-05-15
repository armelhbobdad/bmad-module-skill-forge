---
name: skf-test-skill
description: Cognitive completeness verification — quality gate before export. Use when the user requests to "test a skill" or "verify skill completeness."
---

# Test Skill

## Overview

Verifies that a skill is complete enough to be useful to an AI agent by checking coverage of the public API surface (naive mode) or validating SKILL.md + references coherence (contextual mode). Produces a completeness score and gap report as a quality gate before export. Every finding must trace to actual code with file:line citations.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a skill auditor and completeness analyst operating in Ferris's Audit mode. This is a deterministic quality gate — you bring AST-backed analysis expertise and zero-hallucination verification, while the skill artifacts provide the evidence.

## Workflow Rules

These rules apply to every step in this workflow:

- Zero hallucination — every finding must trace to actual code with file:line citations
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- Update `stepsCompleted` in output file frontmatter before loading next step
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load Skill | references/init.md | Yes |
| 2 | Detect Mode | references/detect-mode.md | Yes |
| 3 | Coverage Check | references/coverage-check.md | Yes |
| 4 | Coherence Check | references/coherence-check.md | Yes |
| 4b | External Validators | references/external-validators.md | Yes |
| 5 | Score | references/score.md | Yes |
| 6 | Report | references/report.md | No (confirm) |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required]; optional flags: `--allow-workspace-drift`, `--no-discovery` (skip §4b Discovery Testing), `--no-health-check` (skip §7 health-check dispatch), `--tier=<Quick\|Forge\|Forge+\|Deep>` (bypass forge-tier.yaml sidecar requirement), `--threshold=<N>` (override pass threshold; CLI wins over `workflow.default_threshold` scalar) |
| **Gates** | step 6: Confirm Gate [C] |
| **Outputs** | test-report-{skill_name}.md with completeness score and result (PASS/FAIL); per-run `skf-test-skill-result-{run_id}.json` and `skf-test-skill-result-latest.json` written atomically under `{forge_version}/` |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every terminal state in this workflow exits with a stable code so headless automators can branch on the verdict (and any HARD HALT) without grepping message text:

| Code | Meaning              | Raised by                                                                                  |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success / PASS       | step 6 §6b — `testResult: 'pass'` (after the result contract is written in §4c)            |
| 2    | fail / FAIL          | step 6 §6b — `testResult: 'fail'` (after the result contract is written in §4c)            |
| 3    | inconclusive         | step 6 §6b — `testResult: 'inconclusive'` (distinct from fail so orchestrators can route to manual-review queues) |
| 4    | pass-with-drift      | step 6 §6b — `testResult: 'pass-with-drift'` (distinct from clean pass — `--allow-workspace-drift` was in effect; orchestrators MUST route to re-test-against-pinned-commit queues and refuse export; never exit 0 under drift override) |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 emits a single-line JSON envelope on **stdout** before chaining to step 7, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_TEST_RESULT_JSON: {"status":"success|error","skill_name":"…","verdict":"PASS|FAIL|INCONCLUSIVE|pass-with-drift","score":N,"threshold":N,"report_path":"…|null","next_workflow":"export-skill|update-skill|null","exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path (any of PASS / FAIL / INCONCLUSIVE / pass-with-drift — the workflow completed), `"error"` on any HARD HALT before §4c. `verdict` is the canonical result string. `next_workflow` is `"export-skill"` only when `verdict == "PASS"`; `"update-skill"` for `FAIL` or `pass-with-drift`; `null` for `INCONCLUSIVE` (manual review). `halt_reason` is `null` on the terminal path or one of the workflow-defined halt strings (`"forge-tier-missing"`, `"target-inaccessible"`, `"write-failed"`, `"step-completeness-violation"`, `"report-anchor-missing"`, `"health-check-missing"`, `"atomic-writer-missing"`). `exit_code` matches the table above.

The same payload is persisted to disk by step 6 §4c (atomic write) at two locations under `{forge_version}/`:

| Path                                          | Purpose                                                                    |
| --------------------------------------------- | -------------------------------------------------------------------------- |
| `skf-test-skill-result-{run_id}.json`         | Per-run record. `{run_id}` carries UTC timestamp + PID + random suffix.    |
| `skf-test-skill-result-latest.json`           | Latest copy — stable path for pipeline consumers (copy, not symlink).      |

The on-disk payload is the richer form: it adds `outputs[]` (report-path entries), `summary` (`score`, `threshold`, `result`, `testMode`, `activeCategories[]`, `inconclusiveReasons[]` when present), `runId`, and `healthCheckDispatched`. The stdout envelope is the compact subset documented above.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append):

   - `{skill-root}/customize.toml` — bundled defaults
   - `_bmad/custom/<skill-name>.toml` under `{project-root}` — team overrides (committed)
   - `_bmad/custom/<skill-name>.user.toml` under `{project-root}` — personal overrides (gitignored)

   If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly — the bundled defaults are an empty string for each path scalar.

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each of the three scalars, if the merged value is empty or absent, use the bundled default:

   - `{testReportTemplatePath}` ← `workflow.test_report_template_path` if non-empty, else `templates/test-report-template.md`
   - `{outputFormatsPath}` ← `workflow.output_formats_path` if non-empty, else `assets/output-section-formats.md`
   - `{scoringRulesPath}` ← `workflow.scoring_rules_path` if non-empty, else `references/scoring-rules.md`
   - `{defaultThreshold}` ← `workflow.default_threshold` if non-empty/non-null, else `80`. CLI `--threshold=<N>` (when present) wins over the scalar at the usage site in `references/score.md`.
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string. When empty, the post-finalization hook in `references/report.md` is a no-op.

   Stash all five as workflow-context variables. Stage files reference `{testReportTemplatePath}` / `{outputFormatsPath}` / `{scoringRulesPath}` / `{defaultThreshold}` / `{onCompleteCommand}` directly — no conditional at the usage site. Empty-string overrides cleanly fall through to the bundled default; non-empty values let orgs swap in house-style copies without forking the skill.

4. Load, read the full file, and then execute `references/init.md` to begin the workflow.
