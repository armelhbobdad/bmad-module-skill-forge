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

## On Activation

1. Read `{project-root}/_bmad/skf/config.yaml` and `{forger_root}/preferences.yaml` in parallel (one batched tool-call message — they are independent files), then resolve:
   - From config: `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`
   - From preferences: `headless_mode` (default false)

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `preferences.yaml`. Default: false.

3. Load, read the full file, and then execute `./steps-c/step-01-resolve-target.md` to begin the workflow.
