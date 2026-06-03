---
nextStepFile: 'health-check.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
reportFile: '{campaignWorkspacePath}/campaign-report.md'
reportScript: 'scripts/campaign-report.py'
reportTemplate: '{reportTemplatePath}'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Maintenance

## STEP GOAL:

Generate a comprehensive campaign report from the accumulated state, emit the headless result envelope, and chain to the shared health check as the campaign's terminal step.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- Update `campaign.current_stage` to `10`.
- If `{headless_mode}` is true, auto-proceed through confirmation gates. Emit the headless envelope on stdout.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2 — Generate Campaign Report

Invoke the campaign report script:

```
uv run {reportScript} \
    --state-file {stateFile} \
    --template-file {reportTemplate} \
    --output-file {reportFile}
```

Capture the JSON result from stdout — it carries `skills_completed`, `skills_failed`, `quality_scores`, and `duration` already computed. Do not recompute these by hand in §3.

**On success** (exit code 0): log the report path and summary stats from the result JSON.

**On failure** (exit code 2): the campaign itself has already completed — do NOT discard it over a missing summary artifact. Display the error from stderr, log "report generation failed (degraded): {error}" to the decision log, set the envelope's `campaign_report_path` to `null`, and CONTINUE to §3. Surface `report-failure` only as a degraded signal in the envelope (`status:"error"`, `exit_code:10`), never as a hard halt that throws away a finished campaign.

Display: "**Campaign report generated:** `{reportFile}`" (or, on degrade, "**Campaign complete — report generation failed (see decision log); state is intact.**")

**Optional post-completion hook:** if `{onComplete}` (resolved in On Activation) is non-empty, invoke `{onComplete} --report-path={reportFile}`. Log the outcome to the decision log; a hook failure is recorded but never fails the campaign.

### §3 — Emit Headless Envelope

When `{headless_mode}` is true, emit the campaign result envelope on stdout, copying the counts, `quality_scores`, and `duration` straight from the §2 report-script result (do not recompute):

```
SKF_CAMPAIGN_RESULT_JSON: {"status":"success","skills_completed":N,"skills_failed":N,"quality_scores":{...},"campaign_report_path":"{reportFile}","decision_log":"{campaignWorkspacePath}/_campaign-decision-log.md","duration":"..."}
```

- `status`: "success" if the campaign completed normally (HARD HALTs emit the error variant per SKILL.md "Result Contract on HARD HALT")
- `skills_completed` / `skills_failed` / `quality_scores` / `duration`: from the §2 report-script result JSON
- `campaign_report_path`: `{reportFile}`
- `decision_log`: path to the append-only decision log

When not in headless mode, skip this section silently.

### §4 — Stage Completion

Set `campaign.current_stage` to `10`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

### §5 — Chain to Health Check

The operator's findings-routing consent (`campaign.health_findings_queue`) is applied by the terminal health-check step: `references/health-check.md` §1 reads it from state and carries it into the shared health check as the pre-decided opt-in (`"improvement"` → route non-bug findings to the shared improvement queue without re-prompting; `"local"` → local queue only). That is what makes the §2 setup consent prompt actionable rather than cosmetic — surface the active setting here for visibility.

Display: "**Campaign complete.** Report at `{reportFile}`. Findings routing: {campaign.health_findings_queue}. Chaining to health check..."

Chain to `{nextStepFile}` (shared/health-check.md).

## OUTPUT

Display campaign completion summary: skills completed, skills failed, report path, total duration. Chain to `{nextStepFile}`.
