---
nextStepFile: 'step-04-provenance.md'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
pinResultsFile: '{campaignWorkspacePath}/_pin-results.json'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
pinScript: 'scripts/campaign-validate-pins.py'
stateScript: 'scripts/campaign-state.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Pins

## STEP GOAL:

Validate all version pins against real releases/branches before the campaign proceeds, catching invalid pins early with actionable suggestions.

## RULES

- Write `campaign.current_stage` = 2 only in this stage's final state write, after every gate: step-resume resumes at `current_stage + 1`, so an early write skips unfinished work.
- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the same code (State Contract in `references/campaign-contracts.md`). A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- If `{headless_mode}` is true, emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`.

## TASKS

### §1: Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2: Read Brief

Load `{briefFile}` only to confirm it parses (the pin script reads it directly). HALT (exit code 8, `missing-brief`) if the brief is missing or unreadable.

### §3: Validate Pins

Run the pin script, keeping its JSON output in `{pinResultsFile}` for §5:

```
uv run {pinScript} --state-file {stateFile} --brief-file {briefFile} > {pinResultsFile}
```

If the script exits 2 (a required tool such as `gh` is unavailable, a file is unreadable, or `INVALID_BRIEF`: a brief that is no mapping or holds a target with no `name` or no `repo_url`), HALT (exit code 2, `invalid-input`) surfacing its error; only when `gh` is what is missing, add that pins cannot be validated without it. Otherwise read `{pinResultsFile}`. For each result: if `status` is `"valid"` or `"resolved"`, the pin is good; if `"invalid"`, collect the failure with suggestions.

### §4: Handle Invalid Pins

If any result is `invalid`, show each with its skill, its attempted `pin` and the script's `suggestions`, and ask for every corrected pin in one question: a version, or nothing for the latest release. Write each answer with `uv run {stateScript} set-skill --state-file {stateFile} --skill <skill> --pin '<pin>' --brief-file {briefFile}`, which writes it to the skill and to its target in `{briefFile}`, so the kickoff's brief summary and a campaign seeded from the brief again hold it too (the pin single-quoted as a log entry is, per the Decision Log in `references/campaign-contracts.md`; exit 2, a Tier A pin that is no X.Y.Z version: ask for that pin again), log it with `uv run {stateScript} log --log-file {decisionLogFile} --type decision --text 'pin: <skill> <old pin> corrected to <new pin>'` (`latest release` for an empty or null pin), then run §3 again.

**GATE [default: HALT]**: in headless mode, HALT (exit code 5, `invalid-pin`) listing each skill, its attempted pin and the script's suggestions, and the ways out: run `campaign resume` interactively (no `--headless`, `headless_mode` off), which asks for the corrected pins here; or, since a headless resume checks the same pin again, run `campaign`, choose overwrite and give the archived `campaign-brief.yaml` with corrected pins.

### §5: Write State

Write every resolved pin and the stage in one write:

```
uv run {stateScript} apply-pins --state-file {stateFile} --results-file {pinResultsFile} --stage 2
```

It refuses results that hold an invalid pin: on exit 5 (nothing written), HALT (exit code 5, `invalid-pin`); on exit 3, HALT (exit code 3, `invalid-state`).

## OUTPUT

Display pin validation summary: for each skill, name, pin, resolved ref, ref type. Chain to `{nextStepFile}`.
