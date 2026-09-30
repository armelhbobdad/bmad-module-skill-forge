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
- Never write into a skill folder SKF did not generate — write-and-validate §1 runs the inventory's write check before creating any directory; without the helper it writes only into a skill folder that does not exist yet
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- **Universal cancel-line affordance**: at any interactive prompt the user may type `cancel`, `exit`, `:q`, or select the `[X] Cancel and exit` menu option (where surfaced) to leave cleanly. HARD HALT with **exit code 6 (user-cancelled)**: stage `{"phase": "<the step's slug>", "halt_reason": "user-cancelled", "reason": "Cancelled. No files were written.", "skill_package": null}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"` (`references/halt-contract.md`). In step 4 §6 the equivalent affordance is `[Q] Quit without writing`, with the same exit code and envelope.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action, and record each auto-decision in the run folder the moment its gate decides, so the envelope's `headless_decisions` carries it: stage `{"gate": "<the gate's name>", "default_action": "<X>", "taken_action": "<X>", "reason": "headless: <why>"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`. Each gate names its gate and default where it decides.
- If `{headless_mode}` is true, print the one-line JSON progress events on stderr that `references/halt-contract.md` (Headless Events) defines: when each step starts, just before it chains on, and at a HARD HALT.

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
| **Inputs** | target (GitHub URL, package name or npm, PyPI or crates.io page URL) [required for single-target mode], language_hint [optional], scope_hint [optional] |
| **Overrides** | `--description`, `--exports`, `--skip-snippet`, `--no-active-pointer`, `--batch <file>`, `--fail-fast` — see On Activation step 4 |
| **Gates** | step 1: target input, ambiguous package name [C/n/U/X] (if another registry also holds the name; headless keeps the first registry's pick), multi-language disambiguation [C/A]; step 2: ecosystem match [P/I/A] (if match); step 3: repo-shape [C/A] + zero-exports rescue [R/P/A]; step 4: review [C/E/S/Q]; step 5: overwrite [Y/N] |
| **Outputs** | SKILL.md, context-snippet.md, metadata.json, active pointer, result contract (timestamped + `-latest` copy), one `SKF_QUICK_SKILL_RESULT_JSON` line (stdout when the run finishes, stderr at a HARD HALT), and under `--batch` the batch summary. Snippet and active pointer can be skipped per overrides. |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true; each auto-decision is recorded in the envelope's `headless_decisions` |
| **Exit codes** | See `references/halt-contract.md`: the exit-code map, and the emit command every HARD HALT runs, with the on-disk `-latest.json` write once `{skill_package}` holds `metadata.json` (never at the step 5 §1 ownership halt) |

## On Activation

1. Read `{project-root}/_bmad/skf/config.yaml` and `{sidecar_path}/preferences.yaml` in parallel (one batched tool-call message — they are independent files), then resolve:
   - From config: `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`
   - From preferences: `headless_mode` (default false)

   Then resolve `{emitEnvelopeHelper}` ← the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`, the shared emitter every envelope and auto-decision goes through, and create the run folder:

   ```bash
   mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-quick-skill-XXXXXXXX"
   ```

   Bind `{run_dir}` ← the path it prints (a finished run deletes it; a halted one keeps it). If it cannot be created, HARD HALT with **exit code 4 (write-failure)**: display "**Quick Skill cannot start: the run folder could not be created.** {the first stderr line}" and emit with nothing to stage in:

   ```bash
   uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --target stderr <<'SKF_JSON'
   {"phase": "on-activation", "halt_reason": "write-failure", "reason": "<that message, one line>", "skill_package": null}
   SKF_JSON
   ```

   With no emitter path (an incomplete install), each halt displays its message alone and step 6 §3 writes no result contract.

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
   | `--description "<string>"` | Override the LLM-derived description in step 4 §2 (used in SKILL.md frontmatter and metadata.json). Subject to the same agentskills.io length (1–1024 chars) and voice (third-person) checks as extracted descriptions. Single-target runs only: batch mode refuses it. |
   | `--exports "<name1,name2,...>"` | Override the extracted export list. Parse as comma-separated; trim whitespace per item; skip empty items. Used in step 4 §2 Key Exports and the count-derived metadata stats. Single-target runs only: batch mode refuses it. |
   | `--skip-snippet` | Skip context-snippet.md generation in step 4 §3 and its write in step 5 §2. Artifact omitted from `outputs`; step 5 §5 advisory snippet validation reports a "skipped" entry. |
   | `--no-active-pointer` | Skip the active-pointer flip in step 6 §1. Deliverables still land in `{skill_package}` but `{skill_group}/active` is not updated. Useful for batch automators that flip pointers in a separate stage. |
   | `--batch <file>` | Run the workflow against a list of targets from a text file rather than a single argument. Implies `--headless` (gates cannot be human-driven across N targets). See `references/batch-mode.md` for input format and summary contract. `--skip-snippet` and `--no-active-pointer` apply to every target in the batch; `--description` and `--exports` do not combine with it (batch mode halts with exit code 2). |
   | `--fail-fast` | Only meaningful with `--batch`. Abort the whole batch on the first per-target failure instead of recording the failure in the summary and proceeding to the next target. |

5. **If `--batch` is set**, load and read `references/batch-mode.md` in full before anything else and follow it: it refuses `--description` and `--exports`, starts the batch from the file, runs steps 1 to 6 for each target, and runs step 7 once, after the batch summary.

6. Load, read the full file, and then execute `references/resolve-target.md` to begin the workflow; when `{headless_mode}` is true, print step 1's `start` event first (`references/halt-contract.md`). In batch mode, `references/batch-mode.md` loads it for each target instead.
