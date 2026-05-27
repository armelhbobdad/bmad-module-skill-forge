---
nextStepFile: 'step-10-export.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
backupFile: 'forge-data/_campaign/_campaign-state.yaml.bak'
---

<!-- Config: communicate in {communication_language}. -->

# Refine

## STEP GOAL:

Invoke RA (skf-refine-architecture) in headless mode with the project's architecture document and VS feasibility report to produce a refined architecture. RA identifies gaps, issues, and improvements based on the generated skills and applies them to the architecture document.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state against `{stateSchemaFile}` on load. HALT on invalid state.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- All field names use `snake_case`, dates use ISO-8601 with timezone, enums use lowercase or uppercase as defined by the schema.
- Update `campaign.current_stage` to `8`.
- If `{headless_mode}` is true, auto-proceed through confirmation gates. RA supports headless via `--headless`.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Validate the loaded state against `{stateSchemaFile}`. HALT on any schema validation error with the specific violation.

### §2 — Locate Inputs

**Architecture doc:** Use the same discovery strategy as step-08:

1. Check if `docs/architecture.md` exists at `{project-root}`.
2. If not found, check `_bmad-output/planning-artifacts/architecture.md`.
3. If not found and `{headless_mode}` is false: prompt the operator.
4. If not found and `{headless_mode}` is true: skip RA invocation with a warning — do not HALT. Log that refinement was skipped due to missing architecture doc and proceed to §5.

Once discovered, proceed to §3 with the resolved path.

**VS feasibility report:** If chaining from step-08, the report path is available from the VS result envelope (`report_latest_path`). On resume, look for `feasibility-report-*-latest.md` in `{project-root}/forge-data/`. If no report exists (VS may have failed or been skipped in step-08), proceed without it — RA's VS report input is optional.

### §3 — Invoke RA

Invoke `skf-refine-architecture` with:

```
skf-refine-architecture --headless --architecture-doc <arch_path> [--vs-report-path <report_path>] [--scope-skills <names>]
```

- `--architecture-doc`: the architecture doc discovered in §2 (required).
- `--vs-report-path`: the VS feasibility report path from §2 (omit if not found).
- `--scope-skills`: comma-separated names of completed campaign skills (from `skills[]` where `status == "completed"`). Optional but improves focus by limiting refinement scope to campaign-relevant skills.

Capture the result envelope from stdout:

```
SKF_REFINE_ARCHITECTURE_RESULT_JSON: {"status":"…","refined_path":"…","gap_count":0,"issue_count":0,"improvement_count":0,"exit_code":0,"halt_reason":null}
```

### §4 — Handle RA Outcome

**On success** (exit code 0): record the refined architecture path and counts (gap_count, issue_count, improvement_count) in OUTPUT.

**On RA failure** (non-zero exit): log the error (exit code and halt_reason from the envelope or stderr). Refinement failure does NOT block the campaign — the campaign continues to export with whatever state exists. Continue to §5 regardless of outcome.

### §5 — Stage Completion

Set `campaign.current_stage` to `8`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state.

## OUTPUT

Display refinement summary: refined architecture path (or "skipped" if architecture doc was not found), gap count, issue count, and improvement count. Chain to `{nextStepFile}`.
