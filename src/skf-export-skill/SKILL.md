---
name: skf-export-skill
description: Package for distribution and inject context into CLAUDE.md/AGENTS.md/.cursorrules. Use when the user requests to "export" or "package a skill."
---

# Export Skill

## Overview

Packages a completed skill as an agentskills.io-compliant package, generates context snippets, and updates the managed section in CLAUDE.md/.cursorrules/AGENTS.md for platform-aware context injection. This workflow is the sole publishing gate for skills — create-skill and update-skill produce draft artifacts, only export-skill writes to platform context files and prepares packages for distribution.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a delivery and packaging specialist collaborating with a skill developer. You bring expertise in skill packaging, ecosystem compliance, and context injection patterns, while the user brings their completed skill and distribution requirements.

## Workflow Rules

These rules apply to every step in this workflow:

- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Load Skill | references/load-skill.md | No (confirm) |
| 2 | Package | references/package.md | Yes |
| 3 | Generate Snippet | references/generate-snippet.md | Yes |
| 4 | Update Context | references/update-context.md | No (confirm) |
| 5 | Token Report | references/token-report.md | Yes |
| 6 | Summary | references/summary.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `skill_name` [one or more, required unless `--all`] |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--all` (export every non-deprecated skill in `.export-manifest.json`); `--dry-run` (resolve and stage everything but exit before §4 writes to context files; envelope `status="dry-run"`) |
| **Gates** | step 1: single Confirm Gate [C] for the whole batch | step 4: single Confirm Gate [C] for the whole batch |
| **Outputs** | Updated `.export-manifest.json` (every skill in the batch), updated context files (CLAUDE.md/AGENTS.md/.cursorrules), per-skill `context-snippet.md`, per-run result contract `export-skill-result-{timestamp}.json` and `export-skill-result-latest.json` |
| **Multi-skill mode** | Activated when more than one skill is selected (via `--all`, multi-selection, or multi-argument invocation). See `references/load-skill.md` §1c for the per-step iteration map. |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Each auto-resolved gate appends a `{gate, default_action, taken_action, reason}` entry to `headless_decisions[]`, surfaced in step 6's `SKF_EXPORT_RESULT_JSON` envelope so non-interactive runs can be audited post-hoc. |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                    |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 7 (terminal); also `status="dry-run"` when `--dry-run` is set                          |
| 2    | input-missing / input-invalid | step 1 (no `skill_name` and no `--all` in headless) → `input-missing`; non-existent or malformed skill → `input-invalid` |
| 3    | resolution-failure   | step 1 §2 (no skills found / required artifacts missing); step 1 §1c (multi-skill batch contains a stack-skill that requires re-composition) |
| 4    | write-failure        | On-Activation §3 pre-flight write probe; step 4 §6 (managed-section rewrite); step 4 §9 (manifest write); step 6 §4 (result-contract write) |
| 5    | state-conflict       | step 4 §3b/§4c.1 (orphan context-files or manifest-orphan rows when user selects [c] Cancel); step 4 (malformed `<!-- SKF:BEGIN/END -->` markers in target context file) |
| 6    | user-cancelled       | step 1 §6 confirmation gate `[X]`/cancel; step 4 §8 confirmation gate `[X]`/cancel; any prompt that accepted `cancel`/`exit`/`:q` |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 emits a single-line JSON envelope on **stdout** before chaining to step 7, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_EXPORT_RESULT_JSON: {"status":"success|error|dry-run","skills":[],"context_files_updated":[],"manifest_path":"…|null","headless_decisions":[],"exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path, `"dry-run"` when `--dry-run` was set and the workflow exited before §4 writes, `"error"` on any HALT. `halt_reason` is one of: `null` (success / dry-run), `"input-missing"`, `"input-invalid"`, `"resolution-failure"`, `"stack-redirect"`, `"orphan-cancelled"`, `"malformed-markers"`, `"manifest-write-failed"`, `"context-rebuild-failed"`, `"write-failed"`, `"user-cancelled"`. `exit_code` matches the table above.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - `snippet_skill_root_override` (optional string) — when set, overrides the IDE-derived `skill_root` for snippet `root:` paths. Authoring repos that keep all skills under a single on-disk folder (e.g. `skills/`) set this once so exported snippets reference the real layout instead of a per-IDE directory that does not exist. Consuming projects omit it.

2. **Compute run-scoped variables:**
   - `timestamp` ← UTC `YYYYMMDD-HHmmss` captured at activation time. Fixed for the entire workflow run; summary.md reuses this when writing the result contract.

3. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

4. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append):

   - `{skill-root}/customize.toml` — bundled defaults
   - `_bmad/custom/<skill-name>.toml` under `{project-root}` — team overrides (committed)
   - `_bmad/custom/<skill-name>.user.toml` under `{project-root}` — personal overrides (gitignored)

   If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly — the bundled defaults are an empty string for each path scalar.

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each scalar, if the merged value is empty or absent, use the bundled default:

   - `{managedSectionFormatPath}` ← `workflow.managed_section_format_path` if non-empty, else `assets/managed-section-format.md`
   - `{snippetFormatPath}` ← `workflow.snippet_format_path` if non-empty, else `assets/snippet-format.md`
   - `{exportManifestPath}` ← `workflow.export_manifest_path` if non-empty, else `{skills_output_folder}/.export-manifest.json`

   Stash all three as workflow-context variables. Stage files reference them directly — no conditional at the usage site.

5. **Pre-flight write probe.** Verify `{skills_output_folder}` is writable. A read-only mount, full disk, or permissions-denied path otherwise only surfaces at step 4's managed-section rewrite — by then the user has already confirmed the batch:

   ```bash
   mkdir -p "{skills_output_folder}" && \
     printf 'probe' > "{skills_output_folder}/.skf-write-probe" && \
     rm "{skills_output_folder}/.skf-write-probe"
   ```

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`). In headless mode, emit the error envelope per **Result Contract (Headless)** with `skills: []`, `context_files_updated: []`, `manifest_path: null`.

6. Load, read the full file, and then execute `references/load-skill.md` to begin the workflow.
