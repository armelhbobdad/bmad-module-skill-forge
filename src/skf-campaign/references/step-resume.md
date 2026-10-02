---
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
resultContextFile: '{campaignWorkspacePath}/_result-context.json'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
stateScript: 'scripts/campaign-state.py'
validateScript: 'scripts/campaign-validate-state.py'
statusScript: 'scripts/campaign-status.py'
---

<!-- Config: communicate in {communication_language}. -->

# Resume

## STEP GOAL:

Validate campaign state integrity, recover it from its backup when it must, get the resume point from the state helper, and chain to that stage's step file.

## RULES

- Leave state untouched except for the two recovery or reset choices below (§1 backup restore, §3 `[R]e-run`), each through `{stateScript}`, and on a non-zero exit HALT with the same code. A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- The chain target is the `step_file` the helper's `resume` operation (`{stateScript}`) returns: never work the stage out by hand.
- If `{headless_mode}` is true, auto-proceed through any confirmation gates with the default action and log each auto-decision (type `auto`); emit the progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`. A campaign already complete (§3) is no error halt: it ends with the success line.

## TASKS

### §1: Read + Validate State (with `.bak` recovery)

If neither `{stateFile}` nor `{backupFile}` exists, HALT (exit code 2, `invalid-input`): "No campaign state found. Run `campaign` to start a new campaign."

Run `uv run {validateScript} --state-file {stateFile}`. If it succeeds (exit 0), proceed to §2.

If it fails (primary missing, corrupt YAML or schema-invalid), recover from the backup rather than dead-halting. `{stateScript}` writes atomically, so its writes never leave a broken primary: the cause is a hand edit, disk damage, or a state written before v3.0.0.

```
uv run {stateScript} recover --state-file {stateFile}
```

It copies `{backupFile}` over `{stateFile}` only when the backup validates. On exit 0, log "primary corrupt: recovered from backup as of {last_updated}" (type `event`, with the `last_updated` it returns), inform the operator, and continue with the recovered state. On exit 9 (the backup is missing or invalid too), HALT with exit code 9 (`corrupt-state`), reporting both the primary's validation errors and the recover call's `errors[]`, so the operator knows neither is usable.

### §2: Backup Check

Unless §1 recovered from it, check `{backupFile}`. When it does not exist, warn "No backup file found: campaign may have been created but never modified." When `uv run {validateScript} --state-file {backupFile}` fails, warn "Backup file fails validation: cannot use for recovery." Continue with the primary either way: each write copies the primary it replaces to `.bak`, so a valid primary is never older than its backup.

### §3: Determine Resume Point

Ask the state helper, passing `--from` when the invocation named a skill:

```
uv run {stateScript} resume --state-file {stateFile} [--from <skill>]
```

It returns the stage to resume and its `step_file`, with the `reason`: `active-skill` (a skill an interruption left `active` resumes its own stage, with no `+1`: a Tier A skill the skill loop, which skips finished skills until it reaches it; a Tier B skill the batch stage, whose batch script, `campaign-render-batch.py`, selects the interrupted active Tier B skills together with the pending ones, so resume resets no status), `next-stage` (the stage after `current_stage`, the highest completed stage), `terminal-cap` (stage 10 runs again, never a stage 11), `from-skill` or `from-next`. Then:

- **`complete: true`:** nothing is left to resume, which is no error halt: stop with exit code 0 and display "Campaign has reached its final stage. All skills have been processed." (after `--next`: "All remaining skills are complete. Run `campaign` to start a new campaign.") In headless mode, end with the campaign's success line instead of an error envelope. When `reason` is `complete` and `{resultContextFile}` exists (step-11 §2 wrote it), run `uv run {emitEnvelopeHelper} emit --workflow skf-campaign < {resultContextFile}` (the shared emitter: Result Contract in `references/campaign-contracts.md`); otherwise give the same command `{"status": "success", "skills_completed": <completed>, "skills_failed": <failed>, "decision_log": "{decisionLogFile}"}` on stdin, with the counts `uv run {statusScript} --state-file {stateFile}` returns. Display the line it prints verbatim as the run's last line, with nothing after it.
- **`stage` 1 with no `{briefFile}`:** Setup stopped after it wrote the state but before the brief, which every later stage reads: HALT (exit code 8, `missing-brief`): "Setup did not finish. Run `campaign` and choose overwrite to start the campaign again."
- **Exit 2** (an unknown `--from` skill): HALT (exit code 2, `invalid-input`) with its `error`, which lists the known skills.
- **`needs_choice: true`:** the `--from` skill is already `completed`, `failed` or `skipped` (`from_status`), and the operator may have meant to re-run it (e.g. it passed with a low score) rather than skip past it. Present a choice:
  - `[R]e-run`: reset it with `uv run {stateScript} set-skill --state-file {stateFile} --skill <skill> --status pending`, then run the `resume` call again: it now resumes that skill's stage.
  - `[N]ext`: run the `resume` call again with `--next`, which resumes at the next pending or active skill after it in `dependency_graph.execution_order`.
  - `[H]alt`: stop without resuming.

  **GATE [default: N]**: in headless mode, default to `[N]ext` and log the auto-decision. Log the chosen action (type `decision`).
- **`active_other`** set: warn "Skill '{active_other}' is currently active: honoring explicit --from override."

### §4: Resume Routing

Derive the skill counts deterministically: `uv run {statusScript} --state-file {stateFile}` returns `completed`, `total`, and the per-status counts (`pending` / `active` / `failed` / `skipped`); do not hand-count `skills[]`. Display a resume summary before chaining:

```
CAMPAIGN RESUME: {campaign.name}

  Resuming from: Stage {stage} ({step_file})
  Target skill:  {skill} (if --from was used, otherwise "auto-detected" or "N/A")
  Skills completed: {completed} / {total}
  Skills remaining: {pending} pending, {active} active, {failed} failed, {skipped} skipped
  Last updated:  {campaign.last_updated}
```

## OUTPUT

Chain to the `step_file` §3 returned (a file in `references/`).
