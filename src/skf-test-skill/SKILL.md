---
name: skf-test-skill
description: Cognitive completeness verification — quality gate before export. Use when the user requests to "test a skill" or "verify skill completeness."
---

# Test Skill

## Overview

Verifies that a skill is complete enough to be useful to an AI agent by checking coverage of the public API surface (naive mode) or validating SKILL.md + references coherence (contextual mode). Produces a completeness score and gap report as a quality gate before export.

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
| 4c | Hard Gate | references/step-hard-gate.md | Yes |
| 5 | Score | references/score.md | Yes |
| 6 | Report | references/report.md | No (confirm) |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required]; optional flags: `--allow-workspace-drift`, `--no-discovery` (skip the report step's Discovery Testing block), `--no-health-check` (skip §7 health-check dispatch), `--tier=<Quick\|Forge\|Forge+\|Deep>` (bypass forge-tier.yaml sidecar requirement), `--threshold=<N>` (override pass threshold; CLI wins over per-pipeline defaults and `workflow.default_threshold` scalar) |
| **Gates** | step 6: Confirm Gate [C] |
| **Outputs** | per-run `test-report-{skill_name}-{run_id}.md` with completeness score and result (PASS/FAIL); per-run `skf-test-skill-result-{run_id}.json` and `skf-test-skill-result-latest.json` written atomically under `{forge_version}/`; `evidence-report-fallback.md` written under `{forge_version}/` when threshold fallback occurs (score between 80% and target threshold) — downstream consumers (export-skill, update-skill `--from-test-report`) glob `test-report-{skill_name}-*.md` and pick newest by parsed ISO timestamp |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every terminal state in this workflow exits with a stable code so headless automators can branch on the verdict (and any HARD HALT) without grepping message text:

| Code | Meaning              | Raised by                                                                                  |
| ---- | -------------------- | ------------------------------------------------------------------------------------------ |
| 0    | success / PASS       | step 6 §6b — `testResult: 'pass'` (after the result contract is written in §4c)            |
| 1    | error (HARD HALT)    | infrastructure / precondition HALT in step 1 or step 6 before a verdict exists — see the "Result Contract" `halt_reason` set (the hard gate uses code 2) |
| 2    | fail / FAIL          | step 4c §3 — hard gate blocked (`halt_reason: "hard-gate-blocked"`); step 6 §6b — `testResult: 'fail'` (after the result contract is written in §4c) |
| 3    | inconclusive         | step 6 §6b — `testResult: 'inconclusive'` (distinct from fail so orchestrators can route to manual-review queues) |
| 4    | pass-with-drift      | step 6 §6b — `testResult: 'pass-with-drift'` (distinct from clean pass — `--allow-workspace-drift` was in effect; re-test against the pinned commit and refuse export — exit 0 would wrongly signal a clean pass) |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 emits a single-line JSON envelope on **stdout** before chaining to step 7, and every HALT the Exit Codes table above marks with a non-zero code emits the same envelope shape on **stderr** with `status: "error"` and the `halt_reason` naming the failure, so a headless orchestrator branches on the reason without grepping prose:

```
SKF_TEST_RESULT_JSON: {"status":"success|error","skill_name":"…","verdict":"PASS|FAIL|INCONCLUSIVE|pass-with-drift","score":N,"threshold":N,"report_path":"…|null","next_workflow":"export-skill|update-skill|null","exit_code":0,"halt_reason":null,"threshold_fallback":true,"original_threshold":90}
```

`status` is `"success"` on the terminal happy path (PASS / FAIL / INCONCLUSIVE / pass-with-drift — the workflow completed), `"error"` on an emitted HARD HALT. `verdict` is the canonical result string (`null` on an infrastructure error halt). `next_workflow` is `"export-skill"` only when `verdict == "PASS"`; `"update-skill"` for `FAIL` or `pass-with-drift`; `null` for `INCONCLUSIVE` and error halts. `halt_reason` is `null` on the terminal path or one of the emitted strings: `"target-inaccessible"`, `"forge-tier-missing"`, `"workspace-drift"`, `"another-run-active"`, `"frontmatter-invalid"` (init HALTs), `"atomic-writer-missing"`, `"step-completeness-violation"`, `"report-anchor-missing"`, `"health-check-missing"` (report HALTs), or `"hard-gate-blocked"` (step 4c). `exit_code` is the code the Exit Codes table above assigns to the reached terminal state or HALT. Step 1 §3 frontmatter-validation now emits the `"frontmatter-invalid"` stderr envelope (see init.md §3c) and is branchable. Only the coverage/coherence analysis aborts print a diagnostic and exit non-zero **without** this envelope — they are the sole remaining outcomes outside the branchable set. When threshold fallback occurred, the envelope includes `"threshold_fallback":true` and `"original_threshold":N`; these fields are omitted when no fallback occurred.

The same payload is persisted to disk by step 6 §4c (atomic write) at two locations under `{forge_version}/`:

| Path                                          | Purpose                                                                    |
| --------------------------------------------- | -------------------------------------------------------------------------- |
| `skf-test-skill-result-{run_id}.json`         | Per-run record. `{run_id}` carries UTC timestamp + PID + random suffix.    |
| `skf-test-skill-result-latest.json`           | Latest copy — stable path for pipeline consumers (copy, not symlink).      |

The on-disk payload is the richer form: it adds `outputs[]` (report-path entries), `summary` (`score`, `threshold`, `result`, `testMode`, `activeCategories[]`, `inconclusiveReasons[]` when present, `threshold_fallback`, `original_threshold`, `evidence_report_path` when threshold fallback occurred), `runId`, and `healthCheckDispatched`. The stdout envelope is the compact subset documented above.

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
   - `{defaultThreshold}` ← `workflow.default_threshold` if non-empty/non-null, else `80`. CLI `--threshold=<N>` wins over per-pipeline defaults (from init.md §1b) which win over this scalar at the usage site in `references/score.md`.
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string (the post-finalization hook in `references/report.md` is then a no-op).

   Stash all five as workflow-context variables that stage files reference directly — no conditional at the usage site.

   **Apply the array surfaces** (not silent no-ops): run `workflow.activation_steps_prepend` in order now; treat each `workflow.persistent_facts` entry as standing context for the run (`file:`-prefixed entries load their file/glob contents as facts — the bundled default globs any `project-context.md`); then run `workflow.activation_steps_append` after activation.

4. Load, read the full file, and then execute `references/init.md` to begin the workflow.
