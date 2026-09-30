---
nextStepFile: 'step-10-export.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Refine

## STEP GOAL:

Invoke RA (skf-refine-architecture) in headless mode with the project's architecture document and VS feasibility report to produce a refined architecture. RA identifies gaps, issues, and improvements based on the generated skills and applies them to the architecture document.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- Update `campaign.current_stage` to `8`.
- If `{headless_mode}` is true, auto-proceed through confirmation gates. RA supports headless via `--headless`.

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2 — Read Directive

If `campaign.directive_path` is set in state, load the file at that path and apply its contents as campaign-wide context for this stage's processing, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §3 — Locate Inputs

**Architecture doc:** Use the same resolution strategy as step-08:

1. If `campaign.architecture_doc_path` is set in state and the file exists, use it directly (step-08 normally persists it).
2. Otherwise check `docs/architecture.md` at `{project-root}`, then `_bmad-output/planning-artifacts/architecture.md`.
3. If still not found and `{headless_mode}` is false: prompt the operator.
4. If still not found and `{headless_mode}` is true: skip RA invocation with a warning — do not HALT. Log that refinement was skipped due to missing architecture doc (to the decision log) and proceed to §6.

Once resolved (steps 2–3), persist the path to `campaign.architecture_doc_path` if not already set, then proceed to §4 with the resolved path.

**VS feasibility report:** read `campaign.verification.report_path` from state, where step-08 saved the report VS wrote, so a chained run and a resumed one pass the same report. When it is null, or `campaign.verification` is unset (VS failed or step-08 skipped it), RA runs without a report: never look for one by file name.

### §4 — Invoke RA

Invoke `skf-refine-architecture` with:

```
skf-refine-architecture --headless --architecture-doc <arch_path> --vs-report-path <report_path|none> [--scope-skills <names>]
```

- `--architecture-doc`: the architecture doc discovered in §3 (required).
- `--vs-report-path`: `campaign.verification.report_path` from §3, or `none` when state holds no report path.
- `--scope-skills`: comma-separated names of completed campaign skills (from `skills[]` where `status == "completed"`). Optional but improves focus by limiting refinement scope to campaign-relevant skills.

Capture the result envelope from stdout:

```
SKF_REFINE_ARCHITECTURE_RESULT_JSON: {"status":"…","refined_path":"…","gap_count":0,"issue_count":0,"improvement_count":0,"exit_code":0,"halt_reason":null}
```

### §5 — Handle RA Outcome

**On success** (exit code 0): persist the summary to `campaign.refinement` (the refined document itself lives at `refined_path`):

- `campaign.refinement.refined_path` — from the envelope
- `campaign.refinement.gap_count` — from the envelope
- `campaign.refinement.issue_count` — from the envelope
- `campaign.refinement.improvement_count` — from the envelope

**On RA failure** (non-zero exit): log the error (exit code and halt_reason from the envelope or stderr). Refinement failure does NOT block the campaign — the campaign continues to export with whatever state exists. Leave `campaign.refinement` unset (or null). Continue to §6 regardless of outcome.

### §6 — Stage Completion

Set `campaign.current_stage` to `8`. Update `campaign.last_updated` to current ISO-8601 with timezone. Backup `{stateFile}` to `{backupFile}`, then write the updated state (including `campaign.refinement` from §5).

## OUTPUT

Display refinement summary: refined architecture path (or "skipped" if architecture doc was not found), gap count, issue count, and improvement count. Chain to `{nextStepFile}`.
