---
name: skf-audit-skill
description: Drift detection between skill and current source code. Use when the user requests to "audit a skill" or "audit skill" for drift.
---

# Audit Skill

## Overview

Detects drift between a skill and its current source code and writes a severity-graded drift report with AST-backed findings and remediation suggestions; analysis depth follows the forge tier (Quick/Forge/Forge+/Deep). Stack skills: a compose-mode stack checks its constituents' freshness by metadata hash; a code-mode stack is diffed library by library. A docs-only skill is audited by its documents' hashes; a skill with no provenance map has no baseline, so step 1 stops it.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `scripts/` holds `render-drift-tables.py`, which steps 3, 5 and 6 run to print their drift tables.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Cross-skill data coupling:** `re-index.md` loads `extraction-patterns.md` and `tier-degradation-rules.md` from `skf-create-skill/references/`.

## Role

You are a skill auditor in Ferris Audit mode: a deterministic drift-detection workflow where the source code is the ground truth and every finding traces back to it.

## Workflow Rules

- Never fabricate findings — all data must trace to source code with file:line citations
- Only load one step file at a time — never preload future steps
- Update `stepsCompleted` in output file frontmatter before loading next step
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision; step 1's gates (manifest-vs-link, upstream-drift, baseline confirm) also record theirs in the run sink as they decide
- Every HARD HALT names its exit code, `halt_reason` and phase; in headless mode it prints its envelope through the shared emitter, as each stage's **Halt envelope** paragraph shows
- Once the [C] of `references/upstream-checkout.md` has bound `{source_tree}` (the private tree it read the upstream ref into), every step reads the source there, never at the recorded `source_path`, and every HALT after it first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` and goes on whatever it prints
- Run state (the gates' decisions, the warnings, the emitter's payloads) lives in `{run_dir}`: step 6 deletes it, a HALT keeps it

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Baseline | references/init.md | No (confirm on a doubt: tier below the compile tier, or provenance map over 90 days old) |
| 1b | Upstream Checkout (only when upstream moved) | references/upstream-checkout.md | No (Upstream-Drift Gate) |
| 1c | Constituent Freshness (compose-mode stacks only) | references/constituent-freshness.md | Yes |
| 2 | Re-Index Source | references/re-index.md | Yes |
| 3 | Structural Diff | references/structural-diff.md | Yes |
| 4 | Semantic Diff | references/semantic-diff.md | Yes (skip at non-Deep) |
| 5 | Severity Classification | references/severity-classify.md | Yes |
| 5a | Doc Drift | references/doc-drift.md | Yes |
| 6 | Report | references/report.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

Stage 1b returns to init.md at §5b's **Record for report**, then §6. Step 1 §4 picks stage 1c from the provenance map: it replaces stages 2 to 4 for a compose-mode stack, which has no source tree to re-index (init.md → constituent-freshness.md → severity-classify.md). A docs-only skill skips stages 2 to 4 too (step 1 §3): init.md → doc-drift.md → severity-classify.md → report.md.

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `skill_name` [required], `skill_path` [optional: the skill folder, bypassing manifest/symlink resolution], `tier_override` [optional: Quick / Forge / Forge+ / Deep, in place of the detected tier], `upstream_drift_choice` [optional: C / S / X; answers the upstream-drift gate in references/upstream-checkout.md; C, auditing the upstream ref from a private tree, when unset] |
| **Gates** | step 1: Manifest-vs-Symlink Gate [N/M/X] · Upstream-Drift Gate [C/S/X] (references/upstream-checkout.md, only when upstream moved) · Baseline Confirm Gate [C/X] (only on a doubt: the forge tier is below the compile tier, or the provenance map is more than 90 days old) |
| **Outputs** | The drift report, the JSON it was built from and the result contract, in `{forge_version}/` (the audited version's folder): `references/headless-contract.md` names each file |
| **Headless** | Every gate takes its default action, a pre-supplied `upstream_drift_choice` answers the upstream-drift gate, `tier_override` sets the tier (step 1 §2), and each gate's decision lands in the envelope's `headless_decisions` |
| **Exit codes** | `references/headless-contract.md`: each halt class's exit code and `halt_reason`, and the `SKF_AUDIT_RESULT_JSON` envelope |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - `timestamp` ← now, as `YYYYMMDD-HHmmss`, fixed for the whole run
   - `run_dir` ← `{project-root}/_bmad-output/.skf-run/skf-audit-skill-{timestamp}`, the run folder step 4 below creates

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-audit-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. Then keep the reason as `{customization_resolver_unavailable}`, which step 6 hands to the emitter as a warning.

   Bind the two scalars the stages read, each to its bundled default when the merged value is empty or absent:

   - `{driftReportTemplatePath}` ← `workflow.drift_report_template_path`, else `assets/drift-report-template.md`
   - `{onCompleteCommand}` ← `workflow.on_complete`, else empty (step 6 then runs no hook)

   Run `workflow.activation_steps_prepend` now, treat `workflow.persistent_facts` as standing context for the run (a `file:` entry loads its file or glob contents as facts: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off), then run `workflow.activation_steps_append` once step 4 below has passed.

4. **Pre-flight: `uv`, the helpers and the run folder.** Before the first prompt, resolve `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. If neither exists, HALT (exit code 3, `halt_reason: "helper-missing"`) and display only: "Audit Skill cannot run without `skf-emit-result-envelope.py`, which is not installed. Re-install SKF."

   Run `uv --version`, and check that `skf-load-provenance.py`, `skf-structural-diff.py`, `skf-severity-classify.py` and `skf-detect-docs.py` each exist in `{project-root}/_bmad/skf/shared/scripts/` or `{project-root}/src/shared/scripts/`. If `uv --version` fails, or a helper is in neither folder, HALT (exit code 3, `halt_reason: "helper-missing"`) at phase `on-activation:helpers`, naming what is missing: "Audit Skill cannot run without `<uv or the script>`, which is not installed. Install uv (<https://docs.astral.sh/uv/>) or re-install SKF, then re-run." Then create the run folder:

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"
   ```

   If the command fails, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation:run-folder`: "Cannot create the run folder `{run_dir}`: {the first stderr line}." With no folder to stage in, a headless HALT of this step passes its payload to the emitter directly, through `python3` in place of `uv run` when `uv` is what is missing:

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --target stderr <<'SKF_AS_HALT'
   {"phase": "<the phase>", "reason": "<the halt message>", "halt_reason": "<the halt_reason>"}
   SKF_AS_HALT
   ```

5. Load, read the full file, and then execute `references/init.md` to begin the workflow.
