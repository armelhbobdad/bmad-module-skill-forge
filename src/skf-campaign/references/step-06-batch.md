---
nextStepFile: 'step-07-capstone.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
batchFile: '{campaignWorkspacePath}/_batch-input.txt'
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

### §1 — Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2 — Read Directive

If `campaign.directive_path` is set in state, load the file at that path and apply its contents as campaign-wide context for this stage's processing, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §3 — Identify Tier B Skills

Filter `skills[]` for entries where `tier == "B"` and `status == "pending"`. Skip skills with status `"completed"`, `"failed"`, or `"skipped"` (resume support — a previous run may have partially completed the batch).

If no Tier B skills need processing, skip to §7 (Stage Completion) — the batch stage completes immediately when all Tier B skills are already handled.

### §4 — Generate Batch File

Generate the QS `--batch` input file deterministically:

```
uv run {batchScript} --state-file {stateFile} --brief-file {briefFile} -o {batchFile}
```

The script filters `skills[]` for `tier == "B" && status == "pending"`, looks up each skill's `repo_url` from the brief's `targets[]` (repo URLs live in the brief, not the state schema), and writes one line per skill at `{batchFile}` in the exact single-target shape QS parses (see `src/skf-quick-skill/references/batch-mode.md`) — the line format is owned once by the script, not re-derived here. It emits a JSON summary (`written`, `count`, `skipped_non_tierB`, `skipped_non_pending`) on stderr.

HALT on non-zero exit: exit code 8 (`missing-brief`) when the brief is missing/unreadable **or** a pending Tier B skill has no matching brief target; exit code 2 (`invalid-input`) on a state file/parse error.

### §5 — Execute QS Batch

Set each pending Tier B skill to `status: "active"` and `started_at` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

Invoke QS in `--batch` mode with the generated batch file:

```
skf-quick-skill --batch {batchFile}
```

QS `--batch` implies `--headless`. Capture per-skill results from the QS batch output — each target reports success/failure, skill path, and quality score.

### §6 — Record Results

For each Tier B skill in the batch:

1. If QS reports success:
   - Set `status` to `"completed"`
   - Set `completed_at` to current ISO-8601 with timezone
   - Record `quality_score` from QS output
   - Record `skill_path` from QS output
2. If QS reports failure:
   - Set `status` to `"failed"`

After all updates: backup `{stateFile}` to `{backupFile}`, then write the updated state.

### §7 — Stage Completion

Set `campaign.current_stage` to `5`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

## OUTPUT

Display per-skill batch summary: name, status, quality_score (if completed). Chain to `{nextStepFile}`.
