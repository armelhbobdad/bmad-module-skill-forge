---
nextStepFile: 'health-check.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
backupFile: 'forge-data/_campaign/_campaign-state.yaml.bak'
reportScript: 'scripts/campaign-report.py'
reportTemplate: 'templates/campaign-report-template.md'
---

<!-- Config: communicate in {communication_language}. -->

# Maintenance

## STEP GOAL:

Generate a comprehensive campaign report from the accumulated state, emit the headless result envelope, and chain to the shared health check as the campaign's terminal step.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state against `{stateSchemaFile}` on load. HALT on invalid state.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- All field names use `snake_case`, dates use ISO-8601 with timezone, enums use lowercase or uppercase as defined by the schema.
- Update `campaign.current_stage` to `10`.
- If `{headless_mode}` is true, auto-proceed through confirmation gates. Emit the headless envelope on stdout.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Validate the loaded state against `{stateSchemaFile}`. HALT on any schema validation error with the specific violation.

### §2 — Generate Campaign Report

Invoke the campaign report script:

```
uv run python {reportScript} \
    --state-file {stateFile} \
    --template-file {reportTemplate} \
    --output-file forge-data/_campaign/campaign-report.md
```

Capture the JSON result from stdout.

**On success** (exit code 0): log the report path and summary stats from the result JSON.

**On failure** (exit code 2): display the error from stderr. HALT — the campaign report is a required terminal artifact.

Display: "**Campaign report generated:** `forge-data/_campaign/campaign-report.md`"

### §3 — Emit Headless Envelope

When `{headless_mode}` is true, emit the campaign result envelope on stdout:

```
SKF_CAMPAIGN_RESULT_JSON: {"status":"success","skills_completed":N,"skills_failed":N,"quality_scores":{...},"campaign_report_path":"forge-data/_campaign/campaign-report.md","duration":"..."}
```

Populate from the campaign state:
- `status`: "success" if campaign completed normally
- `skills_completed`: count of skills with `status == "completed"`
- `skills_failed`: count of skills with `status == "failed"`
- `quality_scores`: map of `{skill_name: quality_score}` from completed skills
- `campaign_report_path`: path to the generated report
- `duration`: `campaign.last_updated - campaign.started_at`

When not in headless mode, skip this section silently.

### §4 — Stage Completion

Set `campaign.current_stage` to `10`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

### §5 — Chain to Health Check

Display: "**Campaign complete.** Report at `forge-data/_campaign/campaign-report.md`. Chaining to health check..."

Chain to `{nextStepFile}` (shared/health-check.md).

## OUTPUT

Display campaign completion summary: skills completed, skills failed, report path, total duration. Chain to `{nextStepFile}`.
