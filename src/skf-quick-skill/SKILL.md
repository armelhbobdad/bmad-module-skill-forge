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
| **Inputs** | target (GitHub URL or package name) [required], language_hint [optional], scope_hint [optional] |
| **Gates** | step-01: Input Gate [use args]; step-02: Choice Gate [P] (if match); step-04: Review Gate [C/E/S/Q] |
| **Outputs** | SKILL.md, context-snippet.md, metadata.json, active pointer, result contract (timestamped + `-latest` copy) |
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

3. Load, read the full file, and then execute `./steps-c/step-01-resolve-target.md` to begin the workflow.
