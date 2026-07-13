---
name: skf-quick-skill
description: Fast skill from a package name or GitHub URL — no brief needed. Use when the user requests a "quick skill" or "skill from URL" or "skill from package."
---

# Quick Skill

## Overview

The fastest path to a skill — accept a GitHub URL or package name, resolve to source, extract the public API surface, and produce a best-effort SKILL.md with context snippet and metadata. No brief needed. Output is always community-tier quality, regardless of which tools are available.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root.
- `references/` holds prompt content carved out of SKILL.md (workflow stages chained via frontmatter `nextStepFile`, plus static reference docs); `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a rapid skill compiler collaborating with a developer. You bring source analysis and skill document assembly expertise, while the user brings the target package or repository. Work together efficiently — speed is the priority.

## Workflow Rules

These rules apply to every step in this workflow:

- Never fabricate content — all data must come from source extraction or user input
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- **Universal cancel-line affordance** — at any interactive prompt the user may type `cancel`, `exit`, `:q`, or select the `[X] Cancel and exit` menu option (where surfaced) to leave cleanly. HARD HALT with **exit code 6 (user-cancelled)** and emit the error result contract per `references/halt-contract.md` with `error.code: "user-cancelled"`. In step 4 §6 the equivalent affordance is `[Q] Quit without writing` — same exit code, same envelope contract.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision
- If `{headless_mode}` is true, emit a single-line JSON progress event to **stderr** at each step's entry and exit so pipeline schedulers can stream live progress instead of post-mortem-parsing the result contract:
  - entry: `{"step":N,"name":"<slug>","status":"start"}`
  - exit (just before chaining to nextStepFile): `{"step":N,"name":"<slug>","status":"done"}`
  - on HARD HALT: `{"step":N,"name":"<slug>","status":"halt","exit":<code>}` instead of "done"

  `N` is the step number and `<slug>` is the kebab portion of the filename (see the Stages table below for the canonical list). One line per event; do not pretty-print.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Resolve Target | references/resolve-target.md | Yes |
| 2 | Ecosystem Check | references/ecosystem-check.md | Yes |
| 3 | Quick Extract | references/quick-extract.md | Yes |
| 4 | Compile | references/compile.md | No (review) |
| 5 | Write & Validate | references/write-and-validate.md | Yes |
| 6 | Finalize | references/finalize.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | target (GitHub URL or package name) [required for single-target mode], language_hint [optional], scope_hint [optional] |
| **Overrides** | `--description`, `--exports`, `--skip-snippet`, `--no-active-pointer`, `--batch <file>`, `--fail-fast` — see On Activation step 4 |
| **Gates** | step 1: target input, multi-language disambiguation [C/A]; step 2: ecosystem match [P/I/A] (if match); step 3: repo-shape [C/A] + zero-exports rescue [R/P/A]; step 4: review [C/E/S/Q]; step 5: overwrite [Y/N] |
| **Outputs** | SKILL.md, context-snippet.md, metadata.json, active pointer, result contract (timestamped + `-latest` copy). Snippet and active pointer can be skipped per overrides. |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |
| **Exit codes** | See `references/halt-contract.md` |

## Exit Codes & HARD HALT Contract

See `references/halt-contract.md` for the exit-code map and the error-result envelope every HARD HALT emits (the `SKF_QUICK_SKILL_RESULT_JSON:` stderr line, the on-disk `-latest.json` write once `{skill_package}` is known, and the schema). Steps load it on their failure path so the wire format survives compaction.

## On Activation

1. Read `{project-root}/_bmad/skf/config.yaml` and `{sidecar_path}/preferences.yaml` in parallel (one batched tool-call message — they are independent files), then resolve:
   - From config: `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - From preferences: `headless_mode` (default false)

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `preferences.yaml`. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py \
       --skill {skill-root} --key workflow
   ```

   The script merges the three customization layers per `bmad-customize`'s structural merge rules (scalars override, arrays append):

   - `{skill-root}/customize.toml` — bundled defaults
   - `_bmad/custom/<skill-name>.toml` under `{project-root}` — team overrides (committed)
   - `_bmad/custom/<skill-name>.user.toml` under `{project-root}` — personal overrides (gitignored)

   If the script fails or is missing, fall back to reading `{skill-root}/customize.toml` directly — the bundled defaults are an empty string for each path scalar.

   Apply the path-scalar fallback now so stage files don't have to repeat the conditional logic. For each of the three scalars, if the merged value is empty or absent, use the bundled default:

   - `{skillTemplatePath}` ← `workflow.skill_template_path` if non-empty, else `assets/skill-template.md`
   - `{registryResolutionPath}` ← `workflow.registry_resolution_path` if non-empty, else `references/registry-resolution.md`
   - `{batchOutputPath}` ← `workflow.batch_output_path` if non-empty, else `{skills_output_folder}/_batch/`
   - `{onCompleteCommand}` ← `workflow.on_complete` if non-empty, else empty (no-op — step 6 §3 skips the hook invocation entirely)

   Stash all four as workflow-context variables. Stage files reference `{skillTemplatePath}` / `{registryResolutionPath}` / `{batchOutputPath}` / `{onCompleteCommand}` directly — no conditional at the usage site. Empty-string overrides cleanly fall through to the bundled default; non-empty values let orgs swap in house-style copies (custom template, registry chain, batch output dir) or wire in a post-completion hook (git-add, register, notify) without forking the skill.

   **Apply the array surfaces** so the declared overrides are not silent no-ops: execute each entry in `workflow.activation_steps_prepend` in order now; treat every entry in `workflow.persistent_facts` as standing context for the whole run (`file:`-prefixed entries are paths or globs whose contents load as facts — the bundled default loads any `project-context.md`); then, after activation completes and before the first stage runs, execute each entry in `workflow.activation_steps_append` in order.

4. **Parse CLI overrides** — capture optional override flags into the workflow context as `{overrides}`. Each override is opt-in; when omitted, the workflow runs as today.

   | Flag | Effect |
   | --- | --- |
   | `--description "<string>"` | Override the LLM-derived description in step 4 §2 (used in SKILL.md frontmatter and metadata.json). Subject to the same agentskills.io length (1–1024 chars) and voice (third-person) checks as extracted descriptions. |
   | `--exports "<name1,name2,...>"` | Override the extracted export list. Parse as comma-separated; trim whitespace per item; skip empty items. Used in step 4 §2 Key Exports and the count-derived metadata stats. |
   | `--skip-snippet` | Skip context-snippet.md generation in step 4 §3 and its write in step 5 §2. Artifact omitted from `outputs`; step 5 §5 advisory snippet validation reports a "skipped" entry. |
   | `--no-active-pointer` | Skip the active-pointer flip in step 6 §1. Deliverables still land in `{skill_package}` but `{skill_group}/active` is not updated. Useful for batch automators that flip pointers in a separate stage. |
   | `--batch <file>` | Run the workflow against a list of targets from a text file rather than a single argument. Implies `--headless` (gates cannot be human-driven across N targets). See `references/batch-mode.md` for input format and summary contract. Single-target overrides above apply globally to every target in the batch. |
   | `--fail-fast` | Only meaningful with `--batch`. Abort the whole batch on the first per-target failure instead of recording the failure in the summary and proceeding to the next target. |

5. **If `--batch` is set**, force `{headless_mode} = true` (log "headless: coerced by --batch" if it was false), then load and read `references/batch-mode.md` in full before proceeding. Follow its protocol to read the batch file, parse the target list, and drive the batch loop that wraps the step 1 → step 7 pipeline that follows.

6. Load, read the full file, and then execute `references/resolve-target.md` to begin the workflow. (In batch mode, control returns here for each subsequent target after step 7 completes; see `references/batch-mode.md`.)
