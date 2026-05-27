---
nextStepFile: 'step-09-refine.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
backupFile: 'forge-data/_campaign/_campaign-state.yaml.bak'
---

<!-- Config: communicate in {communication_language}. -->

# Verify

## STEP GOAL:

Invoke VS (skf-verify-stack) in headless mode against all completed campaign skills to produce a feasibility report. The report cross-references generated skills against the project's architecture document, providing coverage analysis and integration verdicts for operator review.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state against `{stateSchemaFile}` on load. HALT on invalid state.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- All field names use `snake_case`, dates use ISO-8601 with timezone, enums use lowercase or uppercase as defined by the schema.
- Update `campaign.current_stage` to `7`.
- If `{headless_mode}` is true, auto-proceed through confirmation gates. VS supports headless via `--headless`.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Validate the loaded state against `{stateSchemaFile}`. HALT on any schema validation error with the specific violation.

### §2 — Locate Architecture Doc

Discover the architecture document path using this strategy:

1. Check if `docs/architecture.md` exists at `{project-root}` (SKF project convention).
2. If not found, check `_bmad-output/planning-artifacts/architecture.md` (BMM convention).
3. If not found and `{headless_mode}` is false: prompt the operator to provide the architecture doc path.
4. If not found and `{headless_mode}` is true: skip VS invocation with a warning — do not HALT. Log that verification was skipped due to missing architecture doc and proceed to §5.

Once discovered, proceed to §3 with the resolved path.

### §3 — Invoke VS

Invoke `skf-verify-stack` with `--headless --architecture-doc <path>`, where `<path>` is the architecture doc discovered in §2.

VS discovers skills from its own configured `{skills_output_folder}` — the campaign does NOT pass individual skill paths. Capture the result envelope from stdout:

```
SKF_VERIFY_STACK_RESULT_JSON: {"status":"…","report_path":"…","report_latest_path":"…","overall_verdict":"…","coverage_percentage":0,"recommendation_count":0,"exit_code":0,"halt_reason":null}
```

### §4 — Handle VS Outcome

**On success** (exit code 0): record the report path and overall verdict in OUTPUT for downstream consumption by step-09.

**On VS failure** (non-zero exit): log the error (exit code and halt_reason from the envelope or stderr). Verification failure does NOT block the campaign — it produces diagnostic information for operator review. Continue to §5 regardless of outcome.

### §5 — Stage Completion

Set `campaign.current_stage` to `7`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

## OUTPUT

Display verification summary: overall verdict (or "skipped" if architecture doc was not found), report path (if produced), and coverage percentage. Chain to `{nextStepFile}`.
