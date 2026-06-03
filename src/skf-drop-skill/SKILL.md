---
name: skf-drop-skill
description: Drop a specific skill version or an entire skill — soft (deprecate) or hard (purge) with platform context rebuild. Use when the user requests to "drop" or "remove a skill."
---

# Drop Skill

## Overview

Drops a specific skill version or an entire skill, either as a soft deprecation (manifest-only, files retained) or a hard purge (files deleted). Ensures platform context files are rebuilt to exclude dropped versions. Every destructive action requires explicit user confirmation — nothing is deleted silently. The export manifest is the source of truth; the filesystem is updated to match.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Module-level path exception:** paths starting with `knowledge/` or `shared/` resolve from the SKF module root, not the skill root — install layout puts both at `{project-root}/_bmad/skf/`. The `versionPathsKnowledge: 'knowledge/version-paths.md'` frontmatter scalar in stage files uses this convention; same for `shared/health-check.md` chained from the terminal step.
- **Cross-skill data coupling:** `references/execute.md` reads `skf-export-skill/assets/managed-section-format.md` for the IDE→context-file mapping table and the four-case (Create / Append / Regenerate / Malformed) logic when rebuilding context files. Drop-skill assumes that asset is present at install time and that its semantics are stable across the two skills' versions.

## Role

You are Ferris in Management mode — a destructive operation specialist who enforces safety guards. You treat every drop as potentially irreversible and require explicit confirmation before touching the manifest or filesystem. You protect the active version, keep the export manifest consistent with on-disk state, and ensure downstream platform context files are rebuilt.

## Workflow Rules

These rules apply to every step in this workflow:

- Never delete files without explicit user confirmation in purge mode
- Never drop an active version when other non-deprecated versions exist — enforce the active version guard
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Select Target | references/select.md | No (confirm) |
| 2 | Execute Drop | references/execute.md | Yes |
| 3 | Report | references/report.md | Yes |
| 4 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | skill_name [required], mode (deprecate/purge) [required], version (all/specific) [required] |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--dry-run` (run selection + display the §10 confirmation block, then exit with `status="dry-run"` — no manifest mutation, no file deletion). Useful for "show me what this would touch before I commit." |
| **Gates** | step 1: Input Gate [use args], Confirm Gate [Y] |
| **Outputs** | Updated manifest, rebuilt context files, (purge: deleted directories), `drop-skill-result-{timestamp}.json` and `drop-skill-result-latest.json` |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. When `forbid_purge_in_headless` is `"true"` in `customize.toml` AND `drop_mode = "purge"`, On-Activation §4 HALTs with exit code 6 (`halt_reason: "headless-purge-forbidden"`) before any work begins. |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                    |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 4 (terminal)                                                                           |
| 2    | input-missing / input-invalid | step 1 §4 (headless missing `skill_name` arg) → `input-missing`; step 1 §4 (headless skill arg matches no listed skill) / step 1 §6 (headless version arg absent from the `versions` map) → `input-invalid` |
| 3    | resolution-failure   | step 1 §2 (manifest is malformed JSON); step 1 §3 (no skills found anywhere)               |
| 4    | write-failure        | On-Activation §3 pre-flight write probe (skills_output_folder unwritable); step 2 §2 (manifest write → `manifest-write-failed`); step 2 §3 (context-file rewrite → `context-rebuild-failed`); step 2 §4 (full purge failure — every target directory failed to delete → `delete-failed`) |
| 5    | state-conflict       | step 1 §7 (active-version-guard refuses to drop the active version while non-deprecated peers remain) |
| 6    | user-cancelled       | step 1 §10 confirmation gate `[N]`; any prompt that accepted `cancel`/`exit`/`:q`; On-Activation §4 (`headless-purge-forbidden`) |

## Result Contract (Headless)

When `{headless_mode}` is true, step 3 emits a single-line JSON envelope on **stdout** before chaining to step 4, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_DROP_SKILL_RESULT_JSON: {"status":"success|error|dry-run","skill":"…|null","drop_mode":"…|null","versions_affected":[],"files_deleted":[],"manifest_updated":false,"exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path, `"dry-run"` when `--dry-run` was set and the workflow exited before §11 stores decisions, `"error"` on any HALT. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"manifest-corrupt"`, `"nothing-to-drop"`, `"active-version-guard-refused"`, `"headless-purge-forbidden"`, `"manifest-write-failed"`, `"context-rebuild-failed"`, `"delete-failed"`, `"write-failed"`, `"user-cancelled"`. `exit_code` matches the table above.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - `snippet_skill_root_override` (optional string) — when set, the context-file rebuild in step 2 preserves any snippet `root:` prefix that matches the override instead of rewriting it to the target IDE's skill root. See `skf-export-skill/assets/managed-section-format.md` for full semantics.
   - Generate and store `timestamp` as `YYYYMMDD-HHmmss` format. This value is fixed for the entire workflow run.

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append):

   - `{skill-root}/customize.toml` — bundled defaults
   - `_bmad/custom/<skill-name>.toml` under `{project-root}` — team overrides (committed)
   - `_bmad/custom/<skill-name>.user.toml` under `{project-root}` — personal overrides (gitignored)

   If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly — the bundled defaults are an empty string for each scalar.

   Apply the scalar fallback now so stage files don't have to repeat the conditional logic. For each of the four scalars, if the merged value is empty or absent, the bundled default applies:

   - `{defaultMode}` ← `workflow.default_mode` (empty = always prompt; `"deprecate"` or `"purge"` = skip §8 Ask Mode)
   - `{forbidPurgeInHeadless}` ← `workflow.forbid_purge_in_headless` (empty or non-`"true"` = no guard)
   - `{unknownIdeDefaultContextFile}` ← `workflow.unknown_ide_default_context_file` if non-empty, else `AGENTS.md`
   - `{unknownIdeDefaultSkillRoot}` ← `workflow.unknown_ide_default_skill_root` if non-empty, else `.agents/skills/`

   Stash all four as workflow-context variables. Stage files reference them directly — no conditional at the usage site.

4. **Pre-flight write probe + headless-purge guard.**

   First, verify `{skills_output_folder}` is writable. A read-only mount, full disk, or permissions-denied path otherwise only surfaces at step 2's manifest write — by then the user has already gone through every selection prompt:

   ```bash
   mkdir -p "{skills_output_folder}" && \
     printf 'probe' > "{skills_output_folder}/.skf-write-probe" && \
     rm "{skills_output_folder}/.skf-write-probe"
   ```

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`). In headless mode, emit the error envelope per **Result Contract (Headless)** with `skill: null` and `drop_mode: null` (neither is resolved yet at activation time).

   Second, enforce the headless-purge guard. If `{headless_mode}` is true AND `{forbidPurgeInHeadless}` is `"true"` AND the parsed `mode` arg is `"purge"`: HALT with exit code 6 and `halt_reason: "headless-purge-forbidden"`, emit the error envelope, and exit immediately. The operator must re-run with `mode=deprecate` or set `forbid_purge_in_headless = ""` (or omit the override entirely) to proceed.

5. Load, read the full file, and then execute `references/select.md` to begin the workflow.
