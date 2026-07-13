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

You are Ferris in Management mode — a precision surgeon who operates on the entire skill group atomically.

## Workflow Rules

These rules apply to every step in this workflow:

- Never delete the old skill directories until the new name has been fully materialized and verified
- Never proceed past a verification failure — roll back (delete new directories) and halt
- Never allow a rename to collide with an existing skill name
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread — **except** the atomicity and commit-gate safety helpers that execute.md §0 resolves: a missing one there is a HARD HALT (exit 4), never an LLM fall-through, because hand-driven writes/scans would silently regress the transactional guarantees that keep a failed rename recoverable
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
| **Concurrency** | A PID-file lock at `{forge_data_folder}/{old_name}/.skf-rename.lock` serializes concurrent runs against the same `old_name`; a live-PID collision HALTs with `halt_reason: "halted-for-concurrent-run"` (exit 5). See select.md §4b for the acquire / stale-clear / release mechanism. |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. The §6 source-authority warning HALTs by default in headless when `source_authority="official"`; set `force_source_authority_in_headless = "true"` in `customize.toml` to auto-acknowledge and proceed (the override is recorded in `headless_decisions[]`). |
| **Exit codes** | Stable per-failure-class codes — see `references/exit-codes.md` |

## Result Contract (Headless)

When `{headless_mode}` is true, step 3 emits a single-line JSON envelope on **stdout** before chaining to step 4, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_RENAME_SKILL_RESULT_JSON: {"status":"success|error|dry-run","old_name":"…|null","new_name":"…|null","versions_renamed":[],"manifest_rekeyed":false,"context_files_updated":[],"exit_code":0,"halt_reason":null,"headless_decisions":[]}
```

`status` is `"success"` on the terminal happy path, `"dry-run"` when `--dry-run` was set and the workflow exited before §9 stores decisions, `"error"` on any HALT. `halt_reason` is one of: `null` (success), `"input-missing"`, `"input-invalid"`, `"manifest-corrupt"`, `"nothing-to-rename"`, `"name-collision"`, `"source-authority-blocked"`, `"halted-for-concurrent-run"`, `"copy-failed"`, `"verify-failed"`, `"manifest-write-failed"`, `"write-failed"`, `"user-cancelled"`. (§7 context-file rebuild is best-effort and never halts, so it has no `halt_reason`.) `exit_code` matches `references/exit-codes.md`. `headless_decisions` is the audit trail of confirmation gates auto-resolved under `{headless_mode}` — each entry `{gate, default_action, taken_action, reason}` (the §6 source-authority override and the §8 auto-confirm); it is `[]` in interactive runs and whenever no gate was auto-resolved before the envelope was emitted.

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

   - `{forceSourceAuthorityInHeadless}` ← `workflow.force_source_authority_in_headless` (empty or non-`"true"` = HALT in headless on `"official"` source-authority)
   - `{unknownIdeDefaultContextFile}` ← `workflow.unknown_ide_default_context_file` if non-empty, else `AGENTS.md`
   - `{unknownIdeDefaultSkillRoot}` ← `workflow.unknown_ide_default_skill_root` if non-empty, else `.agents/skills/`
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string (no-op — step 3 skips the post-completion hook invocation)

   Stash all four as workflow-context variables. Stage files reference them directly — no conditional at the usage site.

   Then apply the resolved array surfaces so they are not silent no-ops: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (entries prefixed `file:` are paths or globs whose contents load as facts — the bundled default loads any `project-context.md` so rename-policy and public-name-stability guardrails stay in mind); and after activation completes, execute each entry in `workflow.activation_steps_append` in order.

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
