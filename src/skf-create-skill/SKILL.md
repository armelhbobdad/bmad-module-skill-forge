---
name: skf-create-skill
description: Compile a skill from a brief. Supports --batch for multiple briefs. Use when the user requests to "create a skill" or "compile a skill."
---

# Create Skill

## Overview

Compiles a verified agent skill from a skill-brief.yaml and the source code or documentation it names, producing an agentskills.io-compliant SKILL.md with provenance map, evidence report, and progressive disclosure references. The workflow is mostly autonomous: it stops for the user in step 1 when no brief is named and several exist, in step 3 when several tags match the brief's version, for each authoritative AI documentation file the brief's scope leaves out (step 3 §2a), after source extraction (to confirm findings), at step 3c when a source brief extracted no export and none of its `doc_urls` could be fetched, and, for a component library, at step 3d's demo-exclusion and registry prompts. When the user has opted in to Tessl Review, step 6 also records Tessl's review of the skill as advice; it never stops the run. Steps adapt behavior based on forge tier (Quick/Forge/Forge+/Deep). Zero hallucination tolerance: every statement in the output carries a provenance citation, and content that cannot be cited is left out. A single run is not resumable: if it is interrupted mid-compile, re-run from the brief (only `--batch` checkpoints progress across briefs).

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs) and `references/sub/` the conditional sub-steps; a `nextStepFile` is relative to its own stage file (so a sub-step that returns to a main stage names it in the parent folder). `scripts/` and `assets/` hold deterministic helpers and templates.
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
- Once step 3 §2b has bound `{source_tree}` (the private tree a remote source is read from), every HALT after it first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` and goes on whatever it prints. Step 7 removes the tree on a run that finishes, and a later run removes one a stopped run left behind, seven days on
- Every HARD HALT in steps 1 to 7 emits the result envelope before it stops, in every mode. Each HALT names its exit code, `halt_reason` and phase where it fires, and its emit command. Stage `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "summary": {"halt_reason": "<halt_reason>", "evidence_report": null}}` as `{run_dir}/halt.json` (add `"path"` when the halt names a file or folder; once step 7 has promoted the package, add `"skill_package"` and `"outputs"` and set `summary.evidence_report` to `{forge_version}/evidence-report.md`), then run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`, adding `--result-dir "{forge_version}"` once step 7 has created `{forge_version}`, so the emitter also writes the halt's `create-skill-result-*.json` and its `-latest.json` copy there. Display the line it prints, then stop with the exit code; under `--batch` the halt ends only its brief: go to `references/batch-mode.md` §3, which records it and takes the next brief. If `{emitEnvelopeHelper}` resolved no path, display the halt message alone. The schema, `shared/scripts/schemas/skf-create-skill-result-envelope.v1.json`, lists every `halt_reason` with its exit code
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action
- Every decision the run takes without asking (each gate a headless run resolves by its default, step 1's tier override and its pick of the only brief) is recorded the moment it is taken: stage `{"step": "<step>", "gate": "<gate>", "decision": "<action>", "rationale": "<why>", "timestamp": "<ISO-8601>"}`, plus `"value"` or `"fallback"` where the gate names one, as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`. The run sink it appends to, `{run_dir}/headless-decisions.jsonl`, is the brief's one decision trail: it survives context compaction, step 5 §7 renders the evidence report's `## Auto-Decisions` table from it, and the result envelope and contract carry it

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Load Brief | references/load-brief.md | Conditional |
| 2b | CCC Discover | references/sub/ccc-discover.md | Yes |
| 3 | Extract | references/extract.md | No (confirm) |
| 3b | Fetch Temporal | references/sub/fetch-temporal.md | Yes |
| 3c | Fetch Docs | references/sub/fetch-docs.md | Conditional |
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

*Sub-steps under `references/sub/` are conditional branches (CCC discovery, temporal and doc enrichment), lettered by the place they take in the run and kept out of the main-line step count. Step 3d (Component Extraction) is a branch inside step 3 for a `component-library` brief: extract §2c loads it in place of §4 to §4c and resumes at its §5, before Gate 2.*

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | brief_path (a skill-brief.yaml path or a skill name) [optional: without it, step 1 offers the briefs in `{forge_data_folder}`, and a headless run halts unless there is one], --batch [optional: the briefs or folders of briefs after it, `{forge_data_folder}` when none is given, each validated before the first compiles] |
| **Gates** | step 1: Brief Selection (no brief named and several in `{forge_data_folder}`; headless: HARD HALT `brief-missing`, exit 2; one brief: picked and recorded as gate `brief-selection`) | step 3: Tag Choice Gate (several tags match the brief's version; headless: the first in priority order) | step 3 §2a: Authoritative-File Gate [P]/[S]/[U] (an authoritative AI documentation file outside the brief's scope; headless: deferred-headless, one auto-decision per path) | step 3: Review Gate [C]/[R] (with the zero-export warning when a source brief without `doc_urls` extracted no export; [R] with it or the head-cap warning) | step 3c: Zero-Export Gate [C]/[R] (a source brief with no export whose every `doc_urls` fetch failed) | step 3d: Demo-Exclusion Gate [Y], then Registry Gate [Y] (candidate found) or [S] (none found), component-library scope only, each skipped once the brief holds `scope.demo_patterns` or `scope.registry_path`, which step 3d writes when a user confirms or gives the patterns or the registry path |
| **Outputs** | SKILL.md, context-snippet.md, metadata.json, provenance-map.json, evidence-report.md, extraction-rules.yaml, references/; per brief, the result contract (`create-skill-result-{YYYYMMDD-HHmmss}.json` and its `-latest.json` copy in `{forge_version}`) and one `SKF_CREATE_SKILL_RESULT_JSON` line on stdout, on stderr at a HARD HALT |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true; each auto-decision reaches the envelope's and the result contract's `headless_decisions` |
| **Exit codes** | 0 for a finished brief; at a HARD HALT 2 (the brief is missing, malformed or invalid), 3 (no forge config, source, helper or documentation), 4 (a write failed), 5 (a refused or broken package), 6 (the user chose to refine the scope). A `--batch` run exits with the highest code among its briefs, 0 when every brief finished |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `output_folder`, `user_name`, `communication_language`, `document_output_language`, `sidecar_path`, `skills_output_folder`, `forge_data_folder`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-create-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran) for step 1 §0 to record in each brief's run folder.

   Apply the resolved values so the surface is not a silent no-op: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (entries prefixed `file:` are paths or globs whose contents load as facts), except a `!` entry and the entry it names (`!file:{project-root}/**/project-context.md` drops the bundled project-context default); and stash `{onCompleteCommand}` ← `workflow.on_complete` (empty string = no-op) for step 8 to invoke once each brief's result contract is written. After activation completes, execute each entry in `workflow.activation_steps_append` in order.

4. Resolve `{emitEnvelopeHelper}` ← the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`, the shared emitter every result envelope, result contract and recorded decision goes through.

5. If `--batch` was given, load, read the full file, and then execute `references/batch-mode.md`: it validates every brief first, runs steps 1 to 8 for each one and the health check once. Otherwise load, read the full file, and then execute `references/load-brief.md` to begin the workflow.
