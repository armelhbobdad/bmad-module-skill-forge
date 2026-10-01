---
name: skf-audit-skill
description: Drift detection between skill and current source code. Use when the user requests to "audit a skill" or "audit skill" for drift.
---

# Audit Skill

## Overview

Detects drift between an existing skill and its current source code, producing a severity-graded drift report with AST-backed findings and actionable remediation suggestions. Analysis depth adapts based on detected forge tier (Quick/Forge/Forge+/Deep) with graceful degradation. Stack skills: a compose-mode stack checks its constituents' freshness by metadata hash; a code-mode stack's provenance map records no single source root, so its audit stops at step 1 §5.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root — stage files reference `knowledge/version-paths.md` and `knowledge/tool-resolution.md`, and the terminal step chains to `shared/health-check.md`.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Cross-skill data coupling:** `re-index.md` loads `extraction-patterns.md` and `tier-degradation-rules.md` from `skf-create-skill/references/` (their `extractionPatternsData` and `tierDegradationRulesData` paths name the sibling skill, so they resolve from the SKF module root, not this skill root) to keep the ast-grep recipes, the fallback and the labels aligned with create-skill and update-skill. Audit-skill assumes these files are present at install time and that their semantics are stable across the two skills' versions.

## Role

You are a skill auditor in Ferris Audit mode: a deterministic drift-detection workflow where the source code is the ground truth and every finding traces back to it.

## Workflow Rules

These rules apply to every step in this workflow:

- Never fabricate findings — all data must trace to source code with file:line citations
- Only load one step file at a time — never preload future steps
- Update `stepsCompleted` in output file frontmatter before loading next step
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision; step 1's choice gates (manifest-vs-link, degraded-mode, upstream-drift) also record theirs in the run sink as they decide
- Every HARD HALT names its exit code, `halt_reason` and phase; in headless mode it prints its envelope through the shared emitter, as each stage's **Halt envelope** paragraph shows
- Once step 1 §5b has bound `{source_tree}` (the private tree its [C] choice read the upstream ref into), every step reads the source there, never at the recorded `source_path`, and every HALT after it first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` and goes on whatever it prints. Step 6 removes the tree on a finished run; a later SKF run removes one a stopped run left, once it is seven days old
- Run state (the gates' decisions, the warnings, the emitter's payloads) lives in `{run_dir}`: step 6 deletes it, a HALT keeps it

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Baseline | references/init.md | No (confirm) |
| 1c | Constituent Freshness (compose-mode stacks only) | references/constituent-freshness.md | Yes |
| 2 | Re-Index Source | references/re-index.md | Yes |
| 3 | Structural Diff | references/structural-diff.md | Yes |
| 4 | Semantic Diff | references/semantic-diff.md | Yes (skip at non-Deep) |
| 5 | Severity Classification | references/severity-classify.md | Yes |
| 5a | Doc Drift | references/step-doc-drift.md | Yes |
| 6 | Report | references/report.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

Stage 1c is conditional: it replaces stages 2 to 4 for a compose-mode stack, which has no source tree to re-index. Step 1 §4 decides it from the provenance map, and the chain is init.md → constituent-freshness.md → severity-classify.md.

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `skill_name` [required], `skill_path` [optional override: full path to skill directory; bypasses manifest/symlink resolution], `tier_override` [optional: Quick / Forge / Forge+ / Deep; overrides detected tier], `degraded` [optional bool: pre-confirm degraded-mode opt-in when no provenance map exists], `upstream_drift_choice` [optional: C / S / X; pre-supplied answer for the upstream-drift gate at init.md §5b; C, auditing the upstream ref from a private tree, when unset] |
| **Gates** | step 1: Manifest-vs-Symlink Gate [N/M/X] · Upstream-Drift Gate [C/S/X] · Degraded-Mode Gate [D/X] · Baseline Confirm Gate [C] |
| **Outputs** | `drift-report-{timestamp}.md` at `{forge_version}/` (the audited version's folder) with the run context, `drift_score` and `nextWorkflow` in its frontmatter; the JSON it was built from in `{forge_version}/.skf-audit/{timestamp}/`; the result contract `audit-skill-result-{YYYYMMDD-HHmmss}.json` and its `-latest.json` copy in `{forge_version}/`, written by the shared emitter. The shared clone at the recorded source path never changes: an audit of a newer upstream ref reads it from a private tree |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true; the pre-supplied `upstream_drift_choice` and `degraded` answer the gates that would otherwise prompt, and `tier_override` sets the tier (step 1 §2); each choice gate's decision lands in the envelope's `headless_decisions` |
| **Exit codes** | `references/headless-contract.md`: each halt class's exit code and `halt_reason`, and the `SKF_AUDIT_RESULT_JSON` envelope |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - Generate and store `timestamp` as `YYYYMMDD-HHmmss` format. This value is fixed for the entire workflow run.
   - `run_dir` ← `{project-root}/_bmad-output/.skf-run/skf-audit-skill-{timestamp}`, the run folder step 4 below creates

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

   If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly (the bundled defaults are an empty string for each path scalar) and keep the reason as `{customization_resolver_unavailable}`, which step 6 hands to the emitter as a warning.

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each of the scalars, if the merged value is empty or absent, use the bundled default:

   - `{driftReportTemplatePath}` ← `workflow.drift_report_template_path` if non-empty, else `assets/drift-report-template.md`
   - `{severityRulesPath}` ← `workflow.severity_rules_path` if non-empty, else `references/severity-rules.md`
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty (no-op — report.md skips the hook invocation entirely)

   Stash all three as workflow-context variables. Stage files reference `{driftReportTemplatePath}` / `{severityRulesPath}` / `{onCompleteCommand}` directly.

   Also apply the array surfaces (not silent no-ops): run `workflow.activation_steps_prepend` now, treat `workflow.persistent_facts` as standing context for the run (`file:`-prefixed entries load their file/glob contents as facts — the bundled default globs any `project-context.md`), then run `workflow.activation_steps_append` after activation.

4. **Pre-flight: the emitter and the run folder.** Before the first prompt, resolve `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. If neither exists, HALT (exit code 3, `halt_reason: "helper-missing"`) and display only: "Audit Skill cannot run without `skf-emit-result-envelope.py`, which is not installed. Re-install SKF." Then create the run folder:

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"
   ```

   If the command fails, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation:run-folder`: "Cannot create the run folder `{run_dir}`: {the first stderr line}." With no folder to stage in, a headless run passes the payload to the emitter directly:

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --target stderr <<'SKF_AS_HALT'
   {"phase": "on-activation:run-folder", "reason": "<the halt message>", "halt_reason": "write-failed"}
   SKF_AS_HALT
   ```

5. Load, read the full file, and then execute `references/init.md` to begin the workflow.
