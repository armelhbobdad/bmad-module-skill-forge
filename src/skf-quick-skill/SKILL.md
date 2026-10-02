---
name: skf-quick-skill
description: Fast skill from a package name or GitHub URL — no brief needed. Use when the user requests a "quick skill" or "skill from URL" or "skill from package."
---

# Quick Skill

## Overview

The fastest path to a skill — accept a GitHub URL or package name, resolve to source, extract the public API surface, and produce a best-effort SKILL.md with context snippet and metadata. No brief needed. Output is always community-tier quality, regardless of which tools are available.

## Conventions

- Bare paths (e.g. `references/<name>.md`) resolve from the skill root, `{skill-root}`: this skill's installed directory, where `customize.toml` lives.
- `{project-root}`-prefixed paths resolve from the project working directory.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; e.g. `shared/health-check.md`, which the terminal step chains to.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.

## Role

You are a rapid skill compiler collaborating with a developer. You bring source analysis and skill document assembly expertise, while the user brings the target package or repository. Work together efficiently — speed is the priority.

## Workflow Rules

These rules apply to every step in this workflow:

- Never fabricate content — all data must come from source extraction or user input
- Never write into a skill folder SKF did not generate
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- **Universal cancel-line affordance**: at any interactive prompt the user may type `cancel`, `exit`, `:q`, or select the `[X] Cancel and exit` menu option (where surfaced) to leave cleanly. HARD HALT with **exit code 6 (user-cancelled)**: stage `{"phase": "<the step's slug>", "halt_reason": "user-cancelled", "reason": "Cancelled. No files were written.", "skill_package": null}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"` (`references/halt-contract.md`). In step 4 §6 the equivalent affordance is `[Q] Quit without writing`, with the same exit code and envelope.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action, and record each auto-decision in the run folder the moment its gate decides, so the envelope's `headless_decisions` carries it: stage `{"gate": "<the gate's name>", "default_action": "<X>", "taken_action": "<X>", "reason": "headless: <why>"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`. Each gate names its gate and default where it decides.
- If `{headless_mode}` is true, print the one-line JSON progress events on stderr that `references/halt-contract.md` (Headless Events) defines: when each step starts, just before it chains on, and at a HARD HALT.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Resolve Target | references/resolve-target.md | Conditional (no target, or an ambiguous one) |
| 2 | Ecosystem Check | references/ecosystem-check.md | Conditional (an official skill matches) |
| 3 | Quick Extract | references/quick-extract.md | Conditional (an unusual repo shape, zero exports) |
| 4 | Compile | references/compile.md | No (review) |
| 5 | Write & Validate | references/write-and-validate.md | Conditional (the skill folder exists) |
| 6 | Finalize | references/finalize.md | Yes |
| 7 | Workflow Health Check | references/health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | target (GitHub URL, package name or npm, PyPI or crates.io page URL) [required for single-target mode], language_hint [optional, `--language-hint`], scope_hint [optional, `--scope-hint`] |
| **Overrides** | `--language-hint`, `--scope-hint`, `--description`, `--exports`, `--skip-snippet`, `--no-active-pointer`, `--batch <file>`, `--fail-fast`: see On Activation step 4 |
| **Gates** | step 1: target input, ambiguous package name [C/n/U/X] (if another registry also holds the name; headless keeps the first registry's pick), multi-language disambiguation [C/n/A] (pick any detected language); step 2: ecosystem match [P/I/A] (none until agentskills.io has a registry API); step 3: repo-shape [C/A] + zero-exports rescue [R/P/A]; step 4: review [C/E/S/Q]; step 5: overwrite [Y/N] |
| **Outputs** | SKILL.md, context-snippet.md, metadata.json, active pointer, result contract (timestamped + `-latest` copy), one `SKF_QUICK_SKILL_RESULT_JSON` line (stdout when the run finishes, stderr at a HARD HALT), and under `--batch` the batch summary. Snippet and active pointer can be skipped per overrides. |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true; each auto-decision is recorded in the envelope's `headless_decisions` |
| **Exit codes** | See `references/halt-contract.md`: the exit-code map and the envelope every HARD HALT emits, except On Activation step 1's check for `python3` and `uv`, which prints none |

## On Activation

1. Read `{project-root}/_bmad/skf/config.yaml` and resolve `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder` and `sidecar_path`.

   Then check the runtime: every helper this workflow runs, the envelope emitter included, runs through `uv run`, so confirm that `python3` and `uv` are both on `$PATH` (`command -v python3` and `command -v uv`). If either is missing, HARD HALT with **exit code 3 (resolution-failure)**: display "**Quick Skill needs `{the missing tool}`, which is not on your PATH.** Install it (`uv` from <https://docs.astral.sh/uv/getting-started/installation/>, `python3` from <https://www.python.org/downloads/>), then re-run." No envelope is printed: the emitter needs `uv` too.

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

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `{sidecar_path}/preferences.yaml` sets `headless_mode: true`. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-quick-skill.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case keep the reason as `{customization_resolver_unavailable}` (unset when the resolver ran) and, when `{emitEnvelopeHelper}` has a path, record it in the run sink: write `customization_resolver_unavailable: {customization_resolver_unavailable}` to `{run_dir}/resolver-warning.txt` with a file write, never `echo` (the reason can hold quotes or `$( )`), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"`. Under `--batch`, `references/batch-mode.md` §2 records that file in each target's run folder.

   Bind these three as workflow-context variables, taking the default when the merged value is empty or absent:

   - `{skillTemplatePath}` ← `workflow.skill_template_path`, else `assets/skill-template.md`
   - `{batchOutputPath}` ← `workflow.batch_output_path`, else `{skills_output_folder}/_batch/`
   - `{onCompleteCommand}` ← `workflow.on_complete`, else empty (step 6 §3 then runs no hook)

   Run each `workflow.activation_steps_prepend` entry now, in order. Hold every `workflow.persistent_facts` entry as standing context for the whole run; a `file:` entry loads the contents of the paths or globs it names: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off. Once step 4 has parsed the flags, before step 5 or 6 starts the run, run each `workflow.activation_steps_append` entry in order.

4. **Parse CLI overrides** into the workflow context as `{overrides}`:

   | Flag | Effect |
   | --- | --- |
   | `--language-hint <lang>` | Sets `language_hint`: step 1 §4 takes it as the language, with no detection and no multi-language gate, and step 1 §3 asks only that language's registry. |
   | `--scope-hint <path>` | Sets `scope_hint`: the folder step 3 reads the entry points and skill folders from. |
   | `--description "<string>"` | Replaces the extracted description in step 4 §2, which checks its length and voice as it checks an extracted one. |
   | `--exports "<name1,name2,...>"` | Replaces the extracted export list in step 4 §2: comma-separated, each name trimmed, empty items skipped. |
   | `--skip-snippet` | No context-snippet.md: step 4 §3 and step 5 §2 skip it. |
   | `--no-active-pointer` | Step 6 §1 leaves `{skill_group}/active` as it is. |
   | `--batch <file>` | Compiles every target the file lists, headless (On Activation step 5); `--skip-snippet` and `--no-active-pointer` apply to every target in the batch. |
   | `--fail-fast` | With `--batch`: the batch stops at the first failed target. |

   `--language-hint`, `--scope-hint`, `--description` and `--exports` are single-target flags: batch mode refuses them.

5. **If `--batch` is set**, load and read `references/batch-mode.md` in full before anything else and follow it.

6. Load, read the full file, and then execute `references/resolve-target.md` to begin the workflow; when `{headless_mode}` is true, print step 1's `start` event first (`references/halt-contract.md`). In batch mode, `references/batch-mode.md` loads it for each target instead.
