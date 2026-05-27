---
name: skf-campaign
description: Campaign orchestration — multi-library skill production with dependency tracking, file-based state, and resume. Use when the user asks to "run a campaign" or "orchestrate skills."
---

# Campaign

## Overview

Orchestrates the production of 15+ skills across multiple sessions by driving them through the full SKF pipeline (brief, generate, compile, test, export) in dependency order. Campaign sits at the top of the pipeline ladder — it does not produce skill artifacts directly but sequences the workflows that do. File-based state (`_campaign-state.yaml`) survives context death, enabling resume from any point.

## Conventions

- Bare paths (e.g. `references/step-01-setup.md`) resolve from the skill root.
- `references/` holds step files chained by stage number; `scripts/` and `assets/` hold deterministic helpers and templates.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives, if present).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a campaign orchestrator operating in Ferris's Management mode. You sequence workflows, track per-skill state, enforce quality gates, and ensure every skill reaches its target tier — while the individual pipeline workflows handle the actual artifact production.

## Workflow Rules

These rules apply to every step in this workflow:

- State-first — write state to disk before chaining to the next step or workflow
- Read-backup-modify-write for all state mutations (see State Contract below)
- Validate `_campaign-state.yaml` against `assets/campaign-state-schema.json` on every load
- Zero memory dependency (NFR-2) — campaign state is 100% recoverable from disk; never rely on conversation context for progress tracking
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 0 | Setup | references/step-01-setup.md | Yes |
| 1 | Strategy | references/step-02-strategy.md | Yes |
| 2 | Pin Validation | references/step-03-pins.md | Yes |
| 3 | Provenance | references/step-04-provenance.md | Yes |
| 4 | Skill Loop | references/step-05-skill-loop.md | Yes |
| 5 | Tier B Batch | references/step-06-batch.md | Yes |
| 6 | Capstone | references/step-07-capstone.md | Yes |
| 7 | Verification | references/step-08-verify.md | Yes |
| 8 | Refinement | references/step-09-refine.md | Yes |
| 9 | Export | references/step-10-export.md | No (write-gate HALT) |
| 10 | Maintenance | references/step-11-maintenance.md | Yes |

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `campaign` to start a new campaign; `campaign resume [--from=<skill>]` to resume from last active or specified skill |
| **Gates** | Step 9 (Export): write-gate HALT — requires explicit user approval before writing exported skills to disk |
| **Outputs** | `_campaign-state.yaml` (state), `campaign-brief.yaml` (machine-generated brief), `campaign-report.md` (post-campaign summary), `SKF_CAMPAIGN_RESULT_JSON` (headless envelope) |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |
| **Exit codes** | 0 = success, 1 = error |

## Mode Routing

On invocation:

1. **`campaign resume [--from=<skill>]`** — load `references/step-resume.md`. Validates state integrity, checks backup consistency, and chains to the appropriate stage step file. If `--from=<skill>` is provided, override the resume point to the named skill.
2. **`campaign`** (new) — run from stage 0 (Setup). If `_campaign-state.yaml` already exists, offer the user a choice: resume via `references/step-resume.md` or overwrite with a new campaign.
3. **`campaign`** (without args, state exists) — detect existing `_campaign-state.yaml` and prompt: resume via `references/step-resume.md` or overwrite.

## Resume Detection

When resuming:

1. Read `_campaign-state.yaml`
2. Validate integrity against `assets/campaign-state-schema.json` (halt on invalid)
3. Find last active or completed stage from `campaign.current_stage`
4. Skip completed skills (status = `completed` or `skipped`)
5. If `--from=<skill>` is provided, find the named skill and resume from its stage
6. Continue from the next incomplete skill in `dependency_graph.execution_order`

## State Contract

All state mutations follow the read-backup-modify-write pattern:

1. **Read** `_campaign-state.yaml`
2. **Validate** against `assets/campaign-state-schema.json` (halt on invalid)
3. **Backup** — copy current `_campaign-state.yaml` to `_campaign-state.yaml.bak`
4. **Modify** in memory
5. **Update** `campaign.last_updated` to current ISO-8601 timestamp
6. **Write** modified state back to `_campaign-state.yaml`

The `.bak` file is one-deep (overwritten on every write). If the primary file is corrupted (crash during write), the `.bak` file contains the last valid state.

## Campaign Headless Envelope

When `{headless_mode}` is true, the final step emits a single-line JSON envelope on stdout:

```
SKF_CAMPAIGN_RESULT_JSON: {"status":"success|error","skills_completed":0,"skills_failed":0,"quality_scores":{},"campaign_report_path":"","duration":""}
```

`status` is `"success"` when the campaign completes normally, `"error"` on any unrecoverable halt. `skills_completed` and `skills_failed` count per-skill outcomes. `quality_scores` maps skill names to their test-skill scores. `campaign_report_path` points to the generated `campaign-report.md`. `duration` is the wall-clock time of the campaign run.
