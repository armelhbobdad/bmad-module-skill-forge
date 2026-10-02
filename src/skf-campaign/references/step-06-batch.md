---
nextStepFile: 'step-07-capstone.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
batchFile: '{campaignWorkspacePath}/_batch-input.txt'
batchMapFile: '{campaignWorkspacePath}/_batch-map.json'
batchResultsFile: '{campaignWorkspacePath}/_batch-results.json'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
batchScript: 'scripts/campaign-render-batch.py'
stateScript: 'scripts/campaign-state.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Tier B Batch

## STEP GOAL:

Batch all Tier B skills through QS `--batch` mode, recording per-skill results in campaign state. Tier B skills use a faster, simpler path than the full Tier A pipeline — QS handles each target end-to-end in a single invocation.

## RULES

- Write `campaign.current_stage` = 5 only in this stage's final state write, after every result is recorded: step-resume resumes at `current_stage + 1`, so an early write skips unfinished work. An interrupted batch needs no stage write: its skills stay `active`, and resume sends an active Tier B skill back to this stage.
- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the same code (State Contract in `references/campaign-contracts.md`). A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- If `{headless_mode}` is true, emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`. QS `--batch` implies headless.

## TASKS

### §1: Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2: Read Directive

If `campaign.directive_path` is set in state, the batch script applies its `## Skip List` itself (§3), so do not filter skills by hand. Read any other section as campaign-wide context, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §3: Select Tier B Skills and Write the Batch File

The batch script selects the Tier B skills (pending ones, and active ones an interrupted batch left behind), leaves out the ones the directive's Skip List names, and writes the batch file and its line-to-skill map: select and format nothing by hand. Pass `--directive-file` when state sets `campaign.directive_path`:

```
uv run {batchScript} --state-file {stateFile} --brief-file {briefFile} -o {batchFile} --map {batchMapFile} [--directive-file <campaign.directive_path>]
```

Its JSON summary on stderr gives `count`, the skill of each line in order (`skills`), the skills the Skip List left out (`skipped_by_directive`, each with its `reason`) and the hints left off a line (`dropped_hints`: a language or scope hint quick-skill could not read as one word).

HALT on non-zero exit: exit code 8 (`missing-brief`) when the brief is missing/unreadable **or** a selected Tier B skill has no matching brief target; exit code 2 (`invalid-input`) on a state file/parse error or a directive that cannot be read.

Log each `skipped_by_directive` entry as "directive Skip List: {name} ({reason})" and each `dropped_hints` entry as "batch: {skill} built without its {hint} `{value}` (quick-skill reads a hint as one word)", both type `event`.

### §4: Execute QS Batch

Record the batch's start from the map, so no skill is marked by hand:

```
uv run {stateScript} apply-batch --state-file {stateFile} --map-file {batchMapFile} --start
```

It marks each `skipped_by_directive` skill `skipped` and each batched skill `active`, stamping `started_at` from the clock unless an interrupted batch already set it. If the §3 `count` is 0, add `--stage 5` to this call and chain to `{nextStepFile}`: the batch stage completes at once when every Tier B skill is already handled.

Invoke QS in `--batch` mode with the generated batch file:

```
skf-quick-skill --batch {batchFile}
```

QS `--batch` implies `--headless`. When the batch ends it prints a `batch_summary` event on stderr: keep its `summary_path`, the batch summary file that holds each target's result.

### §5: Record Results

Join the batch summary to the skills by line number, never by matching QS output to skills by hand:

```
uv run {batchScript} --record <summary_path> --map {batchMapFile} > {batchResultsFile}
```

When that call exits 0, record the results and the stage in one write:

```
uv run {stateScript} apply-batch --state-file {stateFile} --map-file {batchMapFile} --results-file {batchResultsFile} --stage 5
```

A `completed` result sets the skill `completed`, with `completed_at` from the clock, its `quality_score` (the skill-check score QS records, not a test-skill score) and its `skill_path`; a `failed` one sets it `failed`. Log each entry of the helper's `failed[]` with its `error_code` (`no-batch-result` when the summary holds no result for its line), type `event`.

When QS printed no `batch_summary` event (run no record call), or the record call exits 2 (a missing summary or map, or a summary that belongs to another batch file), fail every skill the map lists instead, and log why: never guess which target built which skill.

```
uv run {stateScript} apply-batch --state-file {stateFile} --map-file {batchMapFile} --no-results --stage 5
```

## OUTPUT

Display per-skill batch summary: name, status, quality_score (if completed). Chain to `{nextStepFile}`.
