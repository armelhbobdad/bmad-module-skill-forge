---
name: skf-quick-skill
description: Fast skill from a package name or GitHub URL — no brief needed. Use when the user requests a "quick skill" or "skill from URL" or "skill from package."
---

# Quick Skill

## Overview

The fastest path to a skill — accept a GitHub URL or package name, resolve to source, extract the public API surface, and produce a best-effort SKILL.md with context snippet and metadata. No brief needed. Quick Skill is tier-unaware by design — all output is produced at community-tier quality regardless of available tools.

## Role

You are a rapid skill compiler collaborating with a developer. You bring source analysis and skill document assembly expertise, while the user brings the target package or repository. Work together efficiently — speed is the priority.

## Workflow Rules

These rules apply to every step in this workflow:

- Never fabricate content — all data must come from source extraction or user input
- Read each step file completely before taking any action
- Follow the mandatory sequence in each step exactly — do not skip, reorder, or optimize
- Only load one step file at a time — never preload future steps
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision
- If `{headless_mode}` is true, emit a single-line JSON progress event to **stderr** at each step's entry and exit so pipeline schedulers can stream live progress instead of post-mortem-parsing the result contract:
  - entry: `{"step":N,"name":"<slug>","status":"start"}`
  - exit (just before chaining to nextStepFile): `{"step":N,"name":"<slug>","status":"done"}`
  - on HARD HALT: `{"step":N,"name":"<slug>","status":"halt","exit":<code>}` instead of "done"

  `N` is the step number (1–7) and `<slug>` is the kebab portion of the filename after the number — `resolve-target`, `ecosystem-check`, `quick-extract`, `compile`, `write-and-validate`, `finalize`, `health-check`. One line per event; do not pretty-print.

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 1 | Resolve Target | steps-c/step-01-resolve-target.md | Yes |
| 2 | Ecosystem Check | steps-c/step-02-ecosystem-check.md | Yes |
| 3 | Quick Extract | steps-c/step-03-quick-extract.md | Yes |
| 4 | Compile | steps-c/step-04-compile.md | No (review) |
| 5 | Write & Validate | steps-c/step-05-write-and-validate.md | Yes |
| 6 | Finalize | steps-c/step-06-finalize.md | Yes |
| 7 | Workflow Health Check | steps-c/step-07-health-check.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | target (GitHub URL or package name) [required for single-target mode], language_hint [optional], scope_hint [optional] |
| **Overrides** | `--description`, `--exports`, `--skip-snippet`, `--no-active-pointer`, `--batch <file>`, `--fail-fast` — see On Activation step 3 |
| **Gates** | step-01: Input Gate [use args]; step-02: Choice Gate [P] (if match); step-04: Review Gate [C/E/S/Q] |
| **Outputs** | SKILL.md, context-snippet.md, metadata.json, active pointer, result contract (timestamped + `-latest` copy). Snippet and active pointer can be skipped per overrides. |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT in this workflow exits with a stable, documented code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning                | Raised by                                                   |
| ---- | ---------------------- | ----------------------------------------------------------- |
| 0    | success                | step-07 (terminal)                                          |
| 3    | resolution-failure     | step-01 §2c (prose input), step-01 §3 (registry chain failed) |
| 4    | write-failure          | step-05 §2 (deliverable write failed)                       |
| 5    | overwrite-cancelled    | step-05 §1 (user selected [N])                              |
| 6    | compile-cancelled      | step-04 §6 (user selected [Q])                              |
| 7    | finalize-blocked       | step-06 §1 (active-pointer flip refused — non-link in place) |

Reserved: `validator-missing` may be promoted from advisory log to fatal exit code in a future revision; consumers should not assume code 8+ is unused.

## Result Contract on HARD HALT

In addition to the success-variant result contract written by step-06 §3, every HARD HALT must surface an **error variant** so headless automators don't silently break when `quick-skill-result-latest.json` is missing on failed runs.

**Always (every HARD HALT, regardless of phase)** — emit a single line on **stderr**:

```
SKF_QUICK_SKILL_RESULT_JSON: {"status":"error","exit_code":<N>,"phase":"<slug>","error":{"code":"<class>","message":"<short>"},"outputs":{},"summary":{},"skill_package":"<path-or-null>"}
```

One line, no pretty-print. Matches the prefix-and-envelope convention used by `skf-emit-result-envelope.py`.

**Additionally, when `{skill_package}` is known** (HALT at step-05 §1 onward) — write the same JSON object (without the `SKF_QUICK_SKILL_RESULT_JSON: ` prefix) to disk:

```
{skill_package}/quick-skill-result-{YYYYMMDD-HHmmss}.json
{skill_package}/quick-skill-result-latest.json   (copy, not symlink)
```

so consumers that hardcode the `-latest.json` path see a deterministic file even on failed runs. HALTs at step-01/02/03/04 cannot write to disk because `{skill_package}` is computed only in step-05 §1; for those, the stderr envelope plus exit code is the contract.

**Schema:**

| Field           | Type           | Notes                                                                                                       |
| --------------- | -------------- | ----------------------------------------------------------------------------------------------------------- |
| `status`        | string         | always `"error"` for HARD HALTs                                                                             |
| `exit_code`     | integer        | matches the Exit Codes table                                                                                |
| `phase`         | string         | step slug where the HALT occurred (e.g. `resolve-target`, `compile`)                                        |
| `error.code`    | string         | one of: `resolution-failure`, `write-failure`, `overwrite-cancelled`, `compile-cancelled`, `finalize-blocked` |
| `error.message` | string         | the user-facing message that was displayed                                                                  |
| `error.details` | any            | optional — phase-specific context (e.g. the failed file path)                                               |
| `outputs`       | object         | empty `{}` on early HALTs; partial when files were already written                                          |
| `summary`       | object         | empty `{}` on early HALTs                                                                                   |
| `skill_package` | string \| null | absolute path when known, `null` when HALT preceded step-05 §1                                              |

## On Activation

1. Read `{project-root}/_bmad/skf/config.yaml` and `{forger_root}/preferences.yaml` in parallel (one batched tool-call message — they are independent files), then resolve:
   - From config: `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`
   - From preferences: `headless_mode` (default false)

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `preferences.yaml`. Default: false.

3. **Parse CLI overrides** — capture optional override flags into the workflow context as `{overrides}`. Each override is opt-in; when omitted, the workflow runs as today.

   | Flag | Effect |
   | --- | --- |
   | `--description "<string>"` | Override the LLM-derived description in step-04 §2 (used in SKILL.md frontmatter and metadata.json). Subject to the same agentskills.io length (1–1024 chars) and voice (third-person) checks as extracted descriptions. |
   | `--exports "<name1,name2,...>"` | Override the extracted export list. Parse as comma-separated; trim whitespace per item; skip empty items. Used in step-04 §2 Key Exports and the count-derived metadata stats. |
   | `--skip-snippet` | Skip context-snippet.md generation in step-04 §3 and its write in step-05 §2. Artifact omitted from `outputs`; step-05 §5 advisory snippet validation reports a "skipped" entry. |
   | `--no-active-pointer` | Skip the active-pointer flip in step-06 §1. Deliverables still land in `{skill_package}` but `{skill_group}/active` is not updated. Useful for batch automators that flip pointers in a separate stage. |
   | `--batch <file>` | Run the workflow against a list of targets from a text file rather than a single argument. Implies `--headless` (gates cannot be human-driven across N targets). See "Batch Mode" below for input format and summary contract. Single-target overrides above apply globally to every target in the batch. |
   | `--fail-fast` | Only meaningful with `--batch`. Abort the whole batch on the first per-target failure instead of recording the failure in the summary and proceeding to the next target. |

4. **If `--batch` is set**, force `{headless_mode} = true` (log "headless: coerced by --batch" if it was false), read the batch file, and parse the target list per "Batch Mode" below. Continue at step 5; the batch loop documented in "Batch Mode" wraps the step-01 → step-07 pipeline that follows.

5. Load, read the full file, and then execute `./steps-c/step-01-resolve-target.md` to begin the workflow. (In batch mode, control returns here for each subsequent target after step-07 completes; see "Batch Mode" below.)

## Batch Mode

When `--batch <file>` is supplied, quick-skill processes a list of targets from a text file in sequence rather than a single target from arguments. Designed for unattended bulk runs (CI pipelines, mass-rebuilds, the skf-batch-skills meta-workflow when it lands).

### Input format

One target per line. Empty lines and lines starting with `#` (after optional leading whitespace) are ignored. Each non-empty line has the same shape as the single-target `target` argument, with optional space-separated per-line modifiers:

```
# A batch input file.
lodash
@vercel/og
cognee@0.5.0
https://github.com/foo/bar
https://github.com/foo/bar@2.1.0-beta

# Per-line modifiers — overrides for THIS target only:
lodash language=javascript scope=src/
cognee@0.5.0 language=python scope=cognee/api/
```

Recognised per-line modifiers:

| Modifier | Effect (this target only) |
| --- | --- |
| `language=<lang>` | Sets `language_hint` for this target — same effect as the optional `language_hint` input on a single-target run. |
| `scope=<path>` | Sets `scope_hint` for this target — same effect as the optional `scope_hint` input on a single-target run. |

Per-line modifiers shadow the global `--description` / `--exports` / `--skip-snippet` / `--no-active-pointer` overrides only when those override fields are not set. Global overrides apply to every target unless a future modifier extends per-line override syntax.

### Execution

`--batch` implies `--headless`. The batch loop runs the full quick-skill pipeline (steps 1–7) for each target in file order:

1. Set `target`, `target_version`, `language_hint`, `scope_hint` from the batch line into the workflow context.
2. Execute steps 1–7 per the normal pipeline.
3. After step-07 completes (success or HARD HALT), record the per-target outcome (target, status, exit_code, skill_package, error.code) into the batch result list.
4. If `--fail-fast` is set and the target failed, exit the batch loop immediately. Otherwise continue with the next target.

Per-target output lands in `{skill_package}/` as today, with the per-target result contract at `{skill_package}/quick-skill-result-latest.json` (success or error variant per "Result Contract on HARD HALT" above).

### Batch summary contract

After the last target completes (or `--fail-fast` triggers an early exit), write the batch summary at:

```
{skills_output_folder}/_batch/quick-skill-batch-{YYYYMMDD-HHmmss}.json
{skills_output_folder}/_batch/quick-skill-batch-latest.json   (copy, not symlink)
```

Schema:

```json
{
  "skill": "skf-quick-skill",
  "mode": "batch",
  "status": "success | partial | failed",
  "timestamp": "<ISO 8601 UTC>",
  "input_file": "<path passed to --batch>",
  "targets_total": 0,
  "succeeded": 0,
  "failed": 0,
  "fail_fast_triggered": false,
  "results": [
    {
      "target": "<line from batch file>",
      "status": "success | error",
      "exit_code": 0,
      "skill_package": "<absolute path or null>",
      "error_code": null
    }
  ]
}
```

`status` resolves as: `"success"` when `failed == 0`; `"partial"` when `failed > 0 && succeeded > 0`; `"failed"` when `succeeded == 0`. `fail_fast_triggered` is `true` only when `--fail-fast` aborted the loop early — `targets_total` then reflects the count actually attempted, not the file's line count.

### Headless events

Batch mode emits per-target boundary events on stderr in addition to the per-step events documented in Workflow Rules:

```
{"batch":<n>,"target":"<target>","status":"start"}
{"batch":<n>,"target":"<target>","status":"done","exit":<code>}
{"batch":<n>,"target":"<target>","status":"fail","exit":<code>,"error_code":"<class>"}
```

`<n>` is the 1-based index of the target in the parsed list. After the loop ends, emit one final batch-summary event:

```
{"batch_summary":true,"targets_total":N,"succeeded":K,"failed":M,"status":"<...>","fail_fast_triggered":<bool>}
```

### Exit code

The batch process exits with code `0` when `failed == 0`, otherwise with the exit code of the first failed target (so automators that already branch on the single-target exit-code map continue to work without batch-specific handling). When `--fail-fast` triggers, the exit code is the failing target's code.
