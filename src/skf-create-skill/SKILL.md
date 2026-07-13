---
name: skf-create-skill
description: Compile a skill from a brief. Supports --batch for multiple briefs. Use when the user requests to "create a skill" or "compile a skill."
---

# Create Skill

## Overview

Compiles a verified agent skill from a skill-brief.yaml and source code, producing an agentskills.io-compliant SKILL.md with provenance map, evidence report, and progressive disclosure references. The workflow is mostly autonomous with three interaction points — after ecosystem check (if match found), after source extraction (to confirm findings), and after content quality review (when tessl produces suggestions). Steps adapt behavior based on forge tier (Quick/Forge/Forge+/Deep). Zero hallucination tolerance: every instruction in the output must trace to source code with a confidence tier citation. A single run is not resumable — if it is interrupted mid-compile, re-run from the brief (only `--batch` checkpoints progress across briefs).

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

- Never include content in SKILL.md that cannot be cited to source code
- Only load one step file at a time — never preload future steps
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
| 6 | Validate | references/validate.md | Conditional |
| 7 | Generate Artifacts | references/generate-artifacts.md | Yes |
| 8 | Report | references/report.md | Yes |
| 9 | Workflow Health Check | references/health-check.md | Yes |

*Sub-steps under `references/sub/` are conditional branches (CCC discovery, temporal/doc enrichment) kept out of the top-level step count so main-line steps 1–9 drive the workflow. Step 3d (Component Extraction) stays top-level as an alternative main step that replaces the standard extraction path when `scope.type: "component-library"`.*

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | brief_path (path to skill-brief.yaml) [required], --batch [optional] |
| **Gates** | step 2: Choice Gate [P] (if match) | step 3: Review Gate [C] | step 6: Content-Quality Gate [C] (if novel tessl suggestions) |
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
