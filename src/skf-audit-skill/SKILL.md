---
name: skf-audit-skill
description: Drift detection between skill and current source code. Use when the user requests to "audit a skill" or "audit skill" for drift.
---

# Audit Skill

## Overview

Detects drift between a skill and its current source code and writes a severity-graded drift report with AST-backed findings and remediation suggestions; analysis depth follows the forge tier (Quick/Forge/Forge+/Deep). Stack skills: a compose-mode stack checks its constituents' freshness by metadata hash; a code-mode stack is diffed library by library. A docs-only skill is audited by its documents' hashes; a skill with no provenance map has no baseline, so step 1 stops it.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root, inside a `references/` file too: only a stage's frontmatter `nextStepFile`, `classifyStepFile`, `composeStepFile`, `docsOnlyStepFile`, `reportStepFile`, `resumeStepFile` and `upstreamCheckoutFile` name a file beside it.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `scripts/` holds `render-drift-tables.py`, which steps 1c, 3, 4, 5, 5a and 6 run to print their drift report tables, and `build-result-context.py`, which step 6 runs to build the result payload and its route.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Cross-skill data coupling:** `re-index.md` loads `extraction-patterns.md` and `tier-degradation-rules.md` from `skf-create-skill/references/`.

## Role

You are a skill auditor in Ferris Audit mode: a deterministic drift-detection workflow where the source code is the ground truth and every finding traces back to it.

## Workflow Rules

- Never fabricate findings — all data must trace to source code with file:line citations
- Only load one step file at a time — never preload future steps
- Run every subagent in the foreground, passing `run_in_background: false` on every Agent call (Claude Code runs a subagent in the background when the flag is left out), with parallel ones as several such calls in one message, and wait for every long-running command to exit before the next instruction; in a headless run, never end a turn while either still runs, since under `claude -p` a run stops when its turn ends.
- Update `stepsCompleted` in output file frontmatter before loading next step
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision; step 1's gates (manifest-vs-link, only when the `active` link's version has no provenance map and the manifest's has one; upstream-drift; baseline confirm) also record theirs in the run sink as they decide
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
| **Gates** | step 1: Manifest-vs-Symlink Gate [N/M/X] (only when the `active` link's version has no provenance map and the manifest's has one) · Upstream-Drift Gate [C/S/X] (references/upstream-checkout.md, only when upstream moved) · Baseline Confirm Gate [C/X] (only on a doubt: the forge tier is below the compile tier, or the provenance map is more than 90 days old) |
| **Outputs** | The drift report, the JSON it was built from and the result contract, in `{forge_version}/` (the audited version's folder): `references/headless-contract.md` names each file |
| **Headless** | Every gate takes its default action, a pre-supplied `upstream_drift_choice` answers the upstream-drift gate, `tier_override` sets the tier (step 1 §2), and each gate's decision lands in the envelope's `headless_decisions`. A caller reads the run's own `SKF_AUDIT_RESULT_JSON` line. A run that printed no envelope line has no result to read, whatever the process exit code: it was cut off, or could not write its result, and `audit-skill-result-latest.json` may then describe an earlier run, so it is never read in its place. |
| **Exit codes** | `references/headless-contract.md`: each halt class's exit code and `halt_reason`, and the `SKF_AUDIT_RESULT_JSON` envelope |

## On Activation

1. **Load the config.** Bind `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` (the first that exists; step 4 binds the same path), and `{preflightHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-preflight.py`, else `{project-root}/src/shared/scripts/skf-preflight.py` (the first that exists). Run it once:

   ```bash
   uv run {preflightHelper} "{project-root}"
   ```

   It parses `{project-root}/_bmad/skf/config.yaml` and `{sidecar_path}/preferences.yaml` into one JSON object: bind `project_name`, `user_name`, `communication_language` and `document_output_language` from its `config`, and `output_folder`, `skills_output_folder`, `forge_data_folder` and `sidecar_path` from `config.<name>_resolved`, each folder's absolute path. With `sidecar.preferences_error` (a `preferences.yaml` that is there but does not load), display that error in one line and go on. Then bind:
   - `timestamp` ← now, as `YYYYMMDD-HHmmss`, fixed for the whole run
   - `run_dir` ← `{project-root}/_bmad-output/.skf-run/skf-audit-skill-{timestamp}`, the run folder step 4 below creates

   If the call exits non-zero or prints no JSON, or neither preflight path exists, HALT (exit code 3) at phase `on-activation:config` with "Audit Skill cannot load its config: {its `error` and `code`, else its first stderr line, else `skf-preflight.py` is missing, so re-install SKF}". Its `code` sets the `halt_reason`: `SIDECAR_UNDEFINED` and `SIDECAR_MISSING` (no forger sidecar to read the forge tier from) take `halt_reason: "forge-tier-missing"`; `CONFIG_MISSING`, `CONFIG_MALFORMED`, any other code, no JSON and no preflight path take `halt_reason: "helper-missing"`. Nothing is written. Under `--headless` or `-H` (step 2 has not run yet), the halt first prints its envelope; with no run folder yet, it passes its fields as options and the message, which quotes preflight's error and its absolute paths, in a quoted heredoc, through `python3` in place of `uv run` when `uv` is what is missing:

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --target stderr --phase on-activation:config --halt-reason '<halt_reason>' --reason - <<'SKF_REASON'
   <the halt message>
   SKF_REASON
   ```

   Display the line it prints, then stop. An interactive run displays the halt message alone, as does a headless one with no emitter path or whose emitter exits non-zero or prints no line.

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if step 1's preflight gave `derived.headless_mode` true (`headless_mode: true` in `{sidecar_path}/preferences.yaml`). Default: false.

3. **Resolve workflow customization.** Bind `{resolveCustomizationHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-resolve-customization.py`, else `{project-root}/src/shared/scripts/skf-resolve-customization.py` (the first that exists), and run:

   ```bash
   uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow --facts
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-audit-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `SKF helper skf-resolve-customization.py not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. Then keep the reason as `{customization_resolver_unavailable}`, which step 6 hands to the emitter as a warning.

   Bind the two scalars the stages read, each to its bundled default when the merged value is empty or absent:

   - `{driftReportTemplatePath}` ← `workflow.drift_report_template_path`, else `assets/drift-report-template.md`, bound as the file it names (`{project-root}` replaced by the project root, a bare path taken from `{skill-root}`); step 4 checks that it is a readable file
   - `{onCompleteCommand}` ← `workflow.on_complete`, else empty (step 6 then runs no hook)

   Run `workflow.activation_steps_prepend` now, treat `workflow.persistent_facts` as standing context for the run (the bundled default loads every `project-context.md` under `{project-root}`, none in `{project-root}/_bmad-output/.skf-run/`; if the resolver ran, `--facts` has applied each `!` entry, which drops each earlier entry it names, and expanded each glob, so a `file:` entry names one file), then run `workflow.activation_steps_append` once step 4 below has passed, before step 5 loads `references/init.md`.

4. **Pre-flight: `uv`, the helpers, the template and the run folder.** Before the first prompt, resolve `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. If neither exists, HALT (exit code 3, `halt_reason: "helper-missing"`) and display only: "Audit Skill cannot run without `skf-emit-result-envelope.py`, which is not installed. Re-install SKF."

   Run `uv --version`, and check that `skf-load-provenance.py`, `skf-forge-tier-rw.py`, `skf-structural-diff.py`, `skf-severity-classify.py` and `skf-detect-docs.py` each exist in `{project-root}/_bmad/skf/shared/scripts/` or `{project-root}/src/shared/scripts/`. If `uv --version` fails, or a helper is in neither folder, HALT (exit code 3, `halt_reason: "helper-missing"`) at phase `on-activation:helpers`, naming what is missing: "Audit Skill cannot run without `<uv or the script>`, which is not installed. Install uv (<https://docs.astral.sh/uv/>) or re-install SKF, then re-run."

   Then check the template: if `test -f "{driftReportTemplatePath}" && test -r "{driftReportTemplatePath}"` fails, HALT (exit code 3, `halt_reason: "template-missing"`) at phase `on-activation:template`, with `"path"` that path: "`drift_report_template_path` names `{driftReportTemplatePath}`, which is not a readable file. Point it at your copy in `{project-root}/_bmad/custom/skf-audit-skill.toml` or `.user.toml`, or re-install SKF when it is the bundled `assets/drift-report-template.md`." Then create the run folder:

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"
   ```

   If the command fails, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `on-activation:run-folder`: "Cannot create the run folder `{run_dir}`: {the first stderr line}." With no folder to stage in, a headless HALT of this step passes its payload to the emitter directly, with `"path"` added when the halt names one, through `python3` in place of `uv run` when `uv` is what is missing:

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --target stderr <<'SKF_AS_HALT'
   {"phase": "<the phase>", "reason": "<the halt message>", "halt_reason": "<the halt_reason>"}
   SKF_AS_HALT
   ```

5. Load, read the full file, and then execute `references/init.md` to begin the workflow.
