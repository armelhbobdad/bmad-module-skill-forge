---
name: skf-campaign
description: Campaign orchestration — multi-library skill production with dependency tracking, file-based state, and resume. Use when the user asks to "run a campaign" or "orchestrate skills."
---

# Campaign

## Overview

Orchestrates the production of 15+ skills across multiple sessions by driving them through the full SKF pipeline (brief, generate, compile, test, export) in dependency order. File-based state (`_campaign-state.yaml`) survives context death, enabling resume from any point.

## Conventions

- Bare paths (e.g. `references/step-01-setup.md`) resolve from the skill root.
- `references/` holds the stage-chained step files plus reference specs (e.g. the `_campaign-directive.md` contract at `references/campaign-directive-spec.md`); `templates/`, `scripts/`, and `assets/` hold templates, deterministic helpers, and the state schema.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root; e.g. `shared/health-check.md` and the envelope schemas under `shared/scripts/schemas/`.
- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves from the SKF module root, and that skill must be installed with this one.

## Role

You are a campaign orchestrator operating in Ferris's Management mode. You sequence workflows, track per-skill state, enforce quality gates, and ensure every skill reaches its target tier, while the individual pipeline workflows handle the actual artifact production.

## On Activation

Run these steps once, in order, before dispatching to Mode Routing.

1. **Load config.** Read `{project-root}/_bmad/skf/config.yaml` and `{sidecar_path}/preferences.yaml` in one batched message (independent files). From config resolve `project_name`, `user_name`, `communication_language`, `document_output_language`, `skills_output_folder`, `forge_data_folder`, `sidecar_path`. If the config file is missing, fall back to `forge_data_folder = forge-data`.

2. **Resolve `{headless_mode}`**: true if `--headless` or `-H` was passed as an argument, or if `headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false.

3. **Resolve workflow customization.** Run:

   ```bash
   uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow
   ```

   It merges the bundled `{skill-root}/customize.toml` with `{project-root}/_bmad/custom/skf-campaign.toml` (team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, prints no JSON or is missing, print one line, `[activation/warn] customization_resolver_unavailable: <reason>` (`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it printed none). If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: the `{project-root}/_bmad/custom/` overrides do not apply to this run. In that case, unless the invocation is `campaign status` (which writes nothing), log `customization_resolver_unavailable: <reason>` as an `event` in the decision log once `{campaignWorkspacePath}` is bound below (`references/campaign-contracts.md`, Decision Log).

   Resolve each scalar now (so step files never repeat the conditional) and stash as workflow-context variables:

   - `{campaignWorkspacePath}` ← `workflow.campaign_workspace_path` if non-empty, else `{forge_data_folder}/_campaign`
   - `{qualityGateHard}` / `{qualityGateSoftTarget}` / `{qualityGateSoftFallback}` ← the `quality_gate_*` scalars (defaults `zero-critical-high` / `90` / `80`): the base gate, which step-01 §2 and `scripts/campaign-quality-gate.py` adjust with the brief and the directive
   - `{reportTemplatePath}` ← `workflow.report_template_path` if non-empty, else `templates/campaign-report-template.md`
   - `{kickoffTemplatePath}` ← `workflow.kickoff_template_path` if non-empty, else `templates/kickoff-template.md`
   - `{briefTemplatePath}` ← `workflow.brief_template_path` if non-empty, else `templates/campaign-brief-template.yaml`
   - `{onComplete}` ← `workflow.on_complete` (empty = no-op)
   - `{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` (the first that exists)

   Load `workflow.persistent_facts` (literal sentences and `file:` references, globs expanded: the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed `!` drops each earlier entry it names and loads nothing itself, so an override's `"!file:{project-root}/**/project-context.md"` turns that default off) and keep them in mind for the whole campaign: they are injected into every per-skill kickoff, whose loader drops a `!` entry the same way. Run any `activation_steps_prepend` now, right after the resolve: the config and preferences of steps 1 and 2 are already loaded, so a prepend step can read them but cannot run before them. `activation_steps_append` runs at step 5, once the CLI overrides are parsed.

4. **Parse CLI overrides** into the workflow context:

   | Flag | Effect |
   | --- | --- |
   | `--headless` / `-H` | Force `{headless_mode} = true` (see step 2). |
   | `--brief <file>` | Seed step-01 targets from a `campaign-brief.yaml` instead of interactive prompts. Implies `--headless`. |
   | `--manifest <file>` | Seed step-01 targets from a plain-text `name,repo_url,tier,pin` manifest. Implies `--headless`. |
   | `--from <skill>` | Resume override — see Mode Routing. |

   If `--brief` or `--manifest` is set, force `{headless_mode} = true` (log "headless: coerced by --brief/--manifest" if it was false). This is deliberate: a seeded run is an unattended run (CI), so it takes the default at every gate. To review the plan and the export, give the same file at the Setup question instead, which stays interactive. step-01 §1 documents the manifest format and validates every target.

5. Run any `activation_steps_append`, then **dispatch** per Mode Routing below.

## Workflow Rules

These rules apply to every step in this workflow:

- State-first: write state to disk before chaining to the next step or workflow
- Every state write goes through `scripts/campaign-state.py` (State Contract in `references/campaign-contracts.md`); never edit the state or its `.bak` by hand
- Validate `_campaign-state.yaml` on every load by running `uv run scripts/campaign-validate-state.py --state-file {stateFile}` and HALT (exit code 3, `invalid-state`) on non-zero; never hand-validate the schema
- Zero memory dependency: campaign state is 100% recoverable from disk; never rely on conversation context for progress tracking
- A sub-skill's result is what the step that runs it reads (an `SKF_*_RESULT_JSON` envelope or a verdict): a missing, unparseable or error result is a sub-skill failure, and never write partial state from an unparsed envelope
- Log every operator decision, headless default and event (skip/force, overwrite, export cancel/proceed, `.bak` recovery, user-cancel, a failed skill) as one typed entry in the append-only `{campaignWorkspacePath}/_campaign-decision-log.md` through `campaign-state.py log` (`references/campaign-contracts.md`), so rationale survives compaction and resume
- **Universal cancel affordance:** at any interactive gate between Setup and the Export gate, `cancel`/`exit`/`:q` triggers a HARD HALT with **exit code 12 (`user-cancelled`)**: log it and leave state intact and resumable. Exception: the Export gate's own `[C]ancel` stays exit code 11 (`export-cancelled`); never also emit 12 there, so an automator's exit-code branch stays deterministic.
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision
- If `{headless_mode}` is true, emit a single-line JSON progress event to **stderr** at each step's entry, exit, and HARD HALT, and at every HARD HALT the error envelope (`references/campaign-contracts.md`: Headless Progress Events, Result Contract on HARD HALT)

## Stages

| # | Step | File | Auto-proceed |
|---|------|------|--------------|
| 0 | Setup | references/step-01-setup.md | Yes |
| 1 | Strategy | references/step-02-strategy.md | No (plan confirmation; headless takes [P]) |
| 2 | Pin Validation | references/step-03-pins.md | Yes |
| 3 | Provenance | references/step-04-provenance.md | Yes |
| 4 | Skill Loop | references/step-05-skill-loop.md | Conditional (a blocked dependency) |
| 5 | Tier B Batch | references/step-06-batch.md | Yes |
| 6 | Capstone | references/step-07-capstone.md | Yes |
| 7 | Verification | references/step-08-verify.md | Yes |
| 8 | Refinement | references/step-09-refine.md | Yes |
| 9 | Export | references/step-10-export.md | No (write-gate HALT) |
| 10 | Maintenance | references/step-11-maintenance.md | Yes |

**Stage numbering:** `campaign.current_stage` is 0-indexed, so step-`NN` runs stage `NN - 1`; `campaign-state.py resume` maps a resumed campaign to its step file.

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `campaign` to start a new campaign; `campaign resume [--from=<skill>]` to resume from last active or specified skill; `campaign status` for a read-only progress summary |
| **Outputs** | `_campaign-state.yaml` (state), `campaign-brief.yaml` (machine-generated brief), `campaign-report.md` (post-campaign summary), `_campaign-decision-log.md` (append-only rationale), all under `{campaignWorkspacePath}`; `SKF_CAMPAIGN_RESULT_JSON` (headless envelope) |

## Contracts

Exit codes, the HARD-HALT error envelope, the **State Contract** (`scripts/campaign-state.py`), the decision log and per-step progress events live in `references/campaign-contracts.md`: consult it when you HALT, write state, or log. The envelope's one definition is `shared/scripts/schemas/skf-campaign-result-envelope.v1.json`; step-11 emits its success line.

## Mode Routing

On invocation:

1. **`campaign resume [--from=<skill>]`**: load `references/step-resume.md` (validates state, recovers from backup, chains to the stage `campaign-state.py resume` computes). `--from=<skill>` overrides the resume point to the named skill.
2. **`campaign`** (new, no existing state) to run from stage 0 (Setup).
3. **`campaign`** (state exists): when `{campaignWorkspacePath}/_campaign-state.yaml` or its `.bak` exists, prompt **resume** (via `references/step-resume.md`) or **overwrite**. On overwrite, first run `uv run scripts/campaign-state.py archive --state-file {campaignWorkspacePath}/_campaign-state.yaml --brief-file {campaignWorkspacePath}/campaign-brief.yaml`, which moves the state, its `.bak` and the brief into a new folder under `{campaignWorkspacePath}/archive/`, and log the `archive_dir` it returns (type `decision`) before chaining to step-01 (its `init` refuses to overwrite a state or backup). A `--brief` that named the workspace's `campaign-brief.yaml` is then read from `archive_dir`. **GATE [default: resume]**: in headless mode, default to **resume** (never silently clobber); archive-and-overwrite only when `--brief`/`--manifest` explicitly seeds a new campaign.
4. **`campaign status`** (read-only): load `{campaignWorkspacePath}/_campaign-state.yaml`, validate it via `campaign-validate-state.py`, then run `uv run scripts/campaign-status.py --state-file {campaignWorkspacePath}/_campaign-state.yaml` and display its summary (campaign name, current stage, completed-vs-total, per-status counts) followed by the last ~15 lines of `{campaignWorkspacePath}/_campaign-decision-log.md` for the recent decision trail, then stop. No backup, no mutation, no chaining. Exit 0 (or 9 if the state is unrecoverable).
