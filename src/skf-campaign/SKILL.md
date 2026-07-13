---
name: skf-campaign
description: Campaign orchestration — multi-library skill production with dependency tracking, file-based state, and resume. Use when the user asks to "run a campaign" or "orchestrate skills."
---

# Campaign

## Overview

Orchestrates the production of 15+ skills across multiple sessions by driving them through the full SKF pipeline (brief, generate, compile, test, export) in dependency order. Campaign sits atop the pipeline ladder: it sequences the workflows that produce skills rather than producing artifacts itself. File-based state (`_campaign-state.yaml`) survives context death, enabling resume from any point.

## Conventions

- Bare paths (e.g. `references/step-01-setup.md`) resolve from the skill root.
- `references/` holds the stage-chained step files plus reference specs (e.g. the `_campaign-directive.md` contract at `references/campaign-directive-spec.md`); `templates/`, `scripts/`, and `assets/` hold templates, deterministic helpers, and the state schema.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## Role

You are a campaign orchestrator operating in Ferris's Management mode. You sequence workflows, track per-skill state, enforce quality gates, and ensure every skill reaches its target tier — while the individual pipeline workflows handle the actual artifact production.

## On Activation

Run these steps once, in order, before dispatching to Mode Routing.

1. **Load config.** Read `{project-root}/_bmad/skf/config.yaml` and `{sidecar_path}/preferences.yaml` in one batched message (independent files). From config resolve `project_name`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`. From preferences resolve `headless_mode` (default false). If the config file is missing, fall back to `forge_data_folder = forge-data`.

2. **Resolve `{headless_mode}`** — true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `preferences.yaml`. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow
   ```

   The script merges three layers (scalars override, arrays append):

   - `{skill-root}/customize.toml` — bundled defaults
   - `_bmad/custom/<skill-name>.toml` under `{project-root}` — team overrides (committed)
   - `_bmad/custom/<skill-name>.user.toml` under `{project-root}` — personal overrides (gitignored)

   If it fails or is missing, fall back to `{skill-root}/customize.toml` directly. Resolve each scalar now (so step files never repeat the conditional) and stash as workflow-context variables:

   - `{campaignWorkspacePath}` ← `workflow.campaign_workspace_path` if non-empty, else `{forge_data_folder}/_campaign`
   - `{qualityGateHard}` / `{qualityGateSoftTarget}` / `{qualityGateSoftFallback}` ← the `quality_gate_*` scalars (defaults `zero-critical-high` / `90` / `80`)
   - `{reportTemplatePath}` ← `workflow.report_template_path` if non-empty, else `templates/campaign-report-template.md`
   - `{kickoffTemplatePath}` ← `workflow.kickoff_template_path` if non-empty, else `templates/kickoff-template.md`
   - `{briefTemplatePath}` ← `workflow.brief_template_path` if non-empty, else `templates/campaign-brief-template.yaml`
   - `{onComplete}` ← `workflow.on_complete` (empty = no-op)

   Load `workflow.persistent_facts` (literal sentences and `file:` references, globs expanded) and keep them in mind for the whole campaign — they are injected into every per-skill kickoff. Run any `activation_steps_prepend` before step 1 and any `activation_steps_append` after this step.

4. **Parse CLI overrides** into the workflow context:

   | Flag | Effect |
   | --- | --- |
   | `--headless` / `-H` | Force `{headless_mode} = true` (see step 2). |
   | `--brief <file>` | Seed step-01 targets from a `campaign-brief.yaml` instead of interactive prompts. Implies `--headless`. |
   | `--manifest <file>` | Seed step-01 targets from a plain-text `name,repo_url,tier,pin` manifest. Implies `--headless`. |
   | `--from <skill>` | Resume override — see Mode Routing. |

   If `--brief` or `--manifest` is set, force `{headless_mode} = true` (log "headless: coerced by --brief/--manifest" if it was false).

   **`--manifest` format:** one `name,repo_url,tier,pin` target per line (empty `pin` = latest); a trailing `;dep1,dep2` segment sets `depends_on`; blank and `#` lines are skipped. A malformed line HALTs step-01 with the offending line numbers — never a partial target set.

5. **Dispatch** per Mode Routing below.

## Workflow Rules

These rules apply to every step in this workflow:

- State-first — write state to disk before chaining to the next step or workflow
- Read-backup-modify-write for all state mutations (State Contract in `references/campaign-contracts.md`)
- Validate `_campaign-state.yaml` on every load by running `uv run scripts/campaign-validate-state.py --state-file {stateFile}` and HALT (exit code 3, `invalid-state`) on non-zero — never hand-validate the schema
- Zero memory dependency — campaign state is 100% recoverable from disk; never rely on conversation context for progress tracking
- Treat a missing or unparseable `SKF_*_RESULT_JSON` envelope from any sub-skill as a sub-skill failure; never write partial state from an unparsed envelope
- Append a one-line entry to the campaign decision log (`{campaignWorkspacePath}/_campaign-decision-log.md`, append-only) at every operator or auto-decision (skip/force, overwrite, export cancel/proceed, `.bak` recovery, user-cancel) so rationale survives compaction and resume
- **Universal cancel affordance** — at any interactive gate between Setup and the Export gate, `cancel`/`exit`/`:q` triggers a HARD HALT with **exit code 12 (`user-cancelled`)**: log it and leave state intact and resumable. Exception: the Export gate's own `[C]ancel` stays exit code 11 (`export-cancelled`) — never also emit 12 there, so an automator's exit-code branch stays deterministic. These keywords count only as a response *to a prompt*; a skill or campaign named `cancel`/`exit` supplied as data is never treated as a cancel.
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision
- If `{headless_mode}` is true, emit a single-line JSON progress event to **stderr** at each step's entry, exit, and HARD HALT so schedulers stream live progress — event format in `references/campaign-contracts.md` (Headless Progress Events)

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

**Stage numbering:** step files are 1-indexed (`step-01` … `step-11`); `campaign.current_stage` in state is 0-indexed, so step-`NN` runs stage `NN − 1` (step-01 = stage 0, step-11 = stage 10). `references/step-resume.md` §3–§4 own how a resolved stage maps back to its step file on resume (including the `current_stage + 1` advance when no skill is active).

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `campaign` to start a new campaign; `campaign resume [--from=<skill>]` to resume from last active or specified skill; `campaign status` for a read-only progress summary |
| **Outputs** | `_campaign-state.yaml` (state), `campaign-brief.yaml` (machine-generated brief), `campaign-report.md` (post-campaign summary), `_campaign-decision-log.md` (append-only rationale), `SKF_CAMPAIGN_RESULT_JSON` (headless envelope) — all under `{campaignWorkspacePath}` |

## Contracts

Exit codes, the HARD-HALT error envelope, the read-backup-modify-write **State Contract**, the headless success envelope, and per-step progress events live in `references/campaign-contracts.md` — consult it when you HALT, mutate state, or emit headless output.

## Mode Routing

On invocation:

1. **`campaign resume [--from=<skill>]`** — load `references/step-resume.md` (validates state, recovers from backup, chains to the right stage). `--from=<skill>` overrides the resume point to the named skill.
2. **`campaign`** (new, no existing state) — run from stage 0 (Setup).
3. **`campaign`** (state exists) — detect existing `{campaignWorkspacePath}/_campaign-state.yaml` and prompt **resume** (via `references/step-resume.md`) or **overwrite**. On overwrite, first archive the existing `_campaign-state.yaml` and `campaign-brief.yaml` to `{campaignWorkspacePath}/archive/{name}-{timestamp}/` and log it before chaining to step-01. In headless mode, default to **resume** (never silently clobber); archive-and-overwrite only when `--brief`/`--manifest` explicitly seeds a new campaign.
4. **`campaign status`** (read-only) — load `{campaignWorkspacePath}/_campaign-state.yaml`, validate it via `campaign-validate-state.py`, then run `uv run scripts/campaign-status.py --state-file {campaignWorkspacePath}/_campaign-state.yaml` and display its summary (campaign name, current stage, completed-vs-total, per-status counts) followed by the last ~15 lines of `{campaignWorkspacePath}/_campaign-decision-log.md` for the recent decision trail, then stop. No backup, no mutation, no chaining. Exit 0 (or 9 if the state is unrecoverable).
