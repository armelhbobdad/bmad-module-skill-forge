---
name: skf-campaign
description: Campaign orchestration — multi-library skill production with dependency tracking, file-based state, and resume. Use when the user asks to "run a campaign" or "orchestrate skills."
---

# Campaign

## Overview

Orchestrates the production of 15+ skills across multiple sessions by driving them through the full SKF pipeline (brief, generate, compile, test, export) in dependency order. Campaign sits at the top of the pipeline ladder — it does not produce skill artifacts directly but sequences the workflows that do. File-based state (`_campaign-state.yaml`) survives context death, enabling resume from any point.

## Conventions

- Bare paths (e.g. `references/step-01-setup.md`) resolve from the skill root.
- `references/` holds step files chained by stage number, plus the directive contract at `references/campaign-directive-spec.md` (the canonical spec for `_campaign-directive.md`); `templates/` holds workflow-loaded templates; `scripts/` and `assets/` hold deterministic helpers and the state schema.
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

   The script merges three layers (scalars override, arrays append): `{skill-root}/customize.toml` (defaults), `{project-root}/_bmad/custom/skf-campaign.toml` (team), `{project-root}/_bmad/custom/skf-campaign.user.toml` (personal). If it fails or is missing, fall back to `{skill-root}/customize.toml` directly. Apply the fallback for each scalar now so step files never repeat the conditional, and stash as workflow-context variables:

   - `{campaignWorkspacePath}` ← `workflow.campaign_workspace_path` if non-empty, else `{forge_data_folder}/_campaign`
   - `{qualityGateHard}` / `{qualityGateSoftTarget}` / `{qualityGateSoftFallback}` ← the `quality_gate_*` scalars (defaults `zero-critical-high` / `90` / `80`)
   - `{reportTemplatePath}` ← `workflow.report_template_path` if non-empty, else `templates/campaign-report-template.md`
   - `{kickoffTemplatePath}` ← `workflow.kickoff_template_path` if non-empty, else `templates/kickoff-template.md`
   - `{briefTemplatePath}` ← `workflow.brief_template_path` if non-empty, else `templates/campaign-brief-template.yaml`
   - `{onComplete}` ← `workflow.on_complete` (empty = no-op)

   Load `workflow.persistent_facts` (literal sentences and `file:` references, globs expanded) and keep them in mind for the whole campaign — they are injected into every per-skill kickoff. Run any `activation_steps_prepend` before step 1 and any `activation_steps_append` after this step.

   Every step file resolves its frontmatter path vars (`stateFile`, `backupFile`, …) under `{campaignWorkspacePath}` — overriding `campaign_workspace_path` relocates the whole campaign workspace without editing a single step.

4. **Parse CLI overrides** into the workflow context:

   | Flag | Effect |
   | --- | --- |
   | `--headless` / `-H` | Force `{headless_mode} = true` (see step 2). |
   | `--brief <file>` | Seed step-01 targets from a `campaign-brief.yaml` instead of interactive prompts. Implies `--headless`. |
   | `--manifest <file>` | Seed step-01 targets from a plain-text `name,repo_url,tier,pin` manifest. Implies `--headless`. |
   | `--from <skill>` | Resume override — see Mode Routing. |

   If `--brief` or `--manifest` is set, force `{headless_mode} = true` (log "headless: coerced by --brief/--manifest" if it was false).

   **`--manifest` format:** one target per line, comma-separated `name,repo_url,tier,pin` (omit `pin` or leave it empty for latest); add a trailing `;dep1,dep2` segment for `depends_on`. Blank lines and `#` comments are skipped. If any line fails to parse, HALT in step-01 listing the offending line numbers rather than silently dropping targets — a partial target set is never run.

5. **Dispatch** per Mode Routing below.

## Workflow Rules

These rules apply to every step in this workflow:

- State-first — write state to disk before chaining to the next step or workflow
- Read-backup-modify-write for all state mutations (see State Contract below)
- Validate `_campaign-state.yaml` on every load by running `uv run scripts/campaign-validate-state.py --state-file {stateFile}` and HALT (exit code 3, `invalid-state`) on non-zero — never hand-validate the schema
- Zero memory dependency (NFR-2) — campaign state is 100% recoverable from disk; never rely on conversation context for progress tracking
- Treat a missing or unparseable `SKF_*_RESULT_JSON` envelope from any sub-skill as a sub-skill failure; never write partial state from an unparsed envelope
- Append a one-line entry to the campaign decision log (`{campaignWorkspacePath}/_campaign-decision-log.md`, append-only) at every operator decision or auto-decision (skip/force, architecture-doc skip, export cancel/proceed, campaign overwrite, `.bak` recovery, user-cancel) so rationale survives compaction and resume
- **Universal cancel affordance** — at any interactive gate the operator may type `cancel`, `exit`, or `:q` to leave cleanly. HARD HALT with **exit code 12 (`user-cancelled`)**, log the cancellation to the decision log, and leave state intact and resumable. This gives the operator a documented way out at every prompt between Setup and the Export gate. **The Export gate is the one exception:** it has its own `[C]ancel` with exit code 11 (`export-cancelled`), which remains canonical there — do not also emit 12 at the export gate, so an automator's exit-code branch stays deterministic. These keywords are recognized only as a response *to an interactive prompt*; a skill or campaign named `cancel`/`exit` supplied as data is never treated as a cancel.
- Always communicate in `{communication_language}`
- If `{headless_mode}` is true, auto-proceed through confirmation gates with their default action and log each auto-decision
- If `{headless_mode}` is true, emit a single-line JSON progress event to **stderr** at each step's entry and exit so schedulers stream live progress instead of post-mortem-parsing the final envelope:
  - entry: `{"stage":N,"name":"<slug>","status":"start"}`
  - exit (just before chaining): `{"stage":N,"name":"<slug>","status":"done"}`
  - on HARD HALT: `{"stage":N,"name":"<slug>","status":"halt","exit":<code>}` instead of "done"

  `N` is the stage number (0–10, per the Stages table) and `<slug>` is the kebab portion of the step filename. For the non-numbered routing/terminal steps (`resume`, `health-check`) emit `"stage":null` with the slug. One line per event; do not pretty-print.

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

**Stage numbering:** step files are 1-indexed (`step-01` … `step-11`); `campaign.current_stage` in state is 0-indexed, so step-`NN` runs stage `NN − 1` (e.g. step-01 = stage 0, step-11 = stage 10). The Resume Routing table in `references/step-resume.md` maps each `current_stage` back to its step file.

## Invocation Contract

| Aspect | Detail |
|--------|--------|
| **Inputs** | `campaign` to start a new campaign; `campaign resume [--from=<skill>]` to resume from last active or specified skill; `campaign status` for a read-only progress summary |
| **Overrides** | `--headless` / `-H`, `--brief <file>`, `--manifest <file>`, `--from <skill>` — see On Activation step 4 |
| **Gates** | Step 9 (Export): write-gate HALT — requires explicit user approval before writing exported skills to disk |
| **Outputs** | `_campaign-state.yaml` (state), `campaign-brief.yaml` (machine-generated brief), `campaign-report.md` (post-campaign summary), `_campaign-decision-log.md` (append-only rationale), `SKF_CAMPAIGN_RESULT_JSON` (headless envelope) — all under `{campaignWorkspacePath}` |
| **Headless** | All gates auto-resolve with default action when `{headless_mode}` is true |
| **Exit codes** | See "Exit Codes" below |

## Exit Codes

Every HARD HALT exits with a stable, documented code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                   |
| ---- | -------------------- | ----------------------------------------------------------- |
| 0    | success              | step-11 (terminal)                                          |
| 3    | invalid-state        | any step §1 (`campaign-validate-state.py` non-zero on load) |
| 4    | circular-deps        | step-02 §5                                                  |
| 5    | invalid-pin          | step-03 §5                                                  |
| 6    | inaccessible-repo    | step-04 §5                                                  |
| 7    | dependency-deadlock  | step-05 §4 (no skill ready and no recovery chosen)          |
| 8    | missing-brief        | step-03/04/05 §2 (brief missing or unreadable)              |
| 9    | corrupt-state        | step-resume §1 (primary unrecoverable, `.bak` also invalid) |
| 10   | report-failure       | step-11 §2 — **degraded only**: the report could not be generated; the campaign still completes and state stays intact (never a hard halt that discards a finished campaign) |
| 11   | export-cancelled     | step-10 §4 (operator chose `[C]ancel` — graceful, resumable) |
| 12   | user-cancelled       | any interactive gate (operator typed `cancel` / `exit` / `:q` — graceful, resumable; see Workflow Rules) |

## Result Contract on HARD HALT

In addition to the success-variant envelope (see Campaign Headless Envelope), every HARD HALT emits an **error variant** so automators don't silently break. Emit one line on **stderr**:

```
SKF_CAMPAIGN_RESULT_JSON: {"status":"error","exit_code":<N>,"phase":"<slug>","error":{"code":"<class>","message":"<short>"},"skills_completed":N,"skills_failed":N,"campaign_report_path":null,"decision_log":"<path-or-null>"}
```

`<class>` is the Exit Codes meaning (e.g. `circular-deps`, `inaccessible-repo`); `<slug>` is the step where the HALT occurred. One line, no pretty-print.

## Mode Routing

On invocation:

1. **`campaign resume [--from=<skill>]`** — load `references/step-resume.md`. Validates state integrity, checks backup consistency, and chains to the appropriate stage step file. If `--from=<skill>` is provided, override the resume point to the named skill.
2. **`campaign`** (new, no existing state) — run from stage 0 (Setup).
3. **`campaign`** (state exists) — detect existing `{campaignWorkspacePath}/_campaign-state.yaml` and prompt: **resume** via `references/step-resume.md`, or **overwrite** with a new campaign. On overwrite, first archive the existing `_campaign-state.yaml` and `campaign-brief.yaml` to `{campaignWorkspacePath}/archive/{name}-{timestamp}/`, log the archive to the decision log, and show a one-line summary of what is being set aside before chaining to step-01. In headless mode, default to **resume** (never silently clobber); archive-and-overwrite only when `--brief`/`--manifest` explicitly seeds a new campaign.
4. **`campaign status`** (read-only) — load `{campaignWorkspacePath}/_campaign-state.yaml`, validate it via `campaign-validate-state.py`, display the Resume Detection summary block followed by the last ~15 lines of `{campaignWorkspacePath}/_campaign-decision-log.md` (so the operator sees the recent decision trail without flooding the terminal on a long campaign), then stop. No backup, no mutation, no chaining. Exit 0 (or 9 if the state is unrecoverable).

## Resume Detection

When resuming:

1. Read `_campaign-state.yaml`
2. Validate via `campaign-validate-state.py` (halt on invalid; attempt `.bak` recovery per step-resume)
3. Find last active or completed stage from `campaign.current_stage`
4. Skip completed skills (status = `completed` or `skipped`)
5. If `--from=<skill>` is provided, find the named skill and resume from its stage
6. Continue from the next incomplete skill in `dependency_graph.execution_order`

## State Contract

All state mutations follow the read-backup-modify-write pattern:

1. **Read** `_campaign-state.yaml`
2. **Validate** via `uv run scripts/campaign-validate-state.py --state-file {stateFile}` (halt on invalid)
3. **Backup** — copy current `_campaign-state.yaml` to `_campaign-state.yaml.bak`
4. **Modify** in memory
5. **Update** `campaign.last_updated` to current ISO-8601 timestamp
6. **Write** modified state back to `_campaign-state.yaml`

The `.bak` file is one-deep (overwritten on every write). If the primary file is corrupted (crash during write), the `.bak` file contains the last valid state — step-resume §1 recovers from it automatically rather than dead-halting.

## Campaign Headless Envelope

When `{headless_mode}` is true, the final step emits a single-line JSON envelope on stdout:

```
SKF_CAMPAIGN_RESULT_JSON: {"status":"success|error","skills_completed":0,"skills_failed":0,"quality_scores":{},"campaign_report_path":"","decision_log":"","duration":""}
```

`status` is `"success"` when the campaign completes normally, `"error"` on any unrecoverable halt (with `exit_code` per the Exit Codes table — see Result Contract on HARD HALT). `skills_completed` and `skills_failed` count per-skill outcomes. `quality_scores` maps skill names to their test-skill scores. `campaign_report_path` points to the generated `campaign-report.md`. `decision_log` points to `_campaign-decision-log.md`. `duration` is the wall-clock time of the campaign run. Populate the counts, `quality_scores`, and `duration` directly from the `campaign-report.py` result JSON (step-11 §2) — do not recompute them by hand.
