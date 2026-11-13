---
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

Skip this check when §1 recovered from the backup or `{backupFile}` does not exist. When `uv run {validateScript} --state-file {backupFile}` fails, warn "Backup file fails validation: cannot use for recovery." and continue with the primary.

### §3: Determine Resume Point

Ask the state helper, passing `--from` when the invocation named a skill:

```
uv run {stateScript} resume --state-file {stateFile} [--from <skill>]
```

It returns the stage to resume, its `step_file` and a `reason`. Then:

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

Before chaining, show the campaign name, the stage and `step_file` it resumes, the `--from` skill when one was named, the `completed` and `total` skills and the `pending`, `active`, `failed` and `skipped` counts that `uv run {statusScript} --state-file {stateFile}` returns (never a hand count of `skills[]`), and `campaign.last_updated`.

## OUTPUT

Chain to the `step_file` §3 returned (a file in `references/`).
