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
- **Cross-skill data coupling:** `assets/managed-section-format.md` (loaded by drop-skill and rename-skill's `execute.md`) and `references/update-context.md` §4a (v2 manifest schema enforced by `skf-manifest-ops.py`) are the source of truth for those contracts — schema-breaking changes here need coordinated updates across those skills.

## Role

You are a delivery and packaging specialist collaborating with a skill developer, pairing your skill-packaging, ecosystem-compliance, and context-injection expertise with their completed skill and distribution requirements.

## Workflow Rules

These rules apply to every step in this workflow:

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
| **Flags** | `--headless` / `-H` (auto-resolve all gates); `--all` (export every non-deprecated skill in `.export-manifest.json`); `--dry-run` (stage everything but write nothing — context files, manifest, and snippet are previewed only; the run completes read-only through the terminal step; `status="dry-run"`) |
| **Gates** | step 1: single Confirm Gate [C] for the whole batch | step 4: single Confirm Gate [C] for the whole batch |
| **Outputs** | Updated `.export-manifest.json` (every skill in the batch), updated context files (CLAUDE.md/AGENTS.md/.cursorrules), per-skill `context-snippet.md`, per-run result contract `export-skill-result-{timestamp}.json` and `export-skill-result-latest.json` |
| **Multi-skill mode** | Activated when more than one skill is selected (via `--all`, multi-selection, or multi-argument invocation). See `references/load-skill.md` §1c for the per-step iteration map. |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true. Each auto-resolved gate appends a `{gate, default_action, taken_action, reason}` entry to `headless_decisions[]`, surfaced in step 6's `SKF_EXPORT_RESULT_JSON` envelope so non-interactive runs can be audited post-hoc. |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by (halt site → `halt_reason`)                                                         |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 7 (terminal); also `status="dry-run"` when `--dry-run` is set                          |
| 2    | input-missing        | step 1 §1 — headless run with no `skill_name` and no `--all` (a non-interactive run cannot answer the skill-selection menu) → `input-missing` |
| 3    | resolution-failure   | step 1 §1 (discovery finds no skills on disk / in the manifest); step 1 §2 (a named skill's required artifacts are missing or its metadata is invalid — export-gate FAIL); multi-skill batch (any skill failing §2 validation halts the whole batch) → `resolution-failure` |
| 4    | write-failure        | On-Activation §5 pre-flight write probe → `write-failed`; step 4 §3b / §9 / §4c.1 (managed-section create/append/rewrite/clear verify fails, or a required helper is unresolvable) → `context-rebuild-failed`; step 4 §9b manifest write → `manifest-write-failed` |
| 5    | state-conflict       | step 4 §6 — malformed `<!-- SKF:BEGIN/END -->` markers in the target context file (`<!-- SKF:BEGIN` present, `<!-- SKF:END -->` missing) → `malformed-markers` |
| 6    | user-cancelled       | step 1 §6 gate `[X]`/cancel; step 1 §1b snippet-root probe (a)/(c); step 4 §8 gate `[X]`/cancel; step 4 §4c.1 orphan-row (c) Cancel; any prompt accepting `cancel`/`exit`/`:q` → `user-cancelled` |

## Result Contract (Headless)

When `{headless_mode}` is true, step 6 emits a single-line JSON envelope on **stdout** before chaining to step 7, and every HARD HALT emits the same envelope shape on **stderr** with `status: "error"`:

```
SKF_EXPORT_RESULT_JSON: {"status":"success|error|dry-run","skills":[],"context_files_updated":[],"manifest_path":"…|null","headless_decisions":[],"exit_code":0,"halt_reason":null}
```

`references/result-envelope.md` is the single source for the full field semantics and the `halt_reason` enum — halting stages load it directly, so the enum lives in exactly one place. `exit_code` matches the Exit Codes table above.

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

   Apply the fallback now so stage files don't have to repeat the conditional logic. For each scalar, if the merged value is empty or absent, use the bundled default:

   - `{managedSectionFormatPath}` ← `workflow.managed_section_format_path` if non-empty, else `assets/managed-section-format.md`
   - `{snippetFormatPath}` ← `workflow.snippet_format_path` if non-empty, else `assets/snippet-format.md`
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty string (no-op — step 6 skips the hook invocation)

   Stash all three as workflow-context variables. Stage files reference them directly — no conditional at the usage site.

   **Apply the array surfaces so they are not silent no-ops:** execute each entry in `workflow.activation_steps_prepend` in order now (org-wide pre-flight such as auth, network, or compliance); treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries are paths or globs whose contents load as facts — the bundled default loads any `project-context.md`); then, after activation completes and before the first stage runs, execute each entry in `workflow.activation_steps_append` in order.

5. **Pre-flight write probe.** Verify `{skills_output_folder}` is writable. A read-only mount, full disk, or permissions-denied path otherwise only surfaces at step 4's managed-section rewrite — by then the user has already confirmed the batch:

   ```bash
   mkdir -p "{skills_output_folder}" && \
     printf 'probe' > "{skills_output_folder}/.skf-write-probe" && \
     rm "{skills_output_folder}/.skf-write-probe"
   ```

   On any non-zero exit: HALT (exit code 4, `halt_reason: "write-failed"`). In headless mode, emit the error envelope per `references/result-envelope.md` with `skills: []`, `context_files_updated: []`, `manifest_path: null`.

6. Load, read the full file, and then execute `references/load-skill.md` to begin the workflow.
