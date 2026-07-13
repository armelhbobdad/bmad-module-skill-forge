---
name: skf-update-skill
description: Smart regeneration preserving [MANUAL] sections after source changes. Use when the user requests to "update a skill" or "regenerate a skill."
---

# Update Skill

## Overview

Surgically updates existing skills when source code changes, preserving all [MANUAL] developer content while re-extracting only affected exports with full provenance tracking. Only changed exports are re-extracted — unchanged content is never touched. Every regenerated instruction must trace to code with file:line citations. Stack skills (`skill_type: "stack"` in metadata.json) are not supported by surgical update — use `skf-create-stack-skill` to re-compose from updated constituents. If a stack skill is provided, this workflow exits with a redirect message.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root — stage files reference `knowledge/version-paths.md` and `knowledge/tool-resolution.md`, and the terminal step chains to `shared/health-check.md`.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Cross-skill data coupling:** stages in this workflow load four shared assets from `skf-create-skill` to keep extraction semantics aligned between create and update — `re-extract.md` pulls `extraction-patterns.md`, `extraction-patterns-tracing.md`, and `tier-degradation-rules.md` from `skf-create-skill/references/`; `remote-source-resolution.md` references `source-resolution-protocols.md`; `write.md` reads `skill-sections.md` from `skf-create-skill/assets/`. Update-skill assumes these files are present at install time and that their semantics are stable across the two skills' versions.

## Role

You are a precision code analyst operating in Ferris Surgeon mode. This is a surgical operation, not an exploratory session. You bring AST-backed structural analysis and provenance-driven change detection expertise, while the source code provides the ground truth.

## Workflow Rules

These rules apply to every step in this workflow:

- Never hallucinate — every statement must have AST provenance
- [MANUAL] sections survive regeneration with zero content loss
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Initialize & Load | references/init.md | No (confirm) |
| 2 | Detect Changes | references/detect-changes.md | Yes |
| 3 | Re-Extract | references/re-extract.md | Yes |
| 4 | Merge | references/merge.md | Yes |
| 5 | Validate | references/validate.md | Yes |
| 6 | Write | references/write.md | Yes |
| 7 | Report | references/report.md | Yes |
| 8 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required] |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--from-test-report` (gap-driven mode); `--allow-workspace-drift` (gap-driven only — bypass §0.a pinning guard); `--allow-degraded` (headless only — pre-authorize the lossy degraded full re-extraction when the provenance map is missing, instead of halting `blocked`; init.md §4); `--detect-only` (run detect-changes only, exit before re-extract; envelope `status="detect-only"`); `--dry-run` (run detect-changes + re-extract, exit before merge/write; envelope `status="dry-run"` describes what would change). If both `--detect-only` and `--dry-run` are passed, `--detect-only` wins. |
| **Gates** | step 1: Confirm Gate [C] | step 4: Confirm Gate [C if clean merge, HALT if conflicts] |
| **Outputs** | Updated SKILL.md, metadata.json, provenance-map.json, evidence-report.md (none when `--detect-only` or `--dry-run` is set — those modes are read-only inspection paths) |
| **Concurrency** | Two simultaneous real-update runs against the same skill would corrupt provenance. init.md §1b acquires a PID-file lock at `{forge_data_folder}/{skill_name}/.skf-update.lock` before any artifact read; live-PID collisions halt with `status: "halted-for-concurrent-run"`. Stale locks (dead PID) are cleared silently with a warning. The lock is released by the terminal health-check step (step 8) on the normal path and by the two init-stage headless halts (§4/§6); mid-workflow halts leave it for the next run's stale-lock self-heal (see init.md §1b Release contract). Read-only modes (`--detect-only`, `--dry-run`) skip the lock entirely — they're safe alongside a concurrent real update. |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Each auto-resolved gate appends a `{gate, default_action, taken_action, reason, evidence?}` entry to `headless_decisions[]`, surfaced in step 7's `SKF_UPDATE_RESULT_JSON` envelope so non-interactive runs can be audited post-hoc. A HALT reached in headless mode emits its own `SKF_UPDATE_RESULT_JSON` at the halt site (the site's `status` code plus an `error: {phase, path?, reason}` object) and exits — halts do not fall through to step 7. Pipeline branches on the envelope's top-level `status` field (`success`, `no-changes`, `detect-only`, `dry-run`, or one of the documented `halted-for-*`/`blocked` codes). The first four are successful exits — pipelines treating non-success as failure must include them in the success set. The status enum is defined once in `src/shared/scripts/schemas/skf-update-result-envelope.v1.json`. |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in preferences.yaml. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   This merges the three layers per `bmad-customize` rules (scalars override, arrays append): `{skill-root}/customize.toml` (bundled defaults), `_bmad/custom/<skill-name>.toml` under `{project-root}` (team overrides), and `_bmad/custom/<skill-name>.user.toml` under `{project-root}` (personal overrides). If the script is missing or fails, read `{skill-root}/customize.toml` directly.

   Apply the resolved values so no surface is a silent no-op: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (entries prefixed `file:` are paths or globs whose contents load as facts — the bundled default loads any `project-context.md` under `{project-root}`); resolve `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string, and stash it in workflow context (`references/report.md` §5b invokes it after the result contract is written; empty string = the hook is a no-op). After activation completes, execute each entry in `workflow.activation_steps_append` in order before `init.md` runs.

4. Load, read the full file, and then execute `references/init.md` to begin the workflow.
