---
name: skf-rename-skill
description: Rename a skill across all its versions — transactional copy-verify-delete with platform context rebuild. Use when the user requests to "rename a skill."
---

# Rename Skill

## Overview

Renames a skill across all its versions with transactional safety — copy to the new name, verify all references updated, delete the old name only after verification succeeds. Rebuilds platform context files to reference the new name. The agentskills.io spec requires `name` to match parent directory name, so a rename is a coordinated move across 9+ locations in every version.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Module-level path exception:** paths starting with `knowledge/` or `shared/` resolve from the SKF module root, not the skill root — install layout puts both at `{project-root}/_bmad/skf/`. The `versionPathsKnowledge: 'knowledge/version-paths.md'` frontmatter scalar in stage files uses this convention; same for `shared/health-check.md` chained from the terminal step.
- **Cross-skill data coupling:** `references/execute.md` reads `skf-export-skill/assets/managed-section-format.md` for the IDE→context-file mapping table and the skill-index rebuild rules when re-keying context files post-rename. Rename-skill assumes that asset is present at install time and that its semantics are stable across the two skills' versions.

## Role

You are Ferris in Management mode — a precision surgeon who operates on the entire skill group atomically. You guarantee safety via copy-before-delete: the new name is fully materialized and verified before the old name is removed, so any failure mid-operation leaves the original skill intact.

## Workflow Rules

These rules apply to every step in this workflow:

- Never delete the old skill directories until the new name has been fully materialized and verified
- Never proceed past a verification failure — roll back (delete new directories) and halt
- Never allow a rename to collide with an existing skill name
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Select & Validate | references/select.md | No (confirm) |
| 2 | Execute Rename | references/execute.md | No (confirm) |
| 3 | Report | references/report.md | Yes |
| 4 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | old_name [required], new_name [required] |
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--dry-run` (run selection + validation + display the §8 confirmation block, then exit with `status="dry-run"` — no copy, no manifest re-key, no delete). Useful for verifying the rename plan before the irreversible §8 (delete old) section. |
| **Gates** | step 1: Input Gate [use args] x2, Confirm Gate [Y] |
| **Outputs** | Renamed skill directories, updated manifest, updated context files, `{new_name}/rename-skill-result-{timestamp}.json` and `{new_name}/rename-skill-result-latest.json` |
| **Concurrency** | Two simultaneous rename runs against the same `old_name` would corrupt state mid-copy. select.md §4b acquires a PID-file lock at `{forge_data_folder}/{old_name}/.skf-rename.lock` once `old_name` is resolved; live-PID collisions HALT with `halt_reason: "halted-for-concurrent-run"`. Stale locks (dead PID) are cleared silently with a warning. The lock is released by the terminal health-check step (step 4) and by every documented halt path. |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. The §6 source-authority warning HALTs by default in headless when `source_authority="official"`; set `force_source_authority_in_headless = "true"` in `customize.toml` to auto-acknowledge and proceed (the override is recorded in `headless_decisions[]`). |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                    |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 4 (terminal)                                                                           |
| 2    | input-missing / input-invalid | step 1 §4/§5 (headless missing `old_name`/`new_name` arg) → `input-missing`; new name fails kebab-case / length / same-as-old → `input-invalid` |
| 3    | resolution-failure   | step 1 §2 (manifest is malformed JSON); step 1 §3 (no skills found anywhere)               |
| 4    | write-failure        | On-Activation §3 pre-flight write probe (skills_output_folder / forge_data_folder unwritable); step 2 §1 (copy); step 2 §3 (file content update); step 2 §6 (manifest write); step 2 §7 (context-file rewrite) |
| 5    | state-conflict       | step 1 §5 (name-collision check fails: target name already in use); step 1 §6 (source-authority="official" headless without `force_source_authority_in_headless`); concurrency lock collision (`halted-for-concurrent-run`) |
| 6    | user-cancelled       | step 1 §6 (source-authority warning [N]); step 1 §8 confirmation gate `[N]`; any prompt that accepted `cancel`/`exit`/`:q` |

## Result Contract (Headless)

When `{headless_mode}` is true, step 3 emits a single-line JSON envelope on **stdout** before chaining to step 4, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_RENAME_SKILL_RESULT_JSON: {"status":"success|error|dry-run","old_name":"…|null","new_name":"…|null","versions_renamed":[],"manifest_rekeyed":false,"context_files_updated":[],"exit_code":0,"halt_reason":null}
```

`status` is `"success"` on the terminal happy path, `"dry-run"` when `--dry-run` was set and the workflow exited before §9 stores decisions, `"error"` on any HALT. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"manifest-corrupt"`, `"nothing-to-rename"`, `"name-collision"`, `"source-authority-blocked"`, `"halted-for-concurrent-run"`, `"copy-failed"`, `"verify-failed"`, `"manifest-write-failed"`, `"context-rebuild-failed"`, `"write-failed"`, `"user-cancelled"`. `exit_code` matches the table above.

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

   Apply the scalar fallback now so stage files don't have to repeat the conditional logic. For each of the three scalars, if the merged value is empty or absent, the bundled default applies:

   - `{forceSourceAuthorityInHeadless}` ← `workflow.force_source_authority_in_headless` (empty or non-`"true"` = HALT in headless on `"official"` source-authority)
   - `{unknownIdeDefaultContextFile}` ← `workflow.unknown_ide_default_context_file` if non-empty, else `AGENTS.md`
   - `{unknownIdeDefaultSkillRoot}` ← `workflow.unknown_ide_default_skill_root` if non-empty, else `.agents/skills/`

   Stash all three as workflow-context variables. Stage files reference them directly — no conditional at the usage site.

4. **Pre-flight write probe.** Verify both `{skills_output_folder}` and `{forge_data_folder}` are writable. A read-only mount, full disk, or permissions-denied path otherwise only surfaces inside step 2's transactional copy — by then the user has already gone through name validation and confirmation:

   ```bash
   for dir in "{skills_output_folder}" "{forge_data_folder}"; do
     mkdir -p "$dir" && \
       printf 'probe' > "$dir/.skf-write-probe" && \
       rm "$dir/.skf-write-probe"
   done
   ```

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`). In headless mode, emit the error envelope per **Result Contract (Headless)** with `old_name: null` and `new_name: null` (neither is resolved yet at activation time).

5. Load, read the full file, and then execute `references/select.md` to begin the workflow.
