---
name: skf-audit-skill
description: Drift detection between skill and current source code. Use when the user requests to "audit a skill" or "audit skill" for drift.
---

# Audit Skill

## Overview

Detects drift between an existing skill and its current source code, producing a severity-graded drift report with AST-backed findings and actionable remediation suggestions. Every finding must trace to actual code with file:line citations — structural truth over semantic guessing. Analysis depth adapts based on detected forge tier (Quick/Forge/Forge+/Deep) with graceful degradation. Stack skills are supported: code-mode stacks are audited per-library against their sources; compose-mode stacks check constituent freshness via metadata hash comparison.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a skill auditor operating in Ferris Audit mode. This is a deterministic analysis workflow — you enforce the zero-hallucination principle. You bring AST analysis expertise and drift detection methodology, while the source code provides the ground truth.

## Workflow Rules

These rules apply to every step in this workflow:

- Never fabricate findings — all data must trace to source code with file:line citations
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- Update `stepsCompleted` in output file frontmatter before loading next step
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Baseline | references/init.md | No (confirm) |
| 2 | Re-Index Source | references/re-index.md | Yes |
| 3 | Structural Diff | references/structural-diff.md | Yes |
| 4 | Semantic Diff | references/semantic-diff.md | Yes (skip at non-Deep) |
| 5 | Severity Classification | references/severity-classify.md | Yes |
| 6 | Report | references/report.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `skill_name` [required], `skill_path` [optional override — full path to skill directory; bypasses manifest/symlink resolution], `tier_override` [optional: Quick / Forge / Forge+ / Deep — overrides detected tier], `degraded` [optional bool — pre-confirm degraded-mode opt-in when no provenance map exists], `upstream_drift_choice` [optional: C / S / X — pre-supplied answer for the upstream-drift gate at init.md §5b], `dirty_worktree_choice` [optional: T / A / F — pre-supplied answer for the dirty-worktree sub-gate at init.md §5b], `force` [optional bool — when paired with `dirty_worktree_choice=F` or used for any future destructive-action gate, signals consent to skip the confirmation] |
| **Gates** | step 1: Manifest-vs-Symlink Gate [N] · Upstream-Drift Gate [C/S/X] · Dirty-Worktree Sub-Gate [T/A/F] · Degraded-Mode Gate [D/X] · Baseline Confirm Gate [C] |
| **Outputs** | `drift-report-{timestamp}.md` at `{forge_version}/` with `drift_score` and `nextWorkflow` frontmatter; per-run result contract at `{forge_version}/audit-skill-result-{timestamp}.json` plus `-latest.json` copy; final `SKF_AUDIT_RESULT_JSON` line on stdout when `{headless_mode}` is true |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true; pre-supplied inputs (`upstream_drift_choice`, `dirty_worktree_choice`, `degraded`, `tier_override`) consumed at the gates that would otherwise prompt |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                                          |
| ---- | -------------------- | ------------------------------------------------------------------------------------------------------------------ |
| 0    | success              | step 7 (terminal health-check)                                                                                     |
| 2    | input-missing        | step 1 §1 — no `skill_name` supplied in headless mode (interactive prompt cannot resolve)                          |
| 3    | resolution-failure   | step 1 §1 (skill not found at resolved path: missing `SKILL.md`); step 1 §2 (`forge-tier.yaml` missing — setup-forge not run); step 1 §5 (source directory from provenance map no longer exists / inaccessible) |
| 4    | write-failure        | step 1 §6 / step 6 §3 (drift report write failed: read-only mount, disk full, permissions denied)                 |
| 6    | user-cancelled       | step 1 §1 manifest-vs-symlink gate `[X]` · step 1 §4 degraded-mode gate `[X]` · step 1 §5b upstream-drift gate `[X]` · step 1 §5b dirty-worktree sub-gate `[A]` (and `[A]` headless default) |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 emits a single-line JSON envelope on **stdout** before chaining to step 7, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_AUDIT_RESULT_JSON: {"status":"success|error","skill_name":"…","drift_score":"CLEAN|MINOR|SIGNIFICANT|CRITICAL|null","report_path":"…|null","next_workflow":"update-skill|null","audit_ref":"…|null","exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path, `"error"` on any HALT. `drift_score` is `null` when the workflow halted before severity classification ran. `next_workflow` is `"update-skill"` when CRITICAL or HIGH findings exist, otherwise `null`. `halt_reason` is one of: `null` (success), `"input-missing"`, `"skill-not-found"`, `"forge-tier-missing"`, `"source-dir-missing"`, `"write-failed"`, `"user-cancelled"`. `exit_code` matches the table above.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - Generate and store `timestamp` as `YYYYMMDD-HHmmss` format. This value is fixed for the entire workflow run.

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

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each of the two scalars, if the merged value is empty or absent, use the bundled default:

   - `{driftReportTemplatePath}` ← `workflow.drift_report_template_path` if non-empty, else `assets/drift-report-template.md`
   - `{severityRulesPath}` ← `workflow.severity_rules_path` if non-empty, else `references/severity-rules.md`

   Stash both as workflow-context variables. Stage files reference `{driftReportTemplatePath}` / `{severityRulesPath}` directly — no conditional at the usage site. Empty-string overrides cleanly fall through to the bundled default; non-empty values let orgs swap in house-style copies (custom drift-report layout, stricter severity thresholds) without forking the skill.

4. Load, read the full file, and then execute `references/init.md` to begin the workflow.
