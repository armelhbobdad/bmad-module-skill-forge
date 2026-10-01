---
name: skf-create-skill
description: Compile a skill from a brief. Supports --batch for multiple briefs. Use when the user requests to "create a skill" or "compile a skill."
---

# Create Skill

## Overview

Compiles a verified agent skill from a skill-brief.yaml and the source code or documentation it names, producing an agentskills.io-compliant SKILL.md with provenance map, evidence report, and progressive disclosure references. The workflow is mostly autonomous: it stops for the user after the ecosystem check (if a match is found), in step 3 when several tags match the brief's version, after source extraction (to confirm findings) and, for a component library, at step 3d's demo-exclusion and registry prompts. When the user has opted in to Tessl Review, step 6 also records Tessl's review of the skill as advice; it never stops the run. Steps adapt behavior based on forge tier (Quick/Forge/Forge+/Deep). Zero hallucination tolerance: every statement in the output carries a provenance citation, and content that cannot be cited is left out. A single run is not resumable: if it is interrupted mid-compile, re-run from the brief (only `--batch` checkpoints progress across briefs).

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are operating in Ferris Architect mode — a skill compilation engine performing structural extraction and assembly. Apply zero hallucination tolerance: uncitable content is excluded, not guessed.

## Workflow Rules

These rules apply to every step in this workflow:

- Never include content in SKILL.md without a provenance citation: `[AST:]` or `[SRC:]` for code (T1 and T1-low), `[QMD:]` for T2 context or `[EXT:]` for T3 documentation, in the forms `assets/skill-sections.md` gives
- Never write into a skill folder SKF did not generate — generate-artifacts §1 runs the inventory's write check before creating any directory; without the helper it writes only into a skill folder that does not exist yet
- Only load one step file at a time — never preload future steps
- Once step 3 §2b has bound `{source_tree}` (the private tree a remote source is read from), every HALT after it first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` and goes on whatever it prints. Step 7 removes the tree on a run that finishes, and a later run removes one a stopped run left behind, seven days on
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action, logging each auto-decision to the in-context `headless_decisions[]` buffer AND appending it as a JSON line to the on-disk auto-decision sink (established at step 1 §3) the moment it lands, so the audit trail survives context compaction before step 5 first writes the evidence report

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Load Brief | references/load-brief.md | Yes |
| 2 | Ecosystem Check | references/ecosystem-check.md | Conditional |
| 2b | CCC Discover | references/sub/ccc-discover.md | Yes |
| 3 | Extract | references/extract.md | No (confirm) |
| 3b | Fetch Temporal | references/sub/fetch-temporal.md | Yes |
| 3c | Fetch Docs | references/sub/fetch-docs.md | Yes |
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

*Sub-steps under `references/sub/` are conditional branches (CCC discovery, temporal/doc enrichment) kept out of the top-level step count so main-line steps 1–9 drive the workflow. Step 3d (Component Extraction) stays top-level as an alternative main step that replaces the standard extraction path when `scope.type: "component-library"`.*

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | brief_path (path to skill-brief.yaml) [required], --batch [optional] |
| **Gates** | step 2: Choice Gate [P] (if match) | step 3: Tag Choice Gate (several tags match the brief's version; headless: the first in priority order) | step 3: Review Gate [C] | step 3d: Demo-Exclusion Gate [Y], then Registry Gate [Y] (candidate found) or [S] (none found), component-library scope only, each skipped once the brief holds `scope.demo_patterns` or `scope.registry_path`, which step 3d writes when a user confirms or gives the patterns or the registry path |
| **Outputs** | SKILL.md, context-snippet.md, metadata.json, provenance-map.json, evidence-report.md, references/ |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `output_folder`, `user_name`, `communication_language`, `document_output_language`, `sidecar_path`, `skills_output_folder`, `forge_data_folder`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append): `{skill-root}/customize.toml` (bundled defaults), `_bmad/custom/skf-create-skill.toml` under `{project-root}` (team overrides, committed), and `_bmad/custom/skf-create-skill.user.toml` under `{project-root}` (personal overrides, gitignored). If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly.

   Apply the resolved values so the surface is not a silent no-op: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (entries prefixed `file:` are paths or globs whose contents load as facts); and stash `{onCompleteCommand}` ← `workflow.on_complete` (empty string = no-op) for the final stage to invoke after the result JSON and metadata.json are finalized. After activation completes, execute each entry in `workflow.activation_steps_append` in order.

4. Load, read the full file, and then execute `references/load-brief.md` to begin the workflow.
