---
name: skf-export-skill
description: Package for distribution and inject context into CLAUDE.md/AGENTS.md/.cursorrules. Use when the user requests to "export" or "package a skill."
---

# Export Skill

## Overview

Packages a completed skill as an agentskills.io-compliant package, generates context snippets, and updates the managed section in CLAUDE.md/.cursorrules/AGENTS.md for platform-aware context injection. It is the sole publishing gate — create-skill/update-skill produce drafts; only export writes platform context files and distribution packages.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- **Module-level path exception:** bare `knowledge/` and `shared/` paths resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root (e.g. `knowledge/version-paths.md`, `shared/health-check.md`).
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Cross-skill data coupling:** export-skill, drop-skill and rename-skill write the managed section through one helper, `shared/scripts/skf-rebuild-managed-sections.py` (`resolve-targets` over `shared/data/ide-context-files.json`, then `check`, `assemble`, `insert` and `replace`), in the format `assets/managed-section-format.md` documents, and change `.export-manifest.json` only through `shared/scripts/skf-manifest-ops.py` (v2 schema in `references/manifest-rebuild.md`). A change to either contract changes all three skills.

## Role

You are a delivery and packaging specialist operating in Ferris's Delivery mode, collaborating with a skill developer, pairing your skill-packaging, ecosystem-compliance, and context-injection expertise with their completed skill and distribution requirements.

## Workflow Rules

These rules apply to every step in this workflow:

- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- At any interactive prompt, the inputs `cancel`, `exit`, `[X]`, `q`, or `:q` exit cleanly with exit code 6 (`halt_reason: "user-cancelled"`)
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and record each auto-decision in the run sink (`references/result-envelope.md`)
- **Snippet timing:** step 3 only stages each `context-snippet.md` outside the project; step 4 §9c copies it into the skill package after its [C] gate, as step 4's last write. A cancel, a dry run or a halt before §9c leaves every snippet, and a carried gotchas line's one `[CARRIED]` cycle, as it was.

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
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--all` (export every non-deprecated skill in `.export-manifest.json`); `--dry-run` (stage everything but write nothing other than a headless run's scratch run folder, as **Outputs** says: the snippet, context-file and manifest changes are previewed only, no result file is written and no `on_complete` hook runs; the run completes through the terminal step with `status="dry-run"` and `manifest_path: null`) |
| **Gates** | step 1: single Confirm Gate [C] for the whole batch | step 4: single Confirm Gate [C] for the whole batch |
| **Outputs** | Updated `.export-manifest.json` (every skill in the batch, also when `passive_context` is off), updated context files (CLAUDE.md/AGENTS.md/.cursorrules), per-skill `context-snippet.md` (written last, after the step-4 gate), per-run result contract `export-skill-result-{YYYYMMDD-HHmmss}.json` and `export-skill-result-latest.json` (none on a dry run); in a headless run, a scratch run folder under `{project-root}/_bmad-output/.skf-run/`, which step 6 deletes (a HARD HALT keeps it) |
| **Multi-skill mode** | Activated when more than one skill is selected (via `--all`, multi-selection, or multi-argument invocation). See `references/load-skill.md` §1c for the per-step iteration map. |
| **Headless** | Every gate takes its default action and records it as it decides (Workflow Rules), and the run ends with one `SKF_EXPORT_RESULT_JSON` line: `references/result-envelope.md` |
| **Exit codes** | 0 on success and on a dry run. Each HARD HALT names its exit code and `halt_reason` where it occurs (3 and `not-skf-output` for a flat skill SKF did not generate, for example); `references/result-envelope.md` maps every halt site to its code |

## On Activation

1. Load config from `{project-root}/_bmad/skf/config.yaml` and resolve:
   - `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
   - `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - `snippet_skill_root_override` (optional string) — when set, overrides the IDE-derived `skill_root` for snippet `root:` paths. Authoring repos that keep all skills under a single on-disk folder (e.g. `skills/`) set this once so exported snippets reference the real layout instead of a per-IDE directory that does not exist. Consuming projects omit it.

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

   If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly. The bundled defaults are an empty string for each scalar.

   Apply the fallback now so stage files don't have to repeat the conditional logic. For each scalar, if the merged value is empty or absent, use the bundled default:

   - `{snippetFormatPath}` ← `workflow.snippet_format_path` if non-empty, else `assets/snippet-format.md`
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string (no-op — step 6 skips the hook invocation)

   Stash both as workflow-context variables. Stage files reference them directly, with no conditional at the usage site.

   **Apply the array surfaces so they are not silent no-ops:** execute each entry in `workflow.activation_steps_prepend` in order now (org-wide pre-flight such as auth, network, or compliance); treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries are paths or globs whose contents load as facts — the bundled default loads any `project-context.md`); then, after activation completes and before the first stage runs, execute each entry in `workflow.activation_steps_append` in order.

4. **Resolve the envelope helper and create the run folder.** `{emitEnvelopeHelper}` ← the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. It builds every `SKF_EXPORT_RESULT_JSON` line and the result files, and records each headless auto-decision. If neither path exists, HALT (exit code 4, `halt_reason: "context-rebuild-failed"`): "`skf-emit-result-envelope.py` is missing. Nothing was changed. Re-install SKF." With no emitter, a headless run displays that reason alone.

   When `{headless_mode}` is true, create the run folder, whose sink holds those decisions:

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-export-skill-XXXXXXXX"
   ```

   Bind `{run_dir}` ← the path it prints. Step 6 deletes it once the run's envelope is out; a HARD HALT leaves it in place. If it cannot be created, HALT (exit code 4, `halt_reason: "write-failed"`) and emit the error envelope per `references/result-envelope.md`, without `--run-dir`, with `skills: []`, `context_files_updated: []`, `manifest_path: null`.

5. **Pre-flight write check.** Verify `{skills_output_folder}` is writable. A read-only mount, full disk, or permissions-denied path otherwise only surfaces at step 4's writes, after the user has confirmed the batch. Without `--dry-run`, probe it with a write:

   ```bash
   mkdir -p "{skills_output_folder}" && \
     printf 'probe' > "{skills_output_folder}/.skf-write-probe" && \
     rm "{skills_output_folder}/.skf-write-probe"
   ```

   With `--dry-run`, check without writing: `test -w "{skills_output_folder}"` when the folder exists; when it does not, skip the check, since step 1 then finds no skill to export.

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`). In headless mode, emit the error envelope per `references/result-envelope.md` with `skills: []`, `context_files_updated: []`, `manifest_path: null`.

6. Load, read the full file, and then execute `references/load-skill.md` to begin the workflow.
