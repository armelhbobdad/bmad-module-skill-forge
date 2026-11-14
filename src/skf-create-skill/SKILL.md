---
name: skf-create-skill
description: Compile a skill from a brief. Supports --batch for multiple briefs. Use when the user requests to "create a skill" or "compile a skill."
---

# Create Skill

## Overview

Compiles a verified agent skill from a skill-brief.yaml and the source code or documentation it names: an agentskills.io-compliant SKILL.md with its provenance map, evidence report and `references/`. The run is mostly autonomous: the Gates row of `references/invocation-contract.md` lists every stop. Steps adapt to the forge tier (Quick, Forge, Forge+ or Deep). A single run is not resumable: an interrupted run starts again from the brief (only `--batch` checkpoints progress across briefs).

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root, inside a `references/` file too: only a stage's frontmatter `nextStepFile`, `healthCheckStepFile`, `componentExtractionStepFile` and `returnToStep` name a file relative to the stage file, and a file the text calls "beside this file" sits beside the file that says so.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs). `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are operating in Ferris Architect mode: a skill compilation engine performing structural extraction and assembly.

## Workflow Rules

These rules apply to every step in this workflow:

- Never include content in SKILL.md without a provenance citation: `[AST:]` or `[SRC:]` for code (T1 and T1-low), `[QMD:]` for T2 context or `[EXT:]` for T3 documentation, in the forms `assets/skill-sections.md` gives
- Never write into a skill folder SKF did not generate — generate-artifacts §1 runs the inventory's write check before creating any directory; without the helper it writes only into a skill folder that does not exist yet
- Only load one step file at a time — never preload future steps
- Run every subagent in the foreground, passing `run_in_background: false` on every Agent call (Claude Code runs a subagent in the background when the flag is left out), with parallel ones as several such calls in one message, and wait for every long-running command to exit before the next instruction; in a headless run, never end a turn while either still runs, since under `claude -p` a run stops when its turn ends.
- Once step 3 §2a has bound `{source_tree}` (the private tree a remote source is read from), every HALT after it first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` and goes on whatever it prints. Step 7 removes the tree on a run that finishes, and a later run removes one a stopped run left behind, seven days on
- Every HARD HALT in steps 1 to 7 emits the result envelope before it stops, in every mode. Each HALT names its exit code, `halt_reason`, phase, path and message where it fires, and its stage file's Rules give the emit command. Stage `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "summary": {"halt_reason": "<halt_reason>", "evidence_report": null}}` as `{run_dir}/halt.json` (add `"path"` when the halt names a file or folder; once step 7 has promoted the package, add `"skill_package"` and `"outputs"` and set `summary.evidence_report` to `{forge_version}/evidence-report.md`), then run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`, adding `--result-dir "{forge_version}"` once step 7 has created `{forge_version}`, so the emitter also writes the halt's `create-skill-result-*.json` and its `-latest.json` copy there. Display the line it prints, then stop with the exit code; under `--batch` the halt ends only its brief: go to `references/batch-mode.md` §3, which records it and takes the next brief. If `{emitEnvelopeHelper}` resolved no path, display the halt message alone. The schema, `shared/scripts/schemas/skf-create-skill-result-envelope.v1.json`, lists every `halt_reason` with its exit code
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action
- Every decision the run takes without asking (each gate a headless run resolves by its default, step 1's tier override and its pick of the only brief, and Gate 2 when a `--batch` run passes a clean extraction) is recorded the moment it is taken: stage `{"step": "<step>", "gate": "<gate>", "decision": "<action>", "rationale": "<why>"}`, plus `"value"` or `"fallback"` where the gate names one, as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`, which stamps the decision's `timestamp` from the clock. The run sink it appends to, `{run_dir}/headless-decisions.jsonl`, is the brief's one decision trail: it survives context compaction, step 5 §7 renders the evidence report's `## Auto-Decisions` table from it, and the result envelope and contract carry it

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Load Brief | references/load-brief.md | Conditional |
| 2b | CCC Discover | references/ccc-discover.md | Yes |
| 3 | Extract | references/extract.md | Conditional |
| 3b | Fetch Temporal | references/fetch-temporal.md | Yes |
| 3c | Fetch Docs | references/fetch-docs.md | Conditional |
| 3d | Component Extraction | references/component-extraction.md | Conditional |
| 4 | Enrich | references/enrich.md | Yes |
| 5 | Compile | references/compile.md | Yes |
| 5a | Doc Sources | references/step-doc-sources.md | Yes |
| 5b | Auto-Shard | references/step-auto-shard.md | Yes |
| 5c | Doc-Rot | references/step-doc-rot.md | Yes |
| 6 | Validate | references/validate.md | Yes |
| 7 | Generate Artifacts | references/generate-artifacts.md | Yes |
| 8 | Report | references/report.md | Yes |
| 9 | Workflow Health Check | references/health-check.md | Yes |

*Step 3d (Component Extraction) is a branch inside step 3 for a `component-library` brief: extract §2c loads it in place of §4 to §4c and resumes at its §5, before Gate 2.*

## Invocation Contract

Headless callers and pipelines: the inputs, gates, outputs, exit codes and the `SKF_CREATE_SKILL_RESULT_JSON` and batch reading rules live in `references/invocation-contract.md`. Interactive runs do not need it.

## On Activation

1. Resolve `{emitEnvelopeHelper}` ← the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`, the shared emitter every result envelope, result contract and recorded decision goes through.

2. **Check the runtime.** Every helper, the customization resolver and every envelope run through `uv run`, and the Extract, Validate and Generate Artifacts stages also call `python3` directly, so confirm that `python3` and `uv` are both on `$PATH` (`command -v python3` and `command -v uv`). If either is missing, **HARD HALT** (exit code 3, `helper-missing`, phase `on-activation:runtime`): "**Create Skill needs `{the missing tool}`, which is not on your PATH.** Install it (`uv` from <https://docs.astral.sh/uv/getting-started/installation/>, `python3` from <https://www.python.org/downloads/>), then re-run." Nothing is written, and the halt ends the run, under `--batch` too. The emitter needs only the standard library, so when only `uv` is missing, emit in every mode with `python3` in place of `uv run` and display the line it prints; with `python3` missing, or no `{emitEnvelopeHelper}` path, display the message alone:

   ```bash
   python3 "{emitEnvelopeHelper}" emit-halt --workflow skf-create-skill --target stderr <<'SKF_JSON'
   {"phase": "on-activation:runtime", "halt_reason": "helper-missing", "reason": "Create Skill needs uv, which is not on your PATH. Install it from https://docs.astral.sh/uv/getting-started/installation/, then re-run.", "summary": {"halt_reason": "helper-missing", "evidence_report": null}}
   SKF_JSON
   ```

3. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `output_folder`, `user_name`, `communication_language`, `document_output_language`, `sidecar_path`, `skills_output_folder`, `forge_data_folder`

4. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

5. **Resolve workflow customization.** Bind `{resolveCustomizationHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-resolve-customization.py`, else `{project-root}/src/shared/scripts/skf-resolve-customization.py` (the first that exists), and run:

   ```bash
   uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow --facts
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-create-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `SKF helper skf-resolve-customization.py not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran) for step 1 §0 to record in each brief's run folder.

   Apply the resolved values so the surface is not a silent no-op: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (the bundled default loads every `project-context.md` under `{project-root}`, none in `{project-root}/_bmad-output/.skf-run/`; if the resolver ran, `--facts` has applied each `!` entry, which drops each earlier entry it names, and expanded each glob, so a `file:` entry names one file); and stash `{onCompleteCommand}` ← `workflow.on_complete` (empty string = no-op) for step 8 to invoke once each brief's result contract is written. Then, before step 6 loads load-brief.md or batch-mode.md, execute each entry in `workflow.activation_steps_append` in order; a --batch run executes them once, not per brief.

6. If `--batch` was given, load, read the full file, and then execute `references/batch-mode.md`: it validates every brief first, runs steps 1 to 8 for each one and the health check once. Otherwise load, read the full file, and then execute `references/load-brief.md` to begin the workflow.
