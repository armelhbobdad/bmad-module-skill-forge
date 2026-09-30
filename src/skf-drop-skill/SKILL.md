---
name: skf-drop-skill
description: Drop a specific skill version or an entire skill — soft (deprecate) or hard (purge) with platform context rebuild. Use when the user requests to "drop" or "remove a skill."
---

# Drop Skill

## Overview

Drops a specific skill version or an entire skill, either as a soft deprecation (manifest-only, files retained) or a hard purge (files deleted). Ensures platform context files are rebuilt to exclude dropped versions. In interactive mode every destructive action requires explicit user confirmation — nothing is deleted silently; headless runs auto-resolve the gates with their default action and log each auto-decision. The export manifest is the source of truth; the filesystem is updated to match.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Module-level path exception:** paths starting with `knowledge/` or `shared/` resolve from the SKF module root, not the skill root — install layout puts both at `{project-root}/_bmad/skf/`. The `versionPathsKnowledge: 'knowledge/version-paths.md'` frontmatter scalar in stage files uses this convention; same for `shared/health-check.md` chained from the terminal step.
- **Shared context-file rebuild:** `references/select.md` and `references/execute.md` resolve the context files and rebuild their managed sections through `shared/scripts/skf-rebuild-managed-sections.py` (`resolve-targets`, `check`, `assemble`, `replace`), the helper export-skill writes them with, so the three skills that write the section produce the same bytes from one IDE mapping (`shared/data/ide-context-files.json`). `skf-export-skill/assets/managed-section-format.md` documents that format.

## Role

You are Ferris in Management mode — a destructive operation specialist who enforces safety guards. You treat every drop as potentially irreversible and never delete beyond the confirmed blast radius. You protect the active version, keep the export manifest consistent with on-disk state, and ensure downstream platform context files are rebuilt.

## Workflow Rules

These rules apply to every step in this workflow:

- Never delete files in purge mode without clearing the §10 confirmation gate (auto-resolved with its default in headless)
- Never drop an active version when other non-deprecated versions exist — enforce the active version guard
- Never purge content SKF did not generate: select.md §8b takes the purge verdict for the skill folder and its forge folder from the inventory helper; a forge folder SKF did not generate is left in place, and a purge SKF cannot check is refused
- Only load one step file at a time — never preload future steps
- If any instruction references a subprocess or tool you lack, achieve the outcome in your main context thread — except the ownership check: never decide by hand whether SKF generated a folder; without the inventory helper, select.md offers manifest skills only and refuses every purge
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
| **Headless** | Gates auto-resolve with their default action (see Workflow Rules). When `forbid_purge_in_headless` is `"true"` in `customize.toml` AND the effective drop mode is `"purge"` (defined in On-Activation §4 — explicit `mode=purge` or `default_mode` purge), §4 HALTs with exit code 6 (`halt_reason: "headless-purge-forbidden"`) before any work begins. A draft skill (no manifest entry) has nothing to deprecate: headless, select.md §8 purges it only on that same effective purge, so this guard covers it too, and refuses `mode=deprecate` or a `default_mode` of `deprecate` (`input-invalid`) and a run with neither (`input-missing`). |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every hard HALT exits with a stable code so headless automators branch on the failure class without grepping message text. The `Raised by` column names the HALT class per code; the authoritative per-site declarations (with exact `halt_reason`) live in the step files.

| Code | Meaning              | Raised by (class) |
| ---- | -------------------- | ----------------- |
| 0    | success              | step 4 (terminal) |
| 2    | input-missing / input-invalid | step 1 headless input gates — missing or unmatched `skill_name`, `version`, or `--mode` value (§4 / §6 / §8); §8 a draft skill with no manifest entry: `mode=deprecate`, or headless with a `default_mode` of `deprecate` → `input-invalid` |
| 3    | resolution-failure   | step 1 manifest/skill-list resolution (§2 corrupt manifest, §3 nothing to drop) |
| 4    | write-failure        | On-Activation write probe; step 1 §9b context-file resolution (the rebuild helper is missing or fails, before any change); step 2 manifest write / context rebuild / full-purge failure |
| 5    | state-conflict       | step 1 active-version guard (§7); step 1 ownership guard — §3/§4 a named folder SKF did not generate (§3 when the roster is empty), §8b a purge of content SKF did not generate or cannot check, in the skill folder or its forge folder → `not-skf-output` |
| 6    | user-cancelled       | any interactive cancel or confirm-gate `[N]`; On-Activation headless-purge guard |

## Result Contract (Headless)

When `{headless_mode}` is true, step 3 emits a single-line `SKF_DROP_SKILL_RESULT_JSON:` envelope on **stdout**; every HARD HALT emits the same shape on **stderr** with `status: "error"`. The template, `status`/`halt_reason` semantics, `exit_code` (per the Exit Codes table above), and full enum live in `references/headless-contract.md` — the emitting stages load it directly, so an error path never depends on this file.

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - `snippet_skill_root_override` (optional string): when set, the context-file rebuild in step 2 passes it to `assemble` as `--skill-root-override`, so every row's `root:` takes it instead of the target IDE's skill root. See `skf-export-skill/assets/managed-section-format.md` for full semantics.
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

   - `{defaultMode}` ← `workflow.default_mode` (empty = always prompt; `"deprecate"` or `"purge"` = skip §8 Ask Mode)
   - `{forbidPurgeInHeadless}` ← `workflow.forbid_purge_in_headless` (empty or non-`"true"` = no guard)
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty (no-op — step 3 skips the post-drop hook entirely)

   Stash all three as workflow-context variables. Stage files reference them directly, with no conditional at the usage site.

   Also apply the array surfaces: run `workflow.activation_steps_prepend` now, keep `workflow.persistent_facts` as standing context (`file:` entries load their contents), then run `workflow.activation_steps_append` after.

4. **Pre-flight write probe + headless-purge guard.**

   First, verify `{skills_output_folder}` is writable. A read-only mount, full disk, or permissions-denied path otherwise only surfaces at step 2's manifest write — by then the user has already gone through every selection prompt:

   ```bash
   mkdir -p "{skills_output_folder}" && \
     printf 'probe' > "{skills_output_folder}/.skf-write-probe" && \
     rm "{skills_output_folder}/.skf-write-probe"
   ```

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`). In headless mode, emit the error envelope per **Result Contract (Headless)** with `skill: null` and `drop_mode: null` (neither is resolved yet at activation time).

   Second, enforce the headless-purge guard. First compute the **effective drop mode**: it is `"purge"` when the parsed `mode` arg is `"purge"`, OR when no `mode` arg was passed AND `{defaultMode}` (resolved in §3) is `"purge"` — a purge reached via `default_mode` is still an unattended irreversible purge and must be caught here, not only an explicit `--mode purge`. If `{headless_mode}` is true AND `{forbidPurgeInHeadless}` is `"true"` AND the effective drop mode is `"purge"`: HALT with exit code 6 and `halt_reason: "headless-purge-forbidden"`, emit the error envelope, and exit immediately. The operator must re-run with an explicit `mode=deprecate` (an explicit arg overrides `default_mode`) or set `forbid_purge_in_headless = ""` (or omit the override entirely) to proceed. A draft skill (no manifest entry) cannot be deprecated, so it needs an interactive run or the guard unset. select.md §8 purges a draft headless only on this same effective drop mode, so this guard is the only check it needs.

5. Load, read the full file, and then execute `references/select.md` to begin the workflow.
