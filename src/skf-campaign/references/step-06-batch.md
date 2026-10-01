---
nextStepFile: 'step-07-capstone.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
batchFile: '{campaignWorkspacePath}/_batch-input.txt'
batchMapFile: '{campaignWorkspacePath}/_batch-map.json'
batchScript: 'scripts/campaign-render-batch.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Tier B Batch

## STEP GOAL:

Batch all Tier B skills through QS `--batch` mode, recording per-skill results in campaign state. Tier B skills use a faster, simpler path than the full Tier A pipeline — QS handles each target end-to-end in a single invocation.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- Update `campaign.current_stage` to `5`.
- If `{headless_mode}` is true, auto-proceed through confirmation gates. QS `--batch` implies headless.

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

Mark each `skipped_by_directive` skill `"skipped"` and log "directive Skip List: {name} ({reason})" to the decision log. Log each `dropped_hints` entry as "batch: {skill} built without its {hint} `{value}` (quick-skill reads a hint as one word)". If `count` is 0, backup `{stateFile}` to `{backupFile}`, write the updated state and skip to §6 (Stage Completion): the batch stage completes at once when every Tier B skill is already handled.

### §4: Execute QS Batch

Set each skill the §3 summary names in `skills` to `status: "active"`, and `started_at` to current ISO-8601 with timezone unless an interrupted batch already set it. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

Invoke QS in `--batch` mode with the generated batch file:

```
skf-quick-skill --batch {batchFile}
```

QS `--batch` implies `--headless`. When the batch ends it prints a `batch_summary` event on stderr: keep its `summary_path`, the batch summary file that holds each target's result.

### §5: Record Results

Join the batch summary to the skills by line number, never by matching QS output to skills by hand:

```
uv run {batchScript} --record <summary_path> --map {batchMapFile}
```

For each entry of its `results[]`:

1. `status` `completed`: set `status` to `"completed"`, `completed_at` to current ISO-8601 with timezone, `quality_score` to its `quality_score` (the skill-check score QS records, not a test-skill score) and `skill_path` to its `skill_path`.
2. `status` `failed`: set `status` to `"failed"`, and log its `error_code` (`no-batch-result` when the summary holds no result for its line) to the decision log.

When QS printed no `batch_summary` event, or the record call exits 2 (a missing summary or map, or a summary that belongs to another batch file), set every skill the map lists (`lines[].skill` in `{batchMapFile}`) to `"failed"` and log why: never guess which target built which skill. After all updates: backup `{stateFile}` to `{backupFile}`, then write the updated state.

### §6: Stage Completion

Set `campaign.current_stage` to `5`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

## OUTPUT

Display per-skill batch summary: name, status, quality_score (if completed). Chain to `{nextStepFile}`.
