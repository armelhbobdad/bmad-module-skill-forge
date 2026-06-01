---
nextStepFile: 'step-07-capstone.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
backupFile: 'forge-data/_campaign/_campaign-state.yaml.bak'
briefFile: 'forge-data/_campaign/campaign-brief.yaml'
batchFile: 'forge-data/_campaign/_batch-input.txt'
---

<!-- Config: communicate in {communication_language}. -->

# Tier B Batch

## STEP GOAL:

Batch all Tier B skills through QS `--batch` mode, recording per-skill results in campaign state. Tier B skills use a faster, simpler path than the full Tier A pipeline — QS handles each target end-to-end in a single invocation.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state against `{stateSchemaFile}` on load. HALT on invalid state.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- All field names use `snake_case`, dates use ISO-8601 with timezone, enums use lowercase or uppercase as defined by the schema.
- Update `campaign.current_stage` to `5`.
- If `{headless_mode}` is true, auto-proceed through confirmation gates. QS `--batch` implies headless.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Validate the loaded state against `{stateSchemaFile}`. HALT on any schema validation error with the specific violation.

### §2 — Read Directive

If `campaign.directive_path` is set in state, load the file at that path. Apply directive contents as campaign-wide context for this stage's processing. If the file is not found, continue without error (directive is optional).

### §3 — Identify Tier B Skills

Filter `skills[]` for entries where `tier == "B"` and `status == "pending"`. Skip skills with status `"completed"`, `"failed"`, or `"skipped"` (resume support — a previous run may have partially completed the batch).

If no Tier B skills need processing, skip to §7 (Stage Completion) — the batch stage completes immediately when all Tier B skills are already handled.

### §4 — Generate Batch File

Load `{briefFile}` to look up `repo_url` for each Tier B skill (repo URLs are in the brief's `targets[]`, not in the state schema).

Write a batch input file listing Tier B skills for QS `--batch` consumption. For each pending Tier B skill, include:

- Skill name (from `skills[].name`)
- Repository URL (from brief's `targets[].repo_url`, matched by name)
- Pin (from `skills[].pin`, or omit if null for latest)

Place the batch file at `{batchFile}`.

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
